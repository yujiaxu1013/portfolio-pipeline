"""本機預覽:組出週回顧文字並印出,不發 Telegram、不需 Telegram 金鑰。"""
import os
from datetime import date

import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ['DATABASE_URL']

TOTAL_LIMIT = 14
PER_TICKER_LIMIT = 3
MACRO_TYPES = {'總經政策', '資金流向'}
MACRO_TICKERS = {'0050.TW'}
MACRO_LIMIT = 3


def fetch_weekly(cur):
    cur.execute("""
        WITH deduped AS (
            SELECT DISTINCT ON (n.summary)
                   n.ticker, n.news_type, n.importance, n.direction, n.summary,
                   w.name AS company_name
            FROM news n
            JOIN watchlist w ON n.ticker = w.ticker
            WHERE n.importance >= 4
              AND n.fetched_at >= NOW() - INTERVAL '7 days'
            ORDER BY n.summary, n.importance DESC
        )
        SELECT ticker, company_name, news_type, importance, direction, summary
        FROM deduped
        ORDER BY importance DESC
    """)
    return cur.fetchall()


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    rows = fetch_weekly(cur)

    stock_pool = {}
    macro_pool = []
    for ticker, name, news_type, importance, direction, summary in rows:
        item = (importance, direction, summary)
        if ticker in MACRO_TICKERS or news_type in MACRO_TYPES:
            macro_pool.append(item)
        else:
            stock_pool.setdefault((name, ticker), []).append(item)

    for key in stock_pool:
        stock_pool[key] = stock_pool[key][:PER_TICKER_LIMIT]
    macro_pool = macro_pool[:MACRO_LIMIT]

    macro_count = len(macro_pool)
    stock_budget = TOTAL_LIMIT - macro_count

    selected = {key: [] for key in stock_pool}
    count = 0
    for key, items in stock_pool.items():
        if count >= stock_budget:
            break
        if items:
            selected[key].append(items[0]); count += 1

    round_idx = 1
    added = True
    while added and count < stock_budget:
        added = False
        for key, items in stock_pool.items():
            if count >= stock_budget:
                break
            if round_idx < len(items):
                selected[key].append(items[round_idx]); count += 1; added = True
        round_idx += 1

    lines = [f"🗓️ 本週回顧 {date.today():%m/%d}"]
    for (name, ticker), items in selected.items():
        if items:
            lines.append(f"\n{name}({ticker})")
            for importance, direction, summary in items:
                lines.append(f"[{direction}★{importance}] {summary}")

    if macro_pool:
        lines.append("\n📊 總經/大盤")
        for importance, direction, summary in macro_pool:
            lines.append(f"[{direction}★{importance}] {summary}")

    total = sum(len(v) for v in selected.values()) + len(macro_pool)
    print("=" * 40)
    print("\n".join(lines))
    print("=" * 40)
    print(f"\n(總則數:{total})")

    cur.close(); conn.close()


if __name__ == '__main__':
    main()