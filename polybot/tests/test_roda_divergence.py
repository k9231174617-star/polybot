from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.analytics.roda import detect_roda_signals


class RodaDivergenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_roda_detects_cross_platform_divergence(self) -> None:
        now = datetime(2026, 6, 4, 12, tzinfo=timezone.utc)
        markets = [{
            "id": "m1",
            "question": "Will X happen?",
            "category": "politics",
            "market_price": 0.52,
            "status": "active",
            "end_date": datetime(2026, 6, 4, 11, tzinfo=timezone.utc),
        }]
        divergence_sources = {
            "m1": [
                {"source": "Kalshi", "probability": 0.74, "confidence": 0.9},
                {"source": "Manifold", "probability": 0.70, "confidence": 0.8},
            ]
        }
        signals = await detect_roda_signals(
            markets,
            config={
                "roda_enabled": True,
                "roda_mode": "divergence",
                "roda_divergence_min_edge": 0.10,
                "roda_divergence_min_confidence": 0.10,
                "roda_divergence_min_sources": 2,
            },
            divergence_sources_by_market=divergence_sources,
            now=now,
            kelly_fraction=0.25,
            total_capital=1000.0,
        )
        self.assertTrue(any(signal["signal_type"] == "roda_divergence" for signal in signals))


if __name__ == "__main__":
    unittest.main()
