import { Router } from "express";
import { db } from "@workspace/db";
import { botStateTable, botConfigTable } from "@workspace/db";
import { eq } from "drizzle-orm";
import {
  ControlBotBody,
  UpdateBotConfigBody,
  GetBotStatusResponse,
  GetBotConfigResponse,
} from "@workspace/api-zod";

const router = Router();

router.get("/bot/status", async (req, res): Promise<void> => {
  try {
    const [state] = await db.select().from(botStateTable).orderBy(botStateTable.id).limit(1);
    if (!state) {
      const data = GetBotStatusResponse.parse({
        state: "stopped",
        uptime_seconds: null,
        markets_scanned: 0,
        last_scan_at: null,
        error_message: null,
        pid: null,
      });
      res.json(data);
      return;
    }
    const uptime = state.started_at && state.state === "running"
      ? Math.floor((Date.now() - new Date(state.started_at).getTime()) / 1000)
      : null;
    const data = GetBotStatusResponse.parse({
      state: state.state,
      uptime_seconds: uptime,
      markets_scanned: state.markets_scanned,
      last_scan_at: state.updated_at?.toISOString() ?? null,
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
      last_scan_at: updated.updated_at?.toISOString() ?? null,
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
    const data = GetBotConfigResponse.parse({
      ...config,
      updated_at: config.updated_at?.toISOString() ?? new Date().toISOString(),
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
    const data = GetBotConfigResponse.parse({
      ...config,
      updated_at: config.updated_at?.toISOString() ?? new Date().toISOString(),
    });
    res.json(data);
  } catch (err) {
    req.log.error({ err }, "Failed to update bot config");
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
