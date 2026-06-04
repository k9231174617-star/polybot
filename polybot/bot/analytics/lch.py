"""LCH detector — liquidation/cascade-style shock recovery strategy."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Deque, Optional

from loguru import logger

from bot.analytics.engine import AnalyticsEngine


@dataclass
class _PricePoint:
    ts: datetime
    yes_price: float
    volume_24h: float


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class LchDetector:
    def __init__(self) -> None:
        self.history: dict[str, Deque[_PricePoint]] = defaultdict(deque)
        self.engine = AnalyticsEngine()

    def _append_point(self, market: dict, now: datetime, lookback_hours: float) -> None:
        market_id = market["id"]
        price = float(market.get("market_price", 0.5))
        volume = float(market.get("volume_24h", 0.0) or 0.0)
        history = self.history[market_id]
        history.append(_PricePoint(ts=now, yes_price=price, volume_24h=volume))

        cutoff = now - timedelta(hours=lookback_hours)
        while history and history[0].ts < cutoff:
            history.popleft()

        while len(history) > 90:
            history.popleft()

    def _hours_to_resolve(self, market: dict, now: datetime) -> Optional[float]:
        end_date = _utc(market.get("end_date"))
        if end_date is None:
            return None
        return max(0.0, (end_date - now).total_seconds() / 3600.0)

    def _build_signal(
        self,
        market: dict,
        current: _PricePoint,
        history: Deque[_PricePoint],
        config: dict,
        total_capital: float,
        kelly_fraction: float,
        now: datetime,
    ) -> Optional[dict]:
        min_hours_to_resolve = float(config.get("lch_min_hours_to_resolve", 48.0))
        min_shock_magnitude = float(config.get("lch_min_shock_magnitude", 0.08))
        min_z_score = float(config.get("lch_min_z_score", 2.5))
        min_recovery_probability = float(config.get("lch_min_recovery_probability", 0.70))
        stop_loss_pct = float(config.get("lch_stop_loss_pct", 0.05))
        take_profit_pct_of_shock = float(config.get("lch_take_profit_pct_of_shock", 0.50))
        max_hold_minutes = int(config.get("lch_max_hold_minutes", 15))
        max_position_pct = float(config.get("lch_max_position_pct", 0.075))
        min_position_size_usd = float(config.get("lch_min_position_size_usd", 50.0))
        max_position_size_usd = float(config.get("lch_max_position_size_usd", 500.0))

        hours_to_resolve = self._hours_to_resolve(market, now)
        if hours_to_resolve is None or hours_to_resolve < min_hours_to_resolve:
            return None

        if len(history) < 6:
            return None

        prices = [p.yes_price for p in history]
        mean = statistics.mean(prices)
        std = statistics.stdev(prices) if len(prices) > 1 else 0.0
        if std <= 0.0:
            return None

        deviation = abs(current.yes_price - mean)
        z_score = deviation / std
        price_move = abs(current.yes_price - prices[-2]) if len(prices) >= 2 else 0.0

        if deviation < min_shock_magnitude and z_score < min_z_score:
            return None
        if price_move < 0.015 and z_score < min_z_score + 0.5:
            return None

        direction = "YES" if current.yes_price < mean else "NO"
        recovery_boost = _clamp(0.12 * z_score + 0.08 * math.log1p(current.volume_24h / 1000.0), 0.0, 0.35)
        recovery_probability = _clamp(0.55 + recovery_boost, min_recovery_probability, 0.99)

        shock = current.yes_price - mean
        if direction == "YES":
            model_probability = _clamp(current.yes_price + abs(shock) * recovery_probability * 1.25, 0.01, 0.99)
        else:
            model_probability = _clamp(current.yes_price - abs(shock) * recovery_probability * 1.25, 0.01, 0.99)

        edge = model_probability - current.yes_price
        if abs(edge) < 0.01:
            return None

        time_decay = _clamp(1.0 - max(0.0, 48.0 - hours_to_resolve) / 96.0, 0.35, 1.0)
        kelly_size = self.engine.calculate_kelly_size(
            edge,
            model_probability,
            current.yes_price,
            total_capital,
            kelly_fraction,
        )
        kelly_size = min(kelly_size * time_decay, total_capital * max_position_pct, max_position_size_usd)
        if kelly_size < min_position_size_usd:
            return None

        entry_price = current.yes_price if direction == "YES" else 1.0 - current.yes_price
        target_exit_price = _clamp(entry_price + abs(shock) * take_profit_pct_of_shock, 0.01, 0.99)
        stop_loss_price = _clamp(entry_price * (1.0 - stop_loss_pct), 0.01, 0.99)

        signal = {
            "market_id": market["id"],
            "market_question": market.get("question", ""),
            "signal_type": "lch_cascade",
            "direction": direction,
            "market_price": current.yes_price,
            "model_probability": model_probability,
            "edge": edge,
            "kelly_size_usd": kelly_size,
            "confidence": _clamp(0.45 + 0.1 * z_score + 0.15 * recovery_probability, 0.0, 0.99),
            "lch_shock_magnitude": abs(shock),
            "lch_z_score": z_score,
            "lch_recovery_probability": recovery_probability,
            "lch_entry_price": entry_price,
            "lch_target_exit_price": target_exit_price,
            "lch_stop_loss_price": stop_loss_price,
            "lch_hold_minutes": max_hold_minutes,
            "lch_hours_to_resolve": hours_to_resolve,
        }
        return signal

    async def detect_signals(
        self,
        markets: list[dict],
        *,
        config: Optional[dict] = None,
        kelly_fraction: float = 0.15,
        total_capital: float = 1000.0,
    ) -> list[dict]:
        cfg = config or {}
        if not cfg.get("lch_enabled", True):
            return []

        lookback_hours = float(cfg.get("lch_lookback_hours", 1.0))
        now = datetime.now(timezone.utc)

        for market in markets:
            if not market.get("id"):
                continue
            self._append_point(market, now, lookback_hours)

        signals: list[dict] = []
        for market in markets:
            market_id = market.get("id")
            if not market_id or market.get("status") not in {"active", "open"}:
                continue
            history = self.history.get(market_id)
            if not history:
                continue

            current = history[-1]
            signal = self._build_signal(market, current, history, cfg, total_capital, kelly_fraction, now)
            if signal:
                signals.append(signal)

        signals.sort(key=lambda s: (s["confidence"], abs(s["edge"])), reverse=True)
        if signals:
            logger.info(f"LCH detected {len(signals)} opportunities")
        return signals
