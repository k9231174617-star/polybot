import { Router } from "express";
import { db } from "@workspace/db";
import { positionsTable, tradesTable, botConfigTable, botStateTable, pnlSnapshotsTable } from "@workspace/db";
import { eq, and, gte, sql } from "drizzle-orm";

const router = Router();

router.get("/risk", async (req, res) => {
  try {
    const [config] = await db.select().from(botConfigTable).limit(1);
    const [state] = await db.select().from(botStateTable).limit(1);

    const TOTAL_CAPITAL = 1000; // Default, in production comes from wallet balance

    const openPositions = await db
      .select()
      .from(positionsTable)
      .where(eq(positionsTable.status, "open"));

    const deployedCapital = openPositions.reduce((sum, p) => sum + p.size_usd, 0);
    const deployedPct = TOTAL_CAPITAL > 0 ? deployedCapital / TOTAL_CAPITAL : 0;

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const todayTrades = await db
      .select()
      .from(tradesTable)
      .where(gte(tradesTable.executed_at, today));

    const dailyPnl = todayTrades.reduce((sum, t) => sum + (t.realized_pnl ?? 0), 0);
    const dailyLossLimitPct = config?.daily_loss_limit_pct ?? 0.03;
    const dailyLossLimitUsd = TOTAL_CAPITAL * dailyLossLimitPct;
    const dailyLossRemaining = Math.max(0, dailyLossLimitUsd + dailyPnl);

    const unrealizedPnl = openPositions.reduce((sum, p) => sum + p.unrealized_pnl, 0);
    const portfolioValue = TOTAL_CAPITAL + unrealizedPnl;

    const maxPosition = openPositions.reduce((max, p) => Math.max(max, p.size_usd), 0);
    const largestPositionPct = portfolioValue > 0 ? maxPosition / portfolioValue : 0;

    // Simple VaR: 5% of deployed capital
    const var95 = deployedCapital * 0.05;

    // Correlation score: higher if multiple positions on same category
    const correlationScore = openPositions.length > 5 ? 0.6 : openPositions.length > 2 ? 0.3 : 0.1;

    res.json({
      total_capital_usd: TOTAL_CAPITAL,
      deployed_capital_usd: deployedCapital,
      deployed_pct: deployedPct,
      daily_pnl: dailyPnl,
      daily_pnl_pct: TOTAL_CAPITAL > 0 ? dailyPnl / TOTAL_CAPITAL : 0,
      daily_loss_limit_usd: dailyLossLimitUsd,
      daily_loss_remaining_usd: dailyLossRemaining,
      max_single_position_usd: TOTAL_CAPITAL * (config?.max_position_pct ?? 0.05),
      num_open_positions: openPositions.length,
      largest_position_pct: largestPositionPct,
      correlation_risk_score: correlationScore,
      var_95: var95,
    });
  } catch (err) {
    req.log.error({ err }, "Failed to get risk metrics");
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
