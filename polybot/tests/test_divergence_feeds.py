from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from bot.data.divergence import fetch_divergence_feeds


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None, params=None):
        self.calls.append({"url": url, "params": params or {}})
        if "manifold" in url:
            return _FakeResponse([
                {
                    "question": "Will OpenAI release GPT-6?",
                    "probability": 0.76,
                    "confidence": 0.88,
                    "updatedTime": 1717500000000,
                },
                {
                    "question": "Will something else happen?",
                    "probability": 0.12,
                },
            ])
        if "kalshi" in url:
            return _FakeResponse({
                "markets": [
                    {
                        "title": "Will OpenAI release GPT-6?",
                        "yes_bid_dollars": 0.71,
                        "event_ticker": "AIOPEN",
                        "volume_fp": 1000,
                    }
                ]
            })
        raise AssertionError(f"Unexpected URL: {url}")


class DivergenceFeedTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_feeds_match_by_market_question(self) -> None:
        markets = [
            {"id": "m1", "question": "Will OpenAI release GPT-6?"},
            {"id": "m2", "question": "Will Anthropic release Claude Opus 5?"},
        ]
        feeds = [
            {"source": "manifold", "provider": "manifold", "min_similarity": 0.2},
            {"source": "kalshi", "provider": "kalshi", "status": "open", "min_similarity": 0.2},
        ]
        with patch("bot.data.divergence.httpx.AsyncClient", _FakeAsyncClient):
            quote_map = await fetch_divergence_feeds(feeds, markets=markets)

        self.assertIn("m1", quote_map)
        self.assertTrue(any(quote["source"] == "manifold" for quote in quote_map["m1"]))
        self.assertTrue(any(quote["source"] == "kalshi" for quote in quote_map["m1"]))
        self.assertNotIn("m2", quote_map)


if __name__ == "__main__":
    unittest.main()
