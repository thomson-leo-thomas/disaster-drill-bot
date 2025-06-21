import os
import random
import json
import sqlite3
from flask import Flask, request, jsonify
import requests
from datetime import datetime

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

# === SQLite Setup ===
conn = sqlite3.connect("users.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    xp INTEGER,
    streak INTEGER,
    rank TEXT,
    completed_today INTEGER,
    last_active TEXT
)''')
conn.commit()

# === Helper Functions ===
def send_message(chat_id, text, reply_markup=None):
    url = TELEGRAM_API + "sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(url, json=payload)

def get_user(chat_id):
    c.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)", (chat_id, 0, 0, LEVELS[0][1], 0, str(datetime.utcnow().date())))
        conn.commit()
        return get_user(chat_id)
    return row

def update_user(chat_id, xp=None, streak=None, rank=None, completed_today=None, last_active=None):
    user = list(get_user(chat_id))
    if xp is not None:
        user[1] = xp
    if streak is not None:
        user[2] = streak
    if rank is not None:
        user[3] = rank
    if completed_today is not None:
        user[4] = int(completed_today)
    if last_active is not None:
        user[5] = last_active
    c.execute("REPLACE INTO users VALUES (?, ?, ?, ?, ?, ?)", tuple(user))
    conn.commit()

def get_level(xp):
    for points, title in reversed(LEVELS):
        if xp >= points:
            return title
    return LEVELS[0][1]

user_sessions = {}

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    message = data.get("message") or data.get("callback_query", {}).get("message")
    user_text = data.get("message", {}).get("text") or data.get("callback_query", {}).get("data")
    chat_id = message["chat"]["id"] if message else None

    if not chat_id:
        return "No chat ID", 200

    session = user_sessions.setdefault(chat_id, {
        "questions": [],
        "answered": set(),
        "count": 0,
        "current_q": None
    })

    user = get_user(chat_id)
    xp, streak, rank, completed_today, last_active = user[1], user[2], user[3], bool(user[4]), user[5]

    today = str(datetime.utcnow().date())
    if today != last_active:
        streak = streak + 1 if completed_today else 0
        update_user(chat_id, completed_today=0, streak=streak, last_active=today)
        session["questions"] = []
        session["answered"] = set()
        session["count"] = 0
        session["current_q"] = None

    cmd = user_text.strip().lower()

    if cmd == "/start":
        send_message(chat_id, "🚨 *Welcome to Disaster Sensei* 🚨\nYour personal dojo for disaster readiness.\n\nType /drill to begin today’s challenge.")

    elif cmd == "/drill":
        user = get_user(chat_id)
        if user[4]:
            send_message(chat_id, "🌞 You've already completed today's drill.\nCome back tomorrow for a new challenge!")
        else:
            available = [s for s in SCENARIOS if s['scenario'] not in session["answered"]]
            if not available:
                send_message(chat_id, "✅ No more new questions available today!")
                return "OK"

            scenario = random.choice(available)
            session["current_q"] = scenario
            session["questions"].append(scenario)
            session["count"] += 1

            msg = f"🔥 *Disaster Drill:*\n\n{scenario['scenario']}\n\n"
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
                send_message(chat_id, "⚠️ Already answered this one, trainee!")
            else:
                selected = cmd.upper()
                session["answered"].add(scenario["scenario"])
                correct = selected == scenario["correct"]

                feedback = scenario["feedback"].get(selected, "Invalid option.")
                xp_gain = (10 + streak) if correct else 0  # streak multiplier here
                xp += xp_gain

                new_rank = get_level(xp)
                rank_up = new_rank != rank
                rank = new_rank

                msg = feedback
                if correct:
                    msg += f"\n✅ You earned *{xp_gain} XP*!"
                else:
                    msg += "\n❌ No XP this time."

                if rank_up:
                    msg += f"\n🌟 Rank Up! Welcome to {rank}"

                update_user(chat_id, xp=xp, rank=rank)
                send_message(chat_id, msg)

                if session["count"] >= 5:
                    update_user(chat_id, completed_today=1)
                    fun_fact = random.choice(MYTHBUSTERS)
                    summary = f"🎯 *Drill Complete!* You earned {xp} XP today.\n\n📚 *Sensei Wisdom:* {fun_fact}\n\nCome back tomorrow for more survival training."
                    send_message(chat_id, summary)
                else:
                    buttons = {"inline_keyboard": [[{"text": "Next Scenario", "callback_data": "/drill"}]]}
                    send_message(chat_id, "✅ Ready for your next test?", reply_markup=json.dumps(buttons))
        else:
            send_message(chat_id, "❗️ Use /drill to begin your session.")

    elif cmd == "/profile":
        profile = f"👤 *Your Profile*\n\nXP: {xp}\nStreak: {streak} days\nRank: {rank}\nDrills Completed Today: {'✅' if user[4] else '❌'}"
        send_message(chat_id, profile)

    elif cmd == "/help":
        msg = "🧭 *Sensei Guide*\n\n/start — Begin your training\n/drill — Face today's disaster scenario\n/profile — View your stats\n/about — Info about the bot"
        send_message(chat_id, msg)

    elif cmd == "/about":
        msg = "👤 *About Disaster Sensei*\n\nBuilt by *Thomson* ⚙️\nGamified safety training to sharpen your instincts.\n\n⚠️ *Disclaimer:* Educational use only. Always follow official emergency protocols."
        send_message(chat_id, msg)

    else:
        send_message(chat_id, "❓ Hmm... that doesn’t compute. Try /drill to get started.")

    return "OK"

@app.route("/cleanup")
def cleanup():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return jsonify({"status": "unauthorized"}), 401
    user_sessions.clear()
    return jsonify({"status": "sessions cleared"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

