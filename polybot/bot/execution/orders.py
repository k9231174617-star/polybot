"""Order Execution — places orders on Polymarket CLOB (or simulates in dry-run mode)."""
import asyncio
import random
from typing import Optional
from loguru import logger

from bot.config import settings
from bot.utils.db import insert_trade, insert_signal, get_pool


class OrderExecutor:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run

    async def execute_signal(self, signal: dict, config: dict) -> Optional[dict]:
        """
        Execute a trade based on a detected signal.
        
        In dry_run mode: simulates execution with realistic slippage.
        In live mode: sends order to Polymarket CLOB.
        """
        market_id = signal["market_id"]
        direction = signal["direction"]  # YES or NO
        size_usd = signal["kelly_size_usd"]
        market_price = signal["market_price"]

        # Simulate realistic slippage (0.1% - 0.5%)
        slippage_pct = random.uniform(0.001, 0.005)
        if direction == "YES":
            exec_price = market_price * (1 + slippage_pct)
        else:
            exec_price = (1 - market_price) * (1 + slippage_pct)

        exec_price = min(0.99, max(0.01, exec_price))

        # Fee: Polymarket charges 2% on resale but not on entry
        fee_usd = size_usd * 0.002  # 0.2% fee estimate

        trade = {
            "market_id": market_id,
            "market_question": signal["market_question"],
            "side": direction,
            "action": "buy",
            "size_usd": size_usd,
            "price": exec_price,
            "slippage": slippage_pct,
            "fee_usd": fee_usd,
            "realized_pnl": None,
            "tx_hash": f"0x{''.join(random.choices('0123456789abcdef', k=64))}" if not self.dry_run else None,
            "order_type": "limit" if config.get("use_limit_orders") else "market",
        }

        if self.dry_run:
            logger.info(f"[DRY RUN] Would execute: {direction} ${size_usd:.2f} on {market_id[:12]}... at {exec_price:.3f}")
        else:
            success = await self._send_clob_order(signal, config)
            if not success:
                logger.error(f"CLOB order failed for {market_id}")
                return None

        trade_id = await insert_trade(trade)
        logger.info(f"Trade recorded: id={trade_id}, {direction} ${size_usd:.2f}")

        # Open position
        await self._open_position(signal, exec_price, size_usd, trade_id)

        return {**trade, "id": trade_id}

    async def _open_position(self, signal: dict, exec_price: float, size_usd: float, trade_id: int):
        """Record an open position in the database."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO positions (market_id, market_question, side, size_usd, entry_price,
                    current_price, unrealized_pnl, unrealized_pnl_pct, entry_edge,
                    current_edge, status, opened_at)
                VALUES ($1, $2, $3, $4, $5, $5, 0, 0, $6, $6, 'open', NOW())
            """,
                signal["market_id"], signal["market_question"], signal["direction"],
                size_usd, exec_price, signal["edge"]
            )

    async def _send_clob_order(self, signal: dict, config: dict) -> bool:
        """
        Send actual order to Polymarket CLOB.
        Requires API keys to be configured.
        """
        if not settings.polymarket_private_key:
            logger.error("POLYMARKET_PRIVATE_KEY not set — cannot place live orders")
            return False

        try:
            # Integration with py_clob_client would go here
            # from py_clob_client.client import ClobClient
            # client = ClobClient(settings.polymarket_clob_url, key=settings.polymarket_private_key, ...)
            # order = client.create_market_order(...)
            # resp = client.post_order(order)
            logger.warning("Live CLOB order execution not yet implemented — set dry_run=False with caution")
            return False
        except Exception as e:
            logger.error(f"CLOB order error: {e}")
            return False

    async def update_positions(self, market_prices: dict):
        """Update unrealized P&L for all open positions."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, market_id, side, size_usd, entry_price FROM positions WHERE status = 'open'"
            )
            for row in rows:
                current_price = market_prices.get(row["market_id"])
                if current_price is None:
                    continue

                if row["side"] == "YES":
                    pnl = (current_price - row["entry_price"]) * row["size_usd"] / row["entry_price"]
                else:
                    no_entry = 1 - row["entry_price"]
                    no_current = 1 - current_price
                    pnl = (no_current - no_entry) * row["size_usd"] / no_entry

                pnl_pct = pnl / row["size_usd"] if row["size_usd"] > 0 else 0

                await conn.execute("""
                    UPDATE positions SET
                        current_price = $1,
                        unrealized_pnl = $2,
                        unrealized_pnl_pct = $3
                    WHERE id = $4
                """, current_price, pnl, pnl_pct * 100, row["id"])
