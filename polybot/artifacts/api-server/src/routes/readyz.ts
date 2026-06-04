import { Router, type IRouter } from "express";
import { pool } from "@workspace/db";

const router: IRouter = Router();

router.get("/readyz", async (_req, res) => {
  try {
    await pool.query("SELECT 1");
    res.status(200).json({ status: "ready", database: "ok" });
  } catch {
    res.status(503).json({ status: "degraded", database: "down" });
  }
});

export default router;
