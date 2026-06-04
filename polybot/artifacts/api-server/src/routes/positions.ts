import { Router } from "express";
import { db } from "@workspace/db";
import { positionsTable } from "@workspace/db";
import { eq, desc } from "drizzle-orm";
import { GetPositionParams } from "@workspace/api-zod";

const router = Router();

const serialize = (p: typeof positionsTable.$inferSelect) => ({
  ...p,
  opened_at: p.opened_at?.toISOString() ?? new Date().toISOString(),
  closed_at: p.closed_at?.toISOString() ?? null,
});

router.get("/positions", async (req, res) => {
  try {
    const rows = await db
      .select()
      .from(positionsTable)
      .where(eq(positionsTable.status, "open"))
      .orderBy(desc(positionsTable.opened_at));
    res.json(rows.map(serialize));
  } catch (err) {
    req.log.error({ err }, "Failed to get positions");
    res.status(500).json({ error: "Internal server error" });
  }
});

router.get("/positions/:positionId", async (req, res): Promise<void> => {
  const parsed = GetPositionParams.safeParse({
    positionId: Number(req.params.positionId),
  });
  if (!parsed.success) { res.status(400).json({ error: "Invalid positionId" }); return; }

  try {
    const [row] = await db
      .select()
      .from(positionsTable)
      .where(eq(positionsTable.id, parsed.data.positionId));
    if (!row) { res.status(404).json({ error: "Position not found" }); return; }
    res.json(serialize(row));
  } catch (err) {
    req.log.error({ err }, "Failed to get position");
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
