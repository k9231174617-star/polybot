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
      lch_enabled BOOLEAN NOT NULL DEFAULT TRUE,
      hybrid_enabled BOOLEAN NOT NULL DEFAULT TRUE,
      updated_at TIMESTAMP DEFAULT NOW()
    )
  `,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS roda_enabled BOOLEAN NOT NULL DEFAULT TRUE`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS lch_enabled BOOLEAN NOT NULL DEFAULT TRUE`,
  sql`ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS hybrid_enabled BOOLEAN NOT NULL DEFAULT TRUE`,
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
      acted_at TIMESTAMP
    )
  `,
  sql`
    CREATE TABLE IF NOT EXISTS trades (
      id SERIAL PRIMARY KEY,
      market_id TEXT NOT NULL,
      market_question TEXT NOT NULL,
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
] as const;

export async function ensureDatabaseSchema(): Promise<void> {
  for (const statement of SCHEMA_STATEMENTS) {
    await db.execute(statement);
  }
}
