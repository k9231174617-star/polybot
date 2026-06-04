"""
Paper Trading Executor.

Real market prices, virtual money. Full portfolio tracking in separate DB tables.
Auto-closes positions when market resolves (price hits ≥0.95 or ≤0.05).
"""
import random
import statistics
from typing import Optional
from loguru import logger

from bot.utils.db import get_pool, log_entry


class PaperExecutor:
    def __init__(self, capital_usd: float = 1000.0):
        self.capital_usd = capital_usd

    async def execute_signal(self, signal: dict) -> Optional[dict]:
        """Open a paper position. Returns trade dict or None if duplicate."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT id FROM paper_positions WHERE market_id=$1 AND status='open'",
                signal["market_id"]
            )
            if existing:
                return None

        slippage = random.uniform(0.001, 0.004)
        mp = signal["market_price"]
        d = signal["direction"]
        exec_price = max(0.01, min(0.99, mp * (1 + slippage) if d == "YES" else (1 - mp) * (1 + slippage)))
        size = signal["kelly_size_usd"]
        fee = size * 0.002

        async with pool.acquire() as conn:
            tid = await conn.fetchval("""
                INSERT INTO paper_trades
                  (market_id, market_question, side, action, size_usd, price, slippage, fee_usd, realized_pnl, signal_type)
                VALUES ($1,$2,$3,'buy',$4,$5,$6,$7,NULL,$8) RETURNING id
            """, signal["market_id"], signal["market_question"], d, size,
                exec_price, slippage, fee, signal.get("signal_type","price_discrepancy"))

            await conn.execute("""
                INSERT INTO paper_positions
                  (market_id, market_question, side, size_usd, entry_price, current_price,
                   unrealized_pnl, unrealized_pnl_pct, entry_edge, signal_type, confidence)
                VALUES ($1,$2,$3,$4,$5,$5,0,0,$6,$7,$8)
            """, signal["market_id"], signal["market_question"], d, size,
                exec_price, signal["edge"],
                signal.get("signal_type","price_discrepancy"), signal.get("confidence", 0.5))

        logger.info(f"[PAPER] {d} ${size:.2f} @ {exec_price:.3f} edge={signal['edge']:.3f}")
        await log_entry("paper", "info",
            f"Paper trade: {d} ${size:.2f} edge={signal['edge']:.3f}",
            {"market_id": signal["market_id"], "signal_type": signal.get("signal_type")})
        return {"id": tid, "size_usd": size, "price": exec_price}

    async def update_positions(self, market_prices: dict[str, float]):
        """Update paper P&L and auto-close resolved positions."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, market_id, side, size_usd, entry_price FROM paper_positions WHERE status='open'"
            )
            for row in rows:
                price = market_prices.get(row["market_id"])
                if price is None:
                    continue

                if row["side"] == "YES":
                    pnl = (price - row["entry_price"]) * row["size_usd"] / row["entry_price"]
                else:
                    ne = 1 - row["entry_price"]
                    pnl = ((1 - price) - ne) * row["size_usd"] / ne if ne > 0 else 0

                pnl_pct = pnl / row["size_usd"] * 100 if row["size_usd"] > 0 else 0
                await conn.execute(
                    "UPDATE paper_positions SET current_price=$1,unrealized_pnl=$2,unrealized_pnl_pct=$3 WHERE id=$4",
                    price, pnl, pnl_pct, row["id"]
                )

                if price >= 0.95 or price <= 0.05:
                    await self._close_position(conn, row, price)

    async def _close_position(self, conn, row, final_price: float):
        if row["side"] == "YES":
            realized = (final_price - row["entry_price"]) * row["size_usd"] / row["entry_price"]
        else:
            ne = 1 - row["entry_price"]
            realized = ((1 - final_price) - ne) * row["size_usd"] / ne if ne > 0 else 0

        await conn.execute(
            "UPDATE paper_positions SET status='closed',closed_at=NOW(),unrealized_pnl=0,unrealized_pnl_pct=0,current_price=$1 WHERE id=$2",
            final_price, row["id"]
        )
        await conn.execute("""
            INSERT INTO paper_trades (market_id, market_question, side, action, size_usd, price, slippage, fee_usd, realized_pnl, signal_type)
            SELECT market_id, market_question, side, 'sell', size_usd, $1, 0, size_usd*0.002, $2, signal_type
            FROM paper_positions WHERE id=$3
        """, final_price, realized, row["id"])
        logger.info(f"[PAPER] Position closed realized={realized:+.2f}")

    async def snapshot_pnl(self):
        pool = await get_pool()
        async with pool.acquire() as conn:
            realized = float(await conn.fetchval(
                "SELECT COALESCE(SUM(realized_pnl),0) FROM paper_trades WHERE realized_pnl IS NOT NULL") or 0)
            unrealized = float(await conn.fetchval(
                "SELECT COALESCE(SUM(unrealized_pnl),0) FROM paper_positions WHERE status='open'") or 0)
            total = int(await conn.fetchval("SELECT COUNT(*) FROM paper_trades WHERE action='buy'") or 0)
            closed = int(await conn.fetchval(
                "SELECT COUNT(*) FROM paper_trades WHERE action='sell' AND realized_pnl IS NOT NULL") or 0)
            wins = int(await conn.fetchval(
                "SELECT COUNT(*) FROM paper_trades WHERE action='sell' AND realized_pnl>0") or 0)
            wr = wins / closed if closed > 0 else 0.0
            await conn.execute(
                "INSERT INTO paper_pnl_snapshots (cumulative_pnl,portfolio_value,win_rate,total_trades) VALUES ($1,$2,$3,$4)",
                realized + unrealized, self.capital_usd + realized + unrealized, wr, total
            )

    async def get_stats(self) -> dict:
        pool = await get_pool()
        async with pool.acquire() as conn:
            r = await conn.fetchrow("""
                SELECT
                  COUNT(*) FILTER (WHERE action='buy') AS total_trades,
                  COUNT(*) FILTER (WHERE action='sell' AND realized_pnl>0) AS wins,
                  COUNT(*) FILTER (WHERE action='sell' AND realized_pnl<0) AS losses,
                  COALESCE(SUM(realized_pnl) FILTER (WHERE realized_pnl IS NOT NULL),0) AS total_realized,
                  COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl IS NOT NULL),0) AS avg_pnl,
                  COALESCE(MAX(realized_pnl),0) AS best,
                  COALESCE(MIN(realized_pnl),0) AS worst
                FROM paper_trades
            """)
            unrealized = float(await conn.fetchval(
                "SELECT COALESCE(SUM(unrealized_pnl),0) FROM paper_positions WHERE status='open'") or 0)
            open_count = int(await conn.fetchval(
                "SELECT COUNT(*) FROM paper_positions WHERE status='open'") or 0)

            wins = int(r["wins"] or 0)
            losses = int(r["losses"] or 0)
            closed = wins + losses
            wr = wins / closed if closed > 0 else 0.0
            total_realized = float(r["total_realized"] or 0)
            cum_pnl = total_realized + unrealized

            type_rows = await conn.fetch("""
                SELECT signal_type,
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE realized_pnl>0) AS wins,
                  COALESCE(SUM(realized_pnl),0) AS pnl
                FROM paper_trades WHERE realized_pnl IS NOT NULL GROUP BY signal_type
            """)
            by_type = {
                row["signal_type"]: {
                    "total": int(row["total"]), "wins": int(row["wins"]),
                    "pnl": float(row["pnl"]),
                    "win_rate": int(row["wins"]) / int(row["total"]) if int(row["total"]) > 0 else 0.0,
                }
                for row in type_rows
            }

            daily_rows = await conn.fetch("""
                SELECT DATE(created_at) AS day, MAX(cumulative_pnl)-MIN(cumulative_pnl) AS dpnl
                FROM paper_pnl_snapshots WHERE created_at > NOW()-INTERVAL '30 days'
                GROUP BY day ORDER BY day
            """)
            dpnls = [float(row["dpnl"]) for row in daily_rows if row["dpnl"] is not None]
            sharpe = 0.0
            if len(dpnls) >= 5:
                mean_d = statistics.mean(dpnls)
                std_d = statistics.stdev(dpnls)
                sharpe = round(mean_d / std_d * (252 ** 0.5), 2) if std_d > 0 else 0.0

            return {
                "capital_usd": self.capital_usd,
                "cumulative_pnl": cum_pnl,
                "portfolio_value": self.capital_usd + cum_pnl,
                "total_return_pct": cum_pnl / self.capital_usd * 100,
                "total_trades": int(r["total_trades"] or 0),
                "open_positions": open_count,
                "wins": wins, "losses": losses, "win_rate": wr,
                "avg_pnl_per_trade": float(r["avg_pnl"] or 0),
                "best_trade": float(r["best"] or 0),
                "worst_trade": float(r["worst"] or 0),
                "sharpe_ratio": sharpe,
                "unrealized_pnl": unrealized,
                "by_signal_type": by_type,
            }
