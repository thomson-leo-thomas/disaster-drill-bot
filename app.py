import os
import json
import random
import psycopg2
from flask import Flask, request
import requests
from functools import wraps

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# Load scenarios from data.json
with open("data.json", "r", encoding="utf-8") as f:
    SCENARIOS = json.load(f)

# Load mythbusters from mythbusters.json
with open("mythbusters.json", "r", encoding="utf-8") as f:
    MYTHS = json.load(f)

# Connect to Postgres
conn = psycopg2.connect(os.environ.get("DATABASE_URL"), sslmode='require')
conn.autocommit = True

def safe_route(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            print(f"Error: {e}")
            return "Internal Error", 500
    return decorated

def send_message(chat_id, text, reply_markup=None, parse_mode="Markdown"):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(TELEGRAM_API + "sendMessage", data=payload)

def get_user(chat_id):
    with conn.cursor() as cur:
        cur.execute("SELECT first_name, xp, streak, rank, drills, completed_today, last_drill_date, current_q FROM users WHERE id=%s", (chat_id,))
        return cur.fetchone()

def create_user(chat_id, first_name):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO users (id, first_name, xp, streak, rank, drills, completed_today, last_drill_date, current_q)
            VALUES (%s, %s, 0, 0, 1, 0, 0, NULL, 0)
            ON CONFLICT (id) DO NOTHING
        """, (chat_id, first_name))

def update_user_progress(chat_id, **kwargs):
    keys = ", ".join(f"{k} = %s" for k in kwargs.keys())
    vals = list(kwargs.values())
    vals.append(chat_id)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE users SET {keys} WHERE id = %s", vals)

def rank_name(rank):
    ranks = {
        1: "Novice",
        2: "Apprentice",
        3: "Adept",
        4: "Expert",
        5: "Sensei"
    }
    return ranks.get(rank, "Legend")

def xp_to_next_rank(rank):
    thresholds = {1: 100, 2: 300, 3: 600, 4: 1000, 5: 2000}
    return thresholds.get(rank, 9999)

def init_user(chat_id, first_name):
    user = get_user(chat_id)
    if not user:
        create_user(chat_id, first_name)

def build_options_keyboard():
    return {
        "inline_keyboard": [
            [
                {"text": "A", "callback_data": "A"},
                {"text": "B", "callback_data": "B"},
                {"text": "C", "callback_data": "C"},
                {"text": "D", "callback_data": "D"}
            ]
        ]
    }

def build_next_button():
    return {
        "inline_keyboard": [
            [{"text": "Next ▶️", "callback_data": "NEXT_QUESTION"}]
        ]
    }

def build_profile_button():
    return {
        "inline_keyboard": [
            [{"text": "View Profile 📊", "callback_data": "VIEW_PROFILE"}]
        ]
    }

def get_disaster_decode_tip():
    # Pick a random myth from mythbusters.json
    myth = random.choice(MYTHS)
    return f"💡 *Disaster Decode:* {myth}"

def handle_drill(chat_id):
    user = get_user(chat_id)
    if not user:
        send_message(chat_id, "Please /start first.")
        return "OK", 200

    first_name, xp, streak, rank, drills, completed_today, last_drill_date, current_q = user

    from datetime import date
    today = date.today()
    if last_drill_date != today:
        completed_today = 0
        drills = 0
        update_user_progress(chat_id, completed_today=0, drills=0, last_drill_date=today)

    if completed_today >= 5:
        send_message(chat_id, "🎉 You've completed your 5 daily drills! Come back tomorrow for more wisdom.")
        return "OK", 200

    question_index = completed_today
    scenario = SCENARIOS[question_index]

    update_user_progress(chat_id, current_q=question_index)

    # No puzzle emoji in scenario, just text
    text = f"{scenario['scenario']} (Question {question_index+1} of 5)\n\nSelect your answer:"

    keyboard = build_options_keyboard()
    send_message(chat_id, text, reply_markup=keyboard)

    return "OK", 200

def handle_answer(chat_id, answer):
    user = get_user(chat_id)
    if not user:
        send_message(chat_id, "Please /start first.")
        return "OK", 200

    first_name, xp, streak, rank, drills, completed_today, last_drill_date, current_q = user

    if current_q is None or current_q >= len(SCENARIOS):
        send_message(chat_id, "No active drill. Use /drill to start.")
        return "OK", 200

    scenario = SCENARIOS[current_q]

    correct_answer = scenario["correct"]
    feedback = scenario["feedback"]

    earned_xp = 10 if answer == correct_answer else 0

    new_xp = xp + earned_xp
    new_streak = streak + 1 if earned_xp == 10 else 0
    new_completed_today = completed_today + 1

    needed_for_next = xp_to_next_rank(rank)
    new_rank = rank
    if new_xp >= needed_for_next:
        new_rank = rank + 1

    update_user_progress(
        chat_id,
        xp=new_xp,
        streak=new_streak,
        rank=new_rank,
        completed_today=new_completed_today,
        drills=drills + 1,
        current_q=None
    )

    feedback_text = feedback.get(answer, "Invalid answer option.")
    msg = f"{feedback_text}\n\nXP Earned: {earned_xp} ⚡"

    if new_completed_today < 5:
        keyboard = build_next_button()
    else:
        needed_for_next = xp_to_next_rank(new_rank) - new_xp
        summary = (
            f"🏁 *Drill Complete!*\n\n"
            f"✅ Total XP earned today: {new_xp - xp} ⚡\n"
            f"🔥 Streak: {new_streak}\n"
            f"🏅 Rank: {rank_name(new_rank)}\n"
            f"📈 XP to next rank: {needed_for_next}\n\n"
            f"{get_disaster_decode_tip()}"
        )
        keyboard = build_profile_button()
        msg = summary

    send_message(chat_id, msg, reply_markup=keyboard)
    return "OK", 200

def handle_profile(chat_id):
    user = get_user(chat_id)
    if not user:
        send_message(chat_id, "Please /start first.")
        return "OK", 200

    first_name, xp, streak, rank, drills, completed_today, last_drill_date, current_q = user

    needed_xp = xp_to_next_rank(rank)
    progress = int((xp / needed_xp) * 20)
    progress_bar = "█" * progress + "░" * (20 - progress)

    msg = (
        f"📊 *Your Profile*\n\n"
        f"XP: {xp} ⚡\n"
        f"Rank: {rank_name(rank)} 🏅\n"
        f"Streak: {streak} 🔥\n"
        f"Progress to next rank:\n`{progress_bar}`\n"
    )
    send_message(chat_id, msg)
    return "OK", 200

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
                f"👋 Welcome, {first_name or 'Survivor'}!\n"
                "Train your instincts in Disaster Sensei Dojo.\n\n"
                "Type /drill to begin your daily survival drill.\n"
                "Use /help for commands."
            )
        elif text == "/drill":
            return handle_drill(chat_id)
        elif text == "/profile":
            return handle_profile(chat_id)
        elif text == "/about":
            send_message(chat_id,
                "🧠 *Disaster Sensei*\n"
                "Your personal guide to mastering disaster preparedness with fun, smarts, and quick wit! 🚀\n\n"
                "⚠️ *Disclaimer:* This bot offers educational safety guidance and is NOT a substitute for professional emergency services. Stay safe and always call emergency responders when needed!"
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

    elif "callback_query" in data:
        chat_id = data["callback_query"]["message"]["chat"]["id"]
        callback_data = data["callback_query"]["data"]

        if callback_data == "VIEW_PROFILE":
            return handle_profile(chat_id)
        elif callback_data == "NEXT_QUESTION":
            return handle_drill(chat_id)
        elif callback_data in ["A", "B", "C", "D"]:
            return handle_answer(chat_id, callback_data)
        else:
            send_message(chat_id, "❓ Unknown action.")
            return "OK", 200

    else:
        return "Unsupported update", 400

if __name__ == "__main__":
    app.run(debug=True)
