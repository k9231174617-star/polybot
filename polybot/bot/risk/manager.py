"""Risk Manager — enforces position limits, daily loss limits, and correlation checks."""
from loguru import logger
from bot.utils.db import get_pool
from bot.notifications import send_telegram_alert


class RiskManager:
    def __init__(self, config: dict, total_capital: float = 1000.0, paper_mode: bool = False):
        self.config = config
        self.total_capital = total_capital
        self.paper_mode = paper_mode

    @property
    def position_table(self) -> str:
        return "paper_positions" if self.paper_mode else "positions"

    @property
    def trade_table(self) -> str:
        return "paper_trades" if self.paper_mode else "trades"

    async def check_daily_loss_limit(self) -> bool:
        """Returns True if trading can continue (within daily loss limit)."""
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today = today.replace(tzinfo=None)

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""SELECT COALESCE(SUM(realized_pnl), 0) as daily_pnl
                   FROM {self.trade_table}
                   WHERE executed_at >= $1""",
                today
            )
            daily_pnl = float(row["daily_pnl"] or 0)

        limit = self.total_capital * self.config.get("daily_loss_limit_pct", 0.03)
        if daily_pnl < -limit:
            logger.warning(f"Daily loss limit hit: {daily_pnl:.2f} < -{limit:.2f}")
            await send_telegram_alert(
                "warning",
                "Daily loss limit hit",
                f"Daily PnL {daily_pnl:.2f} is below the allowed limit {-limit:.2f}",
                {"daily_pnl": daily_pnl, "limit": -limit},
            )
            return False
        return True

    async def check_position_limit(self, new_size_usd: float) -> bool:
        """Returns True if new position fits within per-market cap."""
        max_size = self.total_capital * self.config.get("max_position_pct", 0.05)
        if new_size_usd > max_size:
            logger.warning(f"Position size {new_size_usd:.2f} exceeds max {max_size:.2f}")
            await send_telegram_alert(
                "warning",
                "Position size rejected",
                f"Requested size {new_size_usd:.2f} exceeds max {max_size:.2f}",
                {"requested_size": new_size_usd, "max_size": max_size},
            )
            return False
        return True

    async def check_total_exposure(self, new_size_usd: float) -> bool:
        """Returns True if total deployed capital stays within correlated exposure limit."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT COALESCE(SUM(size_usd), 0) as total FROM {self.position_table} WHERE status = 'open'"
            )
            current_deployed = float(row["total"] or 0)

        max_total = self.total_capital * self.config.get("max_correlated_exposure_pct", 0.15)
        if current_deployed + new_size_usd > max_total:
            logger.warning(f"Total exposure would exceed limit: {current_deployed + new_size_usd:.2f} > {max_total:.2f}")
            await send_telegram_alert(
                "warning",
                "Exposure limit reached",
                f"Current deployed {current_deployed:.2f} + new {new_size_usd:.2f} exceeds max {max_total:.2f}",
                {"current_deployed": current_deployed, "new_size": new_size_usd, "max_total": max_total},
            )
            return False
        return True

    async def check_duplicate_market(self, market_id: str) -> bool:
        """Returns True if we don't already have an open position on this market."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT id FROM {self.position_table} WHERE market_id = $1 AND status = 'open'",
                market_id
            )
            return row is None

    async def can_trade(self, signal: dict) -> tuple[bool, str]:
        """
        Full risk check for a given signal.
        Returns (can_trade, reason).
        """
        if not await self.check_daily_loss_limit():
            return False, "Daily loss limit reached"

        if not await self.check_position_limit(signal["kelly_size_usd"]):
            return False, f"Position size {signal['kelly_size_usd']:.2f} exceeds per-market cap"

        if not await self.check_total_exposure(signal["kelly_size_usd"]):
            return False, "Total exposure limit would be exceeded"

        if not await self.check_duplicate_market(signal["market_id"]):
            return False, f"Already have open position on market {signal['market_id']}"

        return True, "OK"
