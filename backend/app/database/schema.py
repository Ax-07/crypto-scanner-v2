"""Schéma SQLite versionné des données OHLCV."""

SCHEMA_VERSION = 9

MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS candles (
    exchange_id TEXT NOT NULL,
    market_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open_time INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    close_time INTEGER,
    is_closed INTEGER NOT NULL DEFAULT 1 CHECK (is_closed IN (0, 1)),
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (exchange_id, market_type, symbol, timeframe, open_time)
);
CREATE INDEX IF NOT EXISTS idx_candles_market_time
ON candles (exchange_id, market_type, symbol, timeframe, open_time DESC);
"""

MIGRATION_2 = """
CREATE TABLE IF NOT EXISTS markets (
    exchange_id TEXT NOT NULL,
    market_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    base TEXT NOT NULL,
    quote TEXT NOT NULL,
    exchange_market_id TEXT,
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    spot INTEGER NOT NULL CHECK (spot IN (0, 1)),
    margin INTEGER,
    contract INTEGER,
    amount_precision REAL,
    price_precision REAL,
    min_amount REAL,
    min_cost REAL,
    first_seen_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    deactivated_at INTEGER,
    raw_metadata_json TEXT,
    PRIMARY KEY (exchange_id, market_type, symbol)
);
CREATE INDEX IF NOT EXISTS idx_markets_quote_active
ON markets (exchange_id, market_type, quote, active, symbol);

CREATE TABLE IF NOT EXISTS candle_sync_state (
    exchange_id TEXT NOT NULL,
    market_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_from INTEGER,
    requested_to INTEGER,
    earliest_available_time INTEGER,
    latest_available_time INTEGER,
    next_since INTEGER,
    pages_downloaded INTEGER NOT NULL DEFAULT 0,
    candles_downloaded INTEGER NOT NULL DEFAULT 0,
    candles_upserted INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    gap_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    started_at INTEGER,
    completed_at INTEGER,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (exchange_id, market_type, symbol, timeframe)
);
CREATE INDEX IF NOT EXISTS idx_sync_state_status
ON candle_sync_state (exchange_id, market_type, status, updated_at);

CREATE TABLE IF NOT EXISTS backfill_runs (
    id TEXT PRIMARY KEY,
    exchange_id TEXT NOT NULL,
    market_type TEXT NOT NULL,
    quote TEXT NOT NULL,
    status TEXT NOT NULL,
    total_targets INTEGER NOT NULL,
    completed_targets INTEGER NOT NULL DEFAULT 0,
    partial_targets INTEGER NOT NULL DEFAULT 0,
    failed_targets INTEGER NOT NULL DEFAULT 0,
    interrupted_targets INTEGER NOT NULL DEFAULT 0,
    total_pages INTEGER NOT NULL DEFAULT 0,
    total_candles INTEGER NOT NULL DEFAULT 0,
    options_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    started_at INTEGER,
    completed_at INTEGER,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_backfill_runs_created
ON backfill_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS candle_gaps (
    exchange_id TEXT NOT NULL,
    market_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    gap_start INTEGER NOT NULL,
    gap_end INTEGER NOT NULL,
    expected_candles INTEGER NOT NULL,
    status TEXT NOT NULL,
    repair_attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    detected_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (
        exchange_id, market_type, symbol, timeframe, gap_start, gap_end
    )
);
CREATE INDEX IF NOT EXISTS idx_candle_gaps_status
ON candle_gaps (exchange_id, market_type, status, updated_at);
"""

MIGRATION_3 = """
CREATE TABLE IF NOT EXISTS candle_history_bounds (
    exchange_id TEXT NOT NULL,
    market_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    earliest_reached INTEGER NOT NULL DEFAULT 0
        CHECK (earliest_reached IN (0, 1)),
    earliest_open_time INTEGER,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (exchange_id, market_type, symbol, timeframe)
);
"""

MIGRATION_4 = """
ALTER TABLE candle_history_bounds RENAME TO candle_history_bounds_legacy;

CREATE TABLE candle_history_bounds (
    exchange_id TEXT NOT NULL,
    market_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    exchange_earliest_time INTEGER,
    exchange_earliest_verified INTEGER NOT NULL DEFAULT 0
        CHECK (exchange_earliest_verified IN (0, 1)),
    has_more_before INTEGER NOT NULL DEFAULT 1
        CHECK (has_more_before IN (0, 1)),
    last_error TEXT,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (exchange_id, market_type, symbol, timeframe)
);

INSERT INTO candle_history_bounds (
    exchange_id, market_type, symbol, timeframe,
    exchange_earliest_time, exchange_earliest_verified,
    has_more_before, last_error, updated_at
)
SELECT exchange_id, market_type, symbol, timeframe,
       NULL, 0, 1, NULL,
       CAST(strftime('%s', 'now') AS INTEGER) * 1000
FROM candle_history_bounds_legacy;

INSERT OR IGNORE INTO candle_history_bounds (
    exchange_id, market_type, symbol, timeframe,
    exchange_earliest_time, exchange_earliest_verified,
    has_more_before, last_error, updated_at
)
SELECT DISTINCT exchange_id, market_type, symbol, timeframe,
       NULL, 0, 1, NULL,
       CAST(strftime('%s', 'now') AS INTEGER) * 1000
FROM candles;

DROP TABLE candle_history_bounds_legacy;
"""

MIGRATION_5 = """
CREATE TABLE IF NOT EXISTS backtest_jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    config_json TEXT NOT NULL,
    progress_json TEXT NOT NULL,
    summary_json TEXT,
    correlations_json TEXT,
    ablations_json TEXT,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    created_at INTEGER NOT NULL,
    started_at INTEGER,
    completed_at INTEGER,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_backtest_jobs_created
ON backtest_jobs (created_at DESC);

CREATE TABLE IF NOT EXISTS backtest_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES backtest_jobs(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    decision_time INTEGER NOT NULL,
    snapshot_status TEXT NOT NULL,
    accepted INTEGER NOT NULL CHECK (accepted IN (0, 1)),
    rejection_stage TEXT,
    rejection_reason TEXT,
    payload_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_backtest_observation_unique
ON backtest_observations (job_id, symbol, decision_time, snapshot_status);
CREATE INDEX IF NOT EXISTS idx_backtest_observation_page
ON backtest_observations (job_id, decision_time, id);

CREATE TABLE IF NOT EXISTS backtest_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES backtest_jobs(id) ON DELETE CASCADE,
    observation_id INTEGER NOT NULL
        REFERENCES backtest_observations(id) ON DELETE CASCADE,
    horizon INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_backtest_outcome_unique
ON backtest_outcomes (observation_id, horizon);
CREATE INDEX IF NOT EXISTS idx_backtest_outcome_job
ON backtest_outcomes (job_id, horizon, observation_id);
"""

MIGRATION_6 = """
CREATE TABLE IF NOT EXISTS experiment_jobs (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_experiment_jobs_created
ON experiment_jobs (created_at DESC);

CREATE TABLE IF NOT EXISTS signal_profiles (
    id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    status TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_signal_profile_name_version
ON signal_profiles (json_extract(profile_json, '$.name'), version);

CREATE TABLE IF NOT EXISTS promotion_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT NOT NULL REFERENCES signal_profiles(id),
    experiment_id TEXT NOT NULL REFERENCES experiment_jobs(id),
    approved INTEGER NOT NULL CHECK (approved IN (0, 1)),
    decision_json TEXT NOT NULL,
    decided_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS shadow_comparisons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    production_profile_id TEXT NOT NULL,
    candidate_profile_id TEXT NOT NULL,
    comparison_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shadow_comparison_page
ON shadow_comparisons (timestamp DESC, id DESC);
"""

MIGRATION_7 = """
CREATE TABLE IF NOT EXISTS backtest_checkpoints (
    job_id TEXT PRIMARY KEY REFERENCES backtest_jobs(id) ON DELETE CASCADE,
    symbol_index INTEGER NOT NULL DEFAULT 0,
    symbol TEXT,
    decision_index INTEGER NOT NULL DEFAULT -1,
    processed INTEGER NOT NULL DEFAULT 0,
    observations INTEGER NOT NULL DEFAULT 0,
    algorithm_version TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    status TEXT NOT NULL,
    checkpoint_json TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_backtest_checkpoint_status
ON backtest_checkpoints (status, updated_at);

CREATE TABLE IF NOT EXISTS backtest_artifacts (
    job_id TEXT NOT NULL REFERENCES backtest_jobs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    artifact_json TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (job_id, kind)
);

CREATE TABLE IF NOT EXISTS signal_profile_lifecycle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT NOT NULL REFERENCES signal_profiles(id) ON DELETE CASCADE,
    from_status TEXT,
    to_status TEXT NOT NULL,
    decision TEXT NOT NULL,
    comment TEXT NOT NULL,
    origin TEXT NOT NULL,
    changed_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_profile_lifecycle_history
ON signal_profile_lifecycle (profile_id, changed_at, id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_shadow_comparison_unique
ON shadow_comparisons (
    symbol, timeframe, timestamp, production_profile_id, candidate_profile_id
);
"""

MIGRATION_8 = """
CREATE TABLE IF NOT EXISTS backtest_portfolio_runs (
    job_id TEXT PRIMARY KEY REFERENCES backtest_jobs(id) ON DELETE CASCADE,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    engine_version TEXT NOT NULL,
    config_fingerprint TEXT NOT NULL,
    quote_asset TEXT NOT NULL,
    config_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    final_cash TEXT NOT NULL,
    final_equity TEXT NOT NULL,
    final_open_position_json TEXT,
    order_count INTEGER NOT NULL CHECK (order_count >= 0),
    execution_count INTEGER NOT NULL CHECK (execution_count >= 0),
    trade_count INTEGER NOT NULL CHECK (trade_count >= 0),
    equity_point_count INTEGER NOT NULL CHECK (equity_point_count >= 0),
    created_at TEXT NOT NULL,
    completed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_portfolio_orders (
    job_id TEXT NOT NULL
        REFERENCES backtest_portfolio_runs(job_id) ON DELETE CASCADE,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    order_id TEXT NOT NULL,
    observation_id TEXT,
    side TEXT NOT NULL,
    intent_time TEXT NOT NULL,
    execution_policy TEXT NOT NULL,
    requested_cash TEXT,
    status TEXT NOT NULL,
    rejection_reason TEXT,
    PRIMARY KEY (job_id, sequence),
    UNIQUE (job_id, order_id)
);

CREATE TABLE IF NOT EXISTS backtest_portfolio_executions (
    job_id TEXT NOT NULL
        REFERENCES backtest_portfolio_runs(job_id) ON DELETE CASCADE,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    execution_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    side TEXT NOT NULL,
    reference_price TEXT NOT NULL,
    execution_price TEXT NOT NULL,
    quantity TEXT NOT NULL,
    gross_notional TEXT NOT NULL,
    fee TEXT NOT NULL,
    slippage_rate TEXT NOT NULL,
    PRIMARY KEY (job_id, sequence),
    UNIQUE (job_id, execution_id),
    FOREIGN KEY (job_id, order_id)
        REFERENCES backtest_portfolio_orders(job_id, order_id)
);
CREATE INDEX IF NOT EXISTS idx_portfolio_executions_order
ON backtest_portfolio_executions (job_id, order_id);

CREATE TABLE IF NOT EXISTS backtest_portfolio_trades (
    job_id TEXT NOT NULL
        REFERENCES backtest_portfolio_runs(job_id) ON DELETE CASCADE,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    trade_id TEXT NOT NULL,
    position_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quote_asset TEXT NOT NULL,
    entry_observation_id TEXT NOT NULL,
    exit_observation_id TEXT,
    entry_order_id TEXT NOT NULL,
    exit_order_id TEXT NOT NULL,
    entry_execution_id TEXT NOT NULL,
    exit_execution_id TEXT NOT NULL,
    entry_time TEXT NOT NULL,
    exit_time TEXT NOT NULL,
    entry_price TEXT NOT NULL,
    exit_price TEXT NOT NULL,
    quantity TEXT NOT NULL,
    entry_fee TEXT NOT NULL,
    exit_fee TEXT NOT NULL,
    gross_exit_proceeds TEXT NOT NULL,
    net_exit_proceeds TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    return_ratio TEXT NOT NULL,
    duration_bars INTEGER NOT NULL CHECK (duration_bars >= 0),
    exit_reason TEXT NOT NULL,
    PRIMARY KEY (job_id, sequence),
    UNIQUE (job_id, trade_id),
    FOREIGN KEY (job_id, entry_execution_id)
        REFERENCES backtest_portfolio_executions(job_id, execution_id),
    FOREIGN KEY (job_id, exit_execution_id)
        REFERENCES backtest_portfolio_executions(job_id, execution_id)
);

CREATE TABLE IF NOT EXISTS backtest_portfolio_equity (
    job_id TEXT NOT NULL
        REFERENCES backtest_portfolio_runs(job_id) ON DELETE CASCADE,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    sequence INTEGER NOT NULL CHECK (sequence >= 0),
    timestamp TEXT NOT NULL,
    cash TEXT NOT NULL,
    position_value TEXT NOT NULL,
    equity TEXT NOT NULL,
    realized_pnl_cumulative TEXT NOT NULL,
    unrealized_pnl TEXT NOT NULL,
    fees_cumulative TEXT NOT NULL,
    drawdown_ratio TEXT NOT NULL,
    exposed INTEGER NOT NULL CHECK (exposed IN (0, 1)),
    PRIMARY KEY (job_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_portfolio_equity_time
ON backtest_portfolio_equity (job_id, timestamp, sequence);
"""

MIGRATION_9 = """
CREATE TABLE IF NOT EXISTS ml_v2_source_claims (
    source_identity TEXT PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE
        REFERENCES backtest_jobs(id) ON DELETE CASCADE,
    algorithm_version TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ml_v2_source_claims_job
ON ml_v2_source_claims (job_id);
"""

MIGRATIONS = {
    1: MIGRATION_1,
    2: MIGRATION_2,
    3: MIGRATION_3,
    4: MIGRATION_4,
    5: MIGRATION_5,
    6: MIGRATION_6,
    7: MIGRATION_7,
    8: MIGRATION_8,
    9: MIGRATION_9,
}
