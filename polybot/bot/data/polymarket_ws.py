"""Polymarket market websocket cache with REST fallback."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Deque, Optional

import websockets
from loguru import logger

from bot.data.polymarket import PolymarketClient


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _normalize_levels(levels: Any) -> list[dict[str, float]]:
    normalized: list[dict[str, float]] = []
    if not isinstance(levels, list):
        return normalized
    for level in levels:
        try:
            if isinstance(level, dict):
                price = _as_float(level.get("price") or level.get("p") or level.get("rate"))
                size = _as_float(level.get("size") or level.get("quantity") or level.get("qty") or level.get("amount"))
            elif isinstance(level, (list, tuple)) and len(level) >= 2:
                price = _as_float(level[0])
                size = _as_float(level[1])
            else:
                continue
            if price > 0.0 and size > 0.0:
                normalized.append({"price": price, "size": size})
        except Exception:
            continue
    return normalized


def _extract_market_id(data: dict[str, Any]) -> str:
    for key in ("market_id", "marketId", "market", "condition_id", "conditionId"):
        value = data.get(key)
        if value:
            return str(value)
    return ""


def _extract_token_id(data: dict[str, Any]) -> str:
    for key in ("asset_id", "assetId", "token_id", "tokenId", "token_id".upper()):
        value = data.get(key)
        if value:
            return str(value)
    return ""


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        ts = value
    elif isinstance(value, str):
        try:
            ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            ts = datetime.now(timezone.utc)
    else:
        ts = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _normalize_trade(raw: dict[str, Any], market_id: str) -> dict[str, Any]:
    ts = _parse_timestamp(
        raw.get("createdAt")
        or raw.get("created_at")
        or raw.get("timestamp")
        or raw.get("time")
        or raw.get("executedAt")
        or raw.get("executed_at")
    )
    return {
        "market_id": market_id,
        "asset_id": _extract_token_id(raw),
        "price": _as_float(raw.get("price") or raw.get("trade_price") or raw.get("last_trade_price")),
        "size": _as_float(raw.get("size") or raw.get("quantity") or raw.get("amount") or raw.get("trade_size")),
        "wallet": str(raw.get("wallet") or raw.get("trader") or raw.get("address") or ""),
        "side": str(raw.get("side") or raw.get("taker_side") or raw.get("direction") or "").upper(),
        "timestamp": ts,
        "raw": raw,
    }


def _synthetic_levels(best_bid: Any = None, best_ask: Any = None) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
    bids: list[dict[str, float]] = []
    asks: list[dict[str, float]] = []
    bid_price = _as_float(best_bid, 0.0)
    ask_price = _as_float(best_ask, 0.0)
    if bid_price > 0.0:
        bids.append({"price": bid_price, "size": 1.0})
    if ask_price > 0.0:
        asks.append({"price": ask_price, "size": 1.0})
    return bids, asks


class PolymarketMarketStream:
    """Public market websocket cache with REST fallback."""

    def __init__(self, ws_url: str | None = None) -> None:
        self.ws_url = ws_url or "wss://ws-subscriptions-clob.polymarket.com/ws/market"
        self._stop_event = asyncio.Event()
        self._send_lock = asyncio.Lock()
        self._ws: Any | None = None
        self._watchlist_tokens: set[str] = set()
        self._token_to_market: dict[str, str] = {}
        self._market_to_tokens: dict[str, set[str]] = defaultdict(set)
        self._books_by_token: dict[str, dict[str, Any]] = {}
        self._trades_by_market: dict[str, Deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=200))
        self._last_update = datetime.now(timezone.utc)
        self._subscription_sent = False

    async def stop(self) -> None:
        self._stop_event.set()
        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                await ws.close()
            except Exception as exc:
                logger.debug(f"WS close failed during stop: {exc}")

    async def update_watchlist(self, markets: list[dict]) -> None:
        tokens: set[str] = set()
        token_to_market: dict[str, str] = {}
        market_to_tokens: dict[str, set[str]] = defaultdict(set)
        for market in markets:
            market_id = str(market.get("id") or "")
            for token in market.get("tokens") or []:
                token_id = str(token.get("token_id") or token.get("tokenId") or token.get("id") or "")
                if not token_id or not market_id:
                    continue
                tokens.add(token_id)
                token_to_market[token_id] = market_id
                market_to_tokens[market_id].add(token_id)

        if tokens == self._watchlist_tokens:
            return

        self._watchlist_tokens = tokens
        self._token_to_market = token_to_market
        self._market_to_tokens = market_to_tokens
        self._last_update = datetime.now(timezone.utc)
        await self._send_subscription()

    async def run(self) -> None:
        backoff = 5
        while not self._stop_event.is_set():
            try:
                await self._connect_and_listen()
                backoff = 5
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"Polymarket WS error: {exc}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _connect_and_listen(self) -> None:
        async with websockets.connect(
            self.ws_url,
            ping_interval=None,
            close_timeout=5,
            max_queue=512,
        ) as ws:
            self._ws = ws
            self._subscription_sent = False
            heartbeat_task = asyncio.create_task(self._heartbeat())
            try:
                await self._send_subscription()
                logger.info("Polymarket market websocket connected")
                async for raw in ws:
                    if self._stop_event.is_set():
                        break
                    await self._handle_message(raw)
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except BaseException:
                    pass
        self._ws = None

    async def _send_subscription(self) -> None:
        if self._ws is None or not self._watchlist_tokens:
            return
        payload = {
            "type": "market",
            "assets_ids": sorted(self._watchlist_tokens),
            "custom_feature_enabled": True,
        }
        if self._subscription_sent:
            payload["operation"] = "subscribe"
        async with self._send_lock:
            try:
                await self._ws.send(json.dumps(payload))
                self._subscription_sent = True
            except Exception as exc:
                logger.debug(f"WS subscribe failed: {exc}")

    async def _handle_message(self, raw: Any) -> None:
        text = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
        if text in {"PONG", "pong"}:
            return
        if text in {"PING", "ping"}:
            async with self._send_lock:
                if self._ws is not None:
                    try:
                        await self._ws.send("pong")
                    except Exception as exc:
                        logger.debug(f"WS pong send failed: {exc}")
            return
        try:
            data = json.loads(text)
        except Exception:
            logger.debug(f"Unparsed WS payload: {text[:200]}")
            return

        event_type = str(
            data.get("event_type")
            or data.get("type")
            or data.get("event")
            or data.get("message_type")
            or data.get("channel")
            or ""
        ).lower()

        if event_type == "book":
            self._handle_book(data)
        elif event_type in {"price_change", "best_bid_ask", "tick_size_change", "market_resolved", "new_market"}:
            self._handle_market_update(data)
        elif event_type == "last_trade_price":
            self._handle_last_trade_price(data)
        elif event_type == "trade":
            self._handle_trade(data)
        else:
            # Some payloads are shaped like events but do not declare a canonical type.
            if data.get("bids") or data.get("asks"):
                self._handle_book(data)
            elif data.get("price") is not None and (data.get("size") is not None or data.get("quantity") is not None):
                self._handle_trade(data)

    async def _heartbeat(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(10)
            if self._ws is None:
                continue
            async with self._send_lock:
                try:
                    await self._ws.send("PING")
                except Exception as exc:
                    logger.debug(f"WS heartbeat failed: {exc}")

    def _handle_book(self, data: dict[str, Any]) -> None:
        token_id = _extract_token_id(data)
        market_id = _extract_market_id(data) or self._token_to_market.get(token_id, "")
        if not token_id and not market_id:
            return

        book = {
            "market_id": market_id,
            "token_id": token_id,
            "bids": _normalize_levels(data.get("bids") or data.get("yes_bids") or data.get("buy_levels")),
            "asks": _normalize_levels(data.get("asks") or data.get("yes_asks") or data.get("sell_levels")),
            "last_trade_price": _as_float(data.get("last_trade_price") or data.get("lastTradePrice") or data.get("price")),
            "timestamp": _parse_timestamp(data.get("timestamp") or data.get("updated_at") or data.get("updatedAt")),
            "raw": data,
            "source": "websocket",
        }
        if not book["bids"] and not book["asks"]:
            best_bid = data.get("best_bid") or data.get("bestBid") or data.get("best_bid_price")
            best_ask = data.get("best_ask") or data.get("bestAsk") or data.get("best_ask_price")
            bids, asks = _synthetic_levels(best_bid, best_ask)
            if bids:
                book["bids"] = bids
            if asks:
                book["asks"] = asks

        if token_id:
            self._books_by_token[token_id] = book
        if market_id and token_id:
            self._token_to_market[token_id] = market_id
            self._market_to_tokens[market_id].add(token_id)

    def _handle_market_update(self, data: dict[str, Any]) -> None:
        token_id = _extract_token_id(data)
        if not token_id:
            return
        if token_id not in self._books_by_token:
            self._books_by_token[token_id] = {
                "market_id": self._token_to_market.get(token_id, _extract_market_id(data)),
                "token_id": token_id,
                "bids": [],
                "asks": [],
                "last_trade_price": 0.0,
                "timestamp": datetime.now(timezone.utc),
                "raw": data,
                "source": "websocket",
            }
        book = dict(self._books_by_token[token_id])
        if data.get("last_trade_price") is not None or data.get("price") is not None:
            book["last_trade_price"] = _as_float(data.get("last_trade_price") or data.get("price"), book.get("last_trade_price", 0.0))
        if data.get("bids") or data.get("asks"):
            if data.get("bids"):
                book["bids"] = _normalize_levels(data.get("bids"))
            if data.get("asks"):
                book["asks"] = _normalize_levels(data.get("asks"))
        if data.get("best_bid") is not None or data.get("best_ask") is not None:
            bids, asks = _synthetic_levels(data.get("best_bid"), data.get("best_ask"))
            if bids:
                book["bids"] = bids
            if asks:
                book["asks"] = asks
        book["timestamp"] = _parse_timestamp(data.get("timestamp") or data.get("updated_at") or data.get("updatedAt"))
        book["raw"] = data
        self._books_by_token[token_id] = book

    def _handle_last_trade_price(self, data: dict[str, Any]) -> None:
        token_id = _extract_token_id(data)
        if token_id and token_id in self._books_by_token:
            book = dict(self._books_by_token[token_id])
            book["last_trade_price"] = _as_float(data.get("price") or data.get("last_trade_price"), book.get("last_trade_price", 0.0))
            book["timestamp"] = _parse_timestamp(data.get("timestamp") or data.get("updated_at") or data.get("updatedAt"))
            book["raw"] = data
            self._books_by_token[token_id] = book

    def _handle_trade(self, data: dict[str, Any]) -> None:
        market_id = _extract_market_id(data)
        token_id = _extract_token_id(data)
        if not market_id and token_id:
            market_id = self._token_to_market.get(token_id, "")
        if not market_id and not token_id:
            return

        trade = _normalize_trade(data, market_id)
        if market_id:
            cache = self._trades_by_market[market_id]
            cache.append(trade)
            self._trades_by_market[market_id] = deque(sorted(cache, key=lambda item: item["timestamp"]), maxlen=200)

        if token_id and market_id:
            self._token_to_market[token_id] = market_id
            self._market_to_tokens[market_id].add(token_id)

    async def get_clob_orderbook(self, token_id: str) -> Optional[dict]:
        cached = self._books_by_token.get(token_id)
        if cached:
            return {
                "bids": list(cached.get("bids", [])),
                "asks": list(cached.get("asks", [])),
                "market_id": cached.get("market_id", ""),
                "token_id": token_id,
                "last_trade_price": cached.get("last_trade_price", 0.0),
                "timestamp": cached.get("timestamp"),
                "source": cached.get("source", "websocket"),
            }

        async with PolymarketClient() as client:
            book = await client.get_clob_orderbook(token_id)
        if book:
            normalized = {
                "market_id": self._token_to_market.get(token_id, ""),
                "token_id": token_id,
                "bids": _normalize_levels(book.get("bids")),
                "asks": _normalize_levels(book.get("asks")),
                "last_trade_price": _as_float(book.get("last_trade_price") or book.get("price")),
                "timestamp": datetime.now(timezone.utc),
                "raw": book,
                "source": "rest",
            }
            self._books_by_token[token_id] = normalized
            return normalized
        return None

    async def get_trades(self, market_id: str, limit: int = 50) -> list[dict]:
        cached = list(self._trades_by_market.get(market_id, deque()))
        if len(cached) >= max(5, min(limit, 50) // 2):
            return cached[-limit:]

        async with PolymarketClient() as client:
            trades = await client.get_trades(market_id, limit=limit)
        normalized = [_normalize_trade(trade if isinstance(trade, dict) else {}, market_id) for trade in trades or []]
        if normalized:
            cache = self._trades_by_market[market_id]
            for trade in normalized:
                cache.append(trade)
            self._trades_by_market[market_id] = deque(sorted(cache, key=lambda item: item["timestamp"]), maxlen=200)
        return normalized or cached[-limit:]
