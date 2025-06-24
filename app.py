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

# === Load Questions & Disaster Decodes ===
try:
    with open("data.json", encoding="utf-8") as f:
        QUESTIONS = json.load(f)
except Exception as e:
    raise RuntimeError(f"Failed to load data.json: {e}")

try:
    with open("mythbusters.json", encoding="utf-8") as f:
        DISASTER_DECODE = json.load(f)
except Exception as e:
    raise RuntimeError(f"Failed to load mythbusters.json: {e}")

# === Environment Variables ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")

if not BOT_TOKEN or not DATABASE_URL or not ADMIN_TOKEN:
    raise Exception("Please set BOT_TOKEN, DATABASE_URL and ADMIN_TOKEN environment variables.")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# === PostgreSQL Connection Pool ===
try:
    pool = SimpleConnectionPool(1, 5, dsn=DATABASE_URL, sslmode='require')
except Exception as e:
    raise RuntimeError(f"Database connection pool failed: {e}")

# === Rank Labels ===
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
    return "🚨 Disaster Sensei is live!", 200

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
            send_message(chat_id,
                f"🧠 *Welcome, {first_name or 'Survivor'}!*\n"
                "Train your instincts in the Disaster Sensei Dojo.\n\n"
                "Type /drill to begin your daily survival challenge.\n"
                "Use /help to explore commands."
            )
        elif text == "/drill":
            return handle_drill(chat_id)
        elif text == "/profile":
            return handle_profile(chat_id)
        elif text == "/about":
            send_message(chat_id,
                "*👨‍🏫 Disaster Sensei*\n"
                "Master disaster drills one question at a time.\n"
                "Built by *Thomson*.\n\n"
                "📘 *Disclaimer:*\n"
                "This bot is for educational purposes only and is *not* a replacement for professional emergency services."
            )
        elif text == "/help":
            send_message(chat_id,
                "🆘 *Commands:*\n"
                "/start - Welcome message\n"
                "/drill - Daily 5-question drill\n"
                "/profile - Your stats\n"
                "/about - About the bot"
            )
        else:
            send_message(chat_id, "❓ Unknown command. Try /help.")
    elif "callback_query" in data:
        chat_id = data["callback_query"]["message"]["chat"]["id"]
        answer = data["callback_query"]["data"]
        return handle_answer(chat_id, answer)
    else:
        return "Unsupported update", 400

    return "OK", 200

def init_user(chat_id, first_name=None):
    try:
        conn = pool.getconn()
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
                    cur.execute("SELECT xp, rank, streak FROM users WHERE id = %s", (chat_id,))
                    xp, rank, streak = cur.fetchone()
                    rank_label = RANK_LABELS.get(rank, "Unknown Rank")
                    xp_to_next = ((rank + 1) * 50) - xp

                    decode = random.choice(DISASTER_DECODE)
                    msg = (
                        f"🏁 *Drill Complete!*\n\n"
                        f"🎖 Total XP today: {drills * 10}\n"
                        f"🔥 Streak: {streak} day(s)\n"
                        f"🏅 Rank: {rank_label}\n"
                        f"📈 XP to next rank: {xp_to_next}\n\n"
                        f"💡 *Disaster Decode:*\n_{decode}_"
                    )
                    send_message(chat_id, msg, reply_markup={
                        "inline_keyboard": [[{"text": "View Profile", "callback_data": "view_profile"}]]
                    })
                    return "Drill complete", 200

                question = random.choice(QUESTIONS)
                cur.execute("UPDATE users SET current_q = %s WHERE id = %s", (json.dumps(question), chat_id))

                options = ["A", "B", "C", "D"]
                option_buttons = [{"text": f"{opt}) {question[opt]}", "callback_data": opt} for opt in options]
                send_message(chat_id, f"*🧩 Scenario {drills + 1}/5:*\n{question['scenario']}", reply_markup={
                    "inline_keyboard": [[btn] for btn in option_buttons]
                })
    finally:
        pool.putconn(conn)
    return "Drill question sent", 200

@safe_route
def handle_answer(chat_id, answer):
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_q, xp, drills, streak, rank, last_drill_date FROM users WHERE id = %s", (chat_id,))
                row = cur.fetchone()
                if not row or not row[0]:
                    send_message(chat_id, "🚫 No active question. Type /drill to begin.")
                    return "No active question", 200

                current_q_json, xp, drills, streak, rank, last_drill_date = row
                question = current_q_json if isinstance(current_q_json, dict) else json.loads(current_q_json)

                correct = question["correct"]
                feedback = question["feedback"][answer]
                xp_gain = 10 if answer == correct else 0
                new_xp = xp + xp_gain
                new_rank = min(new_xp // 50 + 1, 10)
                new_drills = drills + 1
                completed_today = new_drills >= 5

                if last_drill_date == datetime.utcnow().date() - timedelta(days=1):
                    streak += 1
                elif last_drill_date < datetime.utcnow().date():
                    streak = 1

                cur.execute("""
                    UPDATE users SET xp=%s, rank=%s, drills=%s, streak=%s,
                    completed_today=%s, last_drill_date=%s, current_q=NULL
                    WHERE id=%s
                """, (new_xp, new_rank, new_drills, streak, completed_today, datetime.utcnow().date(), chat_id))

                msg = (
                    f"✅ *Answer:* {correct}\n"
                    f"{feedback}\n"
                    f"🎖 XP gained: +{xp_gain}"
                )
                if not completed_today:
                    send_message(chat_id, msg, reply_markup={
                        "inline_keyboard": [[{"text": "Next ▶️", "callback_data": "next_question"}]]
                    })
                else:
                    handle_drill(chat_id)
    finally:
        pool.putconn(conn)
    return "Answer handled", 200

@safe_route
def handle_profile(chat_id):
    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT xp, rank, streak FROM users WHERE id = %s", (chat_id,))
                row = cur.fetchone()
                if not row:
                    send_message(chat_id, "No profile found. Start with /drill.")
                    return "No profile", 200

                xp, rank, streak = row
                bar = "🟩" * rank + "⬜" * (10 - rank)
                send_message(chat_id,
                    f"📊 *Your Profile*\n"
                    f"XP: {xp}\n"
                    f"Rank: {RANK_LABELS.get(rank)}\n"
                    f"🔥 Streak: {streak} days\n"
                    f"Progress: {bar}"
                )
    finally:
        pool.putconn(conn)
    return "Profile sent", 200

@app.route("/cleanup", methods=["GET"])
@safe_route
def cleanup():
    if request.args.get("token") != ADMIN_TOKEN:
        return "Unauthorized", 401

    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET drills = 0, completed_today = FALSE")
    finally:
        pool.putconn(conn)
    return "Reset complete", 200

@app.errorhandler(Exception)
def global_error_handler(e):
    print(f"Global error: {e}", file=sys.stderr)
    return {"error": "Something went wrong."}, 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🚨 Flask server running on port {port}")
    app.run(debug=False, host="0.0.0.0", port=port)

