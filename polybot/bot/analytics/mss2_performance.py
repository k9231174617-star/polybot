"""MSS2 performance analytics for strategy-level reporting."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any, Optional

from bot.utils.db import get_pool


@dataclass
class Mss2PerformanceTopMarket:
    market_id: str
    market_question: str
    pnl: float
    trades: int


@dataclass
class Mss2PerformanceReport:
    generated_at: datetime
    period_days: int
    signal_type: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    gross_profit: float
    gross_loss: float
    net_pnl: float
    maker_rebate: float
    net_after_rebate: float
    avg_profit_per_trade: float
    avg_profit_per_winner: float
    avg_loss_per_loser: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    avg_hold_time_seconds: float
    median_hold_time_seconds: float
    trades_per_day: float
    capital_utilization_pct: float
    pending_capital_avg_pct: float
    spread_captured: int
    hedged: int
    timeout: int
    stop_loss: int
    requeue_abandoned: int
    adverse_selection: int
    top_markets: list[Mss2PerformanceTopMarket]
    blocklisted_markets: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["generated_at"] = self.generated_at.astimezone(timezone.utc).isoformat()
        data["top_markets"] = [asdict(item) for item in self.top_markets]
        return data


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 0:
        return (ordered[mid - 1] + ordered[mid]) / 2.0
    return ordered[mid]


def _max_drawdown(values: list[float]) -> float:
    peak = 0.0
    cumulative = 0.0
    max_dd = 0.0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
    return max_dd


def _sharpe(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    variance = sum((value - avg) ** 2 for value in values) / (len(values) - 1)
    std_dev = variance**0.5
    if std_dev <= 0.0:
        return 0.0
    return (avg / std_dev) * (252.0**0.5)


def _sortino(values: list[float]) -> float:
    downside = [value for value in values if value < 0.0]
    if not downside:
        return float("inf") if values else 0.0
    avg = mean(values)
    downside_variance = sum(value**2 for value in downside) / len(downside)
    downside_dev = downside_variance**0.5
    if downside_dev <= 0.0:
        return float("inf")
    return (avg / downside_dev) * (252.0**0.5)


class Mss2PerformanceAnalytics:
    def __init__(self, signal_type: str = "mss2_spread_capture") -> None:
        self.signal_type = signal_type

    async def _fetch_rows(self, days: int) -> tuple[list[dict], list[dict], list[str], float]:
        pool = await get_pool()
        since = datetime.now(timezone.utc) - timedelta(days=max(days, 1))
        async with pool.acquire() as conn:
            trade_rows = await conn.fetch(
                """
                SELECT market_id, market_question, side, action, size_usd, price, slippage, fee_usd,
                       realized_pnl, signal_type, executed_at
                FROM paper_trades
                WHERE signal_type = $1 AND executed_at >= $2
                ORDER BY executed_at ASC
                """,
                self.signal_type,
                since.replace(tzinfo=None),
            )
            position_rows = await conn.fetch(
                """
                SELECT market_id, market_question, size_usd, opened_at, closed_at, signal_type
                FROM paper_positions
                WHERE signal_type = $1 AND opened_at >= $2
                """,
                self.signal_type,
                since.replace(tzinfo=None),
            )
            blocklisted_rows = await conn.fetch(
                "SELECT id FROM markets WHERE status = 'blocked' ORDER BY id ASC"
            )
            capital = await conn.fetchval(
                "SELECT paper_capital_usd FROM bot_config ORDER BY id DESC LIMIT 1"
            ) or 1000.0
        return [dict(row) for row in trade_rows], [dict(row) for row in position_rows], [str(row["id"]) for row in blocklisted_rows], float(capital)

    async def generate_report(self, days: int = 30) -> Mss2PerformanceReport:
        trades, positions, blocklisted, capital = await self._fetch_rows(days)
        if not trades and not positions:
            return self.empty_report(days=days, capital=capital, blocklisted_markets=blocklisted)

        buys = [trade for trade in trades if trade.get("action") == "buy"]
        sells = [trade for trade in trades if trade.get("action") == "sell" and trade.get("realized_pnl") is not None]
        pnl_values = [float(trade.get("realized_pnl") or 0.0) for trade in sells]
        winning = [pnl for pnl in pnl_values if pnl > 0.0]
        losing = [-pnl for pnl in pnl_values if pnl < 0.0]

        gross_profit = sum(winning)
        gross_loss = sum(losing)
        net_pnl = gross_profit - gross_loss
        profit_factor = gross_profit / gross_loss if gross_loss > 0.0 else (float("inf") if gross_profit > 0.0 else 0.0)

        daily_pnl: dict[str, float] = defaultdict(float)
        for trade in sells:
            executed_at = trade.get("executed_at")
            if not isinstance(executed_at, datetime):
                continue
            daily_pnl[executed_at.date().isoformat()] += float(trade.get("realized_pnl") or 0.0)
        daily_returns = [value / capital if capital > 0.0 else 0.0 for value in daily_pnl.values() if value != 0.0]

        hold_times = []
        for row in positions:
            opened_at = row.get("opened_at")
            closed_at = row.get("closed_at")
            if not isinstance(opened_at, datetime) or not isinstance(closed_at, datetime):
                continue
            hold_times.append(max(0.0, (closed_at - opened_at).total_seconds()))

        market_buckets: dict[tuple[str, str], dict[str, float | int]] = defaultdict(lambda: {"pnl": 0.0, "trades": 0})
        for trade in trades:
            key = (str(trade.get("market_id") or ""), str(trade.get("market_question") or ""))
            bucket = market_buckets[key]
            bucket["trades"] = int(bucket["trades"]) + 1
            if trade.get("realized_pnl") is not None:
                bucket["pnl"] = float(bucket["pnl"]) + float(trade.get("realized_pnl") or 0.0)

        top_markets = [
            Mss2PerformanceTopMarket(
                market_id=market_id,
                market_question=market_question,
                pnl=float(data["pnl"]),
                trades=int(data["trades"]),
            )
            for (market_id, market_question), data in sorted(
                market_buckets.items(),
                key=lambda item: float(item[1]["pnl"]),
                reverse=True,
            )[:5]
        ]

        max_drawdown_abs = _max_drawdown(pnl_values)
        open_capital = sum(
            float(row.get("size_usd") or 0.0)
            for row in positions
            if not row.get("closed_at")
        )
        return Mss2PerformanceReport(
            generated_at=datetime.now(timezone.utc),
            period_days=max(days, 1),
            signal_type=self.signal_type,
            total_trades=len(buys),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=len(winning) / max(len(winning) + len(losing), 1),
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_pnl=net_pnl,
            maker_rebate=0.0,
            net_after_rebate=net_pnl,
            avg_profit_per_trade=net_pnl / max(len(buys), 1),
            avg_profit_per_winner=gross_profit / max(len(winning), 1),
            avg_loss_per_loser=gross_loss / max(len(losing), 1),
            profit_factor=profit_factor,
            max_drawdown_pct=(max_drawdown_abs / capital * 100.0) if capital > 0.0 else 0.0,
            sharpe_ratio=_sharpe(daily_returns),
            sortino_ratio=_sortino(daily_returns),
            avg_hold_time_seconds=mean(hold_times) if hold_times else 0.0,
            median_hold_time_seconds=_median(hold_times),
            trades_per_day=len(buys) / max(days, 1),
            capital_utilization_pct=(open_capital / capital * 100.0) if capital > 0.0 else 0.0,
            pending_capital_avg_pct=0.0,
            spread_captured=len(buys),
            hedged=0,
            timeout=0,
            stop_loss=0,
            requeue_abandoned=0,
            adverse_selection=0,
            top_markets=top_markets,
            blocklisted_markets=blocklisted,
        )

    def empty_report(
        self,
        *,
        days: int,
        capital: float = 1000.0,
        blocklisted_markets: Optional[list[str]] = None,
    ) -> Mss2PerformanceReport:
        return Mss2PerformanceReport(
            generated_at=datetime.now(timezone.utc),
            period_days=max(days, 1),
            signal_type=self.signal_type,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            gross_profit=0.0,
            gross_loss=0.0,
            net_pnl=0.0,
            maker_rebate=0.0,
            net_after_rebate=0.0,
            avg_profit_per_trade=0.0,
            avg_profit_per_winner=0.0,
            avg_loss_per_loser=0.0,
            profit_factor=0.0,
            max_drawdown_pct=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            avg_hold_time_seconds=0.0,
            median_hold_time_seconds=0.0,
            trades_per_day=0.0,
            capital_utilization_pct=0.0,
            pending_capital_avg_pct=0.0,
            spread_captured=0,
            hedged=0,
            timeout=0,
            stop_loss=0,
            requeue_abandoned=0,
            adverse_selection=0,
            top_markets=[],
            blocklisted_markets=blocklisted_markets or [],
        )
