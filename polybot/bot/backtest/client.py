from __future__ import annotations

from typing import Any

from .models import BacktestSnapshot


class SnapshotMarketClient:
    def __init__(self) -> None:
        self._snapshot: BacktestSnapshot | None = None
        self._token_to_market: dict[str, str] = {}

    def set_snapshot(self, snapshot: BacktestSnapshot) -> None:
        self._snapshot = snapshot
        token_to_market: dict[str, str] = {}
        for market in snapshot.markets:
            market_id = str(market.get("id") or "")
            for token in market.get("tokens") or []:
                token_id = str(token.get("token_id") or token.get("tokenId") or token.get("id") or "")
                if token_id and market_id:
                    token_to_market[token_id] = market_id
        self._token_to_market = token_to_market

    async def get_clob_orderbook(self, token_id: str) -> dict[str, Any] | None:
        if not self._snapshot:
            return None
        book = self._snapshot.orderbooks_by_token.get(str(token_id))
        if book is not None:
            return book
        market_id = self._token_to_market.get(str(token_id))
        if not market_id:
            return None
        market = next((m for m in self._snapshot.markets if str(m.get("id") or "") == market_id), None)
        if not market:
            return None
        return market.get("orderbook")

    async def get_trades(self, market_id: str, limit: int = 50) -> list[dict[str, Any]]:
        if not self._snapshot:
            return []
        trades = self._snapshot.trades_by_market.get(str(market_id), [])
        return list(trades)[-limit:] if limit > 0 else list(trades)
