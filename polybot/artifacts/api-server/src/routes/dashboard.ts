import { Router } from "express";
import { db } from "@workspace/db";
import { positionsTable, signalsTable, tradesTable, paperTradesTable, logEntriesTable, botStateTable, botConfigTable, balanceReconciliationSnapshotsTable, latencyEventsTable } from "@workspace/db";
import { eq, gte, lt, and, count, desc } from "drizzle-orm";

const router = Router();

const summarize = (values: number[]) => {
  if (values.length === 0) {
    return { count: 0, average_ms: 0, p50_ms: 0, p95_ms: 0, p99_ms: 0 };
  }
  const sorted = [...values].sort((a, b) => a - b);
  const percentile = (p: number) => {
    if (sorted.length === 1) return sorted[0];
    const rank = (sorted.length - 1) * p;
    const low = Math.floor(rank);
    const high = Math.min(low + 1, sorted.length - 1);
    if (low === high) return sorted[low];
    const frac = rank - low;
    return sorted[low] * (1 - frac) + sorted[high] * frac;
  };
  const average_ms = values.reduce((sum, value) => sum + value, 0) / values.length;
  return {
    count: values.length,
    average_ms,
    p50_ms: percentile(0.5),
    p95_ms: percentile(0.95),
    p99_ms: percentile(0.99),
  };
};

router.get("/dashboard/summary", async (req, res) => {
  try {
    const TOTAL_CAPITAL = 1000;

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const dayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);

    const [botStateRows, botConfigRows, openPositions, pendingSignalsRows, todayTrades, allTrades, paperTrades, logRows, latestReconciliationRows, latencyRows] = await Promise.all([
      db.select().from(botStateTable).limit(1),
      db.select().from(botConfigTable).limit(1),
      db.select().from(positionsTable).where(eq(positionsTable.status, "open")),
      db.select({ value: count() }).from(signalsTable).where(eq(signalsTable.status, "pending")),
      db.select().from(tradesTable).where(gte(tradesTable.executed_at, today)),
      db.select().from(tradesTable),
      db.select().from(paperTradesTable),
      db.select().from(logEntriesTable).where(gte(logEntriesTable.created_at, dayAgo)),
      db.select().from(balanceReconciliationSnapshotsTable).orderBy(desc(balanceReconciliationSnapshotsTable.created_at)).limit(1),
      db.select().from(latencyEventsTable).orderBy(desc(latencyEventsTable.created_at)).limit(500),
    ]);

    const [botState] = botStateRows;
    const [botConfig] = botConfigRows;
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
    const logCount = logRows.length;
    const errorLogCount = logRows.filter((row) => String(row.level ?? "").toLowerCase() === "error").length;
    const errorRate = logCount > 0 ? errorLogCount / logCount : 0;
    const heartbeatUpdatedAt = botState?.updated_at ? new Date(botState.updated_at) : null;
    const heartbeatAgeSeconds = heartbeatUpdatedAt ? Math.max(0, Math.floor((Date.now() - heartbeatUpdatedAt.getTime()) / 1000)) : null;
    const scanIntervalSeconds = botConfig?.scan_interval_seconds ?? 30;
    const staleSignalsCutoff = new Date(Date.now() - Math.max(scanIntervalSeconds * 2000, 120000));
    const droppedSignalsRows = await db.select({ value: count() })
      .from(signalsTable)
      .where(and(eq(signalsTable.status, "pending"), lt(signalsTable.detected_at, staleSignalsCutoff)));
    const droppedSignalsCount = Number(droppedSignalsRows[0]?.value ?? 0);
    const fills = [...allTrades, ...paperTrades];
    const filledOrders = fills.filter((row) => {
      const status = String(row.order_status ?? "").toLowerCase();
      return status === "filled" || status === "matched" || status === "simulated" || status === "partial" || status === "partially_filled";
    }).length;
    const fillSuccessRate = fills.length > 0 ? filledOrders / fills.length : 0;
    const latencyByStage = new Map<string, number[]>();
    for (const row of latencyRows) {
      const stage = String(row.stage ?? "unknown");
      const value = Number(row.duration_ms ?? 0);
      if (!latencyByStage.has(stage)) {
        latencyByStage.set(stage, []);
      }
      latencyByStage.get(stage)!.push(value);
    }
    const signalToDecision = summarize(latencyByStage.get("signal_to_decision") ?? []);
    const decisionToExecution = summarize(latencyByStage.get("decision_to_execution") ?? []);
    const signalToTradeRecorded = summarize(latencyByStage.get("signal_to_trade_recorded") ?? []);
    const signalToConfirmation = summarize(latencyByStage.get("signal_to_confirmation") ?? []);

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
      error_rate_24h: errorRate,
      log_events_24h: logCount,
      error_events_24h: errorLogCount,
      heartbeat_age_seconds: heartbeatAgeSeconds,
      heartbeat_stale: heartbeatAgeSeconds !== null ? heartbeatAgeSeconds > Math.max(scanIntervalSeconds * 3, 120) : true,
      dropped_signals_count: droppedSignalsCount,
      fill_success_rate: fillSuccessRate,
      balance_reconciliation_status: latestReconciliation?.status ?? "unknown",
      balance_reconciliation_discrepancy_usd: latestReconciliation?.discrepancy_usd ?? null,
      balance_reconciliation_discrepancy_pct: latestReconciliation?.discrepancy_pct ?? null,
      balance_reconciliation_updated_at: latestReconciliation?.created_at ? new Date(latestReconciliation.created_at).toISOString() : null,
      latency_events_count: latencyRows.length,
      latency_signal_to_decision_ms: signalToDecision,
      latency_decision_to_execution_ms: decisionToExecution,
      latency_signal_to_trade_recorded_ms: signalToTradeRecorded,
      latency_signal_to_confirmation_ms: signalToConfirmation,
    });
  } catch (err) {
    req.log.error({ err }, "Failed to get dashboard summary");
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
