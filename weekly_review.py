import os
import html
from datetime import date

import requests
import psycopg2

DATABASE_URL = os.environ['DATABASE_URL']
BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

TOTAL_LIMIT = 14        # 整份週回顧最多幾則(含所有組)
PER_TICKER_LIMIT = 3    # 每檔最多幾則
MACRO_TYPES = {'總經政策', '資金流向'}
MACRO_TICKERS = {'0050.TW'}   # 這些標的的新聞一律歸總經組(ETF=大盤)
MACRO_LIMIT = 3         # 總經組最多幾則


def fetch_weekly(cur):
    cur.execute("""
        WITH deduped AS (
            SELECT DISTINCT ON (n.summary)
                   n.ticker, n.news_type, n.importance, n.direction, n.summary, n.url,
                   w.name AS company_name
            FROM news n
            JOIN watchlist w ON n.ticker = w.ticker
            WHERE n.importance >= 4
              AND n.fetched_at >= NOW() - INTERVAL '7 days'
            ORDER BY n.summary, n.importance DESC
        )
        SELECT ticker, company_name, news_type, importance, direction, summary, url
        FROM deduped
        ORDER BY importance DESC
    """)
    return cur.fetchall()


def build_message(rows):
    stock_pool = {}   # {(name, ticker): [items 按分數排]}
    macro_pool = []

    for ticker, name, news_type, importance, direction, summary, url in rows:
        item = (importance, direction, summary, url)
        # 0050 名下的、或總經/資金類型的,一律歸總經組
        if ticker in MACRO_TICKERS or news_type in MACRO_TYPES:
            macro_pool.append(item)
        else:
            stock_pool.setdefault((name, ticker), []).append(item)

    for key in stock_pool:
        stock_pool[key] = stock_pool[key][:PER_TICKER_LIMIT]
    macro_pool = macro_pool[:MACRO_LIMIT]

    # 先預留總經組的名額,個股組能用的上限 = 總上限 - 總經實際則數
    macro_count = len(macro_pool)
    stock_budget = TOTAL_LIMIT - macro_count

    # 兩階段分配(在 stock_budget 內)
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

    # 組訊息
    lines = [f"🗓️ 本週回顧 {date.today():%m/%d}"]

    def add_item(item):
        importance, direction, summary, url = item
        safe_summary = html.escape(summary)
        if url:
            safe_url = html.escape(url, quote=True)
            lines.append(f'[{direction}★{importance}] {safe_summary} <a href="{safe_url}">詳全文</a>')
        else:
            lines.append(f"[{direction}★{importance}] {safe_summary}")

    for (name, ticker), items in selected.items():
        if items:
            lines.append(f"\n<b>{html.escape(name)}({ticker})</b>")
            for item in items:
                add_item(item)

    if macro_pool:
        lines.append("\n<b>📊 總經/大盤</b>")
        for item in macro_pool:
            add_item(item)

    return "\n".join(lines) if len(lines) > 1 else None


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    rows = fetch_weekly(cur)
    msg = build_message(rows)

    if not msg:
        print("本週沒有符合條件的新聞,不發送。")
        cur.close(); conn.close()
        return

    resp = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=30,
    )
    resp.raise_for_status()
    print("週回顧已發送")

    cur.close(); conn.close()


if __name__ == '__main__':
    main()