CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 个人访问令牌（PAT）：给机器/agent 长期使用，绑定 user、可命名、可吊销
CREATE TABLE IF NOT EXISTS api_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT DEFAULT '',
    token_hash TEXT NOT NULL UNIQUE,
    token_prefix TEXT DEFAULT '',
    last_used_at TEXT,
    revoked INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_api_tokens_user ON api_tokens (user_id);

CREATE TABLE IF NOT EXISTS funds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    type TEXT DEFAULT '',
    fund_type TEXT DEFAULT '',
    pinyin_abbr TEXT DEFAULT '',
    pinyin_full TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_funds_code ON funds (code);
CREATE INDEX IF NOT EXISTS ix_funds_fund_type ON funds (fund_type);

CREATE TABLE IF NOT EXISTS fund_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type_name TEXT NOT NULL UNIQUE,
    category TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS query_presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    filters_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE (user_id, name)
);
CREATE INDEX IF NOT EXISTS ix_query_presets_user_id ON query_presets (user_id);

CREATE TABLE IF NOT EXISTS fund_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    preset_id INTEGER NOT NULL,
    items_json TEXT DEFAULT '[]',
    fund_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE (user_id, preset_id)
);
CREATE INDEX IF NOT EXISTS ix_fund_snapshots_preset ON fund_snapshots (user_id, preset_id);

CREATE TABLE IF NOT EXISTS fund_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_code TEXT NOT NULL UNIQUE,
    detail_json TEXT DEFAULT '{}',
    fetch_time TEXT,
    trade_date TEXT,
    fund_name TEXT,
    fund_full_name TEXT,
    establish_date TEXT,
    scale REAL,
    fund_company TEXT,
    fund_manager TEXT,
    custodian_bank TEXT,
    fund_type TEXT,
    rating_agency TEXT,
    fund_rating TEXT,
    invest_strategy TEXT,
    invest_target TEXT,
    benchmark TEXT,
    position_stock REAL, position_bond REAL, position_cash REAL, position_other REAL,
    risk_return_ratio_1y REAL, anti_risk_ratio_1y REAL, volatility_1y REAL, sharpe_1y REAL, max_drawdown_1y REAL,
    risk_return_ratio_3y REAL, anti_risk_ratio_3y REAL, volatility_3y REAL, sharpe_3y REAL, max_drawdown_3y REAL,
    risk_return_ratio_5y REAL, anti_risk_ratio_5y REAL, volatility_5y REAL, sharpe_5y REAL, max_drawdown_5y REAL,
    return_since_inception REAL, drawdown_since_inception REAL, rank_since_inception TEXT,
    return_ytd REAL, drawdown_ytd REAL, rank_ytd TEXT,
    return_1m REAL, rank_1m TEXT,
    return_3m REAL, drawdown_3m REAL, rank_3m TEXT,
    return_6m REAL, drawdown_6m REAL, rank_6m TEXT,
    return_1y REAL, drawdown_1y REAL, rank_1y TEXT,
    return_3y REAL, drawdown_3y REAL, rank_3y TEXT,
    return_5y REAL, drawdown_5y REAL, rank_5y TEXT,
    return_2015 REAL, drawdown_2015 REAL, rank_2015 TEXT,
    return_2016 REAL, drawdown_2016 REAL, rank_2016 TEXT,
    return_2017 REAL, drawdown_2017 REAL, rank_2017 TEXT,
    return_2018 REAL, drawdown_2018 REAL, rank_2018 TEXT,
    return_2019 REAL, drawdown_2019 REAL, rank_2019 TEXT,
    return_2020 REAL, drawdown_2020 REAL, rank_2020 TEXT,
    return_2021 REAL, drawdown_2021 REAL, rank_2021 TEXT,
    return_2022 REAL, drawdown_2022 REAL, rank_2022 TEXT,
    return_2023 REAL, drawdown_2023 REAL, rank_2023 TEXT,
    return_2024 REAL, drawdown_2024 REAL, rank_2024 TEXT,
    return_2025 REAL, drawdown_2025 REAL, rank_2025 TEXT
);
CREATE INDEX IF NOT EXISTS ix_fund_details_fund_code ON fund_details (fund_code);
CREATE INDEX IF NOT EXISTS ix_fund_details_trade_date ON fund_details (trade_date);

CREATE TABLE IF NOT EXISTS fetch_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    target_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    current_count INTEGER DEFAULT 0,
    executor_ip TEXT DEFAULT '',
    executor_thread TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_fetch_tasks_task_type ON fetch_tasks (task_type);
-- 同一任务类型同时只允许一条 running（数据库级兜底防并发，应用层再做友好提示）
CREATE UNIQUE INDEX IF NOT EXISTS ux_fetch_tasks_running
    ON fetch_tasks (task_type) WHERE status = 'running';

CREATE TABLE IF NOT EXISTS trade_dates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS ix_trade_dates_trade_date ON trade_dates (trade_date);

CREATE TABLE IF NOT EXISTS fund_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_code TEXT NOT NULL,
    quarter TEXT NOT NULL,
    holding_type TEXT NOT NULL DEFAULT 'stock',
    asset_code TEXT NOT NULL,
    asset_name TEXT NOT NULL DEFAULT '',
    hold_ratio REAL,
    hold_amount REAL,
    hold_market_value REAL,
    raw_data TEXT DEFAULT '{}',
    fetch_time TEXT,
    UNIQUE (fund_code, quarter, holding_type, asset_code)
);
CREATE INDEX IF NOT EXISTS ix_fund_holdings_fund_code ON fund_holdings (fund_code);
CREATE INDEX IF NOT EXISTS ix_fund_holdings_quarter ON fund_holdings (quarter);

CREATE TABLE IF NOT EXISTS fund_nav (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_code VARCHAR(10) NOT NULL,
    trade_date VARCHAR(10) NOT NULL,
    nav FLOAT,
    acc_nav FLOAT,
    daily_return FLOAT,
    fetch_time TEXT,
    UNIQUE (fund_code, trade_date)
);
CREATE INDEX IF NOT EXISTS ix_fund_nav_fund_code ON fund_nav (fund_code);
CREATE INDEX IF NOT EXISTS ix_fund_nav_trade_date ON fund_nav (trade_date);

CREATE TABLE IF NOT EXISTS fund_cum_return (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fund_code VARCHAR(10) NOT NULL,
    trade_date VARCHAR(10) NOT NULL,
    cum_return FLOAT,
    fetch_time TEXT,
    UNIQUE (fund_code, trade_date)
);
CREATE INDEX IF NOT EXISTS ix_fund_cum_return_fund_code ON fund_cum_return (fund_code);
CREATE INDEX IF NOT EXISTS ix_fund_cum_return_trade_date ON fund_cum_return (trade_date);
