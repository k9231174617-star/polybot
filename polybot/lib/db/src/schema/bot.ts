import {
  pgTable,
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
});

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
  roda_enabled: boolean("roda_enabled").notNull().default(true),
  lch_enabled: boolean("lch_enabled").notNull().default(true),
  hybrid_enabled: boolean("hybrid_enabled").notNull().default(true),
  mss2_enabled: boolean("mss2_enabled").notNull().default(true),
  updated_at: timestamp("updated_at").defaultNow(),
});

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
});

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
  opened_at: timestamp("opened_at").defaultNow(),
  closed_at: timestamp("closed_at"),
  status: text("status").notNull().default("open"),
});

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
});

export const tradesTable = pgTable("trades", {
  id: serial("id").primaryKey(),
  market_id: text("market_id").notNull(),
  market_question: text("market_question").notNull(),
  side: text("side").notNull(),
  action: text("action").notNull(),
  size_usd: real("size_usd").notNull(),
  price: real("price").notNull(),
  slippage: real("slippage").notNull().default(0),
  fee_usd: real("fee_usd").notNull().default(0),
  realized_pnl: real("realized_pnl"),
  tx_hash: text("tx_hash"),
  executed_at: timestamp("executed_at").defaultNow(),
  order_type: text("order_type").notNull().default("market"),
});

export const pnlSnapshotsTable = pgTable("pnl_snapshots", {
  id: serial("id").primaryKey(),
  cumulative_pnl: real("cumulative_pnl").notNull(),
  portfolio_value: real("portfolio_value").notNull(),
  created_at: timestamp("created_at").defaultNow(),
});

export const logEntriesTable = pgTable("log_entries", {
  id: serial("id").primaryKey(),
  level: text("level").notNull(),
  module: text("module").notNull(),
  message: text("message").notNull(),
  details: jsonb("details"),
  created_at: timestamp("created_at").defaultNow(),
});

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
});

export const paperTradesTable = pgTable("paper_trades", {
  id: serial("id").primaryKey(),
  market_id: text("market_id").notNull(),
  market_question: text("market_question").notNull(),
  side: text("side").notNull(),
  action: text("action").notNull(),
  size_usd: real("size_usd").notNull(),
  price: real("price").notNull(),
  slippage: real("slippage").notNull().default(0),
  fee_usd: real("fee_usd").notNull().default(0),
  realized_pnl: real("realized_pnl"),
  signal_type: text("signal_type").notNull().default("price_discrepancy"),
  executed_at: timestamp("executed_at").defaultNow(),
});

export const paperPnlSnapshotsTable = pgTable("paper_pnl_snapshots", {
  id: serial("id").primaryKey(),
  cumulative_pnl: real("cumulative_pnl").notNull(),
  portfolio_value: real("portfolio_value").notNull(),
  win_rate: real("win_rate").notNull().default(0),
  total_trades: integer("total_trades").notNull().default(0),
  created_at: timestamp("created_at").defaultNow(),
});

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
export type InsertBotConfig = z.infer<typeof insertBotConfigSchema>;
