import { z } from "zod";

export const HealthCheckResponse = z.object({ status: z.string() });

export const ControlBotBody = z.object({ action: z.enum(["start", "stop", "pause", "resume"]) });

export const UpdateBotConfigBody = z.object({
  edge_threshold: z.number().optional(),
  max_position_pct: z.number().optional(),
  daily_loss_limit_pct: z.number().optional(),
  kelly_fraction: z.number().optional(),
  scan_interval_seconds: z.number().int().optional(),
  use_limit_orders: z.boolean().optional(),
  min_liquidity_usd: z.number().optional(),
  max_correlated_exposure_pct: z.number().optional(),
  paper_trading: z.boolean().optional(),
  paper_capital_usd: z.number().optional(),
  reconciliation_enabled: z.boolean().optional(),
  reconciliation_warning_pct: z.number().optional(),
  reconciliation_critical_pct: z.number().optional(),
  reconciliation_warning_usd: z.number().optional(),
  reconciliation_critical_usd: z.number().optional(),
  roda_enabled: z.boolean().optional(),
  lch_enabled: z.boolean().optional(),
  hybrid_enabled: z.boolean().optional(),
  mss2_enabled: z.boolean().optional(),
});

export const GetBotStatusResponse = z.object({
  state: z.enum(["running", "stopped", "paused", "error"]),
  uptime_seconds: z.number().int().nullable(),
  markets_scanned: z.number().int(),
  last_scan_at: z.string().nullable(),
  last_heartbeat_at: z.string().nullable(),
  healthy: z.boolean(),
  error_message: z.string().nullable(),
  pid: z.number().int().nullable(),
});

export const GetBotConfigResponse = z.object({
  id: z.number().int(),
  edge_threshold: z.number(),
  max_position_pct: z.number(),
  daily_loss_limit_pct: z.number(),
  kelly_fraction: z.number(),
  scan_interval_seconds: z.number().int(),
  use_limit_orders: z.boolean(),
  min_liquidity_usd: z.number(),
  max_correlated_exposure_pct: z.number(),
  paper_trading: z.boolean(),
  paper_capital_usd: z.number(),
  reconciliation_enabled: z.boolean(),
  reconciliation_warning_pct: z.number(),
  reconciliation_critical_pct: z.number(),
  reconciliation_warning_usd: z.number(),
  reconciliation_critical_usd: z.number(),
  roda_enabled: z.boolean(),
  lch_enabled: z.boolean(),
  hybrid_enabled: z.boolean(),
  mss2_enabled: z.boolean(),
  updated_at: z.string().nullable().optional(),
});

export const GetLogsQueryParams = z.object({
  limit: z.coerce.number().int().positive().optional(),
  level: z.enum(["debug", "info", "warning", "error", "all"]).optional(),
});

export const GetMarketsQueryParams = z.object({
  status: z.enum(["active", "resolved", "all"]).optional(),
  limit: z.coerce.number().int().positive().optional(),
});

export const GetMarketParams = z.object({ marketId: z.string().min(1) });

export const GetSignalsQueryParams = z.object({
  status: z.enum(["pending", "acted", "dismissed", "all"]).optional(),
  limit: z.coerce.number().int().positive().optional(),
});

export const GetTradesQueryParams = z.object({
  limit: z.coerce.number().int().positive().optional(),
  offset: z.coerce.number().int().nonnegative().optional(),
});

export const GetRiskMetricsQueryParams = z.object({});
export const GetPnlSummaryQueryParams = z.object({});

export const GetPnlChartQueryParams = z.object({
  period: z.enum(["1d", "7d", "30d", "all"]).optional(),
});

export const GetPositionParams = z.object({ positionId: z.coerce.number().int() });
