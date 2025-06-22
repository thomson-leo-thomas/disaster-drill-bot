
import os
import json
import random
import requests
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify
from datetime import datetime, date

app = Flask(__name__)

# === Telegram Bot Setup ===
BOT_TOKEN = os.environ["BOT_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/"
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "securetoken123")

# === PostgreSQL Setup ===
DATABASE_URL = os.environ["DATABASE_URL"]

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

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

def get_level(xp):
    for points, title in reversed(LEVELS):
        if xp >= points:
            return title
    return LEVELS[0][1]

def get_progress_bar(xp):
    for i in range(len(LEVELS) - 1):
        curr_xp, _ = LEVELS[i]
        next_xp, next_rank = LEVELS[i + 1]
        if curr_xp <= xp < next_xp:
            progress = (xp - curr_xp) / (next_xp - curr_xp)
            bar = "🟩" * int(progress * 10) + "⬜" * (10 - int(progress * 10))
            return bar, int(progress * 100), next_xp - xp, next_rank
    return "🟩" * 10, 100, 0, LEVELS[-1][1]

# === Send Telegram Message ===
def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(TELEGRAM_API + "sendMessage", json=payload)

# === Webhook ===
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()

    if "callback_query" in data:
        callback = data["callback_query"]
        chat_id = callback["message"]["chat"]["id"]
        user_text = callback["data"]
        message = callback["message"]
        requests.post(TELEGRAM_API + "answerCallbackQuery", json={"callback_query_id": callback["id"]})
    else:
        message = data.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        user_text = message.get("text", "").strip()

    if not chat_id:
        return "No chat ID", 200

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s", (chat_id,))
    user = cur.fetchone()

    if not user:
        cur.execute("INSERT INTO users (id, first_name, xp, streak, rank, completed_today, drills, current_q, last_active) VALUES (%s, %s, 0, 0, %s, false, 0, NULL, CURRENT_DATE)",
                    (chat_id, message["chat"].get("first_name", "Sensei"), get_level(0)))
        conn.commit()
        cur.execute("SELECT * FROM users WHERE id = %s", (chat_id,))
        user = cur.fetchone()

    today = date.today()
    if user["last_active"] != today:
        streak = user["streak"] + 1 if user["completed_today"] else 0
        cur.execute("UPDATE users SET completed_today = false, drills = 0, current_q = NULL, last_active = %s, streak = %s WHERE id = %s", (today, streak, chat_id))
        conn.commit()
        user["completed_today"] = False
        user["drills"] = 0
        user["streak"] = streak

    cmd = user_text.lower()

    if cmd == "/start":
        send_message(chat_id, "🚨 *Welcome to Disaster Sensei* 🚨
Type /drill to begin today’s challenge.")

    elif cmd == "/drill":
        if user["completed_today"]:
            send_message(chat_id, "🌞 You've already completed today's drill. Come back tomorrow!")
        else:
            send_message(chat_id, "🧠 Sensei is thinking...")
            scenario = random.choice(SCENARIOS)
            msg = f"🔥 *Disaster Drill {user['drills'] + 1}/5:*

{scenario['scenario']}

"
            msg += f"A: {scenario['A']}
B: {scenario['B']}
C: {scenario['C']}
D: {scenario['D']}"
            buttons = {"inline_keyboard": [[{"text": opt, "callback_data": opt} for opt in "ABCD"]]}
            send_message(chat_id, msg, reply_markup=json.dumps(buttons))
            cur.execute("UPDATE users SET current_q = %s WHERE id = %s", (json.dumps(scenario), chat_id))
            conn.commit()

    elif cmd in ["a", "b", "c", "d"]:
        if not user["current_q"]:
            send_message(chat_id, "🌀 No drill in progress. Use /drill to start.")
        else:
            scenario = json.loads(user["current_q"]) if isinstance(user["current_q"], str) else user["current_q"]
            selected = cmd.upper()
            correct = selected == scenario["correct"]
            xp_earned = 10 if correct else 0
            new_xp = user["xp"] + xp_earned
            new_rank = get_level(new_xp)

            feedback = scenario["feedback"].get(selected, "Invalid option.")
            feedback += f"
{'✅' if correct else '❌'} You earned *{xp_earned} XP*."

            if user["drills"] + 1 >= 5:
                fun_fact = random.choice(MYTHBUSTERS)
                feedback += f"
🎯 *Drill Complete!*"
                feedback += f"
✨ Total XP Today: *{new_xp}*"
                feedback += f"
🔥 Streak: *{user['streak']} days*"
                feedback += f"
🏅 Rank: *{new_rank}*"
                feedback += f"
📚 *Sensei Wisdom:* {fun_fact}"
                feedback += f"
🔁 Come back tomorrow!"
                cur.execute("UPDATE users SET xp = %s, rank = %s, drills = 5, completed_today = true, current_q = NULL WHERE id = %s", (new_xp, new_rank, chat_id))
                conn.commit()
            else:
                cur.execute("UPDATE users SET xp = %s, rank = %s, drills = drills + 1, current_q = NULL WHERE id = %s", (new_xp, new_rank, chat_id))
                conn.commit()
                buttons = {"inline_keyboard": [[{"text": "Next Scenario", "callback_data": "/drill"}]]}
                send_message(chat_id, feedback, reply_markup=json.dumps(buttons))
                return "OK"

            bar, percent, left, next_rank = get_progress_bar(new_xp)
            feedback += f"

🏅 *Progress to next rank:* {next_rank}
{bar} {percent}%
🧗 XP to next rank: {left}"
            send_message(chat_id, feedback)

    elif cmd == "/profile":
        bar, percent, left, next_rank = get_progress_bar(user["xp"])
        profile = f"👤 *Your Profile*

XP: {user['xp']}
Streak: {user['streak']} days
Rank: {user['rank']}
Drills Today: {user['drills']}/5

🏅 Progress to next rank: {next_rank}
{bar} {percent}%
🧗 XP to next rank: {left}

Drill Completed: {'✅' if user['completed_today'] else '❌'}"
        send_message(chat_id, profile)

    elif cmd == "/help":
        help_msg = "🧭 *Sensei Guide*

/start — Begin training
/drill — Daily disaster challenge
/profile — View your stats
/help — Show commands"
        send_message(chat_id, help_msg)

    elif cmd == "/about":
        about = "👤 *About Disaster Sensei*

Built by *Thomson* ⚙️
Gamified safety training made smart, fun, and unforgettable.

⚠️ *Disclaimer:*
This bot is for educational purposes only. Follow real-world safety authorities in emergencies."
        send_message(chat_id, about)

    cur.close()
    conn.close()
    return "OK"

