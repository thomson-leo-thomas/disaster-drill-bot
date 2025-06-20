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
def send_message(chat_id, text, buttons=None):
    url = TELEGRAM_API + "sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if buttons:
        payload["reply_markup"] = {
            "keyboard": [[{"text": btn} for btn in buttons]],
            "resize_keyboard": True,
            "one_time_keyboard": False
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

    # Get or create session for user
    session = user_sessions.setdefault(chat_id, {
        "questions": [],
        "current_q": None,
        "xp": 0,
        "count": 0,
        "completed_today": False
    })

    # === Handle /start ===
    if user_text.lower() == "/start":
        welcome = (
            "🚨 *Welcome to Disaster Sensei!* 🚨\n"
            "Your personal dojo for disaster readiness.\n\n"
            "Type /drill to begin today’s challenge. 🧠🔥"
        )
        send_message(chat_id, welcome)

    # === Handle /drill ===
    elif user_text.lower() == "/drill":
        if session["completed_today"]:
            send_message(chat_id, "🌞 You've completed today's drills!\nCome back tomorrow for new challenges.")
        elif session["count"] >= 5:
            session["completed_today"] = True
            fun_fact = random.choice(MYTHBUSTERS)
            summary = f"🎯 *Drill Complete!*\nYou earned *{session['xp']} XP* today."
            summary += f"\n\n📘 *Sensei Wisdom:* _{fun_fact}_"
            summary += "\n\nCome back tomorrow for more survival training!"
            send_message(chat_id, summary)
        else:
            scenario = random.choice(SCENARIOS)
            session["current_q"] = scenario
            session["questions"].append(scenario)
            scenario["answered"] = False
            session["count"] += 1

            msg = f"🔥 *Disaster Drill #{session['count']}*\n\n"
            msg += f"{scenario['scenario']}\n\n"
            msg += f"A: {scenario['A']}\nB: {scenario['B']}\nC: {scenario['C']}\nD: {scenario['D']}"
            send_message(chat_id, msg, buttons=["A", "B", "C", "D"])

    # === Handle Answers A/B/C/D ===
    elif user_text.upper() in ["A", "B", "C", "D"]:
        scenario = session.get("current_q")
        selected = user_text.upper()

        if scenario:
            already_answered = scenario.get("answered", False)
            is_correct = selected == scenario["correct"]
            feedback = scenario["feedback"].get(selected, "Invalid choice.")

            if not already_answered:
                scenario["answered"] = True
                if is_correct:
                    session["xp"] += 10
                    feedback += "\n🟢 *You gained 10 XP!*"
                else:
                    feedback += "\n🔴 *No XP this time.*"
            else:
                feedback += "\n⚠️ *You’ve already answered this question.*"

            send_message(chat_id, feedback)

            # After response, check if it's last question
            if session["count"] >= 5:
                session["completed_today"] = True
                fun_fact = random.choice(MYTHBUSTERS)
                summary = f"\n🎯 *Drill Complete!*\nYou earned *{session['xp']} XP* today."
                summary += f"\n\n📘 *Sensei Wisdom:* _{fun_fact}_"
                summary += "\n\nCome back tomorrow for more survival training!"
                send_message(chat_id, summary)
            else:
                send_message(chat_id, "🟢 *Ready for your next scenario?* Type /drill", buttons=["/drill"])
        else:
            send_message(chat_id, "❗️Start a drill first using /drill")

    # === Handle /help ===
    elif user_text.lower() == "/help":
        msg = (
            "🧭 *Sensei Guide*\n\n"
            "/start — Begin your training\n"
            "/drill — Face today's disaster simulation\n"
            "/about — Learn about the bot\n\n"
            "Need backup? Just type a command above."
        )
        send_message(chat_id, msg)

    # === Handle /about ===
    elif user_text.lower() == "/about":
        about = (
            "👤 *About Disaster Sensei*\n\n"
            "Built by *Thomson* ⚙️\n"
            "On a mission to make safety training smart, simple, and unforgettable.\n\n"
            "Let’s make safety second nature. 💡"
        )
        send_message(chat_id, about)

    # === Catch-All ===
    else:
        send_message(chat_id, "❓ I didn’t understand that. Type /drill to begin.")

    return "OK"

# === For Local Development ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
