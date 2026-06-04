from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Database
    database_url: str = Field(..., env="DATABASE_URL")

    # Polymarket
    polymarket_api_url: str = "https://gamma-api.polymarket.com"
    polymarket_clob_url: str = "https://clob.polymarket.com"
    polymarket_private_key: str = Field(default="", env="POLYMARKET_PRIVATE_KEY")
    polymarket_api_key: str = Field(default="", env="POLYMARKET_API_KEY")
    polymarket_api_secret: str = Field(default="", env="POLYMARKET_API_SECRET")
    polymarket_api_passphrase: str = Field(default="", env="POLYMARKET_API_PASSPHRASE")
    polymarket_funder_address: str = Field(default="", env="POLYMARKET_FUNDER_ADDRESS")
    polymarket_signature_type: int = Field(default=0, env="POLYMARKET_SIGNATURE_TYPE")

    # Redis (optional cache)
    redis_url: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    use_redis: bool = Field(default=False, env="USE_REDIS")

    # Alerts / watchdog
    telegram_bot_token: str = Field(default="", env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", env="TELEGRAM_CHAT_ID")
    alerts_enabled: bool = Field(default=True, env="ALERTS_ENABLED")
    watchdog_timeout_seconds: int = Field(default=120, env="WATCHDOG_TIMEOUT_SECONDS")
    reconciliation_enabled: bool = Field(default=True, env="RECONCILIATION_ENABLED")
    reconciliation_warning_pct: float = Field(default=0.01, env="RECONCILIATION_WARNING_PCT")
    reconciliation_critical_pct: float = Field(default=0.03, env="RECONCILIATION_CRITICAL_PCT")
    reconciliation_warning_usd: float = Field(default=5.0, env="RECONCILIATION_WARNING_USD")
    reconciliation_critical_usd: float = Field(default=25.0, env="RECONCILIATION_CRITICAL_USD")
    log_retention_days: int = Field(default=30, env="LOG_RETENTION_DAYS")
    snapshot_retention_days: int = Field(default=365, env="SNAPSHOT_RETENTION_DAYS")
    trade_retention_days: int = Field(default=730, env="TRADE_RETENTION_DAYS")
    signal_retention_days: int = Field(default=365, env="SIGNAL_RETENTION_DAYS")
    market_retention_days: int = Field(default=180, env="MARKET_RETENTION_DAYS")

    # Bot behaviour
    dry_run: bool = Field(default=True, env="DRY_RUN")
    initial_capital_usd: float = Field(default=1000.0, env="INITIAL_CAPITAL_USD")
    max_markets_to_scan: int = Field(default=100, env="MAX_MARKETS_TO_SCAN")

    # RODA strategy
    roda_enabled: bool = Field(default=True, env="RODA_ENABLED")
    roda_min_confidence: float = Field(default=0.95, env="RODA_MIN_CONFIDENCE")
    roda_min_age_hours: float = Field(default=1.0, env="RODA_MIN_AGE_HOURS")
    roda_max_age_hours: float = Field(default=24.0, env="RODA_MAX_AGE_HOURS")
    roda_max_entry_price: float = Field(default=0.90, env="RODA_MAX_ENTRY_PRICE")
    roda_min_sources: int = Field(default=3, env="RODA_MIN_SOURCES")
    roda_hold_window_hours: float = Field(default=12.0, env="RODA_HOLD_WINDOW_HOURS")
    roda_max_position_pct: float = Field(default=0.10, env="RODA_MAX_POSITION_PCT")

    # LCH strategy
    lch_enabled: bool = Field(default=True, env="LCH_ENABLED")
    lch_min_hours_to_resolve: float = Field(default=48.0, env="LCH_MIN_HOURS_TO_RESOLVE")
    lch_lookback_hours: float = Field(default=1.0, env="LCH_LOOKBACK_HOURS")
    lch_min_shock_magnitude: float = Field(default=0.08, env="LCH_MIN_SHOCK_MAGNITUDE")
    lch_min_z_score: float = Field(default=2.5, env="LCH_MIN_Z_SCORE")
    lch_min_recovery_probability: float = Field(default=0.70, env="LCH_MIN_RECOVERY_PROBABILITY")
    lch_stop_loss_pct: float = Field(default=0.05, env="LCH_STOP_LOSS_PCT")
    lch_take_profit_pct_of_shock: float = Field(default=0.50, env="LCH_TAKE_PROFIT_PCT_OF_SHOCK")
    lch_max_hold_minutes: int = Field(default=15, env="LCH_MAX_HOLD_MINUTES")
    lch_max_position_pct: float = Field(default=0.075, env="LCH_MAX_POSITION_PCT")
    lch_kelly_fraction: float = Field(default=0.15, env="LCH_KELLY_FRACTION")
    lch_min_position_size_usd: float = Field(default=50.0, env="LCH_MIN_POSITION_SIZE_USD")
    lch_max_position_size_usd: float = Field(default=500.0, env="LCH_MAX_POSITION_SIZE_USD")
    lch_max_daily_trades: int = Field(default=2, env="LCH_MAX_DAILY_TRADES")

    # Hybrid strategy
    hybrid_enabled: bool = Field(default=True, env="HYBRID_ENABLED")

    # MSS2 strategy
    mss2_enabled: bool = Field(default=True, env="MSS2_ENABLED")

    # External data sources
    coingecko_api_key: str = Field(default="", env="COINGECKO_API_KEY")
    news_api_key: str = Field(default="", env="NEWS_API_KEY")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
