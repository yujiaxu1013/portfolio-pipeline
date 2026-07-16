import os
from datetime import date

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ['DATABASE_URL']

def ask(prompt, default=None):
    """問一個問題;直接按 Enter 就用預設值"""
    suffix = f"(預設 {default})" if default else ""
    answer = input(f"{prompt}{suffix}:").strip()
    return answer if answer else default

def main():
    print("=== 記一筆交易 ===")
    txn_date = ask("成交日 YYYY-MM-DD", default=str(date.today()))
    shares   = ask("股數")
    price    = ask("成交均價")
    fee      = ask("手續費", default="1")
    note     = ask("備註", default="定期定額")

    print(f"\n即將寫入:0050.TW | {txn_date} | buy {shares} 股 @ {price} | 手續費 {fee}")
    if ask("確認?(y/n)", default="y").lower() != "y":
        print("已取消,什麼都沒寫入。")
        return

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO transactions (ticker, txn_date, action, shares, price, fee, note)
        VALUES (%s, %s, 'buy', %s, %s, %s, %s)
    """, ('0050.TW', txn_date, shares, price, fee, note))
    conn.commit()

    # 立刻印出最新持倉對帳
    cur.execute("SELECT ticker, total_shares, net_cost FROM current_holdings")
    for ticker, total_shares, net_cost in cur.fetchall():
        print(f"\n最新持倉:{ticker} 共 {total_shares} 股,總成本 {net_cost:,.2f}")

    cur.close()
    conn.close()
    print("完成,拿去跟券商 APP 對帳吧。")

if __name__ == '__main__':
    main()