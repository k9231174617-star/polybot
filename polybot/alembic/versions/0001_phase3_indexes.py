"""phase3 indexes and retention bootstrap

Revision ID: 0001_phase3_indexes
Revises:
Create Date: 2026-06-04
"""
from __future__ import annotations

from alembic import op


revision = "0001_phase3_indexes"
down_revision = None
branch_labels = None
depends_on = None


INDEXES = [
    "CREATE INDEX IF NOT EXISTS bot_state_state_updated_at_idx ON bot_state (state, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS bot_config_updated_at_idx ON bot_config (updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS markets_status_end_date_idx ON markets (status, end_date DESC)",
    "CREATE INDEX IF NOT EXISTS markets_category_last_updated_idx ON markets (category, last_updated DESC)",
    "CREATE INDEX IF NOT EXISTS positions_status_market_id_idx ON positions (status, market_id)",
    "CREATE INDEX IF NOT EXISTS positions_order_id_idx ON positions (order_id)",
    "CREATE INDEX IF NOT EXISTS signals_status_detected_at_idx ON signals (status, detected_at DESC)",
    "CREATE INDEX IF NOT EXISTS signals_market_id_idx ON signals (market_id)",
    "CREATE INDEX IF NOT EXISTS trades_order_id_idx ON trades (order_id)",
    "CREATE INDEX IF NOT EXISTS trades_status_executed_at_idx ON trades (order_status, executed_at DESC)",
    "CREATE INDEX IF NOT EXISTS trades_market_id_idx ON trades (market_id)",
    "CREATE INDEX IF NOT EXISTS paper_positions_status_opened_at_idx ON paper_positions (status, opened_at DESC)",
    "CREATE INDEX IF NOT EXISTS paper_positions_market_id_idx ON paper_positions (market_id)",
    "CREATE INDEX IF NOT EXISTS paper_trades_order_id_idx ON paper_trades (order_id)",
    "CREATE INDEX IF NOT EXISTS paper_trades_signal_type_executed_at_idx ON paper_trades (signal_type, executed_at DESC)",
    "CREATE INDEX IF NOT EXISTS log_entries_created_at_idx ON log_entries (created_at DESC)",
    "CREATE INDEX IF NOT EXISTS pnl_snapshots_created_at_idx ON pnl_snapshots (created_at DESC)",
    "CREATE INDEX IF NOT EXISTS paper_pnl_snapshots_created_at_idx ON paper_pnl_snapshots (created_at DESC)",
]

SCHEMA_FIXUPS = [
    "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS retention_scan_interval INTEGER NOT NULL DEFAULT 48",
]


def upgrade() -> None:
    for statement in SCHEMA_FIXUPS:
        op.execute(statement)
    for statement in INDEXES:
        op.execute(statement)


def downgrade() -> None:
    for statement in [
        "DROP INDEX IF EXISTS bot_state_state_updated_at_idx",
        "DROP INDEX IF EXISTS bot_config_updated_at_idx",
        "DROP INDEX IF EXISTS markets_status_end_date_idx",
        "DROP INDEX IF EXISTS markets_category_last_updated_idx",
        "DROP INDEX IF EXISTS positions_status_market_id_idx",
        "DROP INDEX IF EXISTS positions_order_id_idx",
        "DROP INDEX IF EXISTS signals_status_detected_at_idx",
        "DROP INDEX IF EXISTS signals_market_id_idx",
        "DROP INDEX IF EXISTS trades_order_id_idx",
        "DROP INDEX IF EXISTS trades_status_executed_at_idx",
        "DROP INDEX IF EXISTS trades_market_id_idx",
        "DROP INDEX IF EXISTS paper_positions_status_opened_at_idx",
        "DROP INDEX IF EXISTS paper_positions_market_id_idx",
        "DROP INDEX IF EXISTS paper_trades_order_id_idx",
        "DROP INDEX IF EXISTS paper_trades_signal_type_executed_at_idx",
        "DROP INDEX IF EXISTS log_entries_created_at_idx",
        "DROP INDEX IF EXISTS pnl_snapshots_created_at_idx",
        "DROP INDEX IF EXISTS paper_pnl_snapshots_created_at_idx",
    ]:
        op.execute(statement)
