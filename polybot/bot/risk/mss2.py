"""MSS2-specific risk guardrails and circuit breaker."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from loguru import logger

from bot.notifications import send_telegram_alert
from bot.utils.db import get_pool


@dataclass
class Mss2RiskAssessment:
    can_trade: bool
    reason: Optional[str] = None
    size_multiplier: float = 1.0
    risk_level: str = "normal"


class Mss2RiskManager:
    def __init__(self, *, max_consecutive_losses: int = 3, reduction_after_losses: int = 2) -> None:
        self.max_consecutive_losses = max_consecutive_losses
        self.reduction_after_losses = reduction_after_losses

    async def _recent_realized_pnl(self, signal_type: str, paper_mode: bool) -> list[float]:
        pool = await get_pool()
        table = "paper_trades" if paper_mode else "trades"
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT realized_pnl
                FROM {table}
                WHERE signal_type = $1
                  AND action = 'sell'
                  AND realized_pnl IS NOT NULL
                ORDER BY executed_at DESC
                LIMIT 20
                """,
                signal_type,
            )
        return [float(row["realized_pnl"] or 0.0) for row in rows]

    async def _same_category_open_positions(self, market_id: str, paper_mode: bool) -> int:
        pool = await get_pool()
        positions_table = "paper_positions" if paper_mode else "positions"
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT category FROM markets WHERE id = $1", market_id)
            category = str(row["category"] or "") if row else ""
            if not category:
                return 0
            rows = await conn.fetch(
                f"""
                SELECT p.id
                FROM {positions_table} p
                JOIN markets m ON m.id = p.market_id
                WHERE p.status = 'open'
                  AND m.category = $1
                """,
                category,
            )
        return len(rows)

    async def assess_trade(self, signal: dict, *, paper_mode: bool = True) -> Mss2RiskAssessment:
        pnl_history = await self._recent_realized_pnl("mss2_spread_capture", paper_mode)
        consecutive_losses = 0
        for pnl in pnl_history:
            if pnl < 0:
                consecutive_losses += 1
            else:
                break

        if consecutive_losses >= self.max_consecutive_losses:
            logger.warning(f"MSS2 circuit breaker hit: {consecutive_losses} consecutive losses")
            await send_telegram_alert(
                "error",
                "MSS2 circuit breaker",
                f"{consecutive_losses} consecutive losses reached on MSS2",
                {"consecutive_losses": consecutive_losses, "market_id": signal.get("market_id")},
            )
            return Mss2RiskAssessment(
                can_trade=False,
                reason=f"MSS2 circuit breaker: {consecutive_losses} consecutive losses",
                size_multiplier=0.0,
                risk_level="halted",
            )

        if await self._same_category_open_positions(signal["market_id"], paper_mode) >= 2:
            await send_telegram_alert(
                "warning",
                "MSS2 concentration limit",
                f"MSS2 category concentration limit reached for {signal.get('market_id')}",
                {"market_id": signal.get("market_id")},
            )
            return Mss2RiskAssessment(
                can_trade=False,
                reason="MSS2 category concentration limit reached",
                size_multiplier=0.0,
                risk_level="elevated",
            )

        if consecutive_losses >= self.reduction_after_losses:
            return Mss2RiskAssessment(
                can_trade=True,
                reason=f"MSS2 loss streak: {consecutive_losses}",
                size_multiplier=0.5,
                risk_level="elevated",
            )

        return Mss2RiskAssessment(can_trade=True)
