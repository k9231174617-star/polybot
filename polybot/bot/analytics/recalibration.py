"""Automatic strategy recalibration based on recent live/paper results."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any, Iterable

from loguru import logger

from bot.notifications import send_telegram_alert
from bot.utils.db import get_pool, log_entry, update_bot_config


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _prefix(signal_type: str) -> str:
    signal = str(signal_type or "").lower()
    if signal.startswith("roda_"):
        return "roda"
    if signal.startswith("lch_"):
        return "lch"
    if signal.startswith("mss2_"):
        return "mss2"
    if signal.startswith("hybrid_"):
        return "hybrid"
    if signal.startswith("cross_market_arb"):
        return "arb"
    return signal or "unknown"


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (len(ordered) - 1) * _clamp(percentile, 0.0, 1.0)
    lower = int(idx)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    frac = idx - lower
    return ordered[lower] * (1.0 - frac) + ordered[upper] * frac


def _numeric(detail: Any, key: str) -> float | None:
    if not isinstance(detail, dict):
        return None
    value = detail.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


@dataclass(slots=True)
class StrategyPerformance:
    strategy: str
    sample_size: int
    wins: int
    losses: int
    win_rate: float
    gross_profit: float
    gross_loss: float
    net_pnl: float
    avg_pnl: float
    profit_factor: float
    avg_queue_pressure: float
    avg_expected_fill_delay_seconds: float
    avg_latency_signal_to_confirmation_ms: float
    avg_wash_score: float
    p95_latency_signal_to_confirmation_ms: float
    p95_latency_signal_to_trade_recorded_ms: float


@dataclass(slots=True)
class RecalibrationRecommendation:
    strategy: str
    sample_size: int
    reason: str
    confidence: float
    current_config: dict[str, Any]
    proposed_patch: dict[str, Any]
    performance: StrategyPerformance
    applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "sample_size": self.sample_size,
            "reason": self.reason,
            "confidence": self.confidence,
            "current_config": self.current_config,
            "proposed_patch": self.proposed_patch,
            "performance": asdict(self.performance),
            "applied": self.applied,
        }


async def _fetch_recent_data(window_days: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    since = datetime.now(timezone.utc) - timedelta(days=max(1, window_days))
    pool = await get_pool()
    async with pool.acquire() as conn:
        trade_rows = await conn.fetch(
            """
            SELECT
              COALESCE(s.signal_type, t.order_type, 'unknown') AS signal_type,
              COALESCE(t.realized_pnl, 0) AS realized_pnl,
              COALESCE(t.executed_at, NOW()) AS executed_at
            FROM trades t
            LEFT JOIN signals s ON s.id = t.signal_id
            WHERE t.executed_at >= $1 AND t.realized_pnl IS NOT NULL
            UNION ALL
            SELECT
              COALESCE(signal_type, 'unknown') AS signal_type,
              COALESCE(realized_pnl, 0) AS realized_pnl,
              COALESCE(executed_at, NOW()) AS executed_at
            FROM paper_trades
            WHERE executed_at >= $1 AND realized_pnl IS NOT NULL
            ORDER BY executed_at ASC
            """,
            since.replace(tzinfo=None),
        )
        signal_rows = await conn.fetch(
            """
            SELECT signal_type, details, detected_at
            FROM signals
            WHERE detected_at >= $1
            ORDER BY detected_at ASC
            """,
            since.replace(tzinfo=None),
        )
        latency_rows = await conn.fetch(
            """
            SELECT signal_type, stage, duration_ms
            FROM latency_events
            WHERE created_at >= $1
            ORDER BY created_at ASC
            """,
            since.replace(tzinfo=None),
        )
    return [dict(row) for row in trade_rows], [dict(row) for row in signal_rows], [dict(row) for row in latency_rows]


def _aggregate_performance(
    strategy: str,
    trades: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    latencies: list[dict[str, Any]],
) -> StrategyPerformance:
    pnls = [float(row.get("realized_pnl") or 0.0) for row in trades]
    wins = [pnl for pnl in pnls if pnl > 0.0]
    losses = [pnl for pnl in pnls if pnl < 0.0]
    signal_details = [row.get("details") for row in signals if _prefix(row.get("signal_type", "")) == strategy]
    strategy_latencies = [row for row in latencies if _prefix(row.get("signal_type", "")) == strategy]

    queue_pressures = [value for detail in signal_details if (value := _numeric(detail, "mss2_queue_pressure")) is not None]
    fill_delays = [value for detail in signal_details if (value := _numeric(detail, "mss2_expected_fill_delay_seconds")) is not None]
    wash_scores = [value for detail in signal_details if (value := _numeric(detail, "lch_wash_trading_score")) is not None]
    signal_to_confirmation = [float(row.get("duration_ms") or 0.0) for row in strategy_latencies if row.get("stage") == "signal_to_confirmation"]
    signal_to_trade = [float(row.get("duration_ms") or 0.0) for row in strategy_latencies if row.get("stage") == "signal_to_trade_recorded"]

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    net_pnl = gross_profit - gross_loss
    return StrategyPerformance(
        strategy=strategy,
        sample_size=len(pnls),
        wins=len(wins),
        losses=len(losses),
        win_rate=len(wins) / max(len(wins) + len(losses), 1),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_pnl=net_pnl,
        avg_pnl=mean(pnls) if pnls else 0.0,
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0.0 else (float("inf") if gross_profit > 0.0 else 0.0),
        avg_queue_pressure=mean(queue_pressures) if queue_pressures else 0.0,
        avg_expected_fill_delay_seconds=mean(fill_delays) if fill_delays else 0.0,
        avg_latency_signal_to_confirmation_ms=mean(signal_to_confirmation) if signal_to_confirmation else 0.0,
        avg_wash_score=mean(wash_scores) if wash_scores else 0.0,
        p95_latency_signal_to_confirmation_ms=_percentile(signal_to_confirmation, 0.95),
        p95_latency_signal_to_trade_recorded_ms=_percentile(signal_to_trade, 0.95),
    )


def _bounded_update(current: float, delta: float, lo: float, hi: float, max_adjustment_pct: float) -> float:
    adjusted = current + delta
    if current > 0:
        delta_cap = abs(current) * max_adjustment_pct
        adjusted = current + _clamp(delta, -delta_cap, delta_cap)
    return _clamp(adjusted, lo, hi)


def _build_recommendation(
    *,
    strategy: str,
    performance: StrategyPerformance,
    current_config: dict[str, Any],
    max_adjustment_pct: float,
) -> RecalibrationRecommendation | None:
    patch: dict[str, Any] = {}
    reason_parts: list[str] = []
    confidence = _clamp(0.35 + min(0.45, performance.sample_size / 100.0), 0.0, 0.95)

    if strategy == "roda":
        mode = str(current_config.get("roda_mode", "auto") or "auto").lower()
        if mode == "divergence":
            if performance.win_rate < 0.55 or performance.avg_pnl <= 0.0:
                patch["roda_divergence_min_confidence"] = _bounded_update(
                    float(current_config.get("roda_divergence_min_confidence", 0.60)),
                    0.03,
                    0.50,
                    0.90,
                    max_adjustment_pct,
                )
                patch["roda_divergence_min_edge"] = _bounded_update(
                    float(current_config.get("roda_divergence_min_edge", 0.06)),
                    0.01,
                    0.03,
                    0.15,
                    max_adjustment_pct,
                )
                patch["roda_divergence_min_sources"] = int(_bounded_update(
                    float(current_config.get("roda_divergence_min_sources", 2)),
                    1.0,
                    2.0,
                    5.0,
                    max_adjustment_pct,
                ))
                reason_parts.append("divergence signals underperforming")
            elif performance.win_rate > 0.70 and performance.avg_pnl > 0.0:
                patch["roda_divergence_min_confidence"] = _bounded_update(
                    float(current_config.get("roda_divergence_min_confidence", 0.60)),
                    -0.02,
                    0.50,
                    0.90,
                    max_adjustment_pct,
                )
                patch["roda_divergence_min_edge"] = _bounded_update(
                    float(current_config.get("roda_divergence_min_edge", 0.06)),
                    -0.005,
                    0.03,
                    0.15,
                    max_adjustment_pct,
                )
                reason_parts.append("divergence signals performing well")
        else:
            if performance.win_rate < 0.58 or performance.avg_pnl <= 0.0:
                patch["roda_min_confidence"] = _bounded_update(
                    float(current_config.get("roda_min_confidence", 0.95)),
                    0.02,
                    0.85,
                    0.99,
                    max_adjustment_pct,
                )
                patch["roda_min_sources"] = int(_bounded_update(
                    float(current_config.get("roda_min_sources", 3)),
                    1.0,
                    2.0,
                    5.0,
                    max_adjustment_pct,
                ))
                reason_parts.append("news-lag signals underperforming")
            elif performance.win_rate > 0.72 and performance.avg_pnl > 0.0:
                patch["roda_min_confidence"] = _bounded_update(
                    float(current_config.get("roda_min_confidence", 0.95)),
                    -0.01,
                    0.85,
                    0.99,
                    max_adjustment_pct,
                )
                reason_parts.append("news-lag signals performing well")

    elif strategy == "lch":
        if performance.win_rate < 0.55 or performance.avg_pnl <= 0.0 or performance.avg_wash_score > 0.72:
            patch["lch_min_z_score"] = _bounded_update(
                float(current_config.get("lch_min_z_score", 2.5)),
                0.15,
                1.5,
                5.0,
                max_adjustment_pct,
            )
            patch["lch_min_recovery_probability"] = _bounded_update(
                float(current_config.get("lch_min_recovery_probability", 0.70)),
                0.02,
                0.50,
                0.95,
                max_adjustment_pct,
            )
            patch["lch_max_wash_trading_score"] = _bounded_update(
                float(current_config.get("lch_max_wash_trading_score", 0.72)),
                -0.03,
                0.35,
                0.95,
                max_adjustment_pct,
            )
            reason_parts.append("LCH showing poor recovery or high wash score")
        elif performance.win_rate > 0.65 and performance.avg_pnl > 0.0:
            patch["lch_min_z_score"] = _bounded_update(
                float(current_config.get("lch_min_z_score", 2.5)),
                -0.10,
                1.5,
                5.0,
                max_adjustment_pct,
            )
            patch["lch_max_wash_trading_score"] = _bounded_update(
                float(current_config.get("lch_max_wash_trading_score", 0.72)),
                0.02,
                0.35,
                0.95,
                max_adjustment_pct,
            )
            reason_parts.append("LCH robust enough to relax")

    elif strategy == "mss2":
        if (
            performance.win_rate < 0.55
            or performance.avg_pnl <= 0.0
            or performance.avg_queue_pressure > 0.70
            or performance.avg_expected_fill_delay_seconds > 60.0
        ):
            patch["mss2_min_spread_bps"] = _bounded_update(
                float(current_config.get("mss2_min_spread_bps", 35.0)),
                5.0,
                20.0,
                120.0,
                max_adjustment_pct,
            )
            patch["mss2_min_expected_profit_bps"] = _bounded_update(
                float(current_config.get("mss2_min_expected_profit_bps", 35.0)),
                5.0,
                20.0,
                150.0,
                max_adjustment_pct,
            )
            patch["mss2_max_adverse_selection_score"] = _bounded_update(
                float(current_config.get("mss2_max_adverse_selection_score", 0.65)),
                -0.05,
                0.20,
                0.95,
                max_adjustment_pct,
            )
            patch["mss2_max_queue_pressure"] = _bounded_update(
                float(current_config.get("mss2_max_queue_pressure", 0.75)),
                -0.05,
                0.35,
                0.95,
                max_adjustment_pct,
            )
            reason_parts.append("MSS2 queue or fills degrading")
        elif performance.win_rate > 0.68 and performance.avg_pnl > 0.0 and performance.avg_queue_pressure < 0.45:
            patch["mss2_min_spread_bps"] = _bounded_update(
                float(current_config.get("mss2_min_spread_bps", 35.0)),
                -2.0,
                20.0,
                120.0,
                max_adjustment_pct,
            )
            patch["mss2_max_queue_pressure"] = _bounded_update(
                float(current_config.get("mss2_max_queue_pressure", 0.75)),
                0.03,
                0.35,
                0.95,
                max_adjustment_pct,
            )
            reason_parts.append("MSS2 fills and pnl are healthy")

    if not patch:
        return None

    reason = "; ".join(reason_parts) if reason_parts else "performance drift"
    return RecalibrationRecommendation(
        strategy=strategy,
        sample_size=performance.sample_size,
        reason=reason,
        confidence=confidence,
        current_config={key: current_config.get(key) for key in patch.keys()},
        proposed_patch=patch,
        performance=performance,
    )


async def run_auto_recalibration(
    *,
    window_days: int = 14,
    min_trades: int = 20,
    apply_changes: bool = False,
    max_adjustment_pct: float = 0.15,
) -> list[RecalibrationRecommendation]:
    trades, signals, latencies = await _fetch_recent_data(window_days)
    if not trades and not signals:
        return []

    by_strategy_trades: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_strategy_signals: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_strategy_latencies: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in trades:
        by_strategy_trades[_prefix(row.get("signal_type"))].append(row)
    for row in signals:
        by_strategy_signals[_prefix(row.get("signal_type"))].append(row)
    for row in latencies:
        by_strategy_latencies[_prefix(row.get("signal_type"))].append(row)

    current_config = await _load_current_config()
    recommendations: list[RecalibrationRecommendation] = []
    for strategy in ("roda", "lch", "mss2"):
        performance = _aggregate_performance(
            strategy,
            by_strategy_trades.get(strategy, []),
            by_strategy_signals.get(strategy, []),
            by_strategy_latencies.get(strategy, []),
        )
        if performance.sample_size < min_trades:
            continue
        recommendation = _build_recommendation(
            strategy=strategy,
            performance=performance,
            current_config=current_config,
            max_adjustment_pct=max_adjustment_pct,
        )
        if recommendation is None:
            continue

        if apply_changes:
            await update_bot_config(recommendation.proposed_patch)
            recommendation.applied = True
            await log_entry(
                "recalibration",
                "info",
                f"Applied {strategy} recalibration",
                recommendation.to_dict(),
            )
            await send_telegram_alert(
                "info",
                f"{strategy.upper()} recalibrated",
                f"Applied recalibration patch: {recommendation.proposed_patch}",
                recommendation.to_dict(),
            )
        else:
            await log_entry(
                "recalibration",
                "info",
                f"Suggested {strategy} recalibration",
                recommendation.to_dict(),
            )
        recommendations.append(recommendation)

    if recommendations:
        logger.info(f"Auto recalibration generated {len(recommendations)} recommendation(s)")
    return recommendations


async def _load_current_config() -> dict[str, Any]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM bot_config ORDER BY id LIMIT 1")
        return dict(row) if row else {}
