from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import BacktestSnapshot


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("Snapshot timestamp is required")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ensure_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_markets(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [m for m in raw if isinstance(m, dict)]
    return []


def _normalize_datetime_field(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return _parse_datetime(value)
        except Exception:
            return value
    return value


def _normalize_market(market: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(market)
    if "end_date" in normalized:
        normalized["end_date"] = _normalize_datetime_field(normalized["end_date"])
    if "endDate" in normalized:
        normalized["endDate"] = _normalize_datetime_field(normalized["endDate"])
    if "market_price" in normalized:
        try:
            normalized["market_price"] = float(normalized["market_price"])
        except Exception:
            pass
    if "volume_24h" in normalized:
        try:
            normalized["volume_24h"] = float(normalized["volume_24h"])
        except Exception:
            pass
    return normalized


def _normalize_article(article: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(article)
    if "published_at" in normalized:
        normalized["published_at"] = _normalize_datetime_field(normalized["published_at"])
    if "publishedAt" in normalized:
        normalized["publishedAt"] = _normalize_datetime_field(normalized["publishedAt"])
    return normalized


def _normalize_trade(trade: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(trade)
    for key in ("timestamp", "createdAt", "created_at", "time", "executed_at", "executedAt"):
        if key in normalized:
            normalized[key] = _normalize_datetime_field(normalized[key])
    return normalized


def _normalize_snapshot(raw: dict[str, Any]) -> BacktestSnapshot:
    markets = _normalize_markets(raw.get("markets") or raw.get("market") or raw.get("data"))
    news_by_market = _ensure_mapping(raw.get("news_by_market") or raw.get("news") or {})
    trades_by_market = _ensure_mapping(raw.get("trades_by_market") or raw.get("trades") or {})
    orderbooks_by_token = _ensure_mapping(raw.get("orderbooks_by_token") or raw.get("orderbooks") or {})
    metadata = _ensure_mapping(raw.get("metadata") or raw.get("meta") or {})
    return BacktestSnapshot(
        timestamp=_parse_datetime(raw.get("timestamp") or raw.get("ts") or raw.get("time")),
        markets=[_normalize_market(m) for m in markets],
        news_by_market={str(k): [_normalize_article(item) for item in v if isinstance(item, dict)] for k, v in news_by_market.items() if isinstance(v, list)},
        trades_by_market={str(k): [_normalize_trade(item) for item in v if isinstance(item, dict)] for k, v in trades_by_market.items() if isinstance(v, list)},
        orderbooks_by_token={str(k): v for k, v in orderbooks_by_token.items() if isinstance(v, dict)},
        metadata=metadata,
    )


def load_backtest_snapshots(path: str | Path) -> list[BacktestSnapshot]:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)

    text = source.read_text(encoding="utf-8").strip()
    if not text:
        return []

    snapshots: list[BacktestSnapshot] = []
    if text.startswith("["):
        payload = json.loads(text)
        if not isinstance(payload, list):
            raise ValueError("JSON backtest input must be a list of snapshots")
        snapshots = [_normalize_snapshot(item) for item in payload if isinstance(item, dict)]
    else:
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                snapshots.append(_normalize_snapshot(payload))

    snapshots.sort(key=lambda s: s.timestamp)
    return snapshots


def iter_backtest_snapshots(path: str | Path) -> Iterable[BacktestSnapshot]:
    yield from load_backtest_snapshots(path)
