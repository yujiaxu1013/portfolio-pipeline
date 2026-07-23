# Portfolio Pipeline

A personal, fully automated data pipeline that tracks my investment portfolio — built to support long-term index investing, not day trading.

**Stack:** Python · PostgreSQL (Neon) · GitHub Actions · Power BI · Telegram Bot API

---

## What This Is

A personal data pipeline that tracks my investment portfolio automatically. Every trading day, a scheduled job pulls closing prices for everything on my watchlist, writes them to a cloud PostgreSQL database, computes my current position value against my full transaction history, and pushes a summary to my phone. I enter one transaction per month; everything else runs without me.

No server to maintain, no machine that needs to stay on, and no recurring cost — the entire system runs on free tiers.

## Why Not Just Use a Broker App

Broker apps show today's balance in one account. This system answers questions they structurally cannot:

- **Cross-account, cross-asset view.** A broker app only sees the account it hosts. As I add foreign brokerage or a second account, each app tells a partial story. This system's boundary is my portfolio, not a vendor's customer relationship.
- **Complete, portable history.** My transaction table is an event log I own and can query with arbitrary SQL — cost basis over time, fee ratio, contribution curve. Broker apps give you a snapshot and a limited lookup UI. When I switch brokers, their records stay with them; my database comes with me.
- **Derived metrics I define.** The metric that matters most to me does not exist in any broker app: **look-through exposure**. I hold 0050, a Taiwan market-cap ETF where TSMC is roughly 60% of the index — so a large share of what looks like a "diversified ETF position" is in fact concentrated in a single company. Combining index weights with direct holdings to compute true single-name exposure is something no broker will build, because they cannot see inside the ETF and have no incentive to.

## Design Philosophy: Built for Conviction, Not Speed

This system is deliberately slow, and that is the point.

My strategy is monthly dollar-cost averaging into market-cap-weighted ETFs. Under that strategy, intraday price movement is noise: I am not trading on it, and there is no decision I would make differently if I saw it a minute earlier. Chasing real-time data would optimize for a use case I do not have — and worse, it would invite the exact behavior indexing is meant to prevent. A dashboard that updates every second trains you to react every second.

What I actually need is different, and quieter. When the market drops six percent in a week, the question in my head is not "should I sell" — it is "do I understand what is happening, and does it change my thesis?" Almost always the honest answer is no, and holding through it is the entire strategy. But holding is much easier when the drop has context: which of my holdings moved, how far the index is from its high, what the news flow was that week. That context is what turns a scary red number into a known event.

So the system optimizes for **conviction, not reaction**:

- **Daily, end-of-day cadence.** Prices update once after the close. No streaming quotes, no intraday alerts.
- **Weekly, not hourly, news digest.** News is for understanding what happened, not for trading on what just broke.
- **Framing matters.** A drawdown is reported as what it is for a monthly buyer: the same contribution now buys more shares.
- **Full history over live speed.** Knowing what my cost basis curve looked like over three years is worth more than knowing the price three seconds ago.

The measure of success for this system is not that it makes me act faster. It is that it lets me act less, with more confidence.

## What It Deliberately Does Not Do

No real-time quotes. No trading signals. No price predictions. No order execution. The design goal is understanding and record-keeping, not action — the strategy this supports is one where the correct response to most market news is to do nothing.

---

## Architecture

Every weekday after market close, GitHub Actions provisions a container, checks out this repo, injects credentials from repository secrets, and runs two scripts: one fetches and upserts prices, the other queries the valuation view and pushes a summary to Telegram. The container is destroyed afterwards. Nothing runs on my own machine — the pipeline continues whether my computer is on, off, or somewhere else entirely.

**Automated path (daily):**
GitHub Actions (cron, weekdays) → fetch_prices.py → yfinance → prices table → holdings_valuation view → send_summary.py → Telegram → my phone

**Manual path (monthly):**
add_transaction.py (interactive CLI) → transactions table

**Analysis path (on demand):**
Power BI Desktop → Neon PostgreSQL (direct connection)

### Data Model

![Schema diagram](schema-diagram.png)

| Object | Type | Role |
|---|---|---|
| watchlist | table | Configuration hub. Everything the system tracks is a row here; both the price fetcher and the news module iterate over it. Adding a new holding requires no code change. |
| transactions | table | Event log of every buy, sell, and dividend reinvestment. Manually entered, roughly once a month. The only data in the system that cannot be regenerated. |
| prices | table | Daily OHLC and adjusted close for every active ticker. Composite primary key on ticker and date makes re-fetching idempotent. |
| news | table | Article metadata plus LLM-generated labels. Populated by the news module (v1.1). |
| pipeline_log | table | Execution record for every scheduled job: start, end, status, rows written, error message. |
| current_holdings | view | Share count and net cost, derived from the transaction log. |
| holdings_valuation | view | Current holdings joined to the latest close via a lateral join — market value and unrealized P&L, computed on read. |

---

## Design Decisions

Notes on the tradeoffs behind the schema and the infrastructure.

**Transactions are events, not state.** The obvious design is a holdings table with a share count you update each month. I record individual transactions instead and derive holdings from them. Updating a running total destroys history: you can never reconstruct when and at what price a position was accumulated, which makes the single most useful chart for a dollar-cost-averaging investor — contributed capital versus market value over time — impossible to draw. Recording events and deriving state also means adding sells, dividends, or a second ticker requires no schema change.

**Derived values are computed on read, not stored.** Position value and unrealized P&L live in views, not columns. Storing them would mean every price update has to remember to recalculate them, and any missed update leaves the database quietly inconsistent. A view cannot go stale.

**Cloud database over local.** Storage was never the constraint — this dataset is a few megabytes a year. The real reason is that a local database makes my laptop a dependency: the pipeline only runs when that specific machine is awake. With Neon plus GitHub Actions, the entire system is serverless, and my machine is reduced to one of several clients. Neon's scale-to-zero also means the compute cost of an idle database is nothing at all.

**Denormalized news-to-ticker mapping.** An article mentioning two companies is stored as two rows with a uniqueness constraint on (url, ticker), rather than being normalized into a junction table. With a handful of tickers and low overlap, the duplication is negligible and every query stays a simple join. This is a decision worth revisiting if the watchlist grows substantially.

**Scheduled off the hour.** The first version ran on the hour. Delivery drifted later and later — GitHub's free scheduler is a shared queue, and everyone writes their cron on the hour. Moving the schedule to an odd minute sidesteps the congestion. A small thing, but the kind you only learn by running something in production rather than reading about it.

**Secrets never touch the source tree.** Credentials come from environment variables in every environment: a gitignored dotenv file locally, repository secrets in CI. Neither the code nor the working tree contains a working credential. An earlier version of this repo did leak one, through a .gitignore file that was created but never actually populated — the credential was rotated immediately, the file untracked, and the root cause fixed. The lesson kept: a protective mechanism that was created is not the same as one that was verified to work.

---

## Local Setup

Requires Python 3.14 and a PostgreSQL database.

    git clone https://github.com/yujiaxu1013/portfolio-pipeline.git
    cd portfolio-pipeline
    pip install -r requirements.txt

Create a dotenv file in the project root containing a single line:

    DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require

Apply the schema in sql/schema.sql, then run:

    python fetch_prices.py      # fetch and upsert prices
    python add_transaction.py   # interactive monthly entry

For scheduled runs, DATABASE_URL, TELEGRAM_BOT_TOKEN, and TELEGRAM_CHAT_ID are configured as GitHub repository secrets.

---

## Roadmap

- **v1.1 — News module.** RSS ingestion across index constituents and macro keywords, LLM labeling (type, impact level, direction, importance score), weekly digest. Explicitly framed as context, not signal.
- **v1.2 — Market state monitoring.** Index drawdown, foreign institutional flows, FX levels, with alert thresholds stored as data rather than hardcoded. Alerts describe what has happened; they do not predict.
- **v1.3 — Discipline audit.** Plan-versus-actual contribution tracking, and a thesis log for any discretionary position.

---

## Disclaimer

Personal learning project. Nothing here is investment advice.

---

**Thomas** · [github.com/yujiaxu1013](https://github.com/yujiaxu1013)