import { Router, type IRouter } from "express";
import healthRouter from "./health";
import botRouter from "./bot";
import marketsRouter from "./markets";
import positionsRouter from "./positions";
import signalsRouter from "./signals";
import tradesRouter from "./trades";
import riskRouter from "./risk";
import pnlRouter from "./pnl";
import dashboardRouter from "./dashboard";
import logsRouter from "./logs";
import paperRouter from "./paper";

const router: IRouter = Router();

router.use(healthRouter);
router.use(botRouter);
router.use(marketsRouter);
router.use(positionsRouter);
router.use(signalsRouter);
router.use(tradesRouter);
router.use(riskRouter);
router.use(pnlRouter);
router.use(dashboardRouter);
router.use(logsRouter);
router.use(paperRouter);

export default router;
