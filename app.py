import os
import json
import random
import psycopg2
from flask import Flask, request
import requests

app = Flask(__name__)

BOT_TOKEN = os.environ['BOT_TOKEN']
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/"

DATABASE_URL = os.environ['DATABASE_URL']

# Connect to PostgreSQL database
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cursor = conn.cursor()

# Load scenarios from file
with open("data.json", "r", encoding="utf-8") as f:
    scenarios = json.load(f)

# Load mythbusters from file
with open("mythbusters.json", "r", encoding="utf-8") as f:
    mythbusters = json.load(f)

def get_user(chat_id):
    cursor.execute("SELECT id, first_name, xp, streak, rank, drills, completed_today, last_drill_date, current_q FROM users WHERE id=%s", (chat_id,))
    return cursor.fetchone()

def create_user(chat_id, first_name):
    cursor.execute(
        "INSERT INTO users (id, first_name, xp, streak, rank, drills, completed_today, last_drill_date, current_q) VALUES (%s, %s, 0, 0, 'Novice', 0, 0, NULL, NULL)",
        (chat_id, first_name)
    )

def update_user_progress(chat_id, xp=None, streak=None, rank=None, drills=None, completed_today=None, last_drill_date=None, current_q=None):
    # Build dynamic update query parts
    updates = []
    params = []
    if xp is not None:
        updates.append("xp = %s")
        params.append(xp)
    if streak is not None:
        updates.append("streak = %s")
        params.append(streak)
    if rank is not None:
        updates.append("rank = %s")
        params.append(rank)
    if drills is not None:
        updates.append("drills = %s")
        params.append(drills)
    if completed_today is not None:
        updates.append("completed_today = %s")
        params.append(completed_today)
    if last_drill_date is not None:
        updates.append("last_drill_date = %s")
        params.append(last_drill_date)
    if current_q is not None:
        updates.append("current_q = %s")
        params.append(json.dumps(current_q) if isinstance(current_q, dict) else current_q)
    else:
        # If current_q explicitly passed as None, set to NULL in DB
        updates.append("current_q = NULL")

    params.append(chat_id)
    query = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"
    cursor.execute(query, tuple(params))

def get_rank(xp):
    if xp >= 500:
        return "Master"
    elif xp >= 250:
        return "Advanced"
    elif xp >= 100:
        return "Intermediate"
    else:
        return "Novice"

def get_next_rank_xp(xp):
    if xp < 100:
        return 100 - xp
    elif xp < 250:
        return 250 - xp
    elif xp < 500:
        return 500 - xp
    else:
        return 0

def send_message(chat_id, text, reply_markup=None):
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    requests.post(f"{TELEGRAM_API}sendMessage", data=data)

def send_profile(chat_id, user):
    xp = user[2]
    streak = user[3]
    rank = user[4]
    progress = xp / 500  # progress towards max rank, max 500 xp

    progress_bar_length = 20
    filled_length = int(progress_bar_length * min(progress, 1))
    bar = "🟩" * filled_length + "⬜" * (progress_bar_length - filled_length)

    profile_text = (
        f"🏆 *Your Profile*\n"
        f"XP: *{xp}*\n"
        f"Rank: *{rank}*\n"
        f"Streak: *{streak}*\n"
        f"Progress to next rank:\n{bar}"
    )
    send_message(chat_id, profile_text)

def send_about(chat_id):
    about_text = (
        "🧠 *Disaster Sensei* — Your daily disaster safety drill bot!\n\n"
        "Sharpen your skills with quick, fun, and challenging emergency scenarios.\n"
        "Learn smart safety moves with humor and bite-sized lessons.\n\n"
        "_Disclaimer:_ This bot provides educational guidance only. "
        "In real emergencies, always follow professional advice and local authorities."
    )
    send_message(chat_id, about_text)

def get_question_inline_keyboard(scenario):
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "A", "callback_data": "answer_A"},
                {"text": "B", "callback_data": "answer_B"},
                {"text": "C", "callback_data": "answer_C"},
                {"text": "D", "callback_data": "answer_D"},
            ]
        ]
    }
    return keyboard

def send_question(chat_id, question_index):
    scenario = scenarios[question_index]
    text = f"{scenario['scenario']}\n\n" \
           f"A. {scenario['A']}\n" \
           f"B. {scenario['B']}\n" \
           f"C. {scenario['C']}\n" \
           f"D. {scenario['D']}"
    keyboard = get_question_inline_keyboard(scenario)
    send_message(chat_id, text, reply_markup=keyboard)

def send_end_of_drill_summary(chat_id, total_xp, streak, rank, xp_to_next_rank):
    myth_name = "Disaster Decode"
    text = (
        f"🎉 *Drill Complete!*\n\n"
        f"✅ Total XP earned today: *{total_xp}*\n"
        f"🔥 Current streak: *{streak}*\n"
        f"🏅 Rank: *{rank}*\n"
        f"📈 XP to next rank: *{xp_to_next_rank}*\n\n"
        f"💡 *{myth_name}* keeps you sharp every day!"
    )
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "View Profile", "callback_data": "view_profile"},
                {"text": "Start New Drill", "callback_data": "start_drill"}
            ]
        ]
    }
    send_message(chat_id, text, reply_markup=keyboard)

@app.route("/start", methods=["POST"])
def start():
    data = request.get_json()
    chat_id = data['message']['chat']['id']
    first_name = data['message']['chat'].get('first_name', 'Sensei')

    user = get_user(chat_id)
    if not user:
        create_user(chat_id, first_name)
        user = get_user(chat_id)

    welcome_text = f"👋 Hello, {first_name}! Ready to start your disaster drill? Use /drill to begin."
    send_message(chat_id, welcome_text)
    return {"ok": True}

@app.route("/about", methods=["POST"])
def about():
    data = request.get_json()
    chat_id = data['message']['chat']['id']
    send_about(chat_id)
    return {"ok": True}

@app.route("/profile", methods=["POST"])
def profile():
    data = request.get_json()
    chat_id = data['message']['chat']['id']

    user = get_user(chat_id)
    if not user:
        send_message(chat_id, "User not found. Use /start to register.")
        return {"ok": True}

    send_profile(chat_id, user)
    return {"ok": True}

@app.route("/drill", methods=["POST"])
def drill():
    data = request.get_json()
    chat_id = data['message']['chat']['id']
    user = get_user(chat_id)

    if not user:
        send_message(chat_id, "Please start first using /start.")
        return {"ok": True}

    # Start the drill from question 0
    update_user_progress(chat_id, current_q={"index": 0, "xp_gained": 0, "total_xp": 0, "answers": []})
    send_question(chat_id, 0)
    return {"ok": True}

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    if "callback_query" in data:
        callback_query = data["callback_query"]
        chat_id = callback_query["message"]["chat"]["id"]
        message_id = callback_query["message"]["message_id"]
        data_callback = callback_query["data"]

        user = get_user(chat_id)
        if not user:
            send_message(chat_id, "Please start using /start first.")
            return {"ok": True}

        current_q = user[8]  # current_q JSON from DB

        # If current_q is None, ask user to start drill
        if not current_q:
            send_message(chat_id, "Please start a drill first with /drill.")
            return {"ok": True}

        if data_callback.startswith("answer_"):
            selected_option = data_callback[-1]  # 'A', 'B', 'C', or 'D'
            question_index = current_q["index"]
            scenario = scenarios[question_index]

            # Prevent double answering by checking if this question already answered
            if question_index < len(current_q["answers"]):
                # Already answered this question
                send_message(chat_id, "You already answered this question. Click Next to continue.")
                return {"ok": True}

            correct_option = scenario["correct"]
            is_correct = selected_option == correct_option

            gained_xp = 10 if is_correct else 0

            # Streak only increments if correct answer, else reset to 0
            current_streak = user[3]
            new_streak = current_streak + 1 if is_correct else 0

            new_xp = user[2] + gained_xp
            new_rank = get_rank(new_xp)
            new_completed_today = user[6] + 1
            new_drills = user[5]

            # Prepare feedback message
            feedback_msg = scenario["feedback"][selected_option]
            xp_msg = f"🎉 You earned *{gained_xp} XP!*"

            # Update user progress for this question
            updated_answers = current_q["answers"] + [selected_option]
            total_xp_so_far = current_q["total_xp"] + gained_xp

            # Update DB with new progress but keep current_q json updated
            update_user_progress(
                chat_id,
                xp=new_xp,
                streak=new_streak,
                rank=new_rank,
                completed_today=new_completed_today,
                drills=new_drills,
                current_q={
                    "index": question_index,
                    "xp_gained": gained_xp,
                    "total_xp": total_xp_so_far,
                    "answers": updated_answers,
                }
            )

            # Send feedback and XP message
            send_message(chat_id, f"{feedback_msg}\n\n{xp_msg}")

            # If less than 4 questions answered, send "Next" button inline
            if question_index < 4:
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "Next ➡️", "callback_data": "next_question"}]
                    ]
                }
                send_message(chat_id, "Ready for the next question?", reply_markup=keyboard)
            else:
                # Drill completed - show summary
                xp_to_next_rank = get_next_rank_xp(new_xp)
                send_end_of_drill_summary(chat_id, total_xp_so_far, new_streak, new_rank, xp_to_next_rank)
                # Clear current_q after drill
                update_user_progress(chat_id, current_q=None)

        elif data_callback == "next_question":
            current_q = user[8]
            next_index = current_q["index"] + 1
            # Update current_q index for next question but keep answers etc.
            update_user_progress(
                chat_id,
                current_q={
                    "index": next_index,
                    "xp_gained": 0,
                    "total_xp": current_q["total_xp"],
                    "answers": current_q["answers"],
                }
            )
            send_question(chat_id, next_index)

        elif data_callback == "view_profile":
            user = get_user(chat_id)
            send_profile(chat_id, user)

        elif data_callback == "start_drill":
            update_user_progress(chat_id, current_q={"index": 0, "xp_gained": 0, "total_xp": 0, "answers": []})
            send_question(chat_id, 0)

        else:
            send_message(chat_id, "Unknown action. Use /drill to start.")

    elif "message" in data:
        message = data["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text", "")

        if text == "/start":
            first_name = message["chat"].get("first_name", "Sensei")
            user = get_user(chat_id)
            if not user:
                create_user(chat_id, first_name)
            send_message(chat_id, f"👋 Hello, {first_name}! Ready to start your disaster drill? Use /drill to begin.")

        elif text == "/drill":
            user = get_user(chat_id)
            if not user:
                send_message(chat_id, "Please /start first.")
                return {"ok": True}
            update_user_progress(chat_id, current_q={"index": 0, "xp_gained": 0, "total_xp": 0, "answers": []})
            send_question(chat_id, 0)

        elif text == "/profile":
            user = get_user(chat_id)
            if not user:
                send_message(chat_id, "User not found. Use /start to register.")
                return {"ok": True}
            send_profile(chat_id, user)

        elif text == "/about":
            send_about(chat_id)

        else:
            send_message(chat_id, "Use /start, /drill, /profile, or /about.")

    return {"ok": True}

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
