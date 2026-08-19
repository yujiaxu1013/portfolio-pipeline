import os
import html
from datetime import date

import requests
import psycopg2

DATABASE_URL = os.environ['DATABASE_URL']
BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']


def fetch_top_news(cur, limit=2):
    """撈最近抓取日的 ≥4 分新聞,最多 limit 則(含連結)"""
    cur.execute("""
        SELECT importance, direction, summary, url
        FROM news
        WHERE importance >= 4
          AND DATE(fetched_at) = (SELECT MAX(DATE(fetched_at)) FROM news)
        ORDER BY importance DESC, article_id
        LIMIT %s
    """, (limit,))
    return cur.fetchall()


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # 持倉估值(最新收盤)
    cur.execute("SELECT ticker, name, total_shares, net_cost, as_of, close, market_value, unrealized_pnl FROM holdings_valuation")
    holdings = cur.fetchall()

    if not holdings:
        cur.close(); conn.close()
        return

    lines = [f"📊 收盤摘要 {date.today():%m/%d}"]
    total_mv, total_cost = 0, 0

    for (ticker, name, shares, net_cost, as_of, close, mv, pnl) in holdings:
        # 當日漲跌:抓最近兩天收盤比較
        cur.execute("""
            SELECT close FROM prices WHERE ticker = %s
            ORDER BY price_date DESC LIMIT 2
        """, (ticker,))
        closes = [r[0] for r in cur.fetchall()]
        day_chg = (closes[0] - closes[1]) / closes[1] * 100 if len(closes) == 2 else 0

        pnl_pct = pnl / net_cost * 100
        # 持倉的公司名做轉義(避免特殊符號干擾 HTML)
        safe_name = html.escape(name)
        lines.append(
            f"{safe_name}:{close:.2f}({day_chg:+.2f}%)\n"
            f"市值 {mv:,.0f} | 損益 {pnl:+,.0f}({pnl_pct:+.2f}%)"
        )
        total_mv += mv
        total_cost += net_cost

    total_pnl = total_mv - total_cost
    lines.append(f"—\n總市值 {total_mv:,.0f} | 總損益 {total_pnl:+,.0f}({total_pnl/total_cost*100:+.2f}%)")

    # 附上當天高分新聞(≥4 分,最多 2 則,含「詳全文」超連結)
    top_news = fetch_top_news(cur, limit=2)
    if top_news:
        lines.append("—\n📰 今日重點")
        for importance, direction, summary, url in top_news:
            safe_summary = html.escape(summary)
            if url:
                safe_url = html.escape(url, quote=True)
                lines.append(f'[{direction}★{importance}] {safe_summary} <a href="{safe_url}">詳全文</a>')
            else:
                lines.append(f"[{direction}★{importance}] {safe_summary}")

    msg = "\n".join(lines)
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
    print("摘要已發送")

    cur.close(); conn.close()


if __name__ == '__main__':
    main()