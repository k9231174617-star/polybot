"""
Cross-market arbitrage detector.

1. YES/NO complement arb: p(YES) + p(NO) should ≈ 1. Deviations > threshold = arb.
2. Mutually-exclusive group arb: outcome probabilities in an event group should sum ≤ 1.
"""
from typing import Optional
from loguru import logger

_MIN_SPREAD = 0.03


def detect_yes_no_arb(market: dict) -> Optional[dict]:
    yes_price = market.get("market_price")
    no_price = market.get("no_price")
    if yes_price is None or no_price is None:
        return None
    spread = abs((yes_price + no_price) - 1.0)
    if spread < _MIN_SPREAD:
        return None
    if yes_price < (1 - no_price):
        direction, edge = "YES", (1 - no_price) - yes_price
    else:
        direction, edge = "NO", (1 - yes_price) - no_price
    return {
        "market_id": market["id"],
        "market_question": market.get("question", ""),
        "signal_type": "cross_market_arb",
        "direction": direction,
        "market_price": yes_price,
        "model_probability": yes_price + edge if direction == "YES" else yes_price - edge,
        "edge": edge,
    }


def detect_group_arb(group: list[dict]) -> list[dict]:
    if len(group) < 2:
        return []
    prices = [(m, m.get("market_price", 0.5)) for m in group]
    total = sum(p for _, p in prices)
    if total <= 1.0 + _MIN_SPREAD:
        return []
    cheapest_m, cheapest_p = min(prices, key=lambda x: x[1])
    edge = (1.0 / len(group)) - cheapest_p
    if edge < _MIN_SPREAD:
        return []
    logger.info(f"Group arb: {len(group)} markets sum={total:.3f} edge={edge:.3f}")
    return [{
        "market_id": cheapest_m["id"],
        "market_question": cheapest_m.get("question", ""),
        "signal_type": "cross_market_arb",
        "direction": "YES",
        "market_price": cheapest_p,
        "model_probability": cheapest_p + edge,
        "edge": edge,
    }]


def find_all_arb_signals(markets: list[dict], total_capital: float = 1000.0) -> list[dict]:
    signals = []
    for m in markets:
        s = detect_yes_no_arb(m)
        if s:
            signals.append(s)
    groups: dict[str, list[dict]] = {}
    for m in markets:
        cat = m.get("category", "")
        if cat:
            groups.setdefault(cat, []).append(m)
    for group in groups.values():
        if len(group) >= 3:
            signals.extend(detect_group_arb(group))
    return signals
