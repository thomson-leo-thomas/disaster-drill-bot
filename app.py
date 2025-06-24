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
            "Interactive bot teaching disaster preparedness with cool tips and drills.\n"
            "🛡️ Stay safe, stay sharp!\n\n"
            "_Disclaimer:_ This bot provides educational safety guidance and is not a substitute for professional emergency services."
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
                        (id, first_name, xp, streak, rank, drills, completed_today, last_drill_date, current_q, daily_xp)
                        VALUES (%s, %s, 0, 0, 1, 0, FALSE, CURRENT_DATE, NULL, 0)
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
                        "UPDATE users SET drills = 0, completed_today = FALSE, last_drill_date = %s, daily_xp = 0 WHERE id = %s",
                        (today, chat_id)
                    )

                if completed_today or drills >= 5:
                    send_message(chat_id, "✅ You've completed today's 5-question drill. Come back tomorrow!")
                    return "Limit reached", 200

                question = random.choice(QUESTIONS)

                cur.execute("UPDATE users SET current_q = %s WHERE id = %s", (json.dumps(question), chat_id))

                # Compose message with scenario + options fully visible
                options_text = (
                    f"A. {question['A']}\n"
                    f"B. {question['B']}\n"
                    f"C. {question['C']}\n"
                    f"D. {question['D']}"
                )
                message_text = f"{question['scenario']}\n\n{options_text}"

                # Inline buttons just letters A, B, C, D
                buttons = [
                    [
                        {"text": "A", "callback_data": "A"},
                        {"text": "B", "callback_data": "B"},
                        {"text": "C", "callback_data": "C"},
                        {"text": "D", "callback_data": "D"},
                    ]
                ]

                send_message(chat_id, message_text, reply_markup={"inline_keyboard": buttons})
    finally:
        pool.putconn(conn)

    return "Drill sent", 200

@safe_route
def handle_answer(chat_id, answer):
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_q, xp, drills, streak, last_drill_date, daily_xp FROM users WHERE id = %s", (chat_id,))
                row = cur.fetchone()
                if not row or not row[0]:
                    send_message(chat_id, "🚫 No active question. Use /drill to start your daily drills.")
                    return "No active question", 200

                current_q_json, xp, drills, streak, last_drill_date, daily_xp = row
                question = json.loads(current_q_json)

                correct_answer = question["correct"]
                feedback = question["feedback"]
                today = datetime.utcnow().date()

                # XP logic: 10 XP per correct answer, plus 5 XP bonus for streak maintenance
                gained_xp = 10 if answer == correct_answer else 0
                new_xp = xp + gained_xp
                new_daily_xp = daily_xp + gained_xp

                new_rank = min(new_xp // 50 + 1, 10)

                # Streak logic: increment streak if last drill was yesterday
                if last_drill_date == today - timedelta(days=1):
                    new_streak = streak + 1
                elif last_drill_date == today:
                    new_streak = streak
                else:
                    new_streak = 1

                new_drills = drills + 1
                completed_today = new_drills >= 5

                # Update DB: reset current_q, update xp, streak, drills, daily_xp etc.
                cur.execute("""
                    UPDATE users SET
                        xp = %s,
                        rank = %s,
                        drills = %s,
                        streak = %s,
                        last_drill_date = %s,
                        completed_today = %s,
                        current_q = NULL,
                        daily_xp = %s
                    WHERE id = %s
                """, (new_xp, new_rank, new_drills, new_streak, today, completed_today, new_daily_xp, chat_id))

                if not completed_today:
                    # Show only feedback and gained XP after each answer with a Next button
                    msg = (
                        f"✅ *Answer:* {answer}\n"
                        f"{feedback[answer]}\n\n"
                        f"🎖 XP gained: +{gained_xp}"
                    )
                    # Next button to fetch next question
                    next_button = {"inline_keyboard": [[{"text": "Next", "callback_data": "next"}]]}
                    send_message(chat_id, msg, reply_markup=next_button)
                else:
                    # Completed 5 questions — show summary
                    xp_to_next_rank = (new_rank * 50) - new_xp if new_rank < 10 else 0
                    rank_label = RANK_LABELS.get(new_rank, "🌀 Unknown Rank")
                    myth_name = "Disaster Decode"  # renamed mythbusters section

                    msg = (
                        f"✅ *Daily Drill Complete!*\n\n"
                        f"🎯 Total XP earned today: {new_daily_xp}\n"
                        f"🔥 Streak: {new_streak} day(s)\n"
                        f"🏅 Current Rank: {rank_label}\n"
                        f"📈 XP to next rank: {xp_to_next_rank}\n\n"
                        f"💡 *{myth_name}* - Stay safe, stay smart!"
                    )
                    # Button to view profile
                    profile_button = {"inline_keyboard": [[{"text": "View Profile", "callback_data": "profile"}]]}
                    send_message(chat_id, msg, reply_markup=profile_button)

    finally:
        pool.putconn(conn)

    return "Answer processed", 200

@safe_route
def handle_profile(chat_id):
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT xp, rank, streak FROM users WHERE id = %s", (chat_id,))
                row = cur.fetchone()
                if not row:
                    send_message(chat_id, "No profile found. Use /start first.")
                    return "No profile", 200

                xp, rank, streak = row
                rank_label = RANK_LABELS.get(rank, "🌀 Unknown Rank")
                progress_bar = "🟩" * min(rank, 10) + "⬜" * (10 - min(rank, 10))

                msg = (
                    f"🏅 *Your Profile*\n"
                    f"XP: {xp}\n"
                    f"Rank: {rank_label}\n"
                    f"Progress: {progress_bar}\n"
                    f"🔥 Streak: {streak} day(s)"
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
                cur.execute("UPDATE users SET drills = 0, completed_today = FALSE, daily_xp = 0")
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
