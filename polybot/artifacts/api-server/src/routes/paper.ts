import { Router } from "express";
import { db } from "@workspace/db";
import {
  paperPositionsTable,
  paperTradesTable,
  paperPnlSnapshotsTable,
  signalsTable,
  botConfigTable,
} from "@workspace/db";
import { desc, eq, gte, sql } from "drizzle-orm";
import { isoOrNow, isoOrNull } from "../lib/serialize";

type StrategyReport = {
  signal_type: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  gross_profit: number;
  gross_loss: number;
  net_pnl: number;
  maker_rebate: number;
  net_after_rebate: number;
  avg_profit_per_trade: number;
  avg_profit_per_winner: number;
  avg_loss_per_loser: number;
  profit_factor: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  avg_hold_time_seconds: number;
  median_hold_time_seconds: number;
  trades_per_day: number;
  capital_utilization_pct: number;
  pending_capital_avg_pct: number;
  spread_captured: number;
  hedged: number;
  timeout: number;
  stop_loss: number;
  requeue_abandoned: number;
  adverse_selection: number;
  avg_queue_pressure: number;
  avg_expected_fill_delay_seconds: number;
};

const median = (values: number[]): number => {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
};

const maxDrawdown = (values: number[]): number => {
  let peak = 0;
  let cumulative = 0;
  let maxDd = 0;
  for (const value of values) {
    cumulative += value;
    peak = Math.max(peak, cumulative);
    maxDd = Math.max(maxDd, peak - cumulative);
  }
  return maxDd;
};

const sharpe = (values: number[]): number => {
  if (values.length < 2) return 0;
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
  const variance = values.reduce((sum, value) => sum + (value - avg) ** 2, 0) / (values.length - 1);
  const stdDev = Math.sqrt(variance);
  if (stdDev <= 0) return 0;
  return (avg / stdDev) * Math.sqrt(252);
};

const sortino = (values: number[]): number => {
  const downside = values.filter((value) => value < 0);
  if (downside.length === 0) return values.length > 0 ? Number.POSITIVE_INFINITY : 0;
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
  const downsideVariance = downside.reduce((sum, value) => sum + value ** 2, 0) / downside.length;
  const downsideDev = Math.sqrt(downsideVariance);
  if (downsideDev <= 0) return Number.POSITIVE_INFINITY;
  return (avg / downsideDev) * Math.sqrt(252);
};

const buildStrategyReport = (
  signalType: string,
  rows: Array<Record<string, any>>,
  positions: Array<Record<string, any>>,
  signals: Array<Record<string, any>>,
  capitalUsd: number,
): StrategyReport => {
  const buys = rows.filter((row) => row.action === "buy");
  const sells = rows.filter((row) => row.action === "sell" && row.realized_pnl !== null && row.realized_pnl !== undefined);
  const pnlValues = sells.map((row) => Number(row.realized_pnl ?? 0));
  const winning = pnlValues.filter((pnl) => pnl > 0);
  const losing = pnlValues.filter((pnl) => pnl < 0);
  const grossProfit = winning.reduce((sum, pnl) => sum + pnl, 0);
  const grossLoss = Math.abs(losing.reduce((sum, pnl) => sum + pnl, 0));
  const netPnl = grossProfit - grossLoss;

  const dailySeries = new Map<string, number>();
  for (const row of sells) {
    const executedAt = row.executed_at ? new Date(String(row.executed_at)) : null;
    if (!executedAt || Number.isNaN(executedAt.getTime())) continue;
    const dayKey = executedAt.toISOString().slice(0, 10);
    dailySeries.set(dayKey, (dailySeries.get(dayKey) ?? 0) + Number(row.realized_pnl ?? 0));
  }

  const holds = positions
    .filter((row) => row.opened_at && row.closed_at)
    .map((row) => {
      const opened = new Date(String(row.opened_at));
      const closed = new Date(String(row.closed_at));
      if (Number.isNaN(opened.getTime()) || Number.isNaN(closed.getTime())) return 0;
      return Math.max(0, (closed.getTime() - opened.getTime()) / 1000);
    })
    .filter((value) => value > 0);

  const signalDetails = signals
    .filter((row) => String(row.signal_type) === signalType)
    .map((row) => row.details ?? {})
    .filter((details) => details && typeof details === "object");
  const queuePressure = signalDetails
    .map((details) => Number((details as Record<string, any>).mss2_queue_pressure ?? 0))
    .filter((value) => Number.isFinite(value));
  const fillDelay = signalDetails
    .map((details) => Number((details as Record<string, any>).mss2_expected_fill_delay_seconds ?? 0))
    .filter((value) => Number.isFinite(value));

  const dailyReturns = [...dailySeries.values()].map((value) => (capitalUsd > 0 ? value / capitalUsd : 0));
  return {
    signal_type: signalType,
    total_trades: buys.length,
    winning_trades: winning.length,
    losing_trades: losing.length,
    win_rate: winning.length + losing.length > 0 ? winning.length / (winning.length + losing.length) : 0,
    gross_profit: grossProfit,
    gross_loss: grossLoss,
    net_pnl: netPnl,
    maker_rebate: 0,
    net_after_rebate: netPnl,
    avg_profit_per_trade: buys.length > 0 ? netPnl / buys.length : 0,
    avg_profit_per_winner: winning.length > 0 ? grossProfit / winning.length : 0,
    avg_loss_per_loser: losing.length > 0 ? grossLoss / losing.length : 0,
    profit_factor: grossLoss > 0 ? grossProfit / grossLoss : (grossProfit > 0 ? Number.POSITIVE_INFINITY : 0),
    max_drawdown_pct: capitalUsd > 0 ? (maxDrawdown(pnlValues) / capitalUsd) * 100 : 0,
    sharpe_ratio: sharpe(dailyReturns),
    sortino_ratio: sortino(dailyReturns),
    avg_hold_time_seconds: holds.length > 0 ? holds.reduce((sum, value) => sum + value, 0) / holds.length : 0,
    median_hold_time_seconds: median(holds),
    trades_per_day: buys.length / 30,
    capital_utilization_pct: 0,
    pending_capital_avg_pct: 0,
    spread_captured: buys.length,
    hedged: 0,
    timeout: 0,
    stop_loss: 0,
    requeue_abandoned: 0,
    adverse_selection: 0,
    avg_queue_pressure: queuePressure.length > 0 ? queuePressure.reduce((sum, value) => sum + value, 0) / queuePressure.length : 0,
    avg_expected_fill_delay_seconds: fillDelay.length > 0 ? fillDelay.reduce((sum, value) => sum + value, 0) / fillDelay.length : 0,
  };
};

const router = Router();

// GET /paper/positions
router.get("/paper/positions", async (req, res): Promise<void> => {
  try {
    const status = (req.query["status"] as string) || "open";
    const rows =
      status === "all"
        ? await db
            .select()
            .from(paperPositionsTable)
            .orderBy(desc(paperPositionsTable.opened_at))
            .limit(200)
        : await db
            .select()
            .from(paperPositionsTable)
            .where(eq(paperPositionsTable.status, status))
            .orderBy(desc(paperPositionsTable.opened_at))
            .limit(200);
    res.json(
      rows.map((p) => ({
        ...p,
        opened_at: isoOrNow(p.opened_at),
        closed_at: isoOrNull(p.closed_at),
      }))
    );
  } catch (err) {
    req.log.error({ err }, "Failed to get paper positions");
    res.status(500).json({ error: "Internal server error" });
  }
});

// GET /paper/trades
router.get("/paper/trades", async (req, res): Promise<void> => {
  try {
    const limit = parseInt((req.query["limit"] as string) || "100", 10);
    const rows = await db
      .select()
      .from(paperTradesTable)
      .orderBy(desc(paperTradesTable.executed_at))
      .limit(limit);
    res.json(
      rows.map((t) => ({
        ...t,
        executed_at: isoOrNow(t.executed_at),
      }))
    );
  } catch (err) {
    req.log.error({ err }, "Failed to get paper trades");
    res.status(500).json({ error: "Internal server error" });
  }
});

// GET /paper/chart
router.get("/paper/chart", async (req, res): Promise<void> => {
  try {
    const period = (req.query["period"] as string) || "7d";
    const msMap: Record<string, number> = {
      "1d": 86400000,
      "7d": 7 * 86400000,
      "30d": 30 * 86400000,
      all: 10 * 365 * 86400000,
    };
    const since = new Date(Date.now() - (msMap[period] ?? 7 * 86400000));

    const rows = await db
      .select()
      .from(paperPnlSnapshotsTable)
      .where(gte(paperPnlSnapshotsTable.created_at, since))
      .orderBy(paperPnlSnapshotsTable.created_at)
      .limit(500);

    res.json(
      rows.map((r) => ({
        timestamp: isoOrNow(r.created_at),
        cumulative_pnl: r.cumulative_pnl,
        portfolio_value: r.portfolio_value,
        win_rate: r.win_rate,
        total_trades: r.total_trades,
      }))
    );
  } catch (err) {
    req.log.error({ err }, "Failed to get paper chart");
    res.status(500).json({ error: "Internal server error" });
  }
});

// GET /paper/stats
router.get("/paper/stats", async (req, res): Promise<void> => {
  try {
    const [cfg] = await db.select().from(botConfigTable).limit(1);
    const paperCapital = cfg?.paper_capital_usd ?? 1000;

    // Aggregate trades
    const aggResult = await db.execute(sql`
      SELECT
        COUNT(*) FILTER (WHERE action='buy') AS total_trades,
        COUNT(*) FILTER (WHERE action='sell' AND realized_pnl > 0) AS wins,
        COUNT(*) FILTER (WHERE action='sell' AND realized_pnl < 0) AS losses,
        COALESCE(SUM(realized_pnl) FILTER (WHERE realized_pnl IS NOT NULL), 0) AS total_realized,
        COALESCE(AVG(realized_pnl) FILTER (WHERE realized_pnl IS NOT NULL), 0) AS avg_pnl,
        COALESCE(MAX(realized_pnl), 0) AS best_trade,
        COALESCE(MIN(realized_pnl), 0) AS worst_trade,
        COALESCE(SUM(fee_usd), 0) AS total_fees
      FROM paper_trades
    `);
    const agg = aggResult.rows[0] ?? {};

    // Open positions
    const unrResult = await db.execute(sql`
      SELECT COALESCE(SUM(unrealized_pnl), 0) AS unrealized, COUNT(*) AS open_count
      FROM paper_positions WHERE status='open'
    `);
    const unr = unrResult.rows[0] ?? {};

    // By signal type
    const typeResult = await db.execute(sql`
      SELECT signal_type,
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE realized_pnl > 0) AS wins,
        COALESCE(SUM(realized_pnl), 0) AS pnl
      FROM paper_trades WHERE realized_pnl IS NOT NULL GROUP BY signal_type
    `);
    const tradeRows = await db.execute(sql`
      SELECT market_id, market_question, side, action, size_usd, price, slippage, fee_usd,
        realized_pnl, signal_type, executed_at
      FROM paper_trades
      ORDER BY executed_at ASC
    `);
    const positionRows = await db.execute(sql`
      SELECT market_id, market_question, size_usd, opened_at, closed_at, signal_type
      FROM paper_positions
      ORDER BY opened_at ASC
    `);
    const signalRows = await db.execute(sql`
      SELECT signal_type, details
      FROM signals
      ORDER BY detected_at ASC
    `);

    const wins = Number(agg["wins"] ?? 0);
    const losses = Number(agg["losses"] ?? 0);
    const closed = wins + losses;
    const totalRealized = Number(agg["total_realized"] ?? 0);
    const unrealized = Number(unr["unrealized"] ?? 0);
    const cumPnl = totalRealized + unrealized;

    const by_signal_type: Record<string, { total: number; wins: number; pnl: number; win_rate: number }> = {};
    for (const row of typeResult.rows) {
      const t = Number(row["total"]);
      const w = Number(row["wins"]);
      by_signal_type[String(row["signal_type"])] = {
        total: t, wins: w, pnl: Number(row["pnl"]),
        win_rate: t > 0 ? w / t : 0,
      };
    }

    const strategy_reports: Record<string, StrategyReport> = {};
    const rowsByType = new Map<string, Array<Record<string, any>>>();
    for (const row of tradeRows.rows) {
      const key = String(row["signal_type"] ?? "");
      const bucket = rowsByType.get(key) ?? [];
      bucket.push(row);
      rowsByType.set(key, bucket);
    }
    const positionsByType = new Map<string, Array<Record<string, any>>>();
    for (const row of positionRows.rows) {
      const key = String(row["signal_type"] ?? "");
      const bucket = positionsByType.get(key) ?? [];
      bucket.push(row);
      positionsByType.set(key, bucket);
    }
    const signalsByType = new Map<string, Array<Record<string, any>>>();
    for (const row of signalRows.rows) {
      const key = String(row["signal_type"] ?? "");
      const bucket = signalsByType.get(key) ?? [];
      bucket.push(row);
      signalsByType.set(key, bucket);
    }
    for (const key of rowsByType.keys()) {
      strategy_reports[key] = buildStrategyReport(
        key,
        rowsByType.get(key) ?? [],
        positionsByType.get(key) ?? [],
        signalsByType.get(key) ?? [],
        paperCapital,
      );
    }

    // Latest snapshot for win_rate fallback
    const [snap] = await db
      .select()
      .from(paperPnlSnapshotsTable)
      .orderBy(desc(paperPnlSnapshotsTable.created_at))
      .limit(1);

    res.json({
      capital_usd: paperCapital,
      cumulative_pnl: cumPnl,
      portfolio_value: paperCapital + cumPnl,
      total_return_pct: paperCapital > 0 ? (cumPnl / paperCapital) * 100 : 0,
      total_trades: Number(agg["total_trades"] ?? 0),
      open_positions: Number(unr["open_count"] ?? 0),
      wins,
      losses,
      win_rate: closed > 0 ? wins / closed : snap?.win_rate ?? 0,
      avg_pnl_per_trade: Number(agg["avg_pnl"] ?? 0),
      best_trade: Number(agg["best_trade"] ?? 0),
      worst_trade: Number(agg["worst_trade"] ?? 0),
      total_fees: Number(agg["total_fees"] ?? 0),
      unrealized_pnl: unrealized,
      by_signal_type,
      strategy_reports,
    });
  } catch (err) {
    req.log.error({ err }, "Failed to get paper stats");
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
