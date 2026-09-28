import os
from dotenv import load_dotenv
from groq import Groq
from google import genai

load_dotenv()

try:
    groq = Groq(api_key=os.getenv("GROQ_API_KEY"))
    models = [m.id for m in groq.models.list().data]
    print("✅ Groq works. Some models:", models[:5])
except Exception as e:
    print("❌ Groq failed:", e)

try:
    gem = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    models = [m.name for m in gem.models.list()][:5]
    print("✅ Gemini works. Some models:", models)
except Exception as e:
    print("❌ Gemini failed:", e)