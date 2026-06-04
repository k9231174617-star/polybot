import { db } from "@workspace/db";
import { sql } from "drizzle-orm";

const SCHEMA_STATEMENTS = [
  sql`
    CREATE TABLE IF NOT EXISTS bot_state (
      id SERIAL PRIMARY KEY,
      state TEXT NOT NULL DEFAULT 'stopped',
      started_at TIMESTAMP,
      markets_scanned INTEGER NOT NULL DEFAULT 0,
      error_message TEXT,
      pid INTEGER,
      updated_at TIMESTAMP DEFAULT NOW()
    )
  `,
  sql`
    CREATE TABLE IF NOT EXISTS bot_config (
      id SERIAL PRIMARY KEY,
      edge_threshold REAL NOT NULL DEFAULT 0.05,
      max_position_pct REAL NOT NULL DEFAULT 0.05,
      daily_loss_limit_pct REAL NOT NULL DEFAULT 0.03,
      kelly_fraction REAL NOT NULL DEFAULT 0.25,
      scan_interval_seconds INTEGER NOT NULL DEFAULT 30,
      use_limit_orders BOOLEAN NOT NULL DEFAULT TRUE,
      min_liquidity_usd REAL NOT NULL DEFAULT 1000,
      max_correlated_exposure_pct REAL NOT NULL DEFAULT 0.15,
      paper_trading BOOLEAN NOT NULL DEFAULT TRUE,
      paper_capital_usd REAL NOT NULL DEFAULT 1000,
      roda_enabled BOOLEAN NOT NULL DEFAULT TRUE,
      roda_mode TEXT NOT NULL DEFAULT 'auto',
      lch_enabled BOOLEAN NOT NULL DEFAULT TRUE,
      hybrid_enabled BOOLEAN NOT NULL DEFAULT TRUE,
      mss2_enabled BOOLEAN NOT NULL DEFAULT TRUE,
      roda_min_confidence REAL NOT NULL DEFAULT 0.95,
      roda_min_sources INTEGER NOT NULL DEFAULT 3,
      roda_divergence_min_edge REAL NOT NULL DEFAULT 0.06,
      roda_divergence_min_confidence REAL NOT NULL DEFAULT 0.60,
      roda_divergence_min_sources INTEGER NOT NULL DEFAULT 2,
      lch_min_z_score REAL NOT NULL DEFAULT 2.5,
      lch_min_recovery_probability REAL NOT NULL DEFAULT 0.70,
      lch_max_wash_trading_score REAL NOT NULL DEFAULT 0.72,
      mss2_min_spread_bps REAL NOT NULL DEFAULT 35.0,
      mss2_min_expected_profit_bps REAL NOT NULL DEFAULT 35.0,
      mss2_max_adverse_selection_score REAL NOT NULL DEFAULT 0.65,
      mss2_min_fill_probability_proxy REAL NOT NULL DEFAULT 0.30,
      mss2_max_queue_pressure REAL NOT NULL DEFAULT 0.75,
      updated_at TIMESTAMP DEFAULT NOW()
    )
  `,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS roda_enabled BOOLEAN NOT NULL DEFAULT TRUE`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS roda_mode TEXT NOT NULL DEFAULT 'auto'`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS lch_enabled BOOLEAN NOT NULL DEFAULT TRUE`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS hybrid_enabled BOOLEAN NOT NULL DEFAULT TRUE`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS mss2_enabled BOOLEAN NOT NULL DEFAULT TRUE`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS roda_min_confidence REAL NOT NULL DEFAULT 0.95`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS roda_min_sources INTEGER NOT NULL DEFAULT 3`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS roda_divergence_min_edge REAL NOT NULL DEFAULT 0.06`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS roda_divergence_min_confidence REAL NOT NULL DEFAULT 0.60`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS roda_divergence_min_sources INTEGER NOT NULL DEFAULT 2`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS lch_min_z_score REAL NOT NULL DEFAULT 2.5`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS lch_min_recovery_probability REAL NOT NULL DEFAULT 0.70`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS lch_max_wash_trading_score REAL NOT NULL DEFAULT 0.72`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS mss2_min_spread_bps REAL NOT NULL DEFAULT 35.0`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS mss2_min_expected_profit_bps REAL NOT NULL DEFAULT 35.0`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS mss2_max_adverse_selection_score REAL NOT NULL DEFAULT 0.65`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS mss2_min_fill_probability_proxy REAL NOT NULL DEFAULT 0.30`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS mss2_max_queue_pressure REAL NOT NULL DEFAULT 0.75`,
  sql`
    CREATE TABLE IF NOT EXISTS markets (
      id TEXT PRIMARY KEY,
      question TEXT NOT NULL,
      category TEXT DEFAULT '',
      market_price REAL NOT NULL,
      model_probability REAL,
      edge REAL,
      volume_24h REAL NOT NULL DEFAULT 0,
      liquidity_usd REAL NOT NULL DEFAULT 0,
      sentiment_score REAL,
      end_date TIMESTAMP,
      status TEXT NOT NULL DEFAULT 'active',
      last_updated TIMESTAMP DEFAULT NOW()
    )
  `,
  sql`
    CREATE TABLE IF NOT EXISTS positions (
      id SERIAL PRIMARY KEY,
      market_id TEXT NOT NULL,
      market_question TEXT NOT NULL,
      side TEXT NOT NULL,
      size_usd REAL NOT NULL,
      entry_price REAL NOT NULL,
      current_price REAL NOT NULL,
      unrealized_pnl REAL NOT NULL DEFAULT 0,
      unrealized_pnl_pct REAL NOT NULL DEFAULT 0,
      entry_edge REAL NOT NULL DEFAULT 0,
      current_edge REAL,
      opened_at TIMESTAMP DEFAULT NOW(),
      closed_at TIMESTAMP,
      status TEXT NOT NULL DEFAULT 'open'
    )
  `,
  sql`
    CREATE TABLE IF NOT EXISTS signals (
      id SERIAL PRIMARY KEY,
      market_id TEXT NOT NULL,
      market_question TEXT NOT NULL,
      signal_type TEXT NOT NULL,
      direction TEXT NOT NULL,
      market_price REAL NOT NULL,
      model_probability REAL NOT NULL,
      edge REAL NOT NULL,
      kelly_size_usd REAL NOT NULL,
      confidence REAL NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'pending',
      detected_at TIMESTAMP DEFAULT NOW(),
      acted_at TIMESTAMP,
      details JSONB
    )
  `,
  sql`
    CREATE TABLE IF NOT EXISTS trades (
      id SERIAL PRIMARY KEY,
      market_id TEXT NOT NULL,
      market_question TEXT NOT NULL,
      signal_id INTEGER,
      side TEXT NOT NULL,
      action TEXT NOT NULL,
      size_usd REAL NOT NULL,
      price REAL NOT NULL,
      slippage REAL NOT NULL DEFAULT 0,
      fee_usd REAL NOT NULL DEFAULT 0,
      realized_pnl REAL,
      tx_hash TEXT,
      executed_at TIMESTAMP DEFAULT NOW(),
      order_type TEXT NOT NULL DEFAULT 'market'
    )
  `,
  sql`
    CREATE TABLE IF NOT EXISTS pnl_snapshots (
      id SERIAL PRIMARY KEY,
      cumulative_pnl REAL NOT NULL,
      portfolio_value REAL NOT NULL,
      created_at TIMESTAMP DEFAULT NOW()
    )
  `,
  sql`
    CREATE TABLE IF NOT EXISTS log_entries (
      id SERIAL PRIMARY KEY,
      level TEXT NOT NULL,
      module TEXT NOT NULL,
      message TEXT NOT NULL,
      details JSONB,
      created_at TIMESTAMP DEFAULT NOW()
    )
  `,
  sql`
    CREATE TABLE IF NOT EXISTS latency_events (
      id SERIAL PRIMARY KEY,
      signal_id INTEGER,
      market_id TEXT NOT NULL,
      signal_type TEXT NOT NULL,
      stage TEXT NOT NULL,
      duration_ms REAL NOT NULL,
      started_at TIMESTAMP NOT NULL,
      finished_at TIMESTAMP NOT NULL,
      details JSONB,
      created_at TIMESTAMP DEFAULT NOW()
    )
  `,
  sql`
    CREATE TABLE IF NOT EXISTS paper_positions (
      id SERIAL PRIMARY KEY,
      market_id TEXT NOT NULL,
      market_question TEXT NOT NULL,
      side TEXT NOT NULL,
      size_usd REAL NOT NULL,
      entry_price REAL NOT NULL,
      current_price REAL NOT NULL,
      unrealized_pnl REAL NOT NULL DEFAULT 0,
      unrealized_pnl_pct REAL NOT NULL DEFAULT 0,
      entry_edge REAL NOT NULL DEFAULT 0,
      signal_type TEXT NOT NULL DEFAULT 'price_discrepancy',
      confidence REAL NOT NULL DEFAULT 0,
      opened_at TIMESTAMP DEFAULT NOW(),
      closed_at TIMESTAMP,
      status TEXT NOT NULL DEFAULT 'open'
    )
  `,
  sql`
    CREATE TABLE IF NOT EXISTS paper_trades (
      id SERIAL PRIMARY KEY,
      market_id TEXT NOT NULL,
      market_question TEXT NOT NULL,
      signal_id INTEGER,
      side TEXT NOT NULL,
      action TEXT NOT NULL,
      size_usd REAL NOT NULL,
      price REAL NOT NULL,
      slippage REAL NOT NULL DEFAULT 0,
      fee_usd REAL NOT NULL DEFAULT 0,
      realized_pnl REAL,
      signal_type TEXT NOT NULL DEFAULT 'price_discrepancy',
      executed_at TIMESTAMP DEFAULT NOW()
    )
  `,
  sql`
    CREATE TABLE IF NOT EXISTS paper_pnl_snapshots (
      id SERIAL PRIMARY KEY,
      cumulative_pnl REAL NOT NULL,
      portfolio_value REAL NOT NULL,
      win_rate REAL NOT NULL DEFAULT 0,
      total_trades INTEGER NOT NULL DEFAULT 0,
      created_at TIMESTAMP DEFAULT NOW()
    )
  `,
  sql`ALTER TABLE trades ADD COLUMN IF NOT EXISTS signal_id INTEGER`,
  sql`ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS signal_id INTEGER`,
  sql`ALTER TABLE signals ADD COLUMN IF NOT EXISTS details JSONB`,
  sql`CREATE INDEX IF NOT EXISTS trades_signal_id_idx ON trades (signal_id)`,
  sql`CREATE INDEX IF NOT EXISTS latency_events_created_at_idx ON latency_events (created_at DESC)`,
  sql`CREATE INDEX IF NOT EXISTS latency_events_stage_created_at_idx ON latency_events (stage, created_at DESC)`,
  sql`CREATE INDEX IF NOT EXISTS latency_events_signal_type_created_at_idx ON latency_events (signal_type, created_at DESC)`,
  sql`CREATE INDEX IF NOT EXISTS paper_trades_signal_id_idx ON paper_trades (signal_id)`,
] as const;

export async function ensureDatabaseSchema(): Promise<void> {
  for (const statement of SCHEMA_STATEMENTS) {
    await db.execute(statement);
  }
}
