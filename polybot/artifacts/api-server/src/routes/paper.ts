import { Router } from "express";
import { db } from "@workspace/db";
import {
  paperPositionsTable,
  paperTradesTable,
  paperPnlSnapshotsTable,
  botConfigTable,
} from "@workspace/db";
import { desc, eq, gte, sql } from "drizzle-orm";
import { isoOrNow, isoOrNull } from "../lib/serialize";

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
    });
  } catch (err) {
    req.log.error({ err }, "Failed to get paper stats");
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
