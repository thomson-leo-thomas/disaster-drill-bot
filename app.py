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

# Load data
try:
    with open("data.json", encoding="utf-8") as f:
        QUESTIONS = json.load(f)
    with open("mythbusters.json", encoding="utf-8") as f:
        MYTHBUSTERS = json.load(f)
except Exception as e:
    raise RuntimeError(f"Failed to load JSON data: {e}")

# Environment setup
BOT_TOKEN = os.environ["BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_TOKEN = os.environ["ADMIN_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# DB pool
try:
    pool = SimpleConnectionPool(1, 5, dsn=DATABASE_URL, sslmode='require')
except Exception as e:
    raise RuntimeError(f"DB pool error: {e}")

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

# Send message
def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(TELEGRAM_API, json=payload).raise_for_status()
    except Exception as e:
        print(f"Send error: {e}", file=sys.stderr)

# Error wrapper
def safe_route(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            print(f"Error in {f.__name__}: {e}", file=sys.stderr)
            return "Internal error", 500
    return wrapper

@app.route("/", methods=["GET"])
def home():
    return "🔥 Disaster Sensei is live!", 200

@app.route("/", methods=["POST"])
@safe_route
def webhook():
    data = request.get_json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        first_name = data["message"]["chat"].get("first_name")
        text = data["message"].get("text", "").strip()
        init_user(chat_id, first_name)

        if text == "/start":
            send_message(chat_id, f"👋 Welcome, *{first_name or 'Survivor'}*! Ready to sharpen your survival skills?\nType /drill to begin.")
        elif text == "/drill":
            return handle_drill(chat_id)
        elif text == "/profile":
            return handle_profile(chat_id)
        elif text == "/about":
            send_message(chat_id,
                "*🌪️ Disaster Sensei*\n"
                "Your safety sidekick for quick daily disaster drills.\n"
                "Smart, witty, and just might save your life.\n\n"
                "_Disclaimer: This bot provides educational guidance only. Not a substitute for emergency services._"
            )
        elif text == "/help":
            send_message(chat_id, "🆘 /start /drill /profile /about")
        else:
            send_message(chat_id, "❓ Unknown command. Try /help.")
        return "OK", 200

    elif "callback_query" in data:
        chat_id = data["callback_query"]["message"]["chat"]["id"]
        callback_data = data["callback_query"]["data"]
        if callback_data in ["A", "B", "C", "D"]:
            return handle_answer(chat_id, callback_data)
        elif callback_data == "next":
            return handle_drill(chat_id)
        elif callback_data == "view_profile":
            return handle_profile(chat_id)
        else:
            return "Unknown callback", 400
    return "No valid update", 400

# Init user
def init_user(chat_id, first_name=None):
    try: conn = pool.getconn()
    except PoolError: return
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE id = %s", (chat_id,))
            if not cur.fetchone():
                cur.execute("""INSERT INTO users (id, first_name, xp, streak, rank, drills, completed_today, last_drill_date, current_q)
                               VALUES (%s, %s, 0, 0, 1, 0, FALSE, CURRENT_DATE, NULL)""", (chat_id, first_name))
    pool.putconn(conn)

# Send drill
@safe_route
def handle_drill(chat_id):
    today = datetime.utcnow().date()
    conn = pool.getconn()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT drills, completed_today, last_drill_date FROM users WHERE id = %s", (chat_id,))
            drills, completed_today, last_drill_date = cur.fetchone()
            if not last_drill_date or last_drill_date < today:
                drills = 0
                completed_today = False
                cur.execute("UPDATE users SET drills = 0, completed_today = FALSE, last_drill_date = %s WHERE id = %s", (today, chat_id))

            if completed_today or drills >= 5:
                cur.execute("SELECT xp, rank, streak FROM users WHERE id = %s", (chat_id,))
                xp, rank, streak = cur.fetchone()
                xp_to_next = max((rank * 50) - xp, 0)
                tip = random.choice(MYTHBUSTERS)
                send_message(chat_id,
                    f"✅ *Drill Complete!*\n"
                    f"🎖 XP earned today: {drills * 10}\n"
                    f"🔥 Streak: {streak} day(s)\n"
                    f"🏅 Rank: {RANK_LABELS[rank]}\n"
                    f"📈 XP to next rank: {xp_to_next}\n\n"
                    f"💡 *Disaster Decode:* _{tip}_",
                    reply_markup={"inline_keyboard": [[{"text": "👤 View Profile", "callback_data": "view_profile"}]]}
                )
                return "Drill done", 200

            question = random.choice(QUESTIONS)
            cur.execute("UPDATE users SET current_q = %s WHERE id = %s", (json.dumps(question), chat_id))

            options = [{"text": opt, "callback_data": opt} for opt in ["A", "B", "C", "D"]]
            send_message(chat_id,
                f"*Scenario {drills+1}/5:*\n{question['scenario']}",
                reply_markup={"inline_keyboard": [options]}
            )
    pool.putconn(conn)
    return "Drill sent", 200

# Handle answer
@safe_route
def handle_answer(chat_id, answer):
    conn = pool.getconn()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_q, xp, drills, streak, rank, last_drill_date FROM users WHERE id = %s", (chat_id,))
            row = cur.fetchone()
            if not row or not row[0]:
                send_message(chat_id, "🚫 No active question. Use /drill to begin.")
                return "No question", 200

            question = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            xp, drills, streak, rank, last_drill_date = row[1:]
            correct_answer = question["correct"]
            feedback = question["feedback"][answer]
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
                UPDATE users SET xp = %s, rank = %s, drills = %s, streak = %s,
                                completed_today = %s, last_drill_date = %s, current_q = NULL
                WHERE id = %s
            """, (new_xp, new_rank, new_drills, new_streak, completed_today, today, chat_id))

            send_message(chat_id,
                f"{feedback}\n🎖 XP gained: +{gained_xp}",
                reply_markup=None if completed_today else {"inline_keyboard": [[{"text": "➡ Next", "callback_data": "next"}]]}
            )

            if completed_today:
                return handle_drill(chat_id)

    pool.putconn(conn)
    return "Answer handled", 200

# Profile
@safe_route
def handle_profile(chat_id):
    conn = pool.getconn()
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT xp, rank, streak FROM users WHERE id = %s", (chat_id,))
            xp, rank, streak = cur.fetchone()
            progress_bar = "🟩" * rank + "⬜" * (10 - rank)
            send_message(chat_id,
                f"👤 *Your Profile*\n"
                f"XP: {xp}\n"
                f"Rank: {RANK_LABELS[rank]}\n"
                f"🔥 Streak: {streak} day(s)\n"
                f"Progress: {progress_bar}"
            )
    pool.putconn(conn)
    return "Profile sent", 200

# Cleanup
@app.route("/cleanup", methods=["GET"])
@safe_route
def cleanup():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return "Unauthorized", 401

    conn = pool.getconn()
    with conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET drills = 0, completed_today = FALSE")
    pool.putconn(conn)
    return "All drills reset", 200

@app.errorhandler(Exception)
def global_error_handler(e):
    print(f"Global error: {e}", file=sys.stderr)
    return {"error": "Something went wrong."}, 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🧠 Sensei is thinking... Flask is starting on port {port}.")
    app.run(debug=False, host="0.0.0.0", port=port)
