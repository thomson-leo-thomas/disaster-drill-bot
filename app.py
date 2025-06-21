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

# === Load Questions and Mythbusters ===
with open("data.json", "r", encoding="utf-8") as file:
    SCENARIOS = json.load(file)

with open("mythbusters.json", "r", encoding="utf-8") as mythfile:
    MYTHBUSTERS = json.load(mythfile)

# === Database Setup ===
db = sqlite3.connect("users.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    xp INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    rank TEXT DEFAULT '🐣 Trainee Responder',
    last_active TEXT,
    completed_today INTEGER DEFAULT 0
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS answers (
    chat_id INTEGER,
    scenario TEXT
)''')
db.commit()

# === Ranks ===
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

# === Helper Functions ===
def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(TELEGRAM_API + "sendMessage", json=payload)

def get_user(chat_id):
    cursor.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
    user = cursor.fetchone()
    if not user:
        today = datetime.utcnow().date().isoformat()
        cursor.execute("INSERT INTO users (chat_id, last_active) VALUES (?, ?)", (chat_id, today))
        db.commit()
        return (chat_id, 0, 0, "🐣 Trainee Responder", today, 0)
    return user

def update_user(chat_id, xp=None, streak=None, rank=None, completed_today=None):
    updates = []
    params = []
    if xp is not None:
        updates.append("xp = ?")
        params.append(xp)
    if streak is not None:
        updates.append("streak = ?")
        params.append(streak)
    if rank is not None:
        updates.append("rank = ?")
        params.append(rank)
    if completed_today is not None:
        updates.append("completed_today = ?")
        params.append(completed_today)
    if updates:
        updates.append("last_active = ?")
        params.append(datetime.utcnow().date().isoformat())
        params.append(chat_id)
        cursor.execute(f"UPDATE users SET {', '.join(updates)} WHERE chat_id = ?", tuple(params))
        db.commit()

def get_level(xp):
    for points, title in reversed(LEVELS):
        if xp >= points:
            return title
    return LEVELS[0][1]

def has_answered(chat_id, scenario):
    cursor.execute("SELECT 1 FROM answers WHERE chat_id = ? AND scenario = ?", (chat_id, scenario))
    return cursor.fetchone() is not None

def mark_answered(chat_id, scenario):
    cursor.execute("INSERT INTO answers (chat_id, scenario) VALUES (?, ?)", (chat_id, scenario))
    db.commit()

# === Webhook ===
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    message = data.get("message") or data.get("callback_query", {}).get("message")
    user_text = data.get("message", {}).get("text") or data.get("callback_query", {}).get("data")
    chat_id = message["chat"]["id"] if message else None

    if not chat_id:
        return "No chat ID", 200

    user = get_user(chat_id)
    xp, streak, rank, last_active, completed_today = user[1:]
    today = datetime.utcnow().date().isoformat()

    if last_active != today:
        streak = streak + 1 if completed_today else 0
        update_user(chat_id, streak=streak, completed_today=0)
        cursor.execute("DELETE FROM answers WHERE chat_id = ?", (chat_id,))
        db.commit()

    if user_text.lower() == "/start":
        send_message(chat_id, "🚨 *Welcome to Disaster Sensei* 🚨\nYour personal dojo for disaster readiness.\n\nType /drill to begin today’s challenge.")

    elif user_text.lower() == "/drill":
        if completed_today:
            send_message(chat_id, "🌞 You’ve mastered today’s drills already. Come back tomorrow for more challenges!")
        else:
            unanswered = [s for s in SCENARIOS if not has_answered(chat_id, s['scenario'])]
            if not unanswered:
                send_message(chat_id, "🎉 You’ve tackled all our scenarios! Well done!")
                update_user(chat_id, completed_today=1)
                return "OK"
            scenario = random.choice(unanswered)
            mark_answered(chat_id, scenario['scenario'])

            msg = f"🔥 *Disaster Drill:*\n\n{scenario['scenario']}\n\n"
            msg += f"A: {scenario['A']}\nB: {scenario['B']}\nC: {scenario['C']}\nD: {scenario['D']}"

            buttons = {"inline_keyboard": [[
                {"text": "A", "callback_data": f"A|{scenario['correct']}|{scenario['scenario']}"},
                {"text": "B", "callback_data": f"B|{scenario['correct']}|{scenario['scenario']}"},
                {"text": "C", "callback_data": f"C|{scenario['correct']}|{scenario['scenario']}"},
                {"text": "D", "callback_data": f"D|{scenario['correct']}|{scenario['scenario']}"}
            ]]}
            send_message(chat_id, msg, reply_markup=json.dumps(buttons))

    elif "|" in user_text:
        selected, correct, scen_text = user_text.split("|", 2)
        scenario = next((s for s in SCENARIOS if s["scenario"] == scen_text), None)
        if not scenario:
            send_message(chat_id, "⚠️ Hmm, that scenario vanished into thin air. Try /drill again.")
            return "OK"

        feedback = scenario['feedback'].get(selected, "No feedback available.")

        if selected == correct:
            xp += 10
            feedback += "\n✅ *+10 XP earned!*"
        else:
            feedback += "\n❌ No XP this time."

        new_rank = get_level(xp)
        if new_rank != rank:
            feedback += f"\n🎖️ *Rank Up!* Welcome, {new_rank}!"
            rank = new_rank

        cursor.execute("SELECT COUNT(*) FROM answers WHERE chat_id = ?", (chat_id,))
        count = cursor.fetchone()[0]

        if count >= 5:
            fun_fact = random.choice(MYTHBUSTERS)
            feedback += f"\n\n🎯 *Drill Complete!* Total XP: {xp} 🌟\n💬 *Sensei Wisdom:* {fun_fact}"
            update_user(chat_id, xp=xp, rank=rank, completed_today=1)
        else:
            feedback += "\n\n🔥 *Next challenge coming up...* Type /drill."
            update_user(chat_id, xp=xp, rank=rank)

        send_message(chat_id, feedback)

    elif user_text.lower() == "/profile":
        profile = f"👤 *Your Profile*\n\nXP: {xp}\nStreak: {streak} days\nRank: {rank}\nDrill Status: {'✅ Completed' if completed_today else '🔄 In Progress'}"
        send_message(chat_id, profile)

    elif user_text.lower() == "/help":
        msg = "🧭 *Sensei Guide*\n\n"
        msg += "/start — Begin your training\n"
        msg += "/drill — Face today's disaster scenario\n"
        msg += "/profile — View your progress\n"
        msg += "/about — Know your Sensei"
        send_message(chat_id, msg)

    elif user_text.lower() == "/about":
        about = "👤 *About Disaster Sensei*\n\nCrafted by *Thomson* ⚙️\nWhere gamified survival training meets fun and smarts.\n\n⚠️ *Disclaimer:* This is for educational use. In real emergencies, follow official advice."
        send_message(chat_id, about)

    else:
        send_message(chat_id, "🤔 That doesn’t ring a bell. Try /drill to get started.")

    return "OK"

# === Admin Cleanup ===
@app.route("/cleanup")
def cleanup():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return jsonify({"status": "unauthorized"}), 401
    cursor.execute("DELETE FROM users")
    cursor.execute("DELETE FROM answers")
    db.commit()
    return jsonify({"status": "Sessions wiped clean!"})

# === Run Server ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

