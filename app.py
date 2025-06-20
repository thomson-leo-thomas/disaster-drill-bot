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

# === Utility to send message with optional buttons ===
def send_message(chat_id, text, buttons=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }

    # Add reply keyboard buttons for A/B/C/D
    if buttons:
        payload["reply_markup"] = {
            "keyboard": [[{"text": b} for b in buttons]],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }

    requests.post(TELEGRAM_API + "sendMessage", json=payload)

# === Webhook Endpoint ===
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    message = data.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    user_text = message.get("text", "").strip()

    if not chat_id:
        return "No chat ID", 200

    # Initialize session
    session = user_sessions.setdefault(chat_id, {
        "questions": [],
        "current_q": None,
        "xp": 0,
        "streak": 0,
        "count": 0,
        "completed_today": False
    })

    # === /start Command ===
    if user_text.lower() == "/start":
        send_message(chat_id,
            "🚨 *Welcome to Disaster Sensei* 🚨\n"
            "Your personal dojo for disaster readiness.\n\n"
            "Type /drill to begin today’s challenge.")

    # === /drill Command ===
    elif user_text.lower() == "/drill":
        if session["completed_today"]:
            send_message(chat_id,
                "🕓 You've already completed today's drill.\n"
                "Come back tomorrow for a new challenge!")
        else:
            # Pick a scenario the user hasn't seen yet
            available = [s for s in SCENARIOS if s not in session["questions"]]
            if not available:
                send_message(chat_id, "🎉 You've completed all available drills!")
                return "OK"

            scenario = random.choice(available)
            session["current_q"] = scenario
            session["questions"].append(scenario)
            session["count"] += 1

            msg = f"🔥 *Disaster Drill:*\n\n{scenario['scenario']}\n\n"
            msg += f"A: {scenario['A']}\nB: {scenario['B']}\nC: {scenario['C']}\nD: {scenario['D']}"

            send_message(chat_id, msg, buttons=["A", "B", "C", "D"])

    # === Handle Answers ===
    elif user_text.upper() in ["A", "B", "C", "D"]:
        scenario = session.get("current_q")
        if scenario:
            selected = user_text.upper()

            # Prevent XP farming from the same question
            if scenario not in session["questions"]:
                send_message(chat_id, "❗ Start a drill with /drill before answering.")
                return "OK"

            is_correct = selected == scenario["correct"]
            feedback = scenario["feedback"].get(selected, "Invalid choice.")

            if is_correct:
                session["xp"] += 10
                feedback += "\n🟢 *You gained 10 XP!*"
            else:
                feedback += "\n🔴 *No XP this time.*"

            send_message(chat_id, feedback)

            if session["count"] >= 5:
                session["completed_today"] = True
                fun_fact = random.choice(MYTHBUSTERS)
                summary = f"\n🎯 *Drill Complete!*\nYou earned *{session['xp']} XP* today."
                summary += f"\n\n📘 *Sensei Wisdom:* _{fun_fact}_"
                summary += "\n\nCome back tomorrow to keep training!"
                send_message(chat_id, summary)
            else:
                send_message(chat_id, "🟢 *Ready for your next scenario?* Type /drill")
        else:
            send_message(chat_id, "❗ Start a drill with /drill before answering.")

    # === /help Command ===
    elif user_text.lower() == "/help":
        msg = (
            "🧭 *Sensei Guide*\n\n"
            "/start — Begin your training\n"
            "/drill — Face today’s disaster simulation\n"
            "/about — Learn about the bot\n\n"
            "Remember: Panic is the enemy. Preparation is power. 💥"
        )
        send_message(chat_id, msg)

    # === /about Command ===
    elif user_text.lower() == "/about":
        msg = (
            "👤 *About Disaster Sensei*\n\n"
            "Built by *Thomson* ⚙️\n"
            "On a mission to make safety training smart, simple, and unforgettable.\n\n"
            "Let’s make safety second nature."
        )
        send_message(chat_id, msg)

    # === Catch-all
    else:
        send_message(chat_id, "❓ I didn’t understand that. Type /drill to begin.")

    return "OK"

# === Run App Locally ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

