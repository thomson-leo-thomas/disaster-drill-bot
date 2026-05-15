# 🥷 Disaster Sensei

> **Train your instincts. Build resilience. Master disaster response.**

Disaster Sensei is a gamified Telegram bot that teaches disaster preparedness through interactive daily drills, myth-busting facts, and a progression-based ranking system.

Users face realistic emergency scenarios, earn XP for correct decisions, maintain streaks, and rise through elite response ranks — from **🐣 Trainee Responder** to **🥷 Disaster Sensei**.

---

## 🌍 Why Disaster Sensei?

In a real emergency, the right decision made in seconds can save lives.

Disaster Sensei transforms disaster education into an engaging experience by combining:

- 🧠 Scenario-based learning
- 🎮 Gamification and progression
- 📈 Daily streaks and XP
- 💡 Myth-busting educational facts
- 🏆 Rank advancement

The result is a fun, memorable, and practical way to build crisis readiness.

---

## ✨ Features

### 🧪 Daily Survival Drills
- Up to 5 drills per day
- Realistic multiple-choice scenarios
- Instant educational feedback

### 🎖 XP & Rank System
- Earn XP for correct answers
- Unlock 10 unique ranks
- Visual progress tracking

### 🔥 Streak Tracking
- Maintain consecutive training days
- Build discipline and consistency

### 💡 Disaster Decode
- Myth-busting facts after every drill
- Correct common misconceptions

### 👤 Personal Profile
- View XP, rank, streak, and progress

### 📘 Sensei's Toolbox
- Clean command interface
- `/ranks` to view the complete progression system

### 🗄 PostgreSQL Backend
- Persistent storage for all user data
- Connection pooling for efficient scaling

### ☁️ Deployment Ready
- Compatible with Railway, Render, Heroku, and Docker

---

## 🏅 Rank Progression

| Level | Rank |
|------:|------|
| 1 | 🐣 Trainee Responder |
| 2 | 🧯 Drill Novice |
| 3 | 🚒 Ember Fighter |
| 4 | 🏕️ Survivalist |
| 5 | 🧠 Wise Responder |
| 6 | 🔥 Hazard Handler |
| 7 | 🚨 Alert Ace |
| 8 | 🛰️ Crisis Commander |
| 9 | 🎖️ Master Responder |
| 10 | 🥷 Disaster Sensei |

---

## 🤖 Telegram Commands

### 🧰 Sensei's Toolbox

| Command | Description |
|--------|-------------|
| `/start` | Step into the Dojo and begin your training |
| `/drill` | Start your daily survival drills (max 5/day) |
| `/profile` | View your XP, rank, streak, and progress |
| `/ranks` | Explore all ranks and progression milestones |
| `/myth` | Learn a myth-busting disaster fact |
| `/about` | Learn about the project and mission |
| `/help` | Open Sensei's Toolbox |

---

## 🛠 Tech Stack

- 🐍 Python 3
- 🌶 Flask
- 🤖 Telegram Bot API
- 🐘 PostgreSQL
- 🔌 Psycopg2 Connection Pool
- ☁️ Railway

---


## 🗄 Database Schema

```sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    first_name TEXT,
    xp INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0,
    rank INTEGER DEFAULT 1,
    drills INTEGER DEFAULT 0,
    completed_today BOOLEAN DEFAULT FALSE,
    last_drill_date DATE,
    current_q JSONB
);
```

---

## ⚙️ Environment Variables

| Variable | Description |
|--------|--------|
| `BOT_TOKEN` | Telegram bot token from BotFather |
| `DATABASE_URL` | PostgreSQL connection string |
| `ADMIN_TOKEN` | Secret token for the cleanup endpoint |
| `PORT` | Port number (default: `8080`) |

---

## 🚀 Deployment (Railway)

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/disaster-sensei.git
cd disaster-sensei
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Set the required variables in your Railway project.

### 4. Deploy

Railway will automatically detect the Flask app and deploy it.

---

## 🔗 Telegram Webhook Setup

```bash
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://your-app.up.railway.app/
```

---

## 📦 requirements.txt

```txt
Flask
requests
psycopg2-binary
```

---

## 📄 API Endpoints

| Endpoint | Purpose |
|--------|--------|
| `/` (GET) | Health check |
| `/` (POST) | Telegram webhook |
| `/cleanup?token=...` | Reset daily drills for all users |

---

## 🧠 Example User Experience

```text
🧠 Welcome, Survivor!
Train your instincts in the Disaster Sensei Dojo.

🧪 Drill 1/5
Scenario: You smell gas in your home...

A. Turn on the lights
B. Open windows and evacuate
C. Ignore it
D. Use a candle

✅ Correct!
🎖 XP gained: +10
🔥 Streak: 5 days
🏅 Rank: 🚨 Alert Ace
💡 Disaster Decode: Gas leaks should never be tested with flames.
```

---

## 🔒 Security & Reliability

- Connection pooling with `SimpleConnectionPool`
- Centralized exception handling
- Admin-protected cleanup endpoint
- Environment-based secret management

---

## 🗺 Roadmap

- 🏆 Global leaderboard
- 📊 Analytics dashboard
- 🌐 Multi-language support
- 🎯 Personalized drill categories
- 🏅 Achievement badges
- 📱 Web dashboard

---

## 📜 License

Licensed under the Apache License 2.0.


---

## 👨‍💻 Creator

**Thomson Leo Thomas**

Built with code, curiosity, and a mission to make disaster preparedness engaging and accessible.


> **Prepared minds save lives.**
