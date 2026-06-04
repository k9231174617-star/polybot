"""Latency profiling helpers for the signal -> decision -> execution pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Iterable


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def duration_ms(started_at: datetime | None, finished_at: datetime | None) -> float | None:
    if started_at is None or finished_at is None:
        return None
    start = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
    finish = finished_at if finished_at.tzinfo else finished_at.replace(tzinfo=timezone.utc)
    return max(0.0, (finish - start).total_seconds() * 1000.0)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    if low == high:
        return ordered[low]
    frac = rank - low
    return ordered[low] * (1.0 - frac) + ordered[high] * frac


@dataclass(slots=True)
class LatencySummary:
    count: int
    average_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "count": self.count,
            "average_ms": self.average_ms,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
        }


@dataclass(slots=True)
class LatencyEvent:
    signal_id: int | None
    market_id: str
    signal_type: str
    stage: str
    duration_ms: float
    started_at: datetime
    finished_at: datetime
    details: dict[str, Any] | None = None


def summarize(values: Iterable[float]) -> LatencySummary:
    samples = [float(value) for value in values if value is not None and value >= 0]
    if not samples:
        return LatencySummary(count=0, average_ms=0.0, p50_ms=0.0, p95_ms=0.0, p99_ms=0.0)
    return LatencySummary(
        count=len(samples),
        average_ms=mean(samples),
        p50_ms=_percentile(samples, 0.50),
        p95_ms=_percentile(samples, 0.95),
        p99_ms=_percentile(samples, 0.99),
    )


def summarize_by_stage(events: Iterable[LatencyEvent]) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[float]] = {}
    for event in events:
        grouped.setdefault(event.stage, []).append(event.duration_ms)
    return {stage: summarize(values).to_dict() for stage, values in grouped.items()}


def summarize_by_signal_type(events: Iterable[LatencyEvent]) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[float]] = {}
    for event in events:
        grouped.setdefault(event.signal_type, []).append(event.duration_ms)
    return {signal_type: summarize(values).to_dict() for signal_type, values in grouped.items()}
