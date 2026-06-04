import express, { type Express } from "express";
import path from "node:path";
import fs from "node:fs";
import cors from "cors";
import pinoHttp from "pino-http";
import router from "./routes";
import { logger } from "./lib/logger";

const app: Express = express();
const dashboardDist = path.resolve(process.cwd(), "artifacts/dashboard/dist");

app.use(
  pinoHttp({
    logger,
    serializers: {
      req(req) {
        return { id: req.id, method: req.method, url: req.url?.split("?")[0] };
      },
      res(res) {
        return { statusCode: res.statusCode };
      },
    },
  }),
);
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use("/api", router);

if (fs.existsSync(dashboardDist)) {
  app.use(express.static(dashboardDist, { extensions: ["html"] }));
  app.get(/^\/(?!api).*/, (_req, res) => {
    res.sendFile(path.join(dashboardDist, "index.html"));
  });
}

export default app;
