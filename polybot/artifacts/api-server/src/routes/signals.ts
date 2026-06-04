import { Router } from "express";
import { db } from "@workspace/db";
import { signalsTable } from "@workspace/db";
import { eq, desc } from "drizzle-orm";
import { GetSignalsQueryParams } from "@workspace/api-zod";
import { isoOrNow, isoOrNull } from "../lib/serialize";

const router = Router();

const serialize = (s: typeof signalsTable.$inferSelect) => ({
  ...s,
  detected_at: isoOrNow(s.detected_at),
  acted_at: isoOrNull(s.acted_at),
});

router.get("/signals", async (req, res) => {
  const parsed = GetSignalsQueryParams.safeParse(req.query);
  const { status = "pending", limit = 50 } = parsed.success ? parsed.data : {};

  try {
    let query = db.select().from(signalsTable).$dynamic();
    if (status !== "all") {
      query = query.where(eq(signalsTable.status, status));
    }
    const rows = await query.orderBy(desc(signalsTable.detected_at)).limit(limit);
    res.json(rows.map(serialize));
  } catch (err) {
    req.log.error({ err }, "Failed to get signals");
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
