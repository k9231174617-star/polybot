import { Router } from "express";
import { db } from "@workspace/db";
import { tradesTable } from "@workspace/db";
import { desc } from "drizzle-orm";
import { GetTradesQueryParams } from "@workspace/api-zod";
import { isoOrNow } from "../lib/serialize";

const router = Router();

router.get("/trades", async (req, res) => {
  const parsed = GetTradesQueryParams.safeParse(req.query);
  const { limit = 100, offset = 0 } = parsed.success ? parsed.data : {};

  try {
    const rows = await db
      .select()
      .from(tradesTable)
      .orderBy(desc(tradesTable.executed_at))
      .limit(limit)
      .offset(offset);
    res.json(rows.map((t) => ({
      ...t,
      executed_at: isoOrNow(t.executed_at),
    })));
  } catch (err) {
    req.log.error({ err }, "Failed to get trades");
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
