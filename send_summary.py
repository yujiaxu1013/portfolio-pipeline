import os
from datetime import date

import requests
import psycopg2

DATABASE_URL = os.environ['DATABASE_URL']
BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

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
        lines.append(
            f"{name}:{close:.2f}({day_chg:+.2f}%)\n"
            f"市值 {mv:,.0f} | 損益 {pnl:+,.0f}({pnl_pct:+.2f}%)"
        )
        total_mv += mv
        total_cost += net_cost

    total_pnl = total_mv - total_cost
    lines.append(f"—\n總市值 {total_mv:,.0f} | 總損益 {total_pnl:+,.0f}({total_pnl/total_cost*100:+.2f}%)")

    msg = "\n".join(lines)
    resp = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg},
        timeout=30,
    )
    resp.raise_for_status()
    print("摘要已發送")

    cur.close(); conn.close()

if __name__ == '__main__':
    main()