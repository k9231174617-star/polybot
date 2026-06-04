import { Router } from "express";
import { db } from "@workspace/db";
import { positionsTable, signalsTable, tradesTable, botStateTable, balanceReconciliationSnapshotsTable } from "@workspace/db";
import { eq, gte, count, desc } from "drizzle-orm";

const router = Router();

router.get("/dashboard/summary", async (req, res) => {
  try {
    const TOTAL_CAPITAL = 1000;

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const [botStateRows, openPositions, pendingSignalsRows, todayTrades, allTrades, latestReconciliationRows] = await Promise.all([
      db.select().from(botStateTable).limit(1),
      db.select().from(positionsTable).where(eq(positionsTable.status, "open")),
      db.select({ value: count() }).from(signalsTable).where(eq(signalsTable.status, "pending")),
      db.select().from(tradesTable).where(gte(tradesTable.executed_at, today)),
      db.select().from(tradesTable),
      db.select().from(balanceReconciliationSnapshotsTable).orderBy(desc(balanceReconciliationSnapshotsTable.created_at)).limit(1),
    ]);

    const [botState] = botStateRows;
    const [{ value: pendingSignals }] = pendingSignalsRows;
    const [latestReconciliation] = latestReconciliationRows;

    const unrealizedPnl = openPositions.reduce((sum, p) => sum + p.unrealized_pnl, 0);
    const portfolioValue = TOTAL_CAPITAL + unrealizedPnl;
    const dailyPnl = todayTrades.reduce((sum, t) => sum + (t.realized_pnl ?? 0), 0);
    const dailyPnlPct = TOTAL_CAPITAL > 0 ? dailyPnl / TOTAL_CAPITAL : 0;
    const realizedPnl = allTrades.reduce((sum, t) => sum + (t.realized_pnl ?? 0), 0);
    const totalPnl = realizedPnl + unrealizedPnl;
    const totalPnlPct = TOTAL_CAPITAL > 0 ? totalPnl / TOTAL_CAPITAL : 0;

    const winCount = allTrades.filter((t) => (t.realized_pnl ?? 0) > 0).length;
    const winRate = allTrades.length > 0 ? winCount / allTrades.length : 0;

    const deployedCapital = openPositions.reduce((sum, p) => sum + p.size_usd, 0);

    res.json({
      bot_state: botState?.state ?? "stopped",
      portfolio_value_usd: portfolioValue,
      total_pnl: totalPnl,
      total_pnl_pct: totalPnlPct,
      daily_pnl: dailyPnl,
      daily_pnl_pct: dailyPnlPct,
      open_positions_count: openPositions.length,
      pending_signals_count: Number(pendingSignals),
      markets_scanned_today: botState?.markets_scanned ?? 0,
      trades_today: todayTrades.length,
      win_rate: winRate,
      deployed_capital_pct: TOTAL_CAPITAL > 0 ? deployedCapital / TOTAL_CAPITAL : 0,
      balance_reconciliation_status: latestReconciliation?.status ?? "unknown",
      balance_reconciliation_discrepancy_usd: latestReconciliation?.discrepancy_usd ?? null,
      balance_reconciliation_discrepancy_pct: latestReconciliation?.discrepancy_pct ?? null,
      balance_reconciliation_updated_at: latestReconciliation?.created_at ? new Date(latestReconciliation.created_at).toISOString() : null,
    });
  } catch (err) {
    req.log.error({ err }, "Failed to get dashboard summary");
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
