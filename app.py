import os
import random
import json
import sqlite3
from flask import Flask, request, jsonify
import requests
from datetime import datetime, date

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

# === SQLite Setup ===
conn = sqlite3.connect("users.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    xp INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    rank TEXT DEFAULT '🐣 Trainee Responder',
    last_active TEXT,
    completed_today INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS answered_questions (
    chat_id INTEGER,
    question TEXT,
    PRIMARY KEY (chat_id, question)
)
""")

conn.commit()

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

def get_level(xp):
    for points, title in reversed(LEVELS):
        if xp >= points:
            return title
    return LEVELS[0][1]

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(TELEGRAM_API + "sendMessage", json=payload)

def reset_if_new_day(chat_id, last_active):
    today = date.today().isoformat()
    if last_active != today:
        cursor.execute("UPDATE users SET completed_today = 0, last_active = ? WHERE chat_id = ?", (today, chat_id))
        cursor.execute("DELETE FROM answered_questions WHERE chat_id = ?", (chat_id,))
        conn.commit()

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    message = data.get("message") or data.get("callback_query", {}).get("message")
    user_text = data.get("message", {}).get("text") or data.get("callback_query", {}).get("data")
    chat_id = message["chat"]["id"] if message else None

    if not chat_id:
        return "No chat ID", 200

    cursor.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
    user = cursor.fetchone()

    if not user:
        today = date.today().isoformat()
        cursor.execute("INSERT INTO users (chat_id, last_active) VALUES (?, ?)", (chat_id, today))
        conn.commit()
        user = (chat_id, 0, 0, "🐣 Trainee Responder", today, 0)

    _, xp, streak, rank, last_active, completed_today = user
    reset_if_new_day(chat_id, last_active)

    cmd = user_text.strip().lower()

    if cmd == "/start":
        send_message(chat_id, "🚨 *Welcome to Disaster Sensei* 🚨\nYour personal dojo for disaster readiness.\n\nType /drill to begin today’s challenge.")

    elif cmd == "/drill":
        cursor.execute("SELECT completed_today FROM users WHERE chat_id = ?", (chat_id,))
        if cursor.fetchone()[0]:
            send_message(chat_id, "🌞 You've already completed today's drill.\nCome back tomorrow for a new challenge!")
        else:
            # Avoid repeated questions
            cursor.execute("SELECT question FROM answered_questions WHERE chat_id = ?", (chat_id,))
            seen = {q[0] for q in cursor.fetchall()}
            options = [s for s in SCENARIOS if s["scenario"] not in seen]
            if not options:
                send_message(chat_id, "🎉 You've seen all scenarios. Come back tomorrow for new ones!")
                return "OK"

            scenario = random.choice(options)
            cursor.execute("INSERT INTO answered_questions (chat_id, question) VALUES (?, ?)", (chat_id, scenario["scenario"]))
            conn.commit()

            message = f"🔥 *Disaster Drill:*\n\n{scenario['scenario']}\n\n"
            message += f"A: {scenario['A']}\nB: {scenario['B']}\nC: {scenario['C']}\nD: {scenario['D']}"

            buttons = {"inline_keyboard": [[
                {"text": "A", "callback_data": f"A|{scenario['correct']}"},
                {"text": "B", "callback_data": f"B|{scenario['correct']}"},
                {"text": "C", "callback_data": f"C|{scenario['correct']}"},
                {"text": "D", "callback_data": f"D|{scenario['correct']}"}
            ]]}
            send_message(chat_id, message, reply_markup=json.dumps(buttons))

    elif "|" in cmd:
        selected, correct = cmd.split("|")
        is_correct = selected == correct
        earned = 10 if is_correct else 0

        feedback = "✅ Correct!" if is_correct else "❌ Incorrect."
        feedback += f"\n{'🟢' if is_correct else '🔴'} You earned {earned} XP."

        new_xp = xp + earned
        new_rank = get_level(new_xp)

        cursor.execute("""
        UPDATE users SET xp = ?, rank = ?, completed_today = 1 WHERE chat_id = ?
        """, (new_xp, new_rank, chat_id))
        conn.commit()

        bonus = random.choice(MYTHBUSTERS)
        feedback += f"\n\n📚 *Sensei Wisdom:* {bonus}"
        send_message(chat_id, feedback)

    elif cmd == "/profile":
        profile = f"👤 *Your Profile*\n\nXP: {xp}\nStreak: {streak} days\nRank: {rank}"
        send_message(chat_id, profile)

    elif cmd == "/help":
        msg = "🧭 *Sensei Guide*\n\n/start — Begin your training\n/drill — Face today's disaster simulation\n/profile — View your stats\n/about — Learn about the bot"
        send_message(chat_id, msg)

    elif cmd == "/about":
        about = "👤 *About Disaster Sensei*\n\nBuilt by *Thomson* ⚙️\nGamified safety training made smart, fun, and practical.\n\n⚠️ *Disclaimer:*\nThis bot is for educational use only. Follow official guidelines in real-life emergencies."
        send_message(chat_id, about)

    else:
        send_message(chat_id, "❓ I didn’t understand that. Type /drill to begin.")

    return "OK"

@app.route("/cleanup")
def cleanup():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return jsonify({"status": "unauthorized"}), 401
    cursor.execute("DELETE FROM users")
    cursor.execute("DELETE FROM answered_questions")
    conn.commit()
    return jsonify({"status": "sessions cleared"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

