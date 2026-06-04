"""Polymarket fee helpers."""
from __future__ import annotations

from typing import Any


_CATEGORY_FEE_RATES = {
    "crypto": 0.07,
    "sports": 0.03,
    "finance": 0.04,
    "politics": 0.04,
    "economics": 0.05,
    "culture": 0.05,
    "weather": 0.05,
    "other": 0.05,
    "general": 0.05,
    "mentions": 0.04,
    "tech": 0.04,
    "geopolitics": 0.0,
}


def _normalize_category(category: str | None) -> str:
    return str(category or "").strip().lower()


def resolve_market_fee_rate(market: dict[str, Any] | None = None, category: str | None = None) -> float:
    if market:
        if market.get("feesEnabled") is False or market.get("fees_enabled") is False:
            return 0.0
        for key in ("takerFeeRate", "taker_fee_rate", "feeRate", "fee_rate"):
            try:
                value = market.get(key)
                if value is not None and str(value) != "":
                    return max(0.0, float(value))
            except Exception:
                continue
        category = category or str(market.get("category") or market.get("group") or market.get("tag") or "")

    normalized = _normalize_category(category)
    if "geo" in normalized:
        return _CATEGORY_FEE_RATES["geopolitics"]
    if "sport" in normalized:
        return _CATEGORY_FEE_RATES["sports"]
    if "polit" in normalized:
        return _CATEGORY_FEE_RATES["politics"]
    if "financ" in normalized:
        return _CATEGORY_FEE_RATES["finance"]
    if "econom" in normalized:
        return _CATEGORY_FEE_RATES["economics"]
    if "tech" in normalized:
        return _CATEGORY_FEE_RATES["tech"]
    if "weather" in normalized:
        return _CATEGORY_FEE_RATES["weather"]
    if "culture" in normalized:
        return _CATEGORY_FEE_RATES["culture"]
    if "mention" in normalized:
        return _CATEGORY_FEE_RATES["mentions"]
    if "crypto" in normalized or "blockchain" in normalized:
        return _CATEGORY_FEE_RATES["crypto"]
    if not normalized:
        return _CATEGORY_FEE_RATES["other"]
    return _CATEGORY_FEE_RATES.get(normalized, _CATEGORY_FEE_RATES["other"])


def estimate_taker_fee(
    size_usd: float,
    yes_price: float,
    direction: str,
    *,
    market: dict[str, Any] | None = None,
    category: str | None = None,
    fee_rate: float | None = None,
) -> float:
    if size_usd <= 0.0 or yes_price <= 0.0:
        return 0.0

    taker_fee_rate = fee_rate if fee_rate is not None else resolve_market_fee_rate(market=market, category=category)
    if taker_fee_rate <= 0.0:
        return 0.0

    direction_norm = str(direction or "").upper()
    fee_price = (1.0 - yes_price) if direction_norm == "YES" else yes_price
    fee_price = max(0.0, min(1.0, fee_price))
    return size_usd * taker_fee_rate * fee_price

