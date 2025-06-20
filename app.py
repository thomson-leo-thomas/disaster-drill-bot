import os
import random
import json
from flask import Flask, request
import requests

# === Setup Flask App ===
app = Flask(__name__)

# === Telegram Bot Setup ===
BOT_TOKEN = os.environ['BOT_TOKEN']
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# === Load Scenarios from data.json ===
with open("data.json", "r", encoding="utf-8") as file:
    SCENARIOS = json.load(file)

# === Load Mythbusters from mythbusters.json ===
with open("mythbusters.json", "r", encoding="utf-8") as mythfile:
    MYTHBUSTERS = json.load(mythfile)

# === In-memory user session tracking ===
user_sessions = {}

# === Send message to user ===
def send_message(chat_id, text):
    url = TELEGRAM_API + "sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    requests.post(url, json=payload)

# === Telegram Webhook Endpoint ===
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    message = data.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    user_text = message.get("text", "").strip()

    if not chat_id:
        return "No chat ID", 200

    # === Get or create session ===
    session = user_sessions.setdefault(chat_id, {
        "questions": [],
        "current_q": None,
        "xp": 0,
        "streak": 0,
        "count": 0,
        "completed_today": False
    })

    # === Handle /start ===
    if user_text.lower() == "/start":
        send_message(chat_id,
            "🚨 Welcome to Disaster Sensei 🚨\nYour personal dojo for disaster readiness.\n\nType /drill to begin today’s challenge.")

    # === Handle /drill ===
    elif user_text.lower() == "/drill":
        if session["completed_today"]:
            send_message(chat_id, "🌞 You've already completed today's drill.\nCome back tomorrow for a new challenge!")
        else:
            scenario = random.choice(SCENARIOS)
            session["current_q"] = scenario
            session["questions"].append(scenario)
            session["count"] += 1

            msg = f"🔥 Disaster Drill:\n\n{scenario['scenario']}\n\n"
            msg += f"A: {scenario['A']}\nB: {scenario['B']}\nC: {scenario['C']}\nD: {scenario['D']}\n\n"
            msg += "Choose an option: A, B, C, or D."
            send_message(chat_id, msg)

    # === Handle Answer (A/B/C/D) ===
    elif user_text.upper() in ["A", "B", "C", "D"]:
        scenario = session.get("current_q")
        if scenario:
            selected = user_text.upper()
            feedback = scenario["feedback"].get(selected, "Invalid option.")

            if selected == scenario["correct"]:
                session["xp"] += 10
                feedback += "\n✅ You gained 10 XP!"
            else:
                feedback += "\n❌ No XP gained."

            send_message(chat_id, feedback)

            if session["count"] >= 5:
                session["completed_today"] = True
                fun_fact = random.choice(MYTHBUSTERS)
                summary = f"\n🎯 Drill Complete! You earned {session['xp']} XP today."
                summary += f"\n\n📘 Safety Insight: {fun_fact}"
                summary += "\n\nCome back tomorrow for more challenges."
                send_message(chat_id, summary)
            else:
                send_message(chat_id, "✅ Ready for your next scenario? Type /drill")
        else:
            send_message(chat_id, "❗️Start a drill first using /drill")

    # === Handle /help ===
    elif user_text.lower() == "/help":
        msg = "🧭 Sensei Guide\n\n"
        msg += "/start — Begin your training\n"
        msg += "/drill — Face today's disaster simulation\n"
        msg += "/about — Learn about the bot\n"
        msg += "Need backup? Just type one of the commands above."
        send_message(chat_id, msg)

    # === Handle /about ===
    elif user_text.lower() == "/about":
        about = "👤 About Disaster Sensei\n\nBuilt by Thomson ⚙️\nOn a mission to make safety training smart, simple, and unforgettable.\n\nLet’s make safety second nature."
        send_message(chat_id, about)

    # === Catch-all for unknown messages ===
    else:
        send_message(chat_id, "❓ I didn’t understand that. Type /drill to begin.")

    return "OK"

# === Run the Flask App ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

