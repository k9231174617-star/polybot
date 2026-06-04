import { Router } from "express";
import { db } from "@workspace/db";
import { marketsTable } from "@workspace/db";
import { eq, desc } from "drizzle-orm";
import { GetMarketsQueryParams, GetMarketParams } from "@workspace/api-zod";
import { isoOrNow, isoOrNull } from "../lib/serialize";

const router = Router();

router.get("/markets", async (req, res) => {
  const parsed = GetMarketsQueryParams.safeParse(req.query);
  const { status = "active", limit = 50 } = parsed.success ? parsed.data : {};

  try {
    let query = db.select().from(marketsTable).$dynamic();
    if (status !== "all") {
      query = query.where(eq(marketsTable.status, status));
    }
    const rows = await query.orderBy(desc(marketsTable.last_updated)).limit(limit);
    res.json(rows.map((m) => ({
      ...m,
      end_date: isoOrNull(m.end_date),
      last_updated: isoOrNow(m.last_updated),
    })));
  } catch (err) {
    req.log.error({ err }, "Failed to get markets");
    res.status(500).json({ error: "Internal server error" });
  }
});

router.get("/markets/:marketId", async (req, res): Promise<void> => {
  const parsed = GetMarketParams.safeParse(req.params);
  if (!parsed.success) { res.status(400).json({ error: "Invalid marketId" }); return; }

  try {
    const [market] = await db
      .select()
      .from(marketsTable)
      .where(eq(marketsTable.id, parsed.data.marketId));
    if (!market) { res.status(404).json({ error: "Market not found" }); return; }
    res.json({
      ...market,
      end_date: isoOrNull(market.end_date),
      last_updated: isoOrNow(market.last_updated),
    });
  } catch (err) {
    req.log.error({ err }, "Failed to get market");
    res.status(500).json({ error: "Internal server error" });
  }
});

export default router;
