"""Polymarket API client — fetches markets, prices, and order books."""
import asyncio
from typing import Optional
from datetime import datetime, timezone

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from bot.config import settings

GAMMA_API = settings.polymarket_api_url
CLOB_API = settings.polymarket_clob_url


class PolymarketClient:
    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={"Accept": "application/json"},
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("Client not initialized — use async context manager")
        return self._client

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_active_markets(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """Fetch active markets from Gamma API."""
        try:
            r = await self.client.get(
                f"{GAMMA_API}/markets",
                params={
                    "active": "true",
                    "closed": "false",
                    "limit": limit,
                    "offset": offset,
                    "order": "volume24hr",
                    "ascending": "false",
                }
            )
            r.raise_for_status()
            data = r.json()
            markets = data if isinstance(data, list) else data.get("markets", [])
            return markets
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching markets: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching markets: {e}")
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_market(self, market_id: str) -> Optional[dict]:
        """Fetch a single market by ID."""
        try:
            r = await self.client.get(f"{GAMMA_API}/markets/{market_id}")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"Error fetching market {market_id}: {e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_clob_orderbook(self, token_id: str) -> Optional[dict]:
        """Fetch order book from CLOB API."""
        try:
            r = await self.client.get(
                f"{CLOB_API}/book",
                params={"token_id": token_id}
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.warning(f"Error fetching orderbook for {token_id}: {e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_trades(self, market_id: str, limit: int = 50) -> list[dict]:
        """Fetch recent trades for a market."""
        try:
            r = await self.client.get(
                f"{GAMMA_API}/trades",
                params={"market": market_id, "limit": limit}
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.warning(f"Error fetching trades for {market_id}: {e}")
            return []

    def parse_market(self, raw: dict) -> dict:
        """Normalize raw Gamma API market into internal format."""
        tokens = raw.get("tokens", [])
        yes_token = next((t for t in tokens if t.get("outcome", "").upper() == "YES"), None)
        yes_price = float(yes_token.get("price", 0.5)) if yes_token else 0.5

        volume_24h = float(raw.get("volume24hr", raw.get("volumeClob", 0)) or 0)
        liquidity = float(raw.get("liquidityClob", raw.get("liquidity", 0)) or 0)

        end_date = None
        if raw.get("endDate"):
            try:
                end_date = datetime.fromisoformat(raw["endDate"].replace("Z", "+00:00"))
                # Store UTC as naive so asyncpg can bind it to TIMESTAMP columns.
                if end_date.tzinfo is not None:
                    end_date = end_date.astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                pass

        return {
            "id": raw.get("id", raw.get("conditionId", "")),
            "question": raw.get("question", ""),
            "category": raw.get("groupItemTagline", raw.get("category", "")),
            "market_price": yes_price,
            "volume_24h": volume_24h,
            "liquidity_usd": liquidity,
            "end_date": end_date,
            "status": "active" if raw.get("active") else "resolved",
            "tokens": tokens,
        }
