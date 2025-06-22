
import os
import random
import json
import requests
import psycopg2
import psycopg2.extras
from datetime import datetime, date
from flask import Flask, request, jsonify

app = Flask(__name__)

# === Setup ===
BOT_TOKEN = os.environ["BOT_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/"
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "securetoken123")
DATABASE_URL = os.environ["DATABASE_URL"]

with open("data.json", "r", encoding="utf-8") as file:
    SCENARIOS = json.load(file)

with open("mythbusters.json", "r", encoding="utf-8") as file:
    MYTHBUSTERS = json.load(file)

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

def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(TELEGRAM_API + "sendMessage", json=payload)

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

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    message = data.get("message") or data.get("callback_query", {}).get("message")
    user_text = data.get("message", {}).get("text") or data.get("callback_query", {}).get("data")
    if not message:
        return "No message", 200

    chat_id = message["chat"]["id"]
    first_name = message["chat"].get("first_name", "Sensei")
    conn = get_db()
    cur = conn.cursor()

    # Create user if not exists
    cur.execute("""
        INSERT INTO users (id, first_name, last_active)
        VALUES (%s, %s, CURRENT_DATE)
        ON CONFLICT (id) DO UPDATE SET first_name = EXCLUDED.first_name
    """, (chat_id, first_name))

    cur.execute("SELECT * FROM users WHERE id = %s", (chat_id,))
    user = cur.fetchone()
    xp, streak, rank, completed_today = user["xp"], user["streak"], user["rank"], user["completed_today"]
    drills = user.get("drills_done", 0)

    cmd = user_text.strip().lower()

    if cmd == "/start":
        send_message(chat_id, "🚨 *Welcome to Disaster Sensei* 🚨\nYour personal dojo for disaster readiness.\n\nType /drill to begin today’s challenge.")

    elif cmd == "/drill":
        if completed_today or drills >= 5:
            send_message(chat_id, "🌞 You've completed today's 5 drills. Come back tomorrow!")
        else:
            scenario = random.choice(SCENARIOS)
            qjson = json.dumps(scenario)
            cur.execute("UPDATE users SET current_q = %s WHERE id = %s", (qjson, chat_id))
            conn.commit()

            msg = (
                f"🔥 *Disaster Drill {drills + 1}/5:*\n\n"
                f"{scenario['scenario']}\n\n"
                f"A: {scenario['A']}\n"
                f"B: {scenario['B']}\n"
                f"C: {scenario['C']}\n"
                f"D: {scenario['D']}"
            )

            buttons = {"inline_keyboard": [[{"text": x, "callback_data": x} for x in "ABCD"]]}
            send_message(chat_id, msg, reply_markup=json.dumps(buttons))

    elif cmd.upper() in ["A", "B", "C", "D"]:
        scenario = json.loads(user["current_q"] or '{}')
        if not scenario:
            send_message(chat_id, "🌀 No drill in progress. Use /drill to start.")
        else:
            correct = cmd.upper() == scenario["correct"]
            xp_earned = 10 if correct else 0
            xp += xp_earned
            drills += 1
            rank = get_level(xp)

            cur.execute("""
                UPDATE users SET xp = %s, rank = %s, drills_done = %s,
                completed_today = %s, current_q = NULL
                WHERE id = %s
            """, (xp, rank, drills, drills >= 5, chat_id))
            conn.commit()

            feedback = scenario["feedback"].get(cmd.upper(), "Invalid option.")
            feedback += f"\n{'✅' if correct else '❌'} You earned *{xp_earned} XP*."
            bar, percent, left, next_rank = get_progress_bar(xp)
            feedback += f"\n🏅 *Progress to next rank:* {next_rank}\n{bar} {percent}%\n🧗 XP to next rank: {left}"
            send_message(chat_id, feedback)

            if drills >= 5:
                fun_fact = random.choice(MYTHBUSTERS)
                summary = f"\n🎯 *Drill Complete!*\n✨ You earned *{xp} XP* today!\n🔥 *Streak:* {streak} days\n🏅 *Level:* {rank}\n\n📚 *Sensei Wisdom:* {fun_fact}\n🔁 Come back tomorrow for more survival missions!"
                send_message(chat_id, summary)

    elif cmd == "/profile":
        bar, percent, left, next_rank = get_progress_bar(xp)
        profile = f"👤 *Your Profile*\n\nXP: {xp}\nStreak: {streak} days\nRank: {rank}\n\n🏅 Progress to next rank: {next_rank}\n{bar} {percent}%\n🧗 XP to next rank: {left}\n\nDrills Completed Today: {'✅' if completed_today else '❌'}"
        send_message(chat_id, profile)

    elif cmd == "/help":
        send_message(chat_id, "/start — Begin training\n/drill — Daily challenge\n/profile — Your stats\n/help — Command guide")

    elif cmd == "/about":
        send_message(chat_id, "👤 *About Disaster Sensei*\n\nBuilt by *Thomson* ⚙️\nGamified safety training made smart, fun, and practical.\n\n⚠️ *Disclaimer:* For educational use only. Always follow official emergency guidelines.")

    conn.close()
    return "OK"

@app.route("/cleanup")
def cleanup():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return jsonify({"status": "unauthorized"}), 401
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET completed_today = false, drills_done = 0")
    conn.commit()
    conn.close()
    return jsonify({"status": "daily reset complete"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

