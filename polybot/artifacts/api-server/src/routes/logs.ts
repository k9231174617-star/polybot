import { Router } from "express";
import { db } from "@workspace/db";
import { logEntriesTable } from "@workspace/db";
import { eq, desc } from "drizzle-orm";
import { GetLogsQueryParams } from "@workspace/api-zod";

const router = Router();

router.get("/logs", async (req, res) => {
  const parsed = GetLogsQueryParams.safeParse(req.query);
  const { limit = 100, level = "all" } = parsed.success ? parsed.data : {};

  try {
    let query = db.select().from(logEntriesTable).$dynamic();
    if (level !== "all") {
      query = query.where(eq(logEntriesTable.level, level));
    }
    const rows = await query.orderBy(desc(logEntriesTable.created_at)).limit(limit);
    res.json(rows.map((l) => ({
      ...l,
      created_at: l.created_at?.toISOString() ?? new Date().toISOString(),
    })));
  } catch (err) {
    req.log.error({ err }, "Failed to get logs");
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
