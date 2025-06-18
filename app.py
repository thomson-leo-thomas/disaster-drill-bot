import os
import random
import json
from flask import Flask, request
import requests

# === Setup Flask App ===
app = Flask(__name__)

# === Telegram Bot Setup ===
BOT_TOKEN = os.environ['BOT_TOKEN']
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# === Load Scenarios from data.json ===
with open("data.json", "r") as file:
    SCENARIOS = json.load(file)

# === Store active scenarios per user (temporary memory) ===
scenario_by_chat = {}

# === Send Message to Telegram User ===
def send_message(chat_id, text):
    url = TELEGRAM_API + "sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    requests.post(url, json=payload)

# === Telegram Webhook Endpoint ===
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()

    message = data.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    user_text = message.get("text", "").strip()

    if not chat_id:
        return "No chat ID", 200

    # 1️⃣ Handle /start
    if user_text.lower() == "/start":
        send_message(chat_id, "👋 Welcome to the Disaster Drill Bot!\nSend /drill to begin a safety scenario.")

    # 2️⃣ Handle /drill
    elif user_text.lower() == "/drill":
        scenario = random.choice(SCENARIOS)

        msg = f"🔥 Disaster Drill:\n\n{scenario['scenario']}\n\n"
        msg += f"A: {scenario['A']}\nB: {scenario['B']}\nC: {scenario['C']}\nD: {scenario['D']}\n\n"
        msg += "Reply with A, B, C, or D."

        scenario_by_chat[chat_id] = scenario
        send_message(chat_id, msg)

    # 3️⃣ Handle A/B/C/D answer
    elif user_text.upper() in ["A", "B", "C", "D"]:
        scenario = scenario_by_chat.get(chat_id)

        if scenario:
            feedback = scenario["feedback"].get(user_text.upper(), "Invalid option.")
            send_message(chat_id, feedback)
        else:
            send_message(chat_id, "❗Please start a drill first using /drill.")

    # 4️⃣ Handle anything else
    else:
        send_message(chat_id, "❓ I didn't understand that. Type /drill to get started.")

    return "OK"

# === For Local Testing Only ===
if __name__ == "__main__":
    app.run()
