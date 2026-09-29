import os
from dotenv import load_dotenv
from groq import Groq
from google import genai

load_dotenv()

print("=== GROQ ===")
for m in Groq(api_key=os.getenv("GROQ_API_KEY")).models.list().data:
    print(m.id)

print("\n=== GEMINI ===")
gem = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
for m in gem.models.list():
    if "flash" in m.name or "pro" in m.name:
        print(m.name)