# ⚽ Sport Event Bot - Setup & Deployment Guide

This guide will help you set up and deploy your Sport Event Bot using PostgreSQL (Neon.tech).

## 1. Local Setup

### Prerequisites
- Python 3.11+
- A Telegram Bot Token from [@BotFather](https://t.me/botfather)
- Neon.tech Database credentials (provided in `.env.example`)

### Installation
1.  **Clone the repository** (if you haven't already):
    ```bash
    git clone <your-repo-url>
    cd tg-sport-event-bot
    ```

2.  **Create a Virtual Environment**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment**:
    ```bash
    cp .env.example .env
    # Edit .env and add your TELEGRAM_BOT_TOKEN
    ```

5.  **Initialize Database**:
    The bot will automatically create the necessary tables on the first run.

6.  **Run the Bot**:
    ```bash
    python3 -m sport_event_bot.bot
    ```

---

## 2. Production Deployment

### Option A: Render (Easiest, Free Tier)
Render is the easiest way to get started.

1.  **Create a new "Web Service"** on Render.
2.  **Connect your GitHub repository**.
3.  **Configure Service**:
    - **Language**: `Python`
    - **Build Command**: `pip install -r requirements.txt`
    - **Start Command**: `python3 -m sport_event_bot.bot`
4.  **Add Environment Variables**:
    Go to the "Env Vars" tab and add all the variables from your `.env` file.
5.  **Note on Free Tier**: Render's free Web Services sleep after 15 minutes of inactivity. For a Telegram bot, this means the first message might be delayed while it wakes up. To prevent this, you can use a free "uptime" service (like Cron-job.org) to ping your Render URL every 10 minutes.

### Option B: OCI / AWS Always Free (Recommended for Performance)
This is slightly more advanced but provides a 24/7 "always-on" bot.

1.  **Provision a VM**: Create an Ubuntu/Oracle Linux instance on OCI or AWS.
2.  **Connect via SSH**.
3.  **Install Python & Git**:
    ```bash
    sudo apt update
    sudo apt install python3-pip python3-venv git -y
    ```
4.  **Clone & Setup**: Follow the "Local Setup" steps above inside the VM.
5.  **Set up systemd** (To run the bot in the background):
    Create a service file:
    ```bash
    sudo nano /etc/systemd/system/sport-bot.service
    ```
    Paste the following (adjust paths):
    ```ini
    [Unit]
    Description=Sport Event Bot
    After=network.target

    [Service]
    User=ubuntu
    WorkingDirectory=/home/ubuntu/tg-sport-event-bot
    ExecStart=/home/ubuntu/tg-sport-event-bot/venv/bin/python3 -m sport_event_bot.bot
    Restart=always

    [Install]
    WantedBy=multi-user.target
    ```
    Enable and start:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable sport-bot
    sudo systemctl start sport-bot
    ```

---

## 3. Bot Features
- **/event_add [description]**: Create a new football/sport event.
- **/event_remove**: Close the current event.
- **/info**: Show current event status and player list.
- **Inline Buttons**: Players can sign up, cancel, or confirm payment directly via buttons.
- **Localization**: Supports multiple languages based on user settings.

## 4. Troubleshooting
- **Database Connection**: Ensure `DB_SSLMODE=require` is set for Neon DB.
- **Bot Not Responding**: Check logs with `journalctl -u sport-bot -f` (on Linux) or the Render logs.
