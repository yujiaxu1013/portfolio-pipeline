import os
from dotenv import load_dotenv
from google import genai

from prompt_template import TAGGING_PROMPT

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-flash-lite-latest"

# 測試樣本:(標題, 我們期望的分數方向)
samples = [
    ("三大法人賣超台股239.3億元 - 經濟日報", "應壓低到 2(例行法人數據)"),
    ("外資終結連六買提款119億 三大法人賣超239.3億元 - news.cnyes.com", "應壓低到 2(例行法人數據)"),
    ("股匯震盪 新台幣盤中貶破32.4元 - 工商時報", "應壓低到 2(匯率盤面波動)"),
    ("台日韓均遭美列匯率操縱觀察名單 主要貿易夥伴暫無操縱國 - news.cnyes", "應壓低到 2-3(象徵性事件)"),
    ("南韓6月出口大增！晶片外銷激增近200% 半導體景榮支撐7月升息預期", "應維持 4(具體出口數據)"),
    ("台積電A16背面供電技術突破！埃米級競賽再進一步:速度增10%、功耗降", "應維持 4(技術突破有具體幅度)"),
]

def tag(title):
    resp = client.models.generate_content(
        model=MODEL,
        contents=TAGGING_PROMPT.format(title=title),
    )
    return resp.text.strip()

def main():
    for title, expect in samples:
        print(f"\n標題:{title[:40]}")
        print(f"期望:{expect}")
        print("模型輸出:")
        print(tag(title))
        print("-" * 50)

if __name__ == '__main__':
    main()