"""Hybrid strategy that combines Resolution Lag Arb confirmation with cross-market confirmation."""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from loguru import logger

from bot.analytics.engine import AnalyticsEngine


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _best_arb_match(
    roda_signal: dict,
    arb_signals: list[dict],
    markets_by_id: dict[str, dict],
) -> tuple[Optional[dict], str]:
    market_id = roda_signal["market_id"]
    direction = roda_signal.get("direction")

    same_market = [s for s in arb_signals if s.get("market_id") == market_id and s.get("direction") == direction]
    if same_market:
        return max(same_market, key=lambda s: abs(float(s.get("edge", 0.0)))), "same_market"

    roda_market = markets_by_id.get(market_id, {})
    category = str(roda_market.get("category", "") or "").strip()
    if not category:
        return None, ""

    category_matches = [
        s for s in arb_signals
        if s.get("direction") == direction
        and s.get("market_id") != market_id
        and str(markets_by_id.get(s.get("market_id"), {}).get("category", "") or "").strip() == category
    ]
    if category_matches:
        return max(category_matches, key=lambda s: abs(float(s.get("edge", 0.0)))), "category"

    return None, ""


async def detect_hybrid_signals(
    markets: list[dict],
    *,
    roda_signals: list[dict],
    arb_signals: list[dict],
    config: Optional[dict] = None,
    kelly_fraction: float = 0.25,
    total_capital: float = 1000.0,
) -> list[dict]:
    cfg = config or {}
    if not cfg.get("hybrid_enabled", True):
        return []
    if not cfg.get("roda_enabled", True):
        return []
    if not roda_signals or not arb_signals:
        return []

    markets_by_id = {str(m.get("id")): m for m in markets if m.get("id")}
    arb_by_market = defaultdict(list)
    for arb in arb_signals:
        market_id = str(arb.get("market_id") or "")
        if market_id:
            arb_by_market[market_id].append(arb)

    engine = AnalyticsEngine()
    min_edge = float(cfg.get("hybrid_min_edge", 0.02))
    max_position_pct = float(cfg.get("hybrid_max_position_pct", cfg.get("max_position_pct", 0.05)))
    size_multiplier = float(cfg.get("hybrid_size_multiplier", 0.85))

    signals: list[dict] = []
    for roda in roda_signals:
        market_id = str(roda.get("market_id") or "")
        if not market_id:
            continue

        arb_candidates = list(arb_by_market.get(market_id, []))
        if not arb_candidates:
            arb_candidates = arb_signals

        arb_match, match_type = _best_arb_match(roda, arb_candidates, markets_by_id)
        if not arb_match:
            continue

        market = markets_by_id.get(market_id)
        if not market:
            continue

        yes_price = float(market.get("market_price", roda.get("market_price", 0.5)))
        roda_model = float(roda.get("model_probability", yes_price))
        arb_model = float(arb_match.get("model_probability", yes_price))
        roda_edge = float(roda.get("edge", 0.0))
        arb_edge = float(arb_match.get("edge", 0.0))

        combined_model = _clamp(0.7 * roda_model + 0.3 * arb_model, 0.01, 0.99)
        combined_edge = combined_model - yes_price
        if abs(combined_edge) < min_edge:
            continue

        combined_confidence = _clamp(
            0.6 * float(roda.get("confidence", 0.5))
            + 0.4 * _clamp(abs(arb_edge) * 4.0, 0.0, 0.9)
            + (0.06 if match_type == "same_market" else 0.03),
            0.0,
            0.99,
        )
        if combined_confidence < 0.55:
            continue

        size = engine.calculate_kelly_size(
            combined_edge,
            combined_model,
            yes_price,
            total_capital,
            kelly_fraction,
        )
        size = min(size * size_multiplier, total_capital * max_position_pct)
        if size < 1.0:
            continue

        signals.append({
            "market_id": market_id,
            "market_question": market.get("question", roda.get("market_question", "")),
            "market_category": market.get("category", ""),
            "signal_type": "hybrid_roda_lch_cross",
            "direction": roda.get("direction", "YES"),
            "market_price": yes_price,
            "model_probability": combined_model,
            "edge": combined_edge,
            "kelly_size_usd": size,
            "confidence": combined_confidence,
            "hybrid_roda_edge": roda_edge,
            "hybrid_cross_edge": arb_edge,
            "hybrid_cross_market_id": arb_match.get("market_id"),
            "hybrid_cross_match_type": match_type,
        })

    signals.sort(key=lambda s: (s["confidence"], abs(s["edge"])), reverse=True)
    if signals:
        logger.info(f"Hybrid detected {len(signals)} opportunities")
    return signals
