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