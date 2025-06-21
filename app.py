import os
import random
import json
import sqlite3
from flask import Flask, request, jsonify
import requests
from datetime import datetime, timedelta

app = Flask(__name__)

# === Telegram Bot Setup ===
BOT_TOKEN = os.environ['BOT_TOKEN']
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "securetoken123")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# === Load Data ===
with open("data.json", "r", encoding="utf-8") as file:
    SCENARIOS = json.load(file)

with open("mythbusters.json", "r", encoding="utf-8") as mythfile:
    MYTHBUSTERS = json.load(mythfile)

# === User Sessions (in-memory) ===
user_sessions = {}

# === Level Titles ===
LEVELS = [
    (0, "🐣 Trainee Responder"),
    (50, "🛡️ Alert Apprentice"),
    (150, "🔥 Crisis Challenger"),
    (300, "🌪️ Disaster Defender"),
    (500, "🚨 Rescue Ranger"),
    (750, "🌍 Crisis Strategist"),
    (1000, "🎖️ Master Responder"),
    (1500, "🧠 Disaster Sensei"),
    (2000, "🔱 Guardian of Calm")
]

# === Send message to Telegram user ===
def send_message(chat_id, text, reply_markup=None):
    url = TELEGRAM_API + "sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(url, json=payload)

# === Reset user session if new day ===
def reset_if_new_day(session):
    today = datetime.utcnow().date()
    if session.get("last_active") != today:
        if session.get("completed_today"):
            session["streak"] += 1
        else:
            session["streak"] = 0
        session.update({
            "questions": [],
            "current_q": None,
            "answered": set(),
            "count": 0,
            "completed_today": False,
            "last_active": today
        })

# === Get level title ===
def get_level(xp):
    for points, title in reversed(LEVELS):
        if xp >= points:
            return title
    return LEVELS[0][1]

# === Webhook Endpoint ===
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    message = data.get("message") or data.get("callback_query", {}).get("message")
    user_text = data.get("message", {}).get("text") or data.get("callback_query", {}).get("data")
    chat_id = message["chat"]["id"] if message else None

    if not chat_id:
        return "No chat ID", 200

    session = user_sessions.setdefault(chat_id, {
        "xp": 0,
        "streak": 0,
        "rank": "🐣 Trainee Responder",
        "questions": [],
        "answered": set(),
        "count": 0,
        "current_q": None,
        "completed_today": False,
        "last_active": datetime.utcnow().date()
    })

    reset_if_new_day(session)
    cmd = user_text.strip().lower()

    if cmd == "/start":
        send_message(chat_id, "🚨 *Welcome to Disaster Sensei* 🚨\nYour personal dojo for disaster readiness.\n\nType /drill to begin today’s challenge.")

    elif cmd == "/drill":
        if session["completed_today"]:
            send_message(chat_id, "🌞 You've already completed today's drill.\nCome back tomorrow for a new challenge!")
        else:
            send_message(chat_id, "🧠 Sensei is thinking...")
            scenario = random.choice([s for s in SCENARIOS if s not in session["questions"]])
            session["current_q"] = scenario
            session["questions"].append(scenario)
            session["count"] += 1

            msg = f"🔥 *Disaster Drill {session['count']} of 5:*\n\n{scenario['scenario']}\n\n"
            msg += f"A: {scenario['A']}\nB: {scenario['B']}\nC: {scenario['C']}\nD: {scenario['D']}"

            buttons = {"inline_keyboard": [[
                {"text": "A", "callback_data": "A"},
                {"text": "B", "callback_data": "B"},
                {"text": "C", "callback_data": "C"},
                {"text": "D", "callback_data": "D"}
            ]]}
            send_message(chat_id, msg, reply_markup=json.dumps(buttons))

    elif cmd.upper() in ["A", "B", "C", "D"]:
        scenario = session.get("current_q")
        if scenario:
            if scenario["scenario"] in session["answered"]:
                send_message(chat_id, "⚠️ You've tackled this one already. No XP this time!")
            else:
                selected = cmd.upper()
                session["answered"].add(scenario["scenario"])
                correct = selected == scenario["correct"]
                xp_earned = 10 if correct else 0
                if correct and session["count"] == 5:
                    xp_earned += 5
                session["xp"] += xp_earned

                new_rank = get_level(session["xp"])
                if new_rank != session["rank"]:
                    session["rank"] = new_rank
                    rank_msg = f"\n🌟 *Rank Up!* You're now {new_rank}"
                else:
                    rank_msg = ""

                feedback = scenario["feedback"].get(selected, "Invalid option.")
                feedback += f"\n{'✅' if correct else '❌'} You earned *{xp_earned} XP*."
                feedback += f"\n🔥 Streak: {session['streak']} days\n🏅 Level: {new_rank}"
                feedback += rank_msg
                send_message(chat_id, feedback)

                if session["count"] >= 5:
                    session["completed_today"] = True
                    fun_fact = random.choice(MYTHBUSTERS)
                    summary = f"\n🎯 *Drill Complete!*\n"
                    summary += f"✨ You earned *{session['xp']} XP* today!\n"
                    summary += f"🔥 *Streak:* {session['streak']} days\n"
                    summary += f"🏅 *Level:* {session['rank']}\n\n"
                    summary += f"📚 *Sensei Wisdom:* {fun_fact}\n"
                    summary += "🔁 Come back tomorrow for more survival missions!"
                    send_message(chat_id, summary)
                else:
                    buttons = {"inline_keyboard": [[{"text": "Next Scenario", "callback_data": "/drill"}]]}
                    send_message(chat_id, "✅ Ready for your next challenge?", reply_markup=json.dumps(buttons))
        else:
            send_message(chat_id, "🌀 Session expired or no drill in progress. Type /drill to restart.")

    elif cmd == "/profile":
        profile = f"👤 *Your Profile*\n\nXP: {session['xp']}\nStreak: {session['streak']} days\nRank: {session['rank']}\nDrills Completed Today: {'✅' if session['completed_today'] else '❌'}"
        send_message(chat_id, profile)

    elif cmd == "/help":
        msg = "🧭 *Sensei Guide*\n\n"
        msg += "/start — Begin your training\n"
        msg += "/drill — Face today's disaster simulation\n"
        msg += "/profile — View your stats\n"
        msg += "/about — Learn about the bot"
        send_message(chat_id, msg)

    elif cmd == "/about":
        about = "👤 *About Disaster Sensei*\n\nBuilt by *Thomson* ⚙️\nGamified safety training made smart, fun, and practical.\n\n⚠️ *Disclaimer:*\nThis bot is for educational use only. Always follow official emergency guidelines."
        send_message(chat_id, about)

    else:
        send_message(chat_id, "❓ I didn’t get that. Try /drill to start a scenario.")

    return "OK"

# === Admin cleanup route ===
@app.route("/cleanup")
def cleanup():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return jsonify({"status": "unauthorized"}), 401
    user_sessions.clear()
    return jsonify({"status": "sessions cleared"})

# === Run App ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

