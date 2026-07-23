-- Portfolio Pipeline — database schema
-- PostgreSQL 18 (Neon)

-- ============ 1. watchlist: configuration hub ============
CREATE TABLE watchlist (
    ticker       VARCHAR(20) PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    tier         VARCHAR(20) NOT NULL
                 CHECK (tier IN ('holding', 'constituent', 'supply_chain')),
    market       VARCHAR(10) NOT NULL DEFAULT 'TW',
    currency     CHAR(3) NOT NULL DEFAULT 'TWD',
    index_weight NUMERIC(5,2),
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    added_at     DATE NOT NULL DEFAULT CURRENT_DATE,
    note         TEXT
);

-- ============ 2. transactions: manual event log ============
CREATE TABLE transactions (
    txn_id     SERIAL PRIMARY KEY,
    ticker     VARCHAR(20) NOT NULL REFERENCES watchlist(ticker),
    txn_date   DATE NOT NULL,
    action     VARCHAR(15) NOT NULL
               CHECK (action IN ('buy','sell','div_cash','div_reinvest')),
    shares     NUMERIC(14,4) NOT NULL,
    price      NUMERIC(12,4) NOT NULL,
    fee        NUMERIC(10,2) NOT NULL DEFAULT 0,
    tax        NUMERIC(10,2) NOT NULL DEFAULT 0,
    note       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_txn_touch
BEFORE UPDATE ON transactions
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- ============ 3. prices: daily OHLC, auto-fetched ============
CREATE TABLE prices (
    ticker     VARCHAR(20) NOT NULL REFERENCES watchlist(ticker),
    price_date DATE NOT NULL,
    open       NUMERIC(12,4),
    high       NUMERIC(12,4),
    low        NUMERIC(12,4),
    close      NUMERIC(12,4) NOT NULL,
    adj_close  NUMERIC(12,4) NOT NULL,
    volume     BIGINT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, price_date)
);

-- ============ 4. news: articles + LLM labels (v1.1) ============
CREATE TABLE news (
    article_id   SERIAL PRIMARY KEY,
    ticker       VARCHAR(20) NOT NULL REFERENCES watchlist(ticker),
    published_at TIMESTAMPTZ,
    source       VARCHAR(100),
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    news_type    VARCHAR(30),
    impact_level VARCHAR(30),
    direction    VARCHAR(10),
    summary      TEXT,
    llm_model    VARCHAR(50),
    labeled_at   TIMESTAMPTZ,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (url, ticker)
);

-- ============ 5. pipeline_log: job execution record ============
CREATE TABLE pipeline_log (
    run_id       SERIAL PRIMARY KEY,
    job_name     VARCHAR(50) NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL,
    ended_at     TIMESTAMPTZ,
    status       VARCHAR(10) NOT NULL DEFAULT 'running'
                 CHECK (status IN ('running','success','failed')),
    rows_written INTEGER,
    error_msg    TEXT
);

-- ============ View 1: current holdings ============
CREATE VIEW current_holdings AS
SELECT
    t.ticker, w.name,
    SUM(CASE WHEN t.action IN ('buy','div_reinvest') THEN t.shares
             WHEN t.action = 'sell' THEN -t.shares ELSE 0 END) AS total_shares,
    SUM(CASE WHEN t.action IN ('buy','div_reinvest') THEN t.shares*t.price + t.fee
             WHEN t.action = 'sell' THEN -(t.shares*t.price) + t.fee + t.tax
             ELSE 0 END) AS net_cost
FROM transactions t
JOIN watchlist w USING (ticker)
GROUP BY t.ticker, w.name;

-- ============ View 2: holdings valuation ============
CREATE VIEW holdings_valuation AS
SELECT
    h.*, p.price_date AS as_of, p.close,
    h.total_shares * p.close AS market_value,
    h.total_shares * p.close - h.net_cost AS unrealized_pnl
FROM current_holdings h
JOIN LATERAL (
    SELECT price_date, close FROM prices
    WHERE prices.ticker = h.ticker
    ORDER BY price_date DESC LIMIT 1
) p ON TRUE;