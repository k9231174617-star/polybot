import { Router } from "express";
import { db } from "@workspace/db";
import { tradesTable, positionsTable, pnlSnapshotsTable } from "@workspace/db";
import { eq, desc, gte, asc } from "drizzle-orm";
import { GetPnlChartQueryParams } from "@workspace/api-zod";

const router = Router();

router.get("/pnl/summary", async (req, res) => {
  try {
    const allTrades = await db.select().from(tradesTable).orderBy(desc(tradesTable.executed_at));
    const openPositions = await db.select().from(positionsTable).where(eq(positionsTable.status, "open"));

    const realizedPnl = allTrades.reduce((sum, t) => sum + (t.realized_pnl ?? 0), 0);
    const unrealizedPnl = openPositions.reduce((sum, p) => sum + p.unrealized_pnl, 0);
    const totalPnl = realizedPnl + unrealizedPnl;
    const TOTAL_CAPITAL = 1000;
    const totalPnlPct = TOTAL_CAPITAL > 0 ? totalPnl / TOTAL_CAPITAL : 0;

    const winningTrades = allTrades.filter((t) => (t.realized_pnl ?? 0) > 0);
    const losingTrades = allTrades.filter((t) => (t.realized_pnl ?? 0) < 0);
    const winRate = allTrades.length > 0 ? winningTrades.length / allTrades.length : 0;

    const pnlValues = allTrades.map((t) => t.realized_pnl ?? 0);
    const bestTrade = pnlValues.length > 0 ? Math.max(...pnlValues) : 0;
    const worstTrade = pnlValues.length > 0 ? Math.min(...pnlValues) : 0;

    const avgEdge = openPositions.length > 0
      ? openPositions.reduce((sum, p) => sum + p.entry_edge, 0) / openPositions.length
      : 0;

    // Simple Sharpe approximation
    let sharpe: number | null = null;
    if (pnlValues.length >= 5) {
      const mean = pnlValues.reduce((a, b) => a + b, 0) / pnlValues.length;
      const variance = pnlValues.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / pnlValues.length;
      const stdDev = Math.sqrt(variance);
      sharpe = stdDev > 0 ? mean / stdDev : null;
    }

    res.json({
      total_pnl: totalPnl,
      total_pnl_pct: totalPnlPct,
      realized_pnl: realizedPnl,
      unrealized_pnl: unrealizedPnl,
      win_rate: winRate,
      avg_edge_captured: avgEdge,
      total_trades: allTrades.length,
      winning_trades: winningTrades.length,
      losing_trades: losingTrades.length,
      best_trade_pnl: bestTrade,
      worst_trade_pnl: worstTrade,
      sharpe_ratio: sharpe,
    });
  } catch (err) {
    req.log.error({ err }, "Failed to get PnL summary");
    res.status(500).json({ error: "Internal server error" });
  }
});

router.get("/pnl/chart", async (req, res) => {
  const parsed = GetPnlChartQueryParams.safeParse(req.query);
  const { period = "7d" } = parsed.success ? parsed.data : {};

  const periodDays: Record<string, number> = { "1d": 1, "7d": 7, "30d": 30, "all": 3650 };
  const days = periodDays[period] ?? 7;
  const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000);

  try {
    const snapshots = await db
      .select()
      .from(pnlSnapshotsTable)
      .where(gte(pnlSnapshotsTable.created_at, since))
      .orderBy(asc(pnlSnapshotsTable.created_at));

    res.json(snapshots.map((s) => ({
      timestamp: s.created_at?.toISOString() ?? new Date().toISOString(),
      cumulative_pnl: s.cumulative_pnl,
      portfolio_value: s.portfolio_value,
    })));
  } catch (err) {
    req.log.error({ err }, "Failed to get PnL chart data");
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
