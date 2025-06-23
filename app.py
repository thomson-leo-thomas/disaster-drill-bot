import os
import json
import random
import sys
import functools
from datetime import datetime, timedelta
import requests
from flask import Flask, request
import psycopg2
from psycopg2.pool import SimpleConnectionPool, PoolError

app = Flask(__name__)
print("🧠 Sensei is thinking... Flask is starting.")

# Load questions and mythbusters safely
try:
    with open("data.json", encoding="utf-8") as f:
        QUESTIONS = json.load(f)
except Exception as e:
    raise RuntimeError(f"Failed to load data.json: {e}")

try:
    with open("mythbusters.json", encoding="utf-8") as f:
        MYTHBUSTERS = json.load(f)
except Exception as e:
    raise RuntimeError(f"Failed to load mythbusters.json: {e}")

# Environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")

if not BOT_TOKEN or not DATABASE_URL or not ADMIN_TOKEN:
    raise Exception("Please set BOT_TOKEN, DATABASE_URL and ADMIN_TOKEN environment variables.")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# PostgreSQL connection pool
try:
    pool = SimpleConnectionPool(1, 5, dsn=DATABASE_URL, sslmode='require')
except Exception as e:
    raise RuntimeError(f"Database connection pool failed to initialize: {e}")

# Rank labels
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
        print(f"Error sending message: {e}", file=sys.stderr)

def safe_route(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            print(f"Unhandled error in {f.__name__}: {e}", file=sys.stderr)
            return "Internal error", 500
    return wrapper

@app.route("/", methods=["GET"])
def home():
    return "🚨 Disaster Sensei is running!", 200

@app.route("/", methods=["POST"])
@safe_route
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
            f"👋 Hey there, {first_name or 'Survivor'}! Welcome to the *Disaster Sensei Dojo*.\n\n"
            "Here’s where you sharpen your survival skills with daily drills designed to make you the ultimate responder.\n\n"
            "Ready to train? Type /drill to start your first challenge.\n"
            "Need help? Just type /help.\n\n"
            "Remember: Panic is the enemy. Preparation is your superpower! 💪"
        )
    elif text == "/drill":
        return handle_drill(chat_id)
    elif text == "/profile":
        return handle_profile(chat_id)
    elif text == "/about":
        send_message(chat_id,
            "👨‍🏫 *Disaster Sensei*\n"
            "Created by *Thomson* with ❤️ to help you prepare for life's unexpected moments.\n"
            "This bot trains your instincts through fun daily drills and mythbusters.\n\n"
            "Remember: *Panic is the enemy. Preparation is power.* ⚔️🧠"
        )
    elif text == "/help":
        send_message(chat_id,
            "🆘 *Disaster Sensei Commands*\n\n"
            "/start - Welcome message and quick intro\n"
            "/drill - Jump into your daily survival drills (5 questions max per day)\n"
            "/profile - Check your XP, rank, streak, and progress\n"
            "/about - Learn more about Disaster Sensei\n\n"
            "Train daily, stay sharp, and become the ultimate Disaster Sensei! 🥷"
        )
    else:
        send_message(chat_id,
            "🤔 Hmm, I didn’t get that. Try /help to see what I can do!\n"
            "Let’s keep you ready and sharp! 💪"
        )

    return "OK", 200

def init_user(chat_id, first_name=None):
    try:
        conn = pool.getconn()
    except PoolError:
        print("Connection pool exhausted", file=sys.stderr)
        return

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

@safe_route
def handle_drill(chat_id):
    today = datetime.utcnow().date()
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT drills, completed_today, last_drill_date FROM users WHERE id = %s", (chat_id,))
                row = cur.fetchone()
                drills, completed_today, last_drill_date = row if row else (0, False, None)

                if not last_drill_date or last_drill_date < today:
                    drills = 0
                    completed_today = False
                    cur.execute(
                        "UPDATE users SET drills = 0, completed_today = FALSE, last_drill_date = %s WHERE id = %s",
                        (today, chat_id)
                    )

                if completed_today or drills >= 5:
                    send_message(chat_id, "🎉 Woohoo! You've smashed today's 5 drills. Rest up and come back tomorrow for more Disaster Sensei training!")
                    return "Limit reached", 200

                question_num = drills + 1
                question = random.choice(QUESTIONS)
                cur.execute("UPDATE users SET current_q = %s WHERE id = %s", (json.dumps(question), chat_id))

                options_text = (
                    f"A) {question['A']}\n"
                    f"B) {question['B']}\n"
                    f"C) {question['C']}\n"
                    f"D) {question['D']}"
                )

                message_text = (
                    f"🧩 *Scenario {question_num} of 5:*\n{question['scenario']}\n\n"
                    f"{options_text}\n\n_Select your answer by tapping A, B, C, or D below._"
                )

                inline_keyboard = [[
                    {"text": "A", "callback_data": "A"},
                    {"text": "B", "callback_data": "B"},
                    {"text": "C", "callback_data": "C"},
                    {"text": "D", "callback_data": "D"},
                ]]

                send_message(chat_id, message_text, reply_markup={"inline_keyboard": inline_keyboard})

    finally:
        pool.putconn(conn)

    return "Drill sent", 200

@safe_route
def handle_answer(chat_id, answer):
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_q, xp, drills, streak, last_drill_date FROM users WHERE id = %s", (chat_id,))
                row = cur.fetchone()
                if not row or not row[0]:
                    send_message(chat_id, "🚫 No active question. Use /drill to start your daily drills.")
                    return "No active question", 200

                current_q_json, xp, drills, streak, last_drill_date = row
                question = json.loads(current_q_json)

                correct_answer = question["correct"]
                feedback = question["feedback"].get(answer, "🤔 Interesting choice...")

                today = datetime.utcnow().date()

                gained_xp = 10 if answer == correct_answer else 0
                new_xp = xp + gained_xp
                new_rank = min(new_xp // 50 + 1, 10)

                # Update streak logic
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

                rank_label = RANK_LABELS.get(new_rank, "🌀 Disaster Sensei")
                myth = random.choice(MYTHBUSTERS)

                correctness = "🎉 Correct! You're a true Sensei! 🥷" if answer == correct_answer else "❌ Oops! That's not quite right."

                msg = (
                    f"{correctness}\n\n"
                    f"💬 {feedback}\n\n"
                    f"🎖 XP gained: +{gained_xp}\n"
                    f"🔥 Streak: {new_streak} day(s)\n"
                    f"🏅 Rank: {rank_label}\n\n"
                    f"💡 *Mythbuster:* _{myth}_\n\n"
                    "Type /drill to continue training or /profile to see your stats."
                )
                send_message(chat_id, msg)
    finally:
        pool.putconn(conn)

    return "Answer processed", 200

@safe_route
def handle_profile(chat_id):
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT xp, rank, drills, streak FROM users WHERE id = %s", (chat_id,))
                row = cur.fetchone()
                if not row:
                    send_message(chat_id, "⚠️ No profile found. Type /start to join the Disaster Sensei Dojo!")
                    return "No profile", 200

                xp, rank, drills, streak = row
                rank_label = RANK_LABELS.get(rank, "🌀 Disaster Sensei")
                progress_bar = "🟩" * min(rank, 10) + "⬜" * (10 - min(rank, 10))

                msg = (
                    f"🏅 *Your Disaster Sensei Profile*\n\n"
                    f"💥 XP: {xp}\n"
                    f"🎖 Rank: {rank_label}\n"
                    f"📊 Progress: {progress_bar}\n"
                    f"🔥 Current Streak: {streak} day(s) of daily drills\n"
                    f"🛡️ Drills completed today: {drills}/5\n\n"
                    "Keep training to level up and unlock new ranks! 🚀"
                )
                send_message(chat_id, msg)
    finally:
        pool.putconn(conn)

    return "Profile sent", 200

@app.route("/cleanup", methods=["GET"])
@safe_route
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

@app.errorhandler(Exception)
def global_error_handler(e):
    print(f"Global error: {e}", file=sys.stderr)
    return {"error": "Something went wrong."}, 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🧠 Sensei is thinking... Flask is starting on port {port}.")
    app.run(debug=False, host="0.0.0.0", port=port)

