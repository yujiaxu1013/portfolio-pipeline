import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

response = client.models.generate_content(
    model="gemini-3.5-flash",
    contents="用繁體中文回我一句話:如果你收到這則訊息,請說「連線成功」。",
)

print(response.text)