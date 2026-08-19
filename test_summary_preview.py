"""本機預覽用:組出完整摘要文字並印在終端機,不發 Telegram、不需要 Telegram 金鑰。"""
import os
from datetime import date

import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ['DATABASE_URL']


def fetch_top_news(cur, limit=2):
    cur.execute("""
        SELECT importance, direction, summary
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

    cur.execute("SELECT ticker, name, total_shares, net_cost, as_of, close, market_value, unrealized_pnl FROM holdings_valuation")
    holdings = cur.fetchall()

    if not holdings:
        print("沒有持倉資料")
        cur.close(); conn.close()
        return

    lines = [f"📊 收盤摘要 {date.today():%m/%d}"]
    total_mv, total_cost = 0, 0

    for (ticker, name, shares, net_cost, as_of, close, mv, pnl) in holdings:
        cur.execute("""
            SELECT close FROM prices WHERE ticker = %s
            ORDER BY price_date DESC LIMIT 2
        """, (ticker,))
        closes = [r[0] for r in cur.fetchall()]
        day_chg = (closes[0] - closes[1]) / closes[1] * 100 if len(closes) == 2 else 0

        pnl_pct = pnl / net_cost * 100
        lines.append(
            f"{name}:{close:.2f}({day_chg:+.2f}%)\n"
            f"市值 {mv:,.0f} | 損益 {pnl:+,.0f}({pnl_pct:+.2f}%)"
        )
        total_mv += mv
        total_cost += net_cost

    total_pnl = total_mv - total_cost
    lines.append(f"—\n總市值 {total_mv:,.0f} | 總損益 {total_pnl:+,.0f}({total_pnl/total_cost*100:+.2f}%)")

    top_news = fetch_top_news(cur, limit=2)
    if top_news:
        lines.append("—\n📰 今日重點")
        for importance, direction, summary in top_news:
            lines.append(f"[{direction}★{importance}] {summary}")

    msg = "\n".join(lines)
    print("=" * 40)
    print(msg)
    print("=" * 40)
    print(f"\n(新聞則數:{len(top_news)})")

    cur.close(); conn.close()


if __name__ == '__main__':
    main()