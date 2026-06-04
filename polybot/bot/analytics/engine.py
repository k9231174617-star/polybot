"""Analytics Engine — fair probability + edge + Kelly for each market.

Integrates: historical calibration, sentiment, cross-market arb, dynamic Kelly.
"""
import math
from typing import Optional

from bot.analytics.calibration import get_calibration


class AnalyticsEngine:
    def __init__(self, edge_threshold: float = 0.05):
        self.edge_threshold = edge_threshold

    def calculate_fair_probability(
        self, market: dict, orderbook: Optional[dict] = None, sentiment_score: float = 0.0,
    ) -> Optional[float]:
        """
        Layers:
        1. Market price as prior
        2. Liquidity adjustment (low liq → widen to 50%)
        3. Orderbook mid-price signal
        4. Sentiment shift (±5% max)
        5. Historical calibration blend
        """
        mp = market.get("market_price", 0.5)
        if mp <= 0 or mp >= 1:
            return None

        prob = mp

        liquidity = market.get("liquidity_usd", 0)
        if liquidity < 500:
            unc = min(0.10, 500 / max(liquidity, 1) * 0.01)
            prob += unc * (0.5 - prob)

        if orderbook:
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])
            if bids and asks:
                try:
                    mid = (float(bids[0]["price"]) + float(asks[0]["price"])) / 2
                    prob = 0.7 * prob + 0.3 * mid
                except (KeyError, ValueError, IndexError):
                    pass

        if sentiment_score != 0.0:
            prob = prob + sentiment_score * 0.05

        prob = max(0.01, min(0.99, prob))
        return get_calibration().adjust(prob)

    def calculate_edge(self, market_price: float, model_prob: float) -> float:
        return model_prob - market_price

    def calculate_kelly_size(
        self, edge: float, model_prob: float, market_price: float,
        total_capital: float, kelly_fraction: float = 0.25,
    ) -> float:
        if model_prob <= 0 or market_price <= 0 or market_price >= 1:
            return 0.0

        if edge > 0:
            b = (1 - market_price) / market_price
            p, q = model_prob, 1 - model_prob
        else:
            b = market_price / (1 - market_price)
            p, q = 1 - model_prob, model_prob

        if b <= 0:
            return 0.0

        full_kelly = (b * p - q) / b
        return max(0.0, full_kelly) * kelly_fraction * total_capital

    def detect_signal_type(self, market: dict, edge: float, sentiment: float = 0.0) -> str:
        if abs(sentiment) > 0.3:
            return "sentiment_lag"
        if abs(edge) > 0.15:
            return "price_discrepancy"
        if market.get("volume_24h", 0) > 50000 and abs(edge) > 0.05:
            return "momentum"
        if market.get("liquidity_usd", 0) < 2000:
            return "implied_prob"
        return "price_discrepancy"

    def calculate_confidence(self, edge: float, liquidity: float, volume: float, sentiment: float = 0.0) -> float:
        e = min(1.0, abs(edge) / 0.20)
        l = min(1.0, math.log1p(liquidity) / math.log1p(100_000))
        v = min(1.0, math.log1p(volume) / math.log1p(500_000))
        s = min(1.0, abs(sentiment))
        return 0.35 * e + 0.30 * l + 0.20 * v + 0.15 * s

    def analyze_market(
        self,
        market: dict,
        orderbook: Optional[dict] = None,
        config: Optional[dict] = None,
        sentiment_score: float = 0.0,
        kelly_fraction_override: Optional[float] = None,
    ) -> Optional[dict]:
        cfg = config or {}
        edge_threshold = cfg.get("edge_threshold", self.edge_threshold)
        kelly_fraction = kelly_fraction_override or cfg.get("kelly_fraction", 0.25)
        max_position_pct = cfg.get("max_position_pct", 0.05)
        total_capital = cfg.get("total_capital", 1000.0)
        min_liquidity = cfg.get("min_liquidity_usd", 1000.0)

        mp = market.get("market_price")
        if mp is None or market.get("liquidity_usd", 0) < min_liquidity:
            return None

        model_prob = self.calculate_fair_probability(market, orderbook, sentiment_score)
        if model_prob is None:
            return None

        edge = self.calculate_edge(mp, model_prob)
        market["model_probability"] = model_prob
        market["edge"] = edge
        market["sentiment_score"] = sentiment_score

        if abs(edge) < edge_threshold:
            return None

        direction = "YES" if edge > 0 else "NO"
        kelly_size = min(
            self.calculate_kelly_size(edge, model_prob, mp, total_capital, kelly_fraction),
            total_capital * max_position_pct,
        )
        if kelly_size < 1.0:
            return None

        liquidity = market.get("liquidity_usd", 0)
        volume = market.get("volume_24h", 0)

        return {
            "market_id": market["id"],
            "market_question": market.get("question", ""),
            "signal_type": self.detect_signal_type(market, edge, sentiment_score),
            "direction": direction,
            "market_price": mp,
            "model_probability": model_prob,
            "edge": edge,
            "kelly_size_usd": kelly_size,
            "confidence": self.calculate_confidence(edge, liquidity, volume, sentiment_score),
        }
