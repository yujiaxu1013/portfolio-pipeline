import os
import math
from datetime import datetime, timezone

import yfinance as yf
import psycopg2
from dotenv import load_dotenv

load_dotenv()
from psycopg2.extras import execute_values

DATABASE_URL = os.environ['DATABASE_URL']

def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    # 開始記錄這次執行
    cur.execute(
        "INSERT INTO pipeline_log (job_name, started_at) VALUES (%s, %s) RETURNING run_id",
        ('fetch_prices', datetime.now(timezone.utc)),
    )
    run_id = cur.fetchone()[0]
    conn.commit()

    try:
        # 1. 讀 watchlist 的活躍標的
        cur.execute("SELECT ticker FROM watchlist WHERE is_active = TRUE")
        tickers = [row[0] for row in cur.fetchall()]
        print(f"抓取標的:{tickers}")

        # 2. 逐檔抓價格(首跑抓三年;日常維運靠 period 參數改小)
        rows = []
        skipped = 0
        for ticker in tickers:
            data = yf.download(ticker, period='3y', auto_adjust=False, progress=False)
            data = data.droplevel('Ticker', axis=1)   # 剝掉 MultiIndex 那層
            for date_idx, r in data.iterrows():
                close = float(r['Close'])
                # 防呆:收盤價是 NaN(通常是盤中抓、當日收盤價還沒產生)就跳過,不存壞值
                if math.isnan(close):
                    skipped += 1
                    continue
                rows.append((
                    ticker,
                    date_idx.date(),
                    float(r['Open']), float(r['High']), float(r['Low']),
                    close, float(r['Adj Close']),
                    int(r['Volume']),
                ))
        print(f"共 {len(rows)} 列待寫入(跳過 {skipped} 筆 NaN)")

        # 3. UPSERT:主鍵重複就更新,不重複就插入
        execute_values(cur, """
            INSERT INTO prices (ticker, price_date, open, high, low, close, adj_close, volume)
            VALUES %s
            ON CONFLICT (ticker, price_date) DO UPDATE SET
                open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
                close = EXCLUDED.close, adj_close = EXCLUDED.adj_close,
                volume = EXCLUDED.volume, fetched_at = NOW()
        """, rows)

        # 4. 收尾:記錄成功
        cur.execute(
            "UPDATE pipeline_log SET ended_at = %s, status = 'success', rows_written = %s WHERE run_id = %s",
            (datetime.now(timezone.utc), len(rows), run_id),
        )
        conn.commit()
        print("完成,pipeline_log 已記錄 success")

    except Exception as e:
        conn.rollback()
        cur.execute(
            "UPDATE pipeline_log SET ended_at = %s, status = 'failed', error_msg = %s WHERE run_id = %s",
            (datetime.now(timezone.utc), str(e), run_id),
        )
        conn.commit()
        raise

    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    main()