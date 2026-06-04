import {
  pgTable,
  index,
  serial,
  text,
  real,
  integer,
  boolean,
  timestamp,
  jsonb,
} from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod/v4";

export const botStateTable = pgTable("bot_state", {
  id: serial("id").primaryKey(),
  state: text("state").notNull().default("stopped"),
  started_at: timestamp("started_at"),
  markets_scanned: integer("markets_scanned").notNull().default(0),
  error_message: text("error_message"),
  pid: integer("pid"),
  updated_at: timestamp("updated_at").defaultNow(),
}, (t) => ({
  stateUpdatedAtIdx: index("bot_state_state_updated_at_idx").on(t.state, t.updated_at),
}));

export const botConfigTable = pgTable("bot_config", {
  id: serial("id").primaryKey(),
  edge_threshold: real("edge_threshold").notNull().default(0.05),
  max_position_pct: real("max_position_pct").notNull().default(0.05),
  daily_loss_limit_pct: real("daily_loss_limit_pct").notNull().default(0.03),
  kelly_fraction: real("kelly_fraction").notNull().default(0.25),
  scan_interval_seconds: integer("scan_interval_seconds").notNull().default(30),
  use_limit_orders: boolean("use_limit_orders").notNull().default(true),
  min_liquidity_usd: real("min_liquidity_usd").notNull().default(1000),
  max_correlated_exposure_pct: real("max_correlated_exposure_pct").notNull().default(0.15),
  paper_trading: boolean("paper_trading").notNull().default(true),
  paper_capital_usd: real("paper_capital_usd").notNull().default(1000),
  retention_scan_interval: integer("retention_scan_interval").notNull().default(48),
  reconciliation_enabled: boolean("reconciliation_enabled").notNull().default(true),
  reconciliation_warning_pct: real("reconciliation_warning_pct").notNull().default(0.01),
  reconciliation_critical_pct: real("reconciliation_critical_pct").notNull().default(0.03),
  reconciliation_warning_usd: real("reconciliation_warning_usd").notNull().default(5.0),
  reconciliation_critical_usd: real("reconciliation_critical_usd").notNull().default(25.0),
  roda_enabled: boolean("roda_enabled").notNull().default(true),
  roda_mode: text("roda_mode").notNull().default("auto"),
  lch_enabled: boolean("lch_enabled").notNull().default(true),
  hybrid_enabled: boolean("hybrid_enabled").notNull().default(true),
  mss2_enabled: boolean("mss2_enabled").notNull().default(true),
  roda_min_confidence: real("roda_min_confidence").notNull().default(0.95),
  roda_min_sources: integer("roda_min_sources").notNull().default(3),
  roda_divergence_min_edge: real("roda_divergence_min_edge").notNull().default(0.06),
  roda_divergence_min_confidence: real("roda_divergence_min_confidence").notNull().default(0.60),
  roda_divergence_min_sources: integer("roda_divergence_min_sources").notNull().default(2),
  lch_min_z_score: real("lch_min_z_score").notNull().default(2.5),
  lch_min_recovery_probability: real("lch_min_recovery_probability").notNull().default(0.70),
  lch_max_wash_trading_score: real("lch_max_wash_trading_score").notNull().default(0.72),
  mss2_min_spread_bps: real("mss2_min_spread_bps").notNull().default(35.0),
  mss2_min_expected_profit_bps: real("mss2_min_expected_profit_bps").notNull().default(35.0),
  mss2_max_adverse_selection_score: real("mss2_max_adverse_selection_score").notNull().default(0.65),
  mss2_min_fill_probability_proxy: real("mss2_min_fill_probability_proxy").notNull().default(0.30),
  mss2_max_queue_pressure: real("mss2_max_queue_pressure").notNull().default(0.75),
  updated_at: timestamp("updated_at").defaultNow(),
}, (t) => ({
  updatedAtIdx: index("bot_config_updated_at_idx").on(t.updated_at),
}));

export const marketsTable = pgTable("markets", {
  id: text("id").primaryKey(),
  question: text("question").notNull(),
  category: text("category").default(""),
  market_price: real("market_price").notNull(),
  model_probability: real("model_probability"),
  edge: real("edge"),
  volume_24h: real("volume_24h").notNull().default(0),
  liquidity_usd: real("liquidity_usd").notNull().default(0),
  sentiment_score: real("sentiment_score"),
  end_date: timestamp("end_date"),
  status: text("status").notNull().default("active"),
  last_updated: timestamp("last_updated").defaultNow(),
}, (t) => ({
  statusEndDateIdx: index("markets_status_end_date_idx").on(t.status, t.end_date),
  categoryLastUpdatedIdx: index("markets_category_last_updated_idx").on(t.category, t.last_updated),
}));

export const positionsTable = pgTable("positions", {
  id: serial("id").primaryKey(),
  market_id: text("market_id").notNull(),
  market_question: text("market_question").notNull(),
  side: text("side").notNull(),
  size_usd: real("size_usd").notNull(),
  entry_price: real("entry_price").notNull(),
  current_price: real("current_price").notNull(),
  unrealized_pnl: real("unrealized_pnl").notNull().default(0),
  unrealized_pnl_pct: real("unrealized_pnl_pct").notNull().default(0),
  entry_edge: real("entry_edge").notNull().default(0),
  current_edge: real("current_edge"),
  order_id: text("order_id"),
  order_status: text("order_status").notNull().default("open"),
  filled_size_usd: real("filled_size_usd").notNull().default(0),
  remaining_size_usd: real("remaining_size_usd").notNull().default(0),
  opened_at: timestamp("opened_at").defaultNow(),
  closed_at: timestamp("closed_at"),
  status: text("status").notNull().default("open"),
}, (t) => ({
  statusMarketIdIdx: index("positions_status_market_id_idx").on(t.status, t.market_id),
  orderIdIdx: index("positions_order_id_idx").on(t.order_id),
}));

export const signalsTable = pgTable("signals", {
  id: serial("id").primaryKey(),
  market_id: text("market_id").notNull(),
  market_question: text("market_question").notNull(),
  signal_type: text("signal_type").notNull(),
  direction: text("direction").notNull(),
  market_price: real("market_price").notNull(),
  model_probability: real("model_probability").notNull(),
  edge: real("edge").notNull(),
  kelly_size_usd: real("kelly_size_usd").notNull(),
  confidence: real("confidence").notNull().default(0),
  status: text("status").notNull().default("pending"),
  detected_at: timestamp("detected_at").defaultNow(),
  acted_at: timestamp("acted_at"),
  details: jsonb("details"),
}, (t) => ({
  statusDetectedAtIdx: index("signals_status_detected_at_idx").on(t.status, t.detected_at),
  marketIdIdx: index("signals_market_id_idx").on(t.market_id),
}));

export const tradesTable = pgTable("trades", {
  id: serial("id").primaryKey(),
  market_id: text("market_id").notNull(),
  market_question: text("market_question").notNull(),
  signal_id: integer("signal_id"),
  side: text("side").notNull(),
  action: text("action").notNull(),
  size_usd: real("size_usd").notNull(),
  price: real("price").notNull(),
  slippage: real("slippage").notNull().default(0),
  fee_usd: real("fee_usd").notNull().default(0),
  realized_pnl: real("realized_pnl"),
  tx_hash: text("tx_hash"),
  order_id: text("order_id"),
  order_status: text("order_status").notNull().default("filled"),
  filled_size_usd: real("filled_size_usd").notNull().default(0),
  remaining_size_usd: real("remaining_size_usd").notNull().default(0),
  executed_at: timestamp("executed_at").defaultNow(),
  order_type: text("order_type").notNull().default("market"),
}, (t) => ({
  orderIdIdx: index("trades_order_id_idx").on(t.order_id),
  statusExecutedAtIdx: index("trades_status_executed_at_idx").on(t.order_status, t.executed_at),
  marketIdIdx: index("trades_market_id_idx").on(t.market_id),
  signalIdIdx: index("trades_signal_id_idx").on(t.signal_id),
}));

export const pnlSnapshotsTable = pgTable("pnl_snapshots", {
  id: serial("id").primaryKey(),
  cumulative_pnl: real("cumulative_pnl").notNull(),
  portfolio_value: real("portfolio_value").notNull(),
  created_at: timestamp("created_at").defaultNow(),
}, (t) => ({
  createdAtIdx: index("pnl_snapshots_created_at_idx").on(t.created_at),
}));

export const logEntriesTable = pgTable("log_entries", {
  id: serial("id").primaryKey(),
  level: text("level").notNull(),
  module: text("module").notNull(),
  message: text("message").notNull(),
  details: jsonb("details"),
  created_at: timestamp("created_at").defaultNow(),
}, (t) => ({
  createdAtIdx: index("log_entries_created_at_idx").on(t.created_at),
}));

export const latencyEventsTable = pgTable("latency_events", {
  id: serial("id").primaryKey(),
  signal_id: integer("signal_id"),
  market_id: text("market_id").notNull(),
  signal_type: text("signal_type").notNull(),
  stage: text("stage").notNull(),
  duration_ms: real("duration_ms").notNull(),
  started_at: timestamp("started_at").notNull(),
  finished_at: timestamp("finished_at").notNull(),
  details: jsonb("details"),
  created_at: timestamp("created_at").defaultNow(),
}, (t) => ({
  createdAtIdx: index("latency_events_created_at_idx").on(t.created_at),
  stageCreatedAtIdx: index("latency_events_stage_created_at_idx").on(t.stage, t.created_at),
  signalTypeCreatedAtIdx: index("latency_events_signal_type_created_at_idx").on(t.signal_type, t.created_at),
}));

// ── Paper Trading ───────────────────────────────────────────────────────────

export const paperPositionsTable = pgTable("paper_positions", {
  id: serial("id").primaryKey(),
  market_id: text("market_id").notNull(),
  market_question: text("market_question").notNull(),
  side: text("side").notNull(),
  size_usd: real("size_usd").notNull(),
  entry_price: real("entry_price").notNull(),
  current_price: real("current_price").notNull(),
  unrealized_pnl: real("unrealized_pnl").notNull().default(0),
  unrealized_pnl_pct: real("unrealized_pnl_pct").notNull().default(0),
  entry_edge: real("entry_edge").notNull().default(0),
  signal_type: text("signal_type").notNull().default("price_discrepancy"),
  confidence: real("confidence").notNull().default(0),
  opened_at: timestamp("opened_at").defaultNow(),
  closed_at: timestamp("closed_at"),
  status: text("status").notNull().default("open"),
}, (t) => ({
  statusOpenedAtIdx: index("paper_positions_status_opened_at_idx").on(t.status, t.opened_at),
  marketIdIdx: index("paper_positions_market_id_idx").on(t.market_id),
}));

export const paperTradesTable = pgTable("paper_trades", {
  id: serial("id").primaryKey(),
  market_id: text("market_id").notNull(),
  market_question: text("market_question").notNull(),
  signal_id: integer("signal_id"),
  side: text("side").notNull(),
  action: text("action").notNull(),
  size_usd: real("size_usd").notNull(),
  price: real("price").notNull(),
  slippage: real("slippage").notNull().default(0),
  fee_usd: real("fee_usd").notNull().default(0),
  realized_pnl: real("realized_pnl"),
  signal_type: text("signal_type").notNull().default("price_discrepancy"),
  order_id: text("order_id"),
  order_status: text("order_status").notNull().default("filled"),
  filled_size_usd: real("filled_size_usd").notNull().default(0),
  remaining_size_usd: real("remaining_size_usd").notNull().default(0),
  executed_at: timestamp("executed_at").defaultNow(),
}, (t) => ({
  orderIdIdx: index("paper_trades_order_id_idx").on(t.order_id),
  signalTypeExecutedAtIdx: index("paper_trades_signal_type_executed_at_idx").on(t.signal_type, t.executed_at),
  signalIdIdx: index("paper_trades_signal_id_idx").on(t.signal_id),
}));

export const paperPnlSnapshotsTable = pgTable("paper_pnl_snapshots", {
  id: serial("id").primaryKey(),
  cumulative_pnl: real("cumulative_pnl").notNull(),
  portfolio_value: real("portfolio_value").notNull(),
  win_rate: real("win_rate").notNull().default(0),
  total_trades: integer("total_trades").notNull().default(0),
  created_at: timestamp("created_at").defaultNow(),
}, (t) => ({
  createdAtIdx: index("paper_pnl_snapshots_created_at_idx").on(t.created_at),
}));

export const balanceReconciliationSnapshotsTable = pgTable("balance_reconciliation_snapshots", {
  id: serial("id").primaryKey(),
  source: text("source").notNull().default("live"),
  live_collateral_balance: real("live_collateral_balance").notNull().default(0),
  internal_cash_estimate: real("internal_cash_estimate").notNull().default(0),
  internal_equity_estimate: real("internal_equity_estimate").notNull().default(0),
  discrepancy_usd: real("discrepancy_usd").notNull().default(0),
  discrepancy_pct: real("discrepancy_pct").notNull().default(0),
  status: text("status").notNull().default("ok"),
  details: jsonb("details"),
  created_at: timestamp("created_at").defaultNow(),
}, (t) => ({
  createdAtIdx: index("balance_reconciliation_created_at_idx").on(t.created_at),
}));

// ── Schemas & types ─────────────────────────────────────────────────────────

export const insertBotConfigSchema = createInsertSchema(botConfigTable).omit({ id: true, updated_at: true });
export const insertMarketSchema = createInsertSchema(marketsTable);
export const insertPositionSchema = createInsertSchema(positionsTable).omit({ id: true });
export const insertSignalSchema = createInsertSchema(signalsTable).omit({ id: true });
export const insertTradeSchema = createInsertSchema(tradesTable).omit({ id: true });
export const insertLogEntrySchema = createInsertSchema(logEntriesTable).omit({ id: true });
export const insertPaperTradeSchema = createInsertSchema(paperTradesTable).omit({ id: true });
export const insertPaperPositionSchema = createInsertSchema(paperPositionsTable).omit({ id: true });

export type BotState = typeof botStateTable.$inferSelect;
export type BotConfig = typeof botConfigTable.$inferSelect;
export type Market = typeof marketsTable.$inferSelect;
export type Position = typeof positionsTable.$inferSelect;
export type Signal = typeof signalsTable.$inferSelect;
export type Trade = typeof tradesTable.$inferSelect;
export type PnlSnapshot = typeof pnlSnapshotsTable.$inferSelect;
export type LogEntry = typeof logEntriesTable.$inferSelect;
export type PaperPosition = typeof paperPositionsTable.$inferSelect;
export type PaperTrade = typeof paperTradesTable.$inferSelect;
export type PaperPnlSnapshot = typeof paperPnlSnapshotsTable.$inferSelect;
export type BalanceReconciliationSnapshot = typeof balanceReconciliationSnapshotsTable.$inferSelect;
export type InsertBotConfig = z.infer<typeof insertBotConfigSchema>;
