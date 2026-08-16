import os
import time
import psycopg2
from datetime import datetime, timezone
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors

from prompt_template import TAGGING_PROMPT

load_dotenv()
DATABASE_URL = os.environ['DATABASE_URL']

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-flash-lite-latest"

KEY_MAP = {
    "類型": "news_type",
    "影響層級": "impact_level",
    "方向": "direction",
    "摘要": "summary",
    "重要性": "importance",
}

SLEEP_BETWEEN = 4      # 每則之間停幾秒(避免限流)
MAX_RETRY = 3          # 撞到忙碌時最多重試幾次


def fetch_untagged():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT article_id, title
        FROM news
        WHERE importance IS NULL
        ORDER BY article_id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def tag_one(title):
    """呼叫 Gemini,撞到暫時性忙碌(503)會自動重試"""
    prompt = TAGGING_PROMPT.format(title=title)
    for attempt in range(1, MAX_RETRY + 1):
        try:
            resp = client.models.generate_content(model=MODEL, contents=prompt)
            return resp.text
        except genai_errors.ServerError:
            wait = attempt * 20
            print(f"    伺服器忙碌,{wait} 秒後重試({attempt}/{MAX_RETRY})...")
            time.sleep(wait)
    raise RuntimeError("重試多次仍失敗")


def parse_response(text):
    result = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key in KEY_MAP:
            result[KEY_MAP[key]] = value
    return result


def write_back(conn, article_id, tags):
    cur = conn.cursor()
    cur.execute("""
        UPDATE news SET
            news_type = %s, impact_level = %s, direction = %s,
            summary = %s, importance = %s, llm_model = %s, labeled_at = %s
        WHERE article_id = %s
    """, (
        tags.get("news_type"), tags.get("impact_level"), tags.get("direction"),
        tags.get("summary"), int(tags.get("importance")),
        MODEL, datetime.now(timezone.utc), article_id,
    ))
    conn.commit()
    cur.close()


def main():
    rows = fetch_untagged()
    total = len(rows)
    print(f"待標籤新聞共 {total} 則,開始批次處理...\n")

    conn = psycopg2.connect(DATABASE_URL)
    done, failed = 0, 0

    for i, (article_id, title) in enumerate(rows, 1):
        short = title[:30]
        print(f"[{i}/{total}] id={article_id} {short}...")
        try:
            raw = tag_one(title)
            tags = parse_response(raw)
            if len(tags) != 5 or tags.get("importance") not in {"1", "2", "3", "4", "5"}:
                print(f"    ⚠ 格式異常,跳過。原始回傳:{raw.strip()[:60]}")
                failed += 1
            else:
                write_back(conn, article_id, tags)
                print(f"    ✓ {tags['news_type']}/{tags['importance']}分")
                done += 1
        except Exception as e:
            print(f"    ✗ 失敗:{e}")
            failed += 1
        time.sleep(SLEEP_BETWEEN)

    conn.close()
    print(f"\n完成!成功 {done} 則,失敗/跳過 {failed} 則。")
    if failed:
        print("失敗的仍是 NULL,之後重跑本程式會自動只補這些。")


if __name__ == '__main__':
    main()