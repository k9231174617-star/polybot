"""MSS2 detector — spread-capture and adverse-selection filtered market making."""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from loguru import logger

from bot.analytics.engine import AnalyticsEngine


@dataclass
class _Point:
    ts: datetime
    yes_mid: float
    yes_spread_bps: float


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return _utc(parsed)
        except Exception:
            return None
    return None


def _token_id(token: dict | None) -> str:
    if not token:
        return ""
    return str(token.get("token_id") or token.get("id") or token.get("tokenId") or "")


def _token_outcome(token: dict | None) -> str:
    if not token:
        return ""
    return str(token.get("outcome") or token.get("side") or token.get("name") or "").upper()


def _best_prices(book: dict | None) -> tuple[float, float, float, float]:
    if not book:
        return 0.0, 0.0, 0.0, 0.0
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    try:
        best_bid = max(float(level["price"]) for level in bids) if bids else 0.0
        best_ask = min(float(level["price"]) for level in asks) if asks else 0.0
    except (TypeError, ValueError, KeyError):
        return 0.0, 0.0, 0.0, 0.0
    mid = (best_bid + best_ask) / 2.0 if best_bid > 0.0 and best_ask > 0.0 else 0.0
    spread_bps = ((best_ask - best_bid) / mid * 10000.0) if mid > 0.0 else 0.0
    return best_bid, best_ask, mid, spread_bps


def _depth_ahead(book: dict | None, entry_price: float, side: str) -> float:
    if not book:
        return 0.0
    levels = book.get("bids") or []
    try:
        if side == "YES":
            return sum(float(level.get("size", level.get("quantity", 0.0)) or 0.0) for level in levels if float(level.get("price", 0.0)) >= entry_price)
        return sum(float(level.get("size", level.get("quantity", 0.0)) or 0.0) for level in levels if float(level.get("price", 0.0)) >= entry_price)
    except (TypeError, ValueError):
        return 0.0


class Mss2Scanner:
    def __init__(self) -> None:
        self.history: dict[str, deque[_Point]] = defaultdict(deque)
        self.engine = AnalyticsEngine()

    def _append_point(self, market_id: str, yes_mid: float, yes_spread_bps: float, now: datetime) -> None:
        history = self.history[market_id]
        history.append(_Point(ts=now, yes_mid=yes_mid, yes_spread_bps=yes_spread_bps))
        cutoff = now - timedelta(minutes=10)
        while history and history[0].ts < cutoff:
            history.popleft()
        while len(history) > 30:
            history.popleft()

    def _momentum(self, market_id: str) -> float:
        history = self.history.get(market_id)
        if not history or len(history) < 2:
            return 0.0
        recent = list(history)[-6:]
        first = recent[0]
        last = recent[-1]
        if first.yes_mid <= 0.0:
            return 0.0
        return (last.yes_mid - first.yes_mid) / first.yes_mid

    def _spread_velocity(self, market_id: str) -> float:
        history = self.history.get(market_id)
        if not history or len(history) < 2:
            return 0.0
        recent = list(history)[-6:]
        first = recent[0]
        last = recent[-1]
        elapsed = (last.ts - first.ts).total_seconds()
        if elapsed <= 0:
            return 0.0
        return (first.yes_spread_bps - last.yes_spread_bps) / elapsed

    async def detect_signals(
        self,
        markets: list[dict],
        *,
        client,
        config: Optional[dict] = None,
        kelly_fraction: float = 0.25,
        total_capital: float = 1000.0,
    ) -> list[dict]:
        cfg = config or {}
        if not cfg.get("mss2_enabled", True):
            return []

        min_liquidity = float(cfg.get("mss2_min_liquidity_usd", cfg.get("min_liquidity_usd", 1000.0)))
        min_hours_to_resolve = float(cfg.get("mss2_min_hours_to_resolve", 6.0))
        min_spread_bps = float(cfg.get("mss2_min_spread_bps", 35.0))
        max_spread_bps = float(cfg.get("mss2_max_spread_bps", 2500.0))
        max_depth_at_level_usd = float(cfg.get("mss2_max_depth_at_level_usd", 500.0))
        max_time_since_fill_proxy = float(cfg.get("mss2_max_time_since_fill_proxy", 120.0))
        min_fill_probability_proxy = float(cfg.get("mss2_min_fill_probability_proxy", 0.30))
        max_volume_anomaly_ratio = float(cfg.get("mss2_max_volume_anomaly_ratio", 3.0))
        max_price_momentum_2min = float(cfg.get("mss2_max_price_momentum_2min", 0.02))
        max_adverse_selection_score = float(cfg.get("mss2_max_adverse_selection_score", 0.65))
        max_spread_compression_velocity = float(cfg.get("mss2_max_spread_compression_velocity", 60.0))
        max_competitive_pressure = float(cfg.get("mss2_max_competitive_pressure", 0.75))
        min_expected_profit_bps = float(cfg.get("mss2_min_expected_profit_bps", 35.0))
        max_position_pct = float(cfg.get("mss2_max_position_pct", cfg.get("max_position_pct", 0.05)))
        min_position_size_usd = float(cfg.get("mss2_min_position_size_usd", 20.0))
        entry_offset_bps = float(cfg.get("mss2_entry_offset_bps", 8.0))
        exit_offset_bps = float(cfg.get("mss2_exit_offset_bps", 8.0))
        size_multiplier = float(cfg.get("mss2_size_multiplier", 0.7))

        now = datetime.now(timezone.utc)
        candidates = []
        for market in markets:
            end_date = _utc(market.get("end_date"))
            if not market.get("id") or not end_date:
                continue
            if market.get("status") not in {"active", "open"}:
                continue
            hours_to_resolve = max(0.0, (end_date - now).total_seconds() / 3600.0)
            if hours_to_resolve < min_hours_to_resolve:
                continue
            if float(market.get("liquidity_usd", 0.0) or 0.0) < min_liquidity:
                continue
            candidates.append((hours_to_resolve, market))

        if not candidates:
            return []

        candidates.sort(key=lambda item: float(item[1].get("liquidity_usd", 0.0) or 0.0), reverse=True)
        candidates = candidates[: min(len(candidates), 20)]

        signals: list[dict] = []
        for hours_to_resolve, market in candidates:
            try:
                tokens = market.get("tokens") or []
                yes_token = next((t for t in tokens if _token_outcome(t) == "YES"), None)
                no_token = next((t for t in tokens if _token_outcome(t) == "NO"), None)
                yes_token_id = _token_id(yes_token)
                no_token_id = _token_id(no_token)
                if not yes_token_id and not no_token_id:
                    continue

                books = await asyncio.gather(
                    client.get_clob_orderbook(yes_token_id) if yes_token_id else asyncio.sleep(0, result=None),
                    client.get_clob_orderbook(no_token_id) if no_token_id else asyncio.sleep(0, result=None),
                    client.get_trades(str(market["id"]), limit=20),
                )
                yes_book, no_book, trades = books[0], books[1], books[2]
            except Exception as exc:
                logger.debug(f"MSS2 fetch error for {market.get('id')}: {exc}")
                continue

            yes_best_bid, yes_best_ask, yes_mid, yes_spread_bps = _best_prices(yes_book)
            no_best_bid, no_best_ask, no_mid, no_spread_bps = _best_prices(no_book)
            if yes_mid <= 0.0:
                yes_mid = float(market.get("market_price", 0.5))

            self._append_point(str(market["id"]), yes_mid, yes_spread_bps or abs(yes_best_ask - yes_best_bid) * 10000.0, now)
            momentum_2m = self._momentum(str(market["id"]))
            spread_velocity = self._spread_velocity(str(market["id"]))

            trades_5min = 0
            trades_1h = 0
            last_trade_price = yes_mid
            last_trade_time = None
            for trade in trades or []:
                ts = _parse_time(trade.get("createdAt") or trade.get("created_at") or trade.get("timestamp") or trade.get("time"))
                if ts is None:
                    continue
                age_seconds = (now - ts).total_seconds()
                if age_seconds <= 300:
                    trades_5min += 1
                if age_seconds <= 3600:
                    trades_1h += 1
                try:
                    last_trade_price = float(trade.get("price", last_trade_price) or last_trade_price)
                except (TypeError, ValueError):
                    pass
                if last_trade_time is None or ts > last_trade_time:
                    last_trade_time = ts

            volume_anomaly_ratio = trades_5min / max(trades_1h / 12.0, 1.0) if trades_1h > 0 else 1.0
            time_since_fill = (now - last_trade_time).total_seconds() if last_trade_time else 999.0
            if time_since_fill > max_time_since_fill_proxy and trades_5min == 0:
                continue

            side_candidates: list[dict] = []
            for side, book, best_bid, best_ask, spread_bps in (
                ("YES", yes_book, yes_best_bid, yes_best_ask, yes_spread_bps),
                ("NO", no_book, no_best_bid, no_best_ask, no_spread_bps),
            ):
                if not book or best_bid <= 0.0 or best_ask <= 0.0:
                    continue
                if spread_bps < min_spread_bps or spread_bps > max_spread_bps:
                    continue

                token_entry = best_bid + (best_ask - best_bid) * (entry_offset_bps / 10000.0)
                token_exit = best_ask - (best_ask - best_bid) * (exit_offset_bps / 10000.0)
                if token_exit <= token_entry:
                    continue

                depth_at_entry = _depth_ahead(book, token_entry, side)
                if depth_at_entry > max_depth_at_level_usd:
                    continue

                fill_prob = _clamp(
                    0.45 * (1.0 - depth_at_entry / max(max_depth_at_level_usd, 1.0))
                    + 0.35 * min(1.0, trades_5min / 5.0)
                    + 0.20 * (1.0 if time_since_fill < 30.0 else 0.7 if time_since_fill < 60.0 else 0.4),
                    0.0,
                    0.99,
                )
                if fill_prob < min_fill_probability_proxy:
                    continue

                adverse_selection_score = _clamp(
                    0.45 * min(1.0, max(0.0, volume_anomaly_ratio - 1.0) / max(max_volume_anomaly_ratio, 1.0))
                    + 0.35 * min(1.0, abs(momentum_2m) / max(max_price_momentum_2min, 1e-6))
                    + 0.20 * min(1.0, max(0.0, spread_velocity) / max(max_spread_compression_velocity, 1.0)),
                    0.0,
                    1.0,
                )
                if adverse_selection_score > max_adverse_selection_score:
                    continue

                competitive_pressure = _clamp(
                    0.55 * min(1.0, depth_at_entry / max(max_depth_at_level_usd, 1.0))
                    + 0.45 * min(1.0, max(0.0, spread_velocity) / max(max_spread_compression_velocity, 1.0)),
                    0.0,
                    1.0,
                )
                if competitive_pressure > max_competitive_pressure:
                    continue

                expected_profit_bps = ((token_exit - token_entry) / token_entry) * 10000.0
                if expected_profit_bps < min_expected_profit_bps:
                    continue

                model_probability = token_exit if side == "YES" else 1.0 - token_exit
                market_price = float(market.get("market_price", yes_mid))
                edge = model_probability - market_price

                confidence = _clamp(
                    0.40 + 0.25 * fill_prob + 0.20 * (1.0 - adverse_selection_score) + 0.15 * min(1.0, expected_profit_bps / 150.0),
                    0.0,
                    0.99,
                )
                if confidence < 0.50:
                    continue

                size = self.engine.calculate_kelly_size(edge, model_probability, market_price, total_capital, kelly_fraction)
                size = min(size * size_multiplier, total_capital * max_position_pct)
                if size < min_position_size_usd:
                    continue

                side_candidates.append({
                    "market_id": market["id"],
                    "market_question": market.get("question", ""),
                    "signal_type": "mss2_spread_capture",
                    "direction": side,
                    "order_type": "limit",
                    "market_price": market_price,
                    "model_probability": model_probability,
                    "edge": edge,
                    "kelly_size_usd": size,
                    "confidence": confidence,
                    "mss2_side": side,
                    "mss2_entry_price": token_entry,
                    "mss2_target_exit_price": token_exit,
                    "mss2_spread_bps": spread_bps,
                    "mss2_expected_profit_bps": expected_profit_bps,
                    "mss2_depth_at_entry_level": depth_at_entry,
                    "mss2_fill_probability_proxy": fill_prob,
                    "mss2_adverse_selection_score": adverse_selection_score,
                    "mss2_volume_anomaly_ratio": volume_anomaly_ratio,
                    "mss2_price_momentum_2min": momentum_2m,
                    "mss2_spread_compression_velocity": spread_velocity,
                    "mss2_competitive_pressure_score": competitive_pressure,
                    "mss2_hours_to_resolution": hours_to_resolve,
                    "mss2_last_trade_price": last_trade_price,
                })

            if side_candidates:
                best = max(side_candidates, key=lambda s: (s["confidence"], abs(s["edge"]), s["kelly_size_usd"]))
                signals.append(best)

        signals.sort(key=lambda s: (s["confidence"], abs(s["edge"])), reverse=True)
        if signals:
            logger.info(f"MSS2 detected {len(signals)} opportunities")
        return signals
