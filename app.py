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
with open("data.json", encoding="utf-8") as f:
    QUESTIONS = json.load(f)

with open("mythbusters.json", encoding="utf-8") as f:
    MYTHBUSTERS = json.load(f)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")

if not BOT_TOKEN or not DATABASE_URL or not ADMIN_TOKEN:
    raise Exception("Missing BOT_TOKEN, DATABASE_URL or ADMIN_TOKEN.")

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

try:
    pool = SimpleConnectionPool(1, 5, dsn=DATABASE_URL, sslmode='require')
except Exception as e:
    raise RuntimeError(f"Failed to initialize DB pool: {e}")

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
        requests.post(TELEGRAM_API, json=payload).raise_for_status()
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
            "An interactive survival bot for training your instincts in daily disaster drills.\n"
            "Sharpen your mind, not just your pencils. 🧠\n\n"
            "⚠️ *Disclaimer:* This bot provides educational safety guidance. It is not a substitute for professional emergency services."
        )
    elif text == "/help":
        send_message(chat_id,
            "🆘 *Commands:*\n"
            "/start - Welcome intro\n"
            "/drill - Begin today's 5-question drill\n"
            "/profile - View your stats\n"
            "/about - Info & disclaimer"
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
                drills, completed_today, last_drill_date = cur.fetchone()

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
                    xp_to_next = (rank * 50) - xp if rank < 10 else 0
                    myth = random.choice(MYTHBUSTERS)

                    send_message(chat_id,
                        f"🎉 *Daily Drill Completed!*\n\n"
                        f"🎖 XP earned today: {drills * 10}\n"
                        f"🔥 Streak: {streak} day(s)\n"
                        f"🏅 Rank: {rank_label}\n"
                        f"📈 XP to next rank: {xp_to_next}\n\n"
                        f"🧠 *Disaster Decode:*\n_{myth}_",
                        reply_markup={
                            "inline_keyboard": [[
                                {"text": "View Profile", "callback_data": "profile"}
                            ]]
                        }
                    )
                    return "Done", 200

                question = random.choice(QUESTIONS)
                cur.execute("UPDATE users SET current_q = %s WHERE id = %s", (json.dumps(question), chat_id))

                q_text = f"🧩 *Q{drills+1}/5:*\n{question['scenario']}"
                options = [
                    [{"text": f"A", "callback_data": "A"}],
                    [{"text": f"B", "callback_data": "B"}],
                    [{"text": f"C", "callback_data": "C"}],
                    [{"text": f"D", "callback_data": "D"}],
                ]
                send_message(chat_id, q_text, reply_markup={"inline_keyboard": options})
    finally:
        pool.putconn(conn)

    return "Drill sent", 200

@safe_route
def handle_answer(chat_id, answer):
    if answer == "profile":
        return handle_profile(chat_id)

    conn = pool.getconn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_q, xp, drills, streak, rank, last_drill_date FROM users WHERE id = %s", (chat_id,))
                row = cur.fetchone()
                if not row or not row[0]:
                    send_message(chat_id, "🚫 No active question. Use /drill to begin.")
                    return "No active question", 200

                current_q, xp, drills, streak, rank, last_drill_date = row
                q = json.loads(current_q)

                correct = q["correct"]
                gained = 10 if answer == correct else 0
                new_xp = xp + gained
                new_rank = min(new_xp // 50 + 1, 10)

                if last_drill_date == datetime.utcnow().date() - timedelta(days=1):
                    streak += 1
                elif last_drill_date < datetime.utcnow().date():
                    streak = 1

                drills += 1
                completed_today = drills >= 5

                cur.execute("""
                    UPDATE users SET xp = %s, rank = %s, streak = %s, drills = %s, completed_today = %s, current_q = NULL, last_drill_date = %s
                    WHERE id = %s
                """, (new_xp, new_rank, streak, drills, completed_today, datetime.utcnow().date(), chat_id))

                reply = (
                    f"{q['feedback'][answer]}\n\n"
                    f"🎖 *XP gained:* +{gained}"
                )
                if drills < 5:
                    send_message(chat_id, reply, reply_markup={
                        "inline_keyboard": [[{"text": "Next ➡️", "callback_data": "next"}]]
                    })
                else:
                    send_message(chat_id, reply)
                    return handle_drill(chat_id)
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
                xp, rank, streak = cur.fetchone()
                label = RANK_LABELS.get(rank, "Unknown Rank")
                progress = "🟩" * min(rank, 10) + "⬜" * (10 - min(rank, 10))

                send_message(chat_id,
                    f"📊 *Your Profile*\n\n"
                    f"XP: {xp}\n"
                    f"Rank: {label}\n"
                    f"🔥 Streak: {streak} day(s)\n"
                    f"Progress: {progress}"
                )
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

    return "Drills reset", 200

@app.errorhandler(Exception)
def global_error_handler(e):
    print(f"Global error: {e}", file=sys.stderr)
    return {"error": "Something went wrong."}, 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=False, host="0.0.0.0", port=port)

