from __future__ import annotations

import argparse
import asyncio
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from loguru import logger

from bot.analytics.arbitrage import find_all_arb_signals
from bot.analytics.engine import AnalyticsEngine
from bot.analytics.hybrid import detect_hybrid_signals
from bot.analytics.lch import LchDetector
from bot.analytics.mss2 import Mss2Scanner
from bot.analytics.roda import detect_roda_signals
from bot.execution.fees import estimate_taker_fee

from .client import SnapshotMarketClient
from .loader import iter_backtest_snapshots
from .models import BacktestPosition, BacktestReport, BacktestSnapshot, BacktestTrade


def _token_price(side: str, yes_price: float) -> float:
    return yes_price if str(side).upper() == "YES" else 1.0 - yes_price


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _pct_change(current: float, previous: float) -> float:
    if previous <= 0:
        return 0.0
    return (current - previous) / previous


@dataclass(slots=True)
class BacktestConfig:
    initial_capital_usd: float = 1000.0
    kelly_fraction: float = 0.25
    max_position_pct: float = 0.05
    max_correlated_exposure_pct: float = 0.15
    daily_loss_limit_pct: float = 0.03
    max_concurrent_positions: int = 12
    allow_generic_strategy: bool = True
    allow_roda: bool = True
    allow_lch: bool = True
    allow_hybrid: bool = True
    allow_mss2: bool = True
    allow_arb: bool = True
    enable_final_mark_to_market: bool = True
    slippage_min: float = 0.001
    slippage_max: float = 0.005
    lch_lookback_hours: float = 1.0
    roda_min_confidence: float = 0.95
    roda_min_age_hours: float = 1.0
    roda_max_age_hours: float = 24.0
    roda_max_entry_price: float = 0.90
    roda_min_sources: int = 3
    roda_hold_window_hours: float = 12.0


@dataclass(slots=True)
class _OpenPosition:
    position: BacktestPosition
    open_fee_usd: float


class _BacktestRiskGate:
    def __init__(self, config: BacktestConfig) -> None:
        self.config = config

    def can_trade(
        self,
        *,
        signal: dict[str, Any],
        current_equity: float,
        day_start_equity: float,
        open_positions: dict[str, _OpenPosition],
    ) -> tuple[bool, str]:
        size_usd = float(signal.get("kelly_size_usd", 0.0) or 0.0)
        if size_usd < 1.0:
            return False, "size below threshold"
        if len(open_positions) >= self.config.max_concurrent_positions:
            return False, "max concurrent positions reached"
        if signal.get("market_id") in open_positions:
            return False, "duplicate market"
        if size_usd > current_equity * self.config.max_position_pct:
            return False, "position cap exceeded"
        total_open = sum(pos.position.size_usd for pos in open_positions.values())
        if total_open + size_usd > current_equity * self.config.max_correlated_exposure_pct:
            return False, "correlated exposure exceeded"
        daily_pnl = current_equity - day_start_equity
        daily_limit = current_equity * self.config.daily_loss_limit_pct
        if daily_pnl < -daily_limit:
            return False, "daily loss limit reached"
        return True, "OK"


class BacktestEngine:
    def __init__(self, config: BacktestConfig | None = None) -> None:
        self.config = config or BacktestConfig()
        self.analytics = AnalyticsEngine()
        self.lch_detector = LchDetector()
        self.mss2_detector = Mss2Scanner()
        self.client = SnapshotMarketClient()
        self._positions: dict[str, _OpenPosition] = {}
        self._trades: list[BacktestTrade] = []
        self._equity_curve: list[dict[str, Any]] = []
        self._cash_pnl = 0.0
        self._realized_pnl = 0.0
        self._total_fees = 0.0
        self._total_signals = 0
        self._next_position_id = 1
        self._peak_equity = self.config.initial_capital_usd
        self._max_drawdown_pct = 0.0
        self._daily_anchor: tuple[str, float] | None = None
        self._last_market_by_id: dict[str, dict[str, Any]] = {}
        self._strategy_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "signals": 0,
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "pnl": 0.0,
            "fees": 0.0,
            "holds": [],
        })
        self._risk = _BacktestRiskGate(self.config)

    async def run(self, snapshots: Iterable[BacktestSnapshot]) -> BacktestReport:
        previous_equity = self.config.initial_capital_usd
        last_snapshot: BacktestSnapshot | None = None

        for snapshot in snapshots:
            last_snapshot = snapshot
            self.client.set_snapshot(snapshot)
            current_markets = snapshot.markets
            self._last_market_by_id = {str(m.get("id") or ""): m for m in current_markets if m.get("id")}
            current_equity_before = self._equity_from_markets(current_markets)
            self._update_daily_anchor(snapshot.timestamp, current_equity_before)

            signals = await self._collect_signals(snapshot, current_equity_before)
            for signal in signals:
                self._total_signals += 1
                self._strategy_stats[str(signal.get("signal_type") or "unknown")]["signals"] += 1
                self._attempt_trade(signal, snapshot.timestamp, current_markets, current_equity_before)

            self._close_resolved_positions(snapshot.timestamp, current_markets)

            equity = self._equity_from_markets(current_markets)
            self._record_equity(snapshot.timestamp, equity, previous_equity)
            previous_equity = equity

        if self.config.enable_final_mark_to_market and last_snapshot is not None:
            self._finalize(last_snapshot.timestamp, last_snapshot.markets)

        final_markets = last_snapshot.markets if last_snapshot else []
        final_equity = self._equity_from_markets(final_markets)
        unrealized = final_equity - (self.config.initial_capital_usd + self._cash_pnl)
        closed_positions = sum(1 for trade in self._trades if trade.action == "sell")
        open_positions = len(self._positions)
        wins = sum(1 for trade in self._trades if trade.action == "sell" and (trade.realized_pnl or 0.0) > 0)
        losses = sum(1 for trade in self._trades if trade.action == "sell" and (trade.realized_pnl or 0.0) < 0)
        closed = wins + losses
        profit_factor = self._profit_factor()
        sharpe = self._sharpe_ratio()

        by_signal_type = {
            k: {
                "signals": int(v["signals"]),
                "trades": int(v["trades"]),
                "wins": int(v["wins"]),
                "losses": int(v["losses"]),
                "pnl": float(v["pnl"]),
                "fees": float(v["fees"]),
                "win_rate": (v["wins"] / max(v["wins"] + v["losses"], 1)) if (v["wins"] + v["losses"]) else 0.0,
                "avg_hold_seconds": (sum(v["holds"]) / len(v["holds"])) if v["holds"] else 0.0,
            }
            for k, v in sorted(self._strategy_stats.items())
        }

        return BacktestReport(
            initial_capital_usd=self.config.initial_capital_usd,
            final_capital_usd=final_equity,
            realized_pnl_usd=self._realized_pnl,
            unrealized_pnl_usd=unrealized,
            total_fees_usd=self._total_fees,
            total_return_pct=_pct_change(final_equity, self.config.initial_capital_usd) * 100.0,
            max_drawdown_pct=self._max_drawdown_pct,
            sharpe_ratio=sharpe,
            win_rate=(wins / closed) if closed else 0.0,
            profit_factor=profit_factor,
            total_signals=self._total_signals,
            executed_trades=len(self._trades),
            open_positions=open_positions,
            closed_positions=closed_positions,
            by_signal_type=by_signal_type,
            equity_curve=self._equity_curve,
        )

    async def _collect_signals(self, snapshot: BacktestSnapshot, current_equity: float) -> list[dict[str, Any]]:
        cfg_common = {
            "kelly_fraction": self.config.kelly_fraction,
            "max_position_pct": self.config.max_position_pct,
            "total_capital": current_equity,
            "paper_trading": True,
        }
        markets = snapshot.markets

        roda_signals: list[dict[str, Any]] = []
        if self.config.allow_roda:
            roda_signals = await detect_roda_signals(
                markets,
                news_api_key="",
                news_articles_by_market=snapshot.news_by_market,
                config={
                    **cfg_common,
                    "roda_enabled": True,
                    "roda_min_confidence": self.config.roda_min_confidence,
                    "roda_min_age_hours": self.config.roda_min_age_hours,
                    "roda_max_age_hours": self.config.roda_max_age_hours,
                    "roda_max_entry_price": self.config.roda_max_entry_price,
                    "roda_min_sources": self.config.roda_min_sources,
                    "roda_hold_window_hours": self.config.roda_hold_window_hours,
                },
                now=snapshot.timestamp,
                kelly_fraction=self.config.kelly_fraction,
                total_capital=current_equity,
            )

        arb_signals: list[dict[str, Any]] = find_all_arb_signals(markets, current_equity) if self.config.allow_arb else []

        hybrid_signals: list[dict[str, Any]] = []
        if self.config.allow_hybrid and roda_signals and arb_signals:
            hybrid_signals = await detect_hybrid_signals(
                markets,
                roda_signals=roda_signals,
                arb_signals=arb_signals,
                config={**cfg_common, "hybrid_enabled": True, "roda_enabled": True},
                kelly_fraction=self.config.kelly_fraction,
                total_capital=current_equity,
            )

        lch_signals: list[dict[str, Any]] = []
        if self.config.allow_lch:
            lch_signals = await self.lch_detector.detect_signals(
                markets,
                client=self.client,
                config={**cfg_common, "lch_enabled": True, "lch_lookback_hours": self.config.lch_lookback_hours},
                now=snapshot.timestamp,
                kelly_fraction=self.config.kelly_fraction,
                total_capital=current_equity,
            )

        mss2_signals: list[dict[str, Any]] = []
        if self.config.allow_mss2:
            mss2_signals = await self.mss2_detector.detect_signals(
                markets,
                client=self.client,
                config={**cfg_common, "mss2_enabled": True},
                now=snapshot.timestamp,
                kelly_fraction=self.config.kelly_fraction,
                total_capital=current_equity,
            )

        generic_signals: list[dict[str, Any]] = []
        if self.config.allow_generic_strategy:
            for market in markets:
                signal = self.analytics.analyze_market(
                    market,
                    config={
                        **cfg_common,
                        "edge_threshold": 0.05,
                        "min_liquidity_usd": 1000.0,
                    },
                    sentiment_score=float(market.get("sentiment_score", 0.0) or 0.0),
                    kelly_fraction_override=self.config.kelly_fraction,
                )
                if signal:
                    generic_signals.append(signal)

        signals = [
            *roda_signals,
            *lch_signals,
            *hybrid_signals,
            *mss2_signals,
            *generic_signals,
            *arb_signals,
        ]
        signals.sort(key=lambda s: (float(s.get("confidence", 0.0)), abs(float(s.get("edge", 0.0)))), reverse=True)
        return signals

    def _attempt_trade(self, signal: dict[str, Any], now: datetime, markets: list[dict[str, Any]], current_equity: float) -> None:
        market_id = str(signal.get("market_id") or "")
        if not market_id or market_id in self._positions:
            return
        day_start = self._daily_anchor[1] if self._daily_anchor else self.config.initial_capital_usd
        can_trade, _ = self._risk.can_trade(
            signal=signal,
            current_equity=current_equity,
            day_start_equity=day_start,
            open_positions=self._positions,
        )
        if not can_trade:
            return

        market = next((m for m in markets if str(m.get("id") or "") == market_id), None)
        if not market:
            return

        yes_price = float(market.get("market_price", signal.get("market_price", 0.5)) or 0.5)
        side = str(signal.get("direction", "YES")).upper()
        token_price = _token_price(side, yes_price)
        slippage = _clamp(self.config.slippage_min, self.config.slippage_min, self.config.slippage_max)
        entry_token_price = _clamp(token_price * (1.0 + slippage), 0.01, 0.99)
        size_usd = float(signal.get("kelly_size_usd") or 0.0)
        fee_usd = estimate_taker_fee(size_usd, yes_price, side, category=market.get("category", ""), market=market)
        position = BacktestPosition(
            id=self._next_position_id,
            market_id=market_id,
            market_question=str(signal.get("market_question") or market.get("question") or ""),
            side=side,
            signal_type=str(signal.get("signal_type") or "unknown"),
            opened_at=now,
            entry_yes_price=yes_price,
            entry_token_price=entry_token_price,
            size_usd=size_usd,
            confidence=float(signal.get("confidence") or 0.0),
            entry_fee_usd=fee_usd,
            entry_slippage=slippage,
        )
        self._next_position_id += 1
        self._positions[market_id] = _OpenPosition(position=position, open_fee_usd=fee_usd)
        self._cash_pnl -= fee_usd
        self._total_fees += fee_usd
        self._trades.append(
            BacktestTrade(
                position_id=position.id,
                market_id=market_id,
                market_question=position.market_question,
                side=side,
                action="buy",
                signal_type=position.signal_type,
                executed_at=now,
                size_usd=size_usd,
                yes_price=yes_price,
                token_price=entry_token_price,
                fee_usd=fee_usd,
                slippage=slippage,
            )
        )
        self._strategy_stats[position.signal_type]["trades"] += 1
        self._strategy_stats[position.signal_type]["fees"] += fee_usd

    def _close_resolved_positions(self, now: datetime, markets: list[dict[str, Any]]) -> None:
        market_by_id = {str(m.get("id") or ""): m for m in markets if m.get("id")}
        for market_id in list(self._positions.keys()):
            market = market_by_id.get(market_id)
            if not market:
                continue
            resolved_yes = market.get("resolved_yes")
            resolved_price = market.get("resolved_price")
            status = str(market.get("status") or "").lower()
            if resolved_yes is None and resolved_price is None and status not in {"resolved", "closed"}:
                continue
            self._close_position(now, market, resolved_yes=resolved_yes, resolved_price=resolved_price)

    def _close_position(self, now: datetime, market: dict[str, Any], *, resolved_yes: Any = None, resolved_price: Any = None) -> None:
        market_id = str(market.get("id") or "")
        wrapped = self._positions.pop(market_id, None)
        if wrapped is None:
            return

        yes_price = float(market.get("market_price", wrapped.position.entry_yes_price) or wrapped.position.entry_yes_price)
        if resolved_price is not None:
            yes_price = float(resolved_price)
        elif resolved_yes is not None:
            yes_price = 1.0 if bool(resolved_yes) else 0.0

        exit_token_price = _token_price(wrapped.position.side, yes_price)
        gross_pnl = (exit_token_price - wrapped.position.entry_token_price) * wrapped.position.size_usd / max(wrapped.position.entry_token_price, 1e-9)
        exit_fee = estimate_taker_fee(wrapped.position.size_usd, yes_price, wrapped.position.side, category=market.get("category", ""), market=market)
        net_pnl = gross_pnl - exit_fee
        wrapped.position.status = "closed"
        wrapped.position.closed_at = now
        wrapped.position.exit_yes_price = yes_price
        wrapped.position.exit_token_price = exit_token_price
        wrapped.position.exit_fee_usd = exit_fee
        wrapped.position.realized_pnl = net_pnl
        self._cash_pnl += gross_pnl - exit_fee
        self._realized_pnl += net_pnl
        self._total_fees += exit_fee
        self._trades.append(
            BacktestTrade(
                position_id=wrapped.position.id,
                market_id=market_id,
                market_question=wrapped.position.market_question,
                side=wrapped.position.side,
                action="sell",
                signal_type=wrapped.position.signal_type,
                executed_at=now,
                size_usd=wrapped.position.size_usd,
                yes_price=yes_price,
                token_price=exit_token_price,
                fee_usd=exit_fee,
                slippage=0.0,
                realized_pnl=net_pnl,
            )
        )
        stats = self._strategy_stats[wrapped.position.signal_type]
        if net_pnl > 0:
            stats["wins"] += 1
        elif net_pnl < 0:
            stats["losses"] += 1
        stats["pnl"] += net_pnl
        stats["fees"] += exit_fee
        stats["holds"].append(max(0.0, (now - wrapped.position.opened_at).total_seconds()))

    def _finalize(self, now: datetime, markets: list[dict[str, Any]]) -> None:
        market_by_id = {str(m.get("id") or ""): m for m in markets if m.get("id")}
        for market_id in list(self._positions.keys()):
            market = market_by_id.get(market_id) or self._last_market_by_id.get(market_id)
            if market is not None:
                self._close_position(now, market)

    def _equity_from_markets(self, markets: list[dict[str, Any]]) -> float:
        market_by_id = {str(m.get("id") or ""): m for m in markets if m.get("id")}
        unrealized = 0.0
        for market_id, wrapped in self._positions.items():
            market = market_by_id.get(market_id) or self._last_market_by_id.get(market_id)
            if market is None:
                continue
            yes_price = float(market.get("market_price", wrapped.position.entry_yes_price) or wrapped.position.entry_yes_price)
            current_token_price = _token_price(wrapped.position.side, yes_price)
            unrealized += (current_token_price - wrapped.position.entry_token_price) * wrapped.position.size_usd / max(wrapped.position.entry_token_price, 1e-9)
        return self.config.initial_capital_usd + self._cash_pnl + unrealized

    def _update_daily_anchor(self, timestamp: datetime, equity: float) -> None:
        day_key = timestamp.astimezone(timezone.utc).date().isoformat()
        if self._daily_anchor is None or self._daily_anchor[0] != day_key:
            self._daily_anchor = (day_key, equity)

    def _record_equity(self, timestamp: datetime, equity: float, previous_equity: float) -> None:
        self._peak_equity = max(self._peak_equity, equity)
        drawdown = 0.0 if self._peak_equity <= 0 else (self._peak_equity - equity) / self._peak_equity
        self._max_drawdown_pct = max(self._max_drawdown_pct, drawdown * 100.0)
        self._equity_curve.append({
            "timestamp": timestamp.astimezone(timezone.utc).isoformat(),
            "equity": equity,
            "return_pct": _pct_change(equity, self.config.initial_capital_usd) * 100.0,
            "step_return_pct": _pct_change(equity, previous_equity) * 100.0 if previous_equity > 0 else 0.0,
            "drawdown_pct": drawdown * 100.0,
        })

    def _profit_factor(self) -> float:
        gains = sum(t.realized_pnl for t in self._trades if t.action == "sell" and (t.realized_pnl or 0.0) > 0)
        losses = abs(sum(t.realized_pnl for t in self._trades if t.action == "sell" and (t.realized_pnl or 0.0) < 0))
        if losses <= 0:
            return float("inf") if gains > 0 else 0.0
        return gains / losses

    def _sharpe_ratio(self) -> float:
        returns = [float(point["step_return_pct"]) / 100.0 for point in self._equity_curve if point["step_return_pct"] is not None]
        if len(returns) < 2:
            return 0.0
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        if variance <= 0:
            return 0.0
        std = math.sqrt(variance)
        return round((mean / std) * math.sqrt(252.0), 2)


async def run_backtest_file(path: str, *, config: BacktestConfig | None = None) -> BacktestReport:
    engine = BacktestEngine(config=config)
    snapshots = iter_backtest_snapshots(path)
    return await engine.run(snapshots)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Polybot historical backtest engine")
    parser.add_argument("--input", required=True, help="Path to JSON or JSONL replay file")
    parser.add_argument("--capital", type=float, default=1000.0, help="Initial capital in USD")
    parser.add_argument("--kelly", type=float, default=0.25, help="Kelly fraction")
    parser.add_argument("--max-position-pct", type=float, default=0.05, dest="max_position_pct")
    parser.add_argument("--max-exposure-pct", type=float, default=0.15, dest="max_correlated_exposure_pct")
    parser.add_argument("--daily-loss-pct", type=float, default=0.03, dest="daily_loss_limit_pct")
    parser.add_argument(
        "--strategies",
        default="roda,lch,hybrid,mss2,arb,generic",
        help="Comma-separated strategies to enable",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    return parser


def _config_from_args(args: argparse.Namespace) -> BacktestConfig:
    enabled = {item.strip().lower() for item in str(args.strategies or "").split(",") if item.strip()}
    return BacktestConfig(
        initial_capital_usd=float(args.capital),
        kelly_fraction=float(args.kelly),
        max_position_pct=float(args.max_position_pct),
        max_correlated_exposure_pct=float(args.max_correlated_exposure_pct),
        daily_loss_limit_pct=float(args.daily_loss_limit_pct),
        allow_roda="roda" in enabled,
        allow_lch="lch" in enabled,
        allow_hybrid="hybrid" in enabled,
        allow_mss2="mss2" in enabled,
        allow_arb="arb" in enabled,
        allow_generic_strategy="generic" in enabled,
    )


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    report = asyncio.run(run_backtest_file(args.input, config=_config_from_args(args)))
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    else:
        data = report.to_dict()
        print(
            f"Final equity: ${data['final_capital_usd']:.2f} | "
            f"Return: {data['total_return_pct']:.2f}% | "
            f"Max DD: {data['max_drawdown_pct']:.2f}% | "
            f"Win rate: {data['win_rate']:.2%} | "
            f"Trades: {data['executed_trades']}"
        )
    return 0
