import { Router } from "express";
import { db } from "@workspace/db";
import { botStateTable, botConfigTable } from "@workspace/db";
import { eq } from "drizzle-orm";
import { isoOrNull, isoOrNow } from "../lib/serialize";
import {
  ControlBotBody,
  UpdateBotConfigBody,
  GetBotStatusResponse,
  GetBotConfigResponse,
} from "@workspace/api-zod";

const router = Router();

const BOT_CONFIG_DEFAULTS = {
  edge_threshold: 0.05,
  max_position_pct: 0.05,
  daily_loss_limit_pct: 0.03,
  kelly_fraction: 0.25,
  scan_interval_seconds: 30,
  use_limit_orders: true,
  min_liquidity_usd: 1000,
  max_correlated_exposure_pct: 0.15,
  paper_trading: true,
  paper_capital_usd: 1000,
  retention_scan_interval: 48,
  reconciliation_enabled: true,
  reconciliation_warning_pct: 0.01,
  reconciliation_critical_pct: 0.03,
  reconciliation_warning_usd: 5,
  reconciliation_critical_usd: 25,
  auto_recalibration_enabled: false,
  auto_recalibration_interval_seconds: 3600,
  auto_recalibration_window_days: 14,
  auto_recalibration_min_trades: 20,
  auto_recalibration_apply_changes: false,
  auto_recalibration_max_adjustment_pct: 0.15,
  roda_enabled: true,
  roda_mode: "auto",
  lch_enabled: true,
  hybrid_enabled: true,
  mss2_enabled: true,
  roda_min_confidence: 0.95,
  roda_min_sources: 3,
  roda_divergence_min_edge: 0.06,
  roda_divergence_min_confidence: 0.6,
  roda_divergence_min_sources: 2,
  lch_min_z_score: 2.5,
  lch_min_recovery_probability: 0.7,
  lch_max_wash_trading_score: 0.72,
  mss2_min_spread_bps: 35,
  mss2_min_expected_profit_bps: 35,
  mss2_max_adverse_selection_score: 0.65,
  mss2_min_fill_probability_proxy: 0.3,
  mss2_max_queue_pressure: 0.75,
};

function normalizeBotConfig(row: Record<string, unknown> | undefined) {
  const nonNull = Object.fromEntries(
    Object.entries(row ?? {}).filter(([, value]) => value !== null && value !== undefined),
  );
  return {
    ...BOT_CONFIG_DEFAULTS,
    ...nonNull,
  };
}

router.get("/bot/status", async (req, res): Promise<void> => {
  try {
    const [state] = await db.select().from(botStateTable).orderBy(botStateTable.id).limit(1);
    const [config] = await db.select().from(botConfigTable).limit(1);
    if (!state) {
      const data = GetBotStatusResponse.parse({
        state: "stopped",
        uptime_seconds: null,
        markets_scanned: 0,
        last_scan_at: null,
        last_heartbeat_at: null,
        healthy: false,
        error_message: null,
        pid: null,
      });
      res.json(data);
      return;
    }
    const uptime = state.started_at && state.state === "running"
      ? Math.floor((Date.now() - new Date(state.started_at).getTime()) / 1000)
      : null;
    const scanInterval = config?.scan_interval_seconds ?? 30;
    const heartbeatAt = isoOrNull(state.updated_at);
    const heartbeatAgeMs = state.updated_at ? Date.now() - new Date(state.updated_at).getTime() : Number.POSITIVE_INFINITY;
    const healthy = state.state === "running" && heartbeatAgeMs <= Math.max(scanInterval * 3000, 120000);
    const data = GetBotStatusResponse.parse({
      state: state.state,
      uptime_seconds: uptime,
      markets_scanned: state.markets_scanned,
      last_scan_at: isoOrNow(state.updated_at),
      last_heartbeat_at: heartbeatAt,
      healthy,
      error_message: state.error_message,
      pid: state.pid,
    });
    res.json(data);
  } catch (err) {
    req.log.error({ err }, "Failed to get bot status");
    res.status(500).json({ error: "Internal server error" });
  }
});

router.post("/bot/control", async (req, res): Promise<void> => {
  const parsed = ControlBotBody.safeParse(req.body);
  if (!parsed.success) { res.status(400).json({ error: "Invalid action" }); return; }

  const { action } = parsed.data;
  const stateMap: Record<string, string> = {
    start: "running",
    stop: "stopped",
    pause: "paused",
    resume: "running",
  };
  const newState = stateMap[action];
  if (!newState) { res.status(400).json({ error: "Unknown action" }); return; }

  try {
    const [existing] = await db.select().from(botStateTable).limit(1);
    let updated;
    if (existing) {
      [updated] = await db
        .update(botStateTable)
        .set({
          state: newState,
          started_at: action === "start" ? new Date() : existing.started_at,
          error_message: null,
          updated_at: new Date(),
        })
        .where(eq(botStateTable.id, existing.id))
        .returning();
    } else {
      [updated] = await db
        .insert(botStateTable)
        .values({ state: newState, started_at: action === "start" ? new Date() : undefined })
        .returning();
    }
    const data = GetBotStatusResponse.parse({
      state: updated.state,
      uptime_seconds: null,
      markets_scanned: updated.markets_scanned,
      last_scan_at: isoOrNull(updated.updated_at),
      last_heartbeat_at: isoOrNull(updated.updated_at),
      healthy: true,
      error_message: updated.error_message,
      pid: updated.pid,
    });
    res.json(data);
  } catch (err) {
    req.log.error({ err }, "Failed to control bot");
    res.status(500).json({ error: "Internal server error" });
  }
});

router.get("/bot/config", async (req, res) => {
  try {
    let [config] = await db.select().from(botConfigTable).limit(1);
    if (!config) {
      [config] = await db.insert(botConfigTable).values({}).returning();
    }
    const normalized = normalizeBotConfig(config as Record<string, unknown> | undefined);
    const data = GetBotConfigResponse.parse({
      ...normalized,
      updated_at: isoOrNow(config.updated_at),
    });
    res.json(data);
  } catch (err) {
    req.log.error({ err }, "Failed to get bot config");
    res.status(500).json({ error: "Internal server error" });
  }
});

router.put("/bot/config", async (req, res): Promise<void> => {
  const parsed = UpdateBotConfigBody.safeParse(req.body);
  if (!parsed.success) { res.status(400).json({ error: parsed.error.message }); return; }

  try {
    const [existing] = await db.select().from(botConfigTable).limit(1);
    let config;
    if (existing) {
      [config] = await db
        .update(botConfigTable)
        .set({ ...parsed.data, updated_at: new Date() })
        .where(eq(botConfigTable.id, existing.id))
        .returning();
    } else {
      [config] = await db.insert(botConfigTable).values(parsed.data).returning();
    }
    const normalized = normalizeBotConfig(config as Record<string, unknown> | undefined);
    const data = GetBotConfigResponse.parse({
      ...normalized,
      updated_at: isoOrNow(config.updated_at),
    });
    res.json(data);
  } catch (err) {
    req.log.error({ err }, "Failed to update bot config");
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
