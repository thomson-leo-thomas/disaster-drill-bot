import os
import json
import random
from datetime import datetime, timedelta
import requests
from flask import Flask, request
import psycopg2
from psycopg2.pool import SimpleConnectionPool

app = Flask(__name__)

# Load questions and mythbusters data
with open("data.json", encoding="utf-8") as f:
    QUESTIONS = json.load(f)

with open("mythbusters.json", encoding="utf-8") as f:
    MYTHBUSTERS = json.load(f)

# Environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")

if not BOT_TOKEN or not DATABASE_URL or not ADMIN_TOKEN:
    raise Exception("Please set BOT_TOKEN, DATABASE_URL and ADMIN_TOKEN environment variables.")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# Setup PostgreSQL connection pool (min 1, max 5 connections)
pool = SimpleConnectionPool(1, 5, dsn=DATABASE_URL, sslmode='require')

# Rank labels for display
RANK_LABELS = {
    1: "🐣 Trainee Responder",
    2: "🧯 Drill Novice",
    3: "🚒 Ember Fighter",
    4: "🏕️ Survivalist",
    5: "🧠 Wise Responder",
    6: "🔥 Hazard Handler",
    7: "🚨 Alert Ace",
    8: "🛰️ Crisis Commander",
    9: "🎖️ Master Responder",
    10: "🥷 Disaster Sensei"
}

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        resp = requests.post(TELEGRAM_API, json=payload)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error sending message: {e}")

def init_user(chat_id, first_name=None):
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM users WHERE id = %s", (chat_id,))
                if not cur.fetchone():
                    cur.execute("""
                        INSERT INTO users
                        (id, first_name, xp, streak, rank, drills, completed_today, last_drill_date, current_q)
                        VALUES (%s, %s, 0, 0, 1, 0, FALSE, CURRENT_DATE, NULL)
                    """, (chat_id, first_name))
    finally:
        pool.putconn(conn)

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        first_name = data["message"]["chat"].get("first_name")
        text = data["message"].get("text", "").strip()
    elif "callback_query" in data:
        chat_id = data["callback_query"]["message"]["chat"]["id"]
        answer = data["callback_query"]["data"]
        return handle_answer(chat_id, answer)
    else:
        return "Unsupported update", 400

    init_user(chat_id, first_name)

    if text == "/start":
        send_message(chat_id,
            f"🧠 *Welcome, {first_name or 'Survivor'}!*\n"
            "Train your instincts in the Disaster Sensei Dojo.\n\n"
            "Type /drill to begin your daily survival drill.\n"
            "Use /help for available commands."
        )
    elif text == "/drill":
        return handle_drill(chat_id)
    elif text == "/profile":
        return handle_profile(chat_id)
    elif text == "/about":
        send_message(chat_id,
            "👨‍🏫 *Disaster Sensei*\n"
            "Created by *Thomson*.\n"
            "An interactive bot teaching disaster preparedness.\n"
            "Panic is the enemy, preparation is power."
        )
    elif text == "/help":
        send_message(chat_id,
            "🆘 *Available Commands:*\n"
            "/start - Welcome message\n"
            "/drill - Start daily drills (max 5 per day)\n"
            "/profile - Show your stats\n"
            "/about - About this bot"
        )
    else:
        send_message(chat_id, "❓ Unknown command. Try /help.")

    return "OK", 200

def handle_drill(chat_id):
    today = datetime.utcnow().date()
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT drills, completed_today, last_drill_date FROM users WHERE id = %s", (chat_id,))
                row = cur.fetchone()
                if not row:
                    drills, completed_today, last_drill_date = 0, False, None
                else:
                    drills, completed_today, last_drill_date = row

                # Reset daily counters if new day
                if not last_drill_date or last_drill_date < today:
                    drills = 0
                    completed_today = False
                    cur.execute(
                        "UPDATE users SET drills = 0, completed_today = FALSE, last_drill_date = %s WHERE id = %s",
                        (today, chat_id)
                    )

                if completed_today or drills >= 5:
                    send_message(chat_id, "✅ You've completed today's 5-question drill. Come back tomorrow!")
                    return "Limit reached", 200

                # Pick random question
                question = random.choice(QUESTIONS)

                # Save question in DB
                cur.execute(
                    "UPDATE users SET current_q = %s WHERE id = %s",
                    (json.dumps(question), chat_id)
                )

                options = [{"text": opt, "callback_data": opt} for opt in question["options"]]
                reply_markup = {"inline_keyboard": [options]}
                send_message(chat_id, f"🧩 *Scenario:*\n{question['question']}", reply_markup=reply_markup)
    finally:
        pool.putconn(conn)

    return "Drill sent", 200

def handle_answer(chat_id, answer):
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT current_q, xp, drills, streak, last_drill_date FROM users WHERE id = %s",
                    (chat_id,)
                )
                row = cur.fetchone()
                if not row or not row[0]:
                    send_message(chat_id, "🚫 No active question. Use /drill to start your daily drills.")
                    return "No active question", 200

                current_q_json, xp, drills, streak, last_drill_date = row
                question = json.loads(current_q_json)

                correct_answer = question["answer"]
                feedback = question["feedback"]
                today = datetime.utcnow().date()

                gained_xp = 10 if answer == correct_answer else 0
                new_xp = xp + gained_xp
                new_rank = min(new_xp // 50 + 1, 10)

                if last_drill_date == today - timedelta(days=1):
                    new_streak = streak + 1
                elif last_drill_date == today:
                    new_streak = streak
                else:
                    new_streak = 1

                new_drills = drills + 1
                completed_today = new_drills >= 5

                cur.execute("""
                    UPDATE users SET
                        xp = %s,
                        rank = %s,
                        drills = %s,
                        streak = %s,
                        last_drill_date = %s,
                        completed_today = %s,
                        current_q = NULL
                    WHERE id = %s
                """, (new_xp, new_rank, new_drills, new_streak, today, completed_today, chat_id))

                rank_label = RANK_LABELS.get(new_rank, "🌀 Unknown Rank")
                myth = random.choice(MYTHBUSTERS)
                msg = (
                    f"✅ *Answer:* {correct_answer}\n"
                    f"💬 {feedback}\n\n"
                    f"🎖 XP gained: +{gained_xp}\n"
                    f"🔥 Streak: {new_streak} day(s)\n"
                    f"🏅 Rank: {rank_label}\n\n"
                    f"💡 *Mythbuster:* _{myth}_"
                )
                send_message(chat_id, msg)
    finally:
        pool.putconn(conn)

    return "Answer processed", 200

def handle_profile(chat_id):
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT xp, rank, drills, streak FROM users WHERE id = %s",
                    (chat_id,)
                )
                row = cur.fetchone()
                if not row:
                    send_message(chat_id, "No profile found. Use /start first.")
                    return "No profile", 200

                xp, rank, drills, streak = row
                rank_label = RANK_LABELS.get(rank, "🌀 Unknown Rank")
                progress_blocks = rank if rank <= 10 else 10
                progress_bar = "🟩" * progress_blocks + "⬜" * (10 - progress_blocks)

                msg = (
                    f"🏅 *Your Profile*\n"
                    f"XP: {xp}\n"
                    f"Rank: {rank_label}\n"
                    f"Progress: {progress_bar}\n"
                    f"🔥 Streak: {streak} day(s)\n"
                    f"Drills today: {drills}/5"
                )
                send_message(chat_id, msg)
    finally:
        pool.putconn(conn)

    return "Profile sent", 200

@app.route("/cleanup", methods=["GET"])
def cleanup():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return "Unauthorized", 401

    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET drills = 0, completed_today = FALSE")
    finally:
        pool.putconn(conn)

    return "Daily drills reset for all users", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port)
