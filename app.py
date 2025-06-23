
import os
import json
import random
import requests
import psycopg2
from datetime import datetime, timedelta
from flask import Flask, request, jsonify


print("🧠 Sensei is thinking... Flask is starting.")
app = Flask(__name__)

# === Telegram Bot Setup ===
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "securetoken123")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# === Load Scenarios and Mythbusters ===
with open("data.json", "r", encoding="utf-8") as file:
    SCENARIOS = json.load(file)

with open("mythbusters.json", "r", encoding="utf-8") as file:
    MYTHBUSTERS = json.load(file)

# === PostgreSQL Connection ===
def get_db():
    return psycopg2.connect(
        host=os.environ["PGHOST"],
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        port=os.environ.get("PGPORT", 5432)
    )

# === Level Ranks ===
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

# === Send Message ===
def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(TELEGRAM_API + "sendMessage", json=payload)

# === Get Level by XP ===
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

leaderboard_cache = {"data": None, "last_updated": None}

def get_leaderboard():
    now = datetime.utcnow()
    if leaderboard_cache["data"] and leaderboard_cache["last_updated"].date() == now.date():
        return leaderboard_cache["data"]
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT first_name, xp, streak FROM users ORDER BY xp DESC LIMIT 10")
    rows = cur.fetchall()
    leaderboard_cache["data"] = rows
    leaderboard_cache["last_updated"] = now
    cur.close()
    conn.close()
    return rows

@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    message = data.get("message") or data.get("callback_query", {}).get("message")
    user_text = data.get("message", {}).get("text") or data.get("callback_query", {}).get("data")
    if not message: return "No message", 200
    chat_id = message["chat"]["id"]
    first_name = message["chat"].get("first_name", "Sensei")
    cmd = user_text.strip().lower()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (id, first_name, last_active, completed_today, xp, streak, rank)
        VALUES (%s, %s, CURRENT_DATE, false, 0, 0, %s)
        ON CONFLICT (id) DO UPDATE SET first_name = EXCLUDED.first_name
    """, (chat_id, first_name, get_level(0)))
    conn.commit()

    cur.execute("SELECT * FROM users WHERE id = %s", (chat_id,))
    user = cur.fetchone()
    xp, streak, completed_today, current_q, drills = user[4], user[5], user[3], user[7], user[8]

    if cmd == "/start":
        send_message(chat_id, "🚨 *Welcome to Disaster Sensei* 🚨\nType /drill to begin today’s challenge.")

    elif cmd == "/drill":
        if completed_today or drills >= 5:
            send_message(chat_id, "🌞 You've completed today's 5 drills. Come back tomorrow!")
        else:
            scenario = random.choice(SCENARIOS)
            qjson = json.dumps(scenario)
            cur.execute("UPDATE users SET current_q = %s WHERE id = %s", (qjson, chat_id))
            conn.commit()
            msg = f"🔥 *Disaster Drill {drills+1}/5:*\n\n"

{scenario['scenario']}

"
            msg += f"A: {scenario['A']}
B: {scenario['B']}
C: {scenario['C']}
D: {scenario['D']}"
            buttons = {"inline_keyboard": [[{"text": x, "callback_data": x} for x in "ABCD"]]}
            send_message(chat_id, msg, reply_markup=json.dumps(buttons))

    elif cmd.upper() in ["A", "B", "C", "D"]:
        if not current_q:
            send_message(chat_id, "🌀 No active drill. Type /drill to start.")
        else:
            scenario = json.loads(current_q)
            correct = cmd.upper() == scenario["correct"]
            xp_earned = 10 if correct else 0
            new_xp = xp + xp_earned
            new_rank = get_level(new_xp)
            drills += 1
            done_today = drills >= 5

            cur.execute("UPDATE users SET xp = %s, rank = %s, completed_today = %s, drills = %s WHERE id = %s",
                        (new_xp, new_rank, done_today, drills, chat_id))
            conn.commit()

            feedback = scenario["feedback"].get(cmd.upper(), "🧠 Wise choice, Sensei.")
            feedback += f"\n{'✅' if correct else '❌'} You earned *{xp_earned} XP*."
            bar, percent, left, next_rank = get_progress_bar(new_xp)
            feedback += f"\n\n🏅 *Progress to next rank:* {next_rank}\n{bar} {percent}%\n🧗 XP to next rank: {left}"
            send_message(chat_id, feedback)

            if done_today:
                wisdom = random.choice(MYTHBUSTERS)
                msg = f"🎯 *Drill Complete!*\n✨ Total XP: *{new_xp}*\n🔥 Streak: {streak} days\n🏅 Rank: {new_rank}\n\n📚 *Sensei Wisdom:* {wisdom}\n🔁 Return tomorrow to train more!"
                send_message(chat_id, msg)
            else:
                buttons = {"inline_keyboard": [[{"text": "Next Scenario", "callback_data": "/drill"}]]}
                send_message(chat_id, "✅ Ready for your next challenge?", reply_markup=json.dumps(buttons))

    elif cmd == "/profile":
        bar, percent, left, next_rank = get_progress_bar(xp)
        profile = f"👤 *Your Profile*\n\nXP: {xp}\nStreak: {streak} days\nRank: {get_level(xp)}\n\n🏅 Progress to next rank: {next_rank}\n{bar} {percent}%\n🧗 XP to next rank: {left}\n\nDrill Completed Today: {'✅' if completed_today else '❌'}"
        send_message(chat_id, profile)

    elif cmd == "/leaderboard":
        top = get_leaderboard()
        msg = "🏆 *Disaster Sensei — Daily Leaderboard* 🏆\n\n🔥 Top responders mastering disaster readiness:\n\n"
        for i, row in enumerate(top, 1):
            msg += f"{i}️⃣ {row[0]} — {row[1]} XP, 🔥 {row[2]}d streak\n"
        msg += "\n⏳ Leaderboard resets daily at midnight UTC\n💡 Use /drill to climb ranks!"
        send_message(chat_id, msg)

    elif cmd == "/help":
        msg = "/start — Begin training\n/drill — Daily challenge\n/profile — View your stats\n/leaderboard — XP leaderboard\n/about — About this bot"
        send_message(chat_id, msg)

    elif cmd == "/about":
        msg = "👤 *About Disaster Sensei*\n\nBuilt by *Thomson* ⚙️\nMaking safety fun, smart, and practical.\n\n⚠️ *Disclaimer:* This bot is for educational use only. Follow official emergency guidelines."
        send_message(chat_id, msg)

    else:
        send_message(chat_id, "❓ I didn’t get that. Type /drill to start training.")

    cur.close()
    conn.close()
    return "OK"

@app.route("/cleanup")
def cleanup():
    token = request.args.get("token")
    if token != ADMIN_TOKEN:
        return jsonify({"status": "unauthorized"}), 401
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET completed_today = false, drills = 0")
    conn.commit()
    cur.close()
    conn.close()
    leaderboard_cache.clear()
    return jsonify({"status": "daily reset complete"})
print("🚀 Flask is launching with dynamic port...")
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

