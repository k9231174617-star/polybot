"""Database utilities for the bot — uses asyncpg for async access."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

import asyncpg
from loguru import logger

from bot.config import settings

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def log_entry(module: str, level: str, message: str, details: Optional[dict] = None):
    """Write a log entry to the database."""
    try:
        pool = await get_pool()
        import json
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO log_entries (level, module, message, details, created_at)
                   VALUES ($1, $2, $3, $4, NOW())""",
                level, module, message,
                json.dumps(details) if details else None
            )
    except Exception as e:
        logger.error(f"Failed to write log to DB: {e}")


async def update_bot_state(state: str, markets_scanned: Optional[int] = None,
                            error_message: Optional[str] = None, pid: Optional[int] = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT id FROM bot_state LIMIT 1")
        if existing:
            sets = ["state = $1", "updated_at = NOW()"]
            vals: list[Any] = [state]
            idx = 2
            if markets_scanned is not None:
                sets.append(f"markets_scanned = ${idx}")
                vals.append(markets_scanned)
                idx += 1
            if error_message is not None:
                sets.append(f"error_message = ${idx}")
                vals.append(error_message)
                idx += 1
            if pid is not None:
                sets.append(f"pid = ${idx}")
                vals.append(pid)
                idx += 1
            if state == "running":
                sets.append("started_at = NOW()")
            await conn.execute(
                f"UPDATE bot_state SET {', '.join(sets)} WHERE id = ${ idx }",
                *vals, existing["id"]
            )
        else:
            await conn.execute(
                """INSERT INTO bot_state (state, started_at, markets_scanned, error_message, pid, updated_at)
                   VALUES ($1, CASE WHEN $1='running' THEN NOW() ELSE NULL END, $2, $3, $4, NOW())""",
                state, markets_scanned or 0, error_message, pid
            )


async def upsert_market(market: dict):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO markets (id, question, category, market_price, model_probability, edge,
                                 volume_24h, liquidity_usd, end_date, status, last_updated)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
            ON CONFLICT (id) DO UPDATE SET
                market_price = EXCLUDED.market_price,
                model_probability = EXCLUDED.model_probability,
                edge = EXCLUDED.edge,
                volume_24h = EXCLUDED.volume_24h,
                liquidity_usd = EXCLUDED.liquidity_usd,
                status = EXCLUDED.status,
                last_updated = NOW()
        """,
            market["id"], market["question"], market.get("category", ""),
            market["market_price"], market.get("model_probability"),
            market.get("edge"), market.get("volume_24h", 0),
            market.get("liquidity_usd", 0), market.get("end_date"),
            market.get("status", "active")
        )


async def insert_signal(signal: dict) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO signals (market_id, market_question, signal_type, direction,
                                  market_price, model_probability, edge, kelly_size_usd,
                                  confidence, status, detected_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending', NOW())
            RETURNING id
        """,
            signal["market_id"], signal["market_question"], signal["signal_type"],
            signal["direction"], signal["market_price"], signal["model_probability"],
            signal["edge"], signal["kelly_size_usd"], signal.get("confidence", 0.5)
        )
        return row["id"]


async def insert_trade(trade: dict) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            INSERT INTO trades (market_id, market_question, side, action, size_usd, price,
                                 slippage, fee_usd, realized_pnl, tx_hash, executed_at, order_type)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), $11)
            RETURNING id
        """,
            trade["market_id"], trade["market_question"], trade["side"], trade["action"],
            trade["size_usd"], trade["price"], trade.get("slippage", 0),
            trade.get("fee_usd", 0), trade.get("realized_pnl"),
            trade.get("tx_hash"), trade.get("order_type", "market")
        )
        return row["id"]


async def get_bot_config() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM bot_config LIMIT 1")
        if not row:
            return {
                "edge_threshold": 0.05,
                "max_position_pct": 0.05,
                "daily_loss_limit_pct": 0.03,
                "kelly_fraction": 0.25,
                "scan_interval_seconds": 30,
                "use_limit_orders": True,
                "min_liquidity_usd": 1000,
                "max_correlated_exposure_pct": 0.15,
            }
        return dict(row)


async def snapshot_pnl(cumulative_pnl: float, portfolio_value: float):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO pnl_snapshots (cumulative_pnl, portfolio_value, created_at) VALUES ($1, $2, NOW())",
            cumulative_pnl, portfolio_value
        )
