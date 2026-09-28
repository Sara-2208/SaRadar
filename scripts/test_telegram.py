import os, requests
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("TELEGRAM_BOT_TOKEN")

# 1. Find your chat ID
updates = requests.get(f"https://api.telegram.org/bot{token}/getUpdates").json()
if not updates.get("result"):
    print("❌ No messages found. Send 'hi' to your bot first, then rerun.")
else:
    chat_id = updates["result"][-1]["message"]["chat"]["id"]
    print("✅ Your chat ID:", chat_id)

    # 2. Send a test alert
    msg = "📡 SaRadar is online! Job alerts will appear here."
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat_id, "text": msg})
    print("✅ Message sent!" if r.ok else f"❌ Send failed: {r.text}")