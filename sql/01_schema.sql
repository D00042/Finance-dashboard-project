-- Star schema for the Meridian Travel Group finance model
-- Dimensions: entity, account, date  |  Facts: P&L (actual + budget), balance sheet (actual)

DROP TABLE IF EXISTS fact_balance;
DROP TABLE IF EXISTS fact_pnl;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_account;
DROP TABLE IF EXISTS dim_entity;

CREATE TABLE dim_entity (
    entity_id   TEXT PRIMARY KEY,
    entity_name TEXT NOT NULL,
    country     TEXT NOT NULL,
    currency    TEXT NOT NULL
);

CREATE TABLE dim_account (
    account_id   INTEGER PRIMARY KEY,
    account_name TEXT NOT NULL,
    statement    TEXT NOT NULL CHECK (statement IN ('P&L', 'BS')),
    category     TEXT NOT NULL
);

CREATE TABLE dim_date (
    month        TEXT PRIMARY KEY,        -- first day of month, ISO format
    year         INTEGER NOT NULL,
    quarter      INTEGER NOT NULL,
    month_num    INTEGER NOT NULL,
    month_name   TEXT NOT NULL,
    period_label TEXT NOT NULL
);

CREATE TABLE fact_pnl (
    month      TEXT    NOT NULL REFERENCES dim_date(month),
    entity_id  TEXT    NOT NULL REFERENCES dim_entity(entity_id),
    account_id INTEGER NOT NULL REFERENCES dim_account(account_id),
    actual     REAL    NOT NULL,          -- amounts stored as positive numbers; sign comes from category
    budget     REAL    NOT NULL,
    PRIMARY KEY (month, entity_id, account_id)
);

CREATE TABLE fact_balance (
    month      TEXT    NOT NULL REFERENCES dim_date(month),
    entity_id  TEXT    NOT NULL REFERENCES dim_entity(entity_id),
    account_id INTEGER NOT NULL REFERENCES dim_account(account_id),
    amount     REAL    NOT NULL,
    PRIMARY KEY (month, entity_id, account_id)
);
