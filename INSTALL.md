# 📦 Installation Guide

Complete step-by-step guide for setting up the Sport Event Bot.

## Prerequisites

Before you begin, ensure you have:
- ✅ Linux/Unix server or local machine
- ✅ Python 3.11 or higher
- ✅ MySQL 5.7+ or MariaDB 10.3+
- ✅ Internet connection
- ✅ Telegram account

## Step 1: System Preparation

### Update System Packages

```bash
sudo apt update
sudo apt upgrade -y
```

### Install Python and Required Tools

```bash
sudo apt install python3 python3-pip python3-venv git mysql-server -y
```

### Verify Installations

```bash
python3 --version   # Should show 3.11+
mysql --version     # Should show MySQL/MariaDB version
```

## Step 2: Create Telegram Bot

1. Open Telegram and find [@BotFather](https://t.me/botfather)

2. Send `/newbot` command

3. Follow the prompts:
   ```
   BotFather: Alright, a new bot. How are we going to call it?
   You: Sport Event Bot

   BotFather: Good. Now let's choose a username for your bot.
   You: yourusername_sport_bot
   ```

4. **Save the token** BotFather gives you. It looks like:
   ```
   1234567890:ABCdefGHIjklMNOpqrsTUVwxyz-1234567
   ```

5. **Optional**: Set bot description and commands:
   ```
   /setdescription - Set bot description
   /setcommands - Set bot commands list
   ```

## Step 3: Database Setup

### Secure MySQL Installation (Production)

```bash
sudo mysql_secure_installation
```

Follow prompts:
- Set root password: **YES**
- Remove anonymous users: **YES**
- Disallow root login remotely: **YES**
- Remove test database: **YES**
- Reload privilege tables: **YES**

### Create Database and User

```bash
sudo mysql -u root -p
```

In MySQL console:

```sql
-- Create database
CREATE DATABASE futsal_bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Create user (replace 'your_secure_password' with actual password)
CREATE USER 'futsal_bot'@'localhost' IDENTIFIED BY 'your_secure_password';

-- Grant privileges
GRANT ALL PRIVILEGES ON futsal_bot.* TO 'futsal_bot'@'localhost';

-- Apply changes
FLUSH PRIVILEGES;

-- Exit
EXIT;
```

### Test Database Connection

```bash
mysql -u futsal_bot -p futsal_bot
```

If successful, you'll see MySQL prompt. Type `EXIT;` to leave.

## Step 4: Clone and Configure Project

### Clone Repository

```bash
cd /opt  # or your preferred location
git clone https://github.com/wavcheb/champ.git
cd champ
```

### Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

Your prompt should now show `(venv)`.

### Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Configure Environment

Create `.env` file from template:

```bash
cp .env.example .env
nano .env
```

Set your values:

```
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHI...  # From Step 2
MYSQL_HOST=localhost
MYSQL_DATABASE=futsal_bot
MYSQL_USER=futsal_bot
MYSQL_PASSWORD=your_secure_password
```

Save and secure:
```bash
chmod 600 .env
```

**Note:** For backward compatibility, the bot also checks `sport_event_bot/token.txt` if env var is not set.

## Step 5: Test Run

### Start the Bot

```bash
./run_sport_event_bot.sh
```

Or directly with Python:
```bash
python3 -m sport_event_bot.bot
```

You should see:
```
INFO     | __main__:main:622 - Telegram Futsal Bot is starting...
INFO     | __main__:main:626 - Bot is running...
```

### Test in Telegram

1. Find your bot in Telegram (search by username)
2. Send `/start` or `/help`
3. Bot should respond with command list

### Stop the Bot

Press `Ctrl+C` in the terminal.

## Step 6: Production Setup (Optional)

### Create Systemd Service

For production, run bot as a system service:

```bash
sudo nano /etc/systemd/system/sport-event-bot.service
```

Paste this content (adjust paths if needed):

```ini
[Unit]
Description=Sport Event Telegram Bot
After=network.target mysql.service

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/opt/champ
Environment="PATH=/opt/champ/venv/bin"
ExecStart=/opt/champ/venv/bin/python -m sport_event_bot.bot
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Replace `YOUR_USERNAME` with your actual username.

### Enable and Start Service

```bash
sudo systemctl daemon-reload
sudo systemctl enable sport-event-bot
sudo systemctl start sport-event-bot
```

### Check Service Status

```bash
sudo systemctl status sport-event-bot
```

### View Logs

```bash
# Real-time logs
sudo journalctl -u sport-event-bot -f

# Bot application logs
tail -f /opt/champ/logs/logs.log
```

### Service Management Commands

```bash
# Stop bot
sudo systemctl stop sport-event-bot

# Restart bot
sudo systemctl restart sport-event-bot

# Disable auto-start
sudo systemctl disable sport-event-bot
```

## Step 7: Add Bot to Your Group

1. Open your Telegram group
2. Group Settings → Administrators → Add Administrator
3. Search for your bot
4. Add it with these permissions:
   - ✅ Delete messages (to clean up old event messages)
   - ✅ Pin messages (optional)
   - ✅ Send messages
   - ✅ Add members (optional)

5. Send `/help` in the group to test

## 🔒 Security Best Practices

### 1. Protect Your Token

```bash
# Set restrictive permissions
chmod 600 token.txt
```

### 2. Regular Updates

```bash
cd /opt/champ
git pull
pip install -r requirements.txt --upgrade
sudo systemctl restart sport-event-bot
```

### 3. Backup Database

```bash
# Create backup script
sudo nano /usr/local/bin/backup-futsal-bot.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/var/backups/futsal-bot"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
mysqldump -u futsal_bot -p'your_password' futsal_bot > $BACKUP_DIR/futsal_bot_$DATE.sql
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete  # Keep only 7 days
```

```bash
# Make executable
sudo chmod +x /usr/local/bin/backup-futsal-bot.sh

# Add to crontab (daily backup at 2 AM)
sudo crontab -e
# Add line: 0 2 * * * /usr/local/bin/backup-futsal-bot.sh
```

### 4. Monitor Logs

Set up log rotation:

```bash
sudo nano /etc/logrotate.d/sport-event-bot
```

```
/opt/champ/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    missingok
    copytruncate
}
```

## 🔧 Troubleshooting

### Bot doesn't start

**Check Python version:**
```bash
python3 --version
```

**Check virtual environment:**
```bash
source venv/bin/activate
which python  # Should point to venv/bin/python
```

**Check dependencies:**
```bash
pip list
```

### Database connection fails

**Test MySQL connection:**
```bash
mysql -u futsal_bot -p futsal_bot
```

**Check MySQL is running:**
```bash
sudo systemctl status mysql
```

**Check credentials in sport_event_bot/db_mysql.py**

### Bot responds slowly

**Check system resources:**
```bash
top
free -h
df -h
```

**Check database performance:**
```sql
SHOW PROCESSLIST;
```

### Permission errors

**Fix file permissions:**
```bash
cd /opt/champ
sudo chown -R $USER:$USER .
chmod +x run_sport_event_bot.sh run_tournament_bot.sh
chmod 600 sport_event_bot/token.txt tournament_bot/token.txt
```

## 📈 Monitoring

### Check Bot Status

```bash
# Service status
sudo systemctl status sport-event-bot

# Process check
ps aux | grep sport_event_bot

# Port check (if using webhooks)
sudo netstat -tulpn | grep python
```

### Monitor Resource Usage

```bash
# Memory usage
ps aux | grep sport_event_bot | awk '{print $4}'

# CPU usage
top -p $(pgrep -f sport_event_bot)
```

## 🎉 Next Steps

- Read the [README.md](README.md) for usage instructions
- Configure translations for your language
- Customize bot messages
- Set up monitoring/alerting
- Join the community

## 💡 Tips

1. **Use tmux or screen** for manual testing:
   ```bash
   tmux new -s bot
   python sport_event_bot2.py
   # Detach: Ctrl+B then D
   # Reattach: tmux attach -t bot
   ```

2. **Enable debug logging** for troubleshooting:
   Edit `sport_event_bot2.py` line 590:
   ```python
   logger.add("logs/logs.log", level="DEBUG")  # Change from INFO
   ```

3. **Test in private chat first** before adding to groups

4. **Set up alerts** for bot downtime (UptimeRobot, etc.)

## 🆘 Getting Help

- Check logs: `tail -f logs/logs.log`
- Check GitHub Issues
- Review error messages carefully
- Google specific errors

---

**Installation complete! Your bot is ready to organize sports events! ⚽**
