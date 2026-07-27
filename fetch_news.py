import os
import time
from datetime import datetime, timezone
from urllib.parse import quote

import feedparser
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ['DATABASE_URL']

# 白名單:只保留這些來源的新聞(比對 RSS 回傳的來源名稱)
SOURCE_WHITELIST = ['鉅亨', 'cnyes', '經濟日報', '工商', '中央社', 'MoneyDJ', 'moneydj']

# 標題黑名單:含這些字的直接丟棄(內容農場特徵)
TITLE_BLACKLIST = ['專家', '這樣說', '這樣看', '後市', '一文看懂', '網友', '驚呼', '曝光', '真相']

# 總經關鍵字(不綁定特定 ticker)
MACRO_KEYWORDS = ['外資 買賣超', '台幣 匯率', '半導體 出口']


def build_rss_url(query):
    q = quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"


def passes_filters(title, source):
    # 來源白名單
    if not any(w.lower() in source.lower() for w in SOURCE_WHITELIST):
        return False
    # 標題黑名單
    if any(bad in title for bad in TITLE_BLACKLIST):
        return False
    return True


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO pipeline_log (job_name, started_at) VALUES (%s, %s) RETURNING run_id",
        ('fetch_news', datetime.now(timezone.utc)),
    )
    run_id = cur.fetchone()[0]
    conn.commit()

    try:
        # 建立查詢清單:每檔成分股一條 + 每個總經關鍵字一條
        cur.execute("SELECT ticker, name FROM watchlist WHERE is_active = TRUE AND tier = 'constituent'")
        constituents = cur.fetchall()

        queries = []  # (query_string, ticker)
        for ticker, name in constituents:
            queries.append((name, ticker))          # 用中文公司名查,歸給該 ticker
        for kw in MACRO_KEYWORDS:
            queries.append((kw, '0050.TW'))         # 總經新聞暫掛在 0050 名下

        rows = []
        for query, ticker in queries:
            feed = feedparser.parse(build_rss_url(query))
            for entry in feed.entries:
                title = entry.get('title', '')
                # Google News 的來源在 entry.source.title,或標題結尾的 " - 來源"
                source = ''
                if 'source' in entry and hasattr(entry.source, 'title'):
                    source = entry.source.title
                elif ' - ' in title:
                    source = title.rsplit(' - ', 1)[-1]

                if not passes_filters(title, source):
                    continue

                url = entry.get('link', '')
                published = entry.get('published', None)
                rows.append((ticker, source[:100], title, url))
            time.sleep(1)  # 對 Google 客氣一點,每條查詢間隔一秒

        print(f"通過過濾的新聞:{len(rows)} 則")

        # 寫入(靠 UNIQUE(url, ticker) 去重,重複的自動跳過)
        if rows:
            execute_values(cur, """
                INSERT INTO news (ticker, source, title, url)
                VALUES %s
                ON CONFLICT (url, ticker) DO NOTHING
            """, rows)

        inserted = cur.rowcount
        print(f"實際新增(去重後):{inserted} 則")

        cur.execute(
            "UPDATE pipeline_log SET ended_at = %s, status = 'success', rows_written = %s WHERE run_id = %s",
            (datetime.now(timezone.utc), inserted, run_id),
        )
        conn.commit()
        print("完成")

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