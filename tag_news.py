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

SLEEP_BETWEEN = 4
MAX_RETRY = 3

# 分界時間點:只重標「在此時間之前標記的」新聞。
# 每則重標後 labeled_at 會更新為現在,自然被排除,分天跑不會重複。
RELABEL_BEFORE = "2026-08-19 00:00:00+08"


def fetch_to_relabel():
    """撈出還沒用新標準重標的新聞(labeled_at 早於分界點,或從沒標過)"""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT article_id, title
        FROM news
        WHERE labeled_at IS NULL OR labeled_at < %s
        ORDER BY article_id
    """, (RELABEL_BEFORE,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def tag_one(title):
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
    rows = fetch_to_relabel()
    total = len(rows)

    if total == 0:
        print("沒有需要重標的新聞——全部都已用新標準標記完成!")
        return

    print(f"待重標新聞共 {total} 則(分界點:{RELABEL_BEFORE} 之前標記的)")
    ans = input("確認開始重標?(y/n):").strip().lower()
    if ans != "y":
        print("已取消,什麼都沒動。")
        return

    conn = psycopg2.connect(DATABASE_URL)
    done, failed = 0, 0

    for i, (article_id, title) in enumerate(rows, 1):
        short = title[:30]
        print(f"[{i}/{total}] id={article_id} {short}...")
        try:
            raw = tag_one(title)
            tags = parse_response(raw)
            if len(tags) != 5 or tags.get("importance") not in {"1", "2", "3", "4", "5"}:
                print(f"    ⚠ 格式異常,跳過。原始:{raw.strip()[:60]}")
                failed += 1
            else:
                write_back(conn, article_id, tags)
                print(f"    ✓ {tags['news_type']}/{tags['importance']}分")
                done += 1
        except Exception as e:
            print(f"    ✗ 失敗:{e}")
            failed += 1
            # 撞到額度上限就停止,已標的都保留,明天接續
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                print("\n⚠ 撞到每日額度上限,今天先停。已重標的都保留,明天重跑本程式會自動接續。")
                break
        time.sleep(SLEEP_BETWEEN)

    conn.close()
    print(f"\n本次完成:成功 {done} 則,失敗/跳過 {failed} 則。")
    remaining = total - done - failed
    if remaining > 0:
        print(f"還有約 {remaining} 則待重標,明天重跑本程式即可接續。")


if __name__ == '__main__':
    main()