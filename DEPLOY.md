# 🚀 Deployment Guide

Complete guide for deploying telegram-sport-event-bots Bots on a production server.

## 📋 Prerequisites

- Ubuntu/Debian server (20.04+ or 11+)
- MySQL 5.7+ or MariaDB 10.3+
- Python 3.11+
- Root or sudo access
- Telegram Bot Tokens from [@BotFather](https://t.me/botfather)

## 🔧 Server Preparation

### 1. Update System

```bash
sudo apt update
sudo apt upgrade -y
```

### 2. Install Dependencies

```bash
# Python and build tools
sudo apt install -y python3 python3-venv python3-pip python3-dev

# MySQL server (if not installed)
sudo apt install -y mysql-server

# Other useful tools
sudo apt install -y git curl wget nano
```

### 3. Install MySQL Client (if needed)

```bash
sudo apt install -y python3-mysqldb libmysqlclient-dev
```

## 📦 Project Setup

### 1. Clone Repository

```bash
cd /usr/local
sudo mkdir tgbot
sudo chown $USER:$USER tgbot
cd tgbot

git clone https://github.com/wavcheb/telegram-sport-event-bots.git .
```

### 2. Setup Virtual Environments

Each bot uses its own isolated virtual environment:

```bash
# IMPORTANT: Fix line endings first (if cloning on Linux from Windows/Git)
# If you get "cannot execute: required file not found" error, run:
chmod +x fix_line_endings.sh
./fix_line_endings.sh

# Make setup scripts executable
chmod +x setup_all.sh
chmod +x sport_event_bot/setup_venv.sh
chmod +x tournament_bot/setup_venv.sh
chmod +x run_sport_event_bot.sh
chmod +x run_tournament_bot.sh

# Run setup for all bots
./setup_all.sh
```

This will:
- Create `sport_event_bot/venv/` with all dependencies
- Create `tournament_bot/venv/` with all dependencies
- Install all required packages from `requirements.txt`

**Common Issue - Line Endings:**
If you see error: `./setup_all.sh: cannot execute: required file not found`

This means files have Windows line endings (CRLF). Quick fix:
```bash
# Option 1: Use fix script (recommended)
chmod +x fix_line_endings.sh
./fix_line_endings.sh

# Option 2: Manual fix
sudo apt install dos2unix
find . -name "*.sh" -type f -exec dos2unix {} \;
chmod +x *.sh sport_event_bot/*.sh tournament_bot/*.sh
```

### 3. Configure Databases

#### Sport Event Bot Database

```bash
mysql -u root -p
```

```sql
CREATE DATABASE futsal_bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'futsal_bot'@'localhost' IDENTIFIED BY 'YOUR_STRONG_PASSWORD';
GRANT ALL PRIVILEGES ON futsal_bot.* TO 'futsal_bot'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

Create `.env` file:
```bash
cp .env.example .env
nano .env
```

Set your values:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
MYSQL_HOST=localhost
MYSQL_DATABASE=futsal_bot
MYSQL_USER=futsal_bot
MYSQL_PASSWORD=YOUR_STRONG_PASSWORD
```

Secure the file:
```bash
chmod 600 .env
```

#### Tournament Bot Database

```bash
mysql -u root -p
```

```sql
CREATE DATABASE tournament_bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'tournament_bot'@'localhost' IDENTIFIED BY 'YOUR_STRONG_PASSWORD';
GRANT ALL PRIVILEGES ON tournament_bot.* TO 'tournament_bot'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

Configuration is read from `.env` file (same file as Sport Event Bot).
Add tournament bot settings if using separate database:
```
TOURNAMENT_BOT_TOKEN=your_tournament_bot_token
TOURNAMENT_MYSQL_DATABASE=tournament_bot
TOURNAMENT_MYSQL_USER=tournament_bot
TOURNAMENT_MYSQL_PASSWORD=your_password
```

Initialize database:
```bash
source tournament_bot/venv/bin/activate
python -m tournament_bot.db_tournament
deactivate
```

### 4. Configure Bots

Both bots read configuration from `.env` file in the project root:

```bash
cp .env.example .env
nano .env
```

Set all required values:
```
# Sport Event Bot
TELEGRAM_BOT_TOKEN=your_sport_bot_token

# Database (shared or separate)
MYSQL_HOST=localhost
MYSQL_DATABASE=futsal_bot
MYSQL_USER=futsal_bot
MYSQL_PASSWORD=your_secure_password
```

**Secure the config:**
```bash
chmod 600 .env
```

**Note:** For backward compatibility, bots also check `token.txt` files if env var is not set.

## 🧪 Test Run

### Test Sport Event Bot
```bash
./run_sport_event_bot.sh
```

You should see:
```
🚀 Starting Sport Event Bot...
INFO | Telegram Futsal Bot is starting...
```

Press `Ctrl+C` to stop.

### Test Tournament Bot
```bash
./run_tournament_bot.sh
```

You should see:
```
🚀 Starting Tournament Bot...
INFO | Tournament Bot started
```

Press `Ctrl+C` to stop.

## 🔄 Production Setup with systemd

**ВАЖНО:** Боты **НЕ требуют root** прав и **НЕ должны** запускаться от root!
Для безопасности используйте:
- **Вариант A**: Systemd User Services (рекомендуется для обычных пользователей)
- **Вариант B**: System Services с указанием пользователя (требует sudo для управления)

### Вариант A: User Services (БЕЗ ROOT) - Рекомендуется

Если у вас **нет sudo/root** доступа (например, пользователь `fastuser`), используйте user services:

#### 1. Create User Service Directory
```bash
mkdir -p ~/.config/systemd/user
```

#### 2. Create Service Files

**Sport Event Bot:**
```bash
nano ~/.config/systemd/user/sport-event-bot.service
```

Paste:
```ini
[Unit]
Description=Telegram Sport Event Bot (User Service)
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/tgbot
EnvironmentFile=%h/tgbot/.env
ExecStart=%h/tgbot/run_sport_event_bot.sh
Restart=always
RestartSec=10
StandardOutput=append:%h/tgbot/sport_event_bot/logs/systemd.log
StandardError=append:%h/tgbot/sport_event_bot/logs/systemd.log

NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
```

**Tournament Bot:**
```bash
nano ~/.config/systemd/user/tournament-bot.service
```

Paste:
```ini
[Unit]
Description=Telegram Tournament Bot (User Service)
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/tgbot
EnvironmentFile=%h/tgbot/.env
ExecStart=%h/tgbot/run_tournament_bot.sh
Restart=always
RestartSec=10
StandardOutput=append:%h/tgbot/tournament_bot/logs/systemd.log
StandardError=append:%h/tgbot/tournament_bot/logs/systemd.log

NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
```

**Note:** `%h` автоматически заменяется на домашнюю директорию пользователя.

#### 3. Enable and Start User Services
```bash
# Reload user services
systemctl --user daemon-reload

# Enable services (start on login)
systemctl --user enable sport-event-bot
systemctl --user enable tournament-bot

# Enable lingering (запуск сервисов даже если пользователь не залогинен)
loginctl enable-linger $USER

# Start services
systemctl --user start sport-event-bot
systemctl --user start tournament-bot

# Check status
systemctl --user status sport-event-bot
systemctl --user status tournament-bot
```

#### 4. User Service Management Commands
```bash
# Start
systemctl --user start sport-event-bot
systemctl --user start tournament-bot

# Stop
systemctl --user stop sport-event-bot
systemctl --user stop tournament-bot

# Restart
systemctl --user restart sport-event-bot
systemctl --user restart tournament-bot

# View logs
journalctl --user -u sport-event-bot -f
journalctl --user -u tournament-bot -f
```

**Преимущества User Services:**
- ✅ Не требуют root/sudo прав
- ✅ Безопаснее (запускаются от обычного пользователя)
- ✅ Легче управлять
- ✅ Автоматически изолированы от системы

---

### Вариант B: System Services (С ROOT доступом)

Если у вас есть sudo доступ и вы хотите запускать боты как системные сервисы:

#### 1. Create systemd Service for Sport Event Bot

```bash
sudo nano /etc/systemd/system/sport-event-bot.service
```

Paste:
```ini
[Unit]
Description=Telegram Sport Event Bot
After=network.target mysql.service
Wants=mysql.service

[Service]
Type=simple
User=YOUR_USERNAME
Group=YOUR_USERNAME
WorkingDirectory=/usr/local/tgbot
EnvironmentFile=/usr/local/tgbot/.env
ExecStart=/usr/local/tgbot/run_sport_event_bot.sh
Restart=always
RestartSec=10
StandardOutput=append:/usr/local/tgbot/sport_event_bot/logs/systemd.log
StandardError=append:/usr/local/tgbot/sport_event_bot/logs/systemd.log

# Security
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Replace `YOUR_USERNAME` with your actual username (check with `whoami`).

### 2. Create systemd Service for Tournament Bot

```bash
sudo nano /etc/systemd/system/tournament-bot.service
```

Paste:
```ini
[Unit]
Description=Telegram Tournament Bot
After=network.target mysql.service
Wants=mysql.service

[Service]
Type=simple
User=YOUR_USERNAME
Group=YOUR_USERNAME
WorkingDirectory=/usr/local/tgbot
EnvironmentFile=/usr/local/tgbot/.env
ExecStart=/usr/local/tgbot/run_tournament_bot.sh
Restart=always
RestartSec=10
StandardOutput=append:/usr/local/tgbot/tournament_bot/logs/systemd.log
StandardError=append:/usr/local/tgbot/tournament_bot/logs/systemd.log

# Security
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Replace `YOUR_USERNAME` with your actual username.

#### 2. Enable and Start System Services

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable services (start on boot)
sudo systemctl enable sport-event-bot
sudo systemctl enable tournament-bot

# Start services
sudo systemctl start sport-event-bot
sudo systemctl start tournament-bot

# Check status
sudo systemctl status sport-event-bot
sudo systemctl status tournament-bot
```

#### 3. System Service Management Commands

```bash
# Start
sudo systemctl start sport-event-bot
sudo systemctl start tournament-bot

# Stop
sudo systemctl stop sport-event-bot
sudo systemctl stop tournament-bot

# Restart
sudo systemctl restart sport-event-bot
sudo systemctl restart tournament-bot

# View logs
sudo journalctl -u sport-event-bot -f
sudo journalctl -u tournament-bot -f

# Or view bot logs directly
tail -f sport_event_bot/logs/logs.log
tail -f tournament_bot/logs/tournament_bot.log
```

## 🔒 Security Checklist

- [ ] Strong passwords for MySQL users
- [ ] `.env` file has 600 permissions
- [ ] Bots run as non-root user
- [ ] MySQL only accepts local connections
- [ ] Regular system updates enabled
- [ ] Firewall configured (if needed)
- [ ] Log rotation configured

### Setup Log Rotation

```bash
sudo nano /etc/logrotate.d/tgbots
```

```
/usr/local/tgbot/*/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    missingok
    create 644 YOUR_USERNAME YOUR_USERNAME
}
```

Test:
```bash
sudo logrotate -f /etc/logrotate.d/tgbots
```

## 📊 Monitoring

### Check Bot Status
```bash
# Check if processes are running
ps aux | grep "sport_event_bot\|tournament_bot"

# Check service status
sudo systemctl status sport-event-bot tournament-bot

# Check recent logs
tail -n 50 sport_event_bot/logs/logs.log
tail -n 50 tournament_bot/logs/tournament_bot.log
```

### Monitor Resource Usage
```bash
# CPU and Memory
top -p $(pgrep -d',' -f "sport_event_bot|tournament_bot")

# Or use htop (install with: sudo apt install htop)
htop
```

## 🐛 Troubleshooting

### Line Ending Issues

If you get "cannot execute: required file not found":
```bash
# Install dos2unix
sudo apt install dos2unix

# Fix line endings
find . -name "*.sh" -type f -exec dos2unix {} \;

# Make scripts executable again
chmod +x setup_all.sh run_*.sh */setup_venv.sh
```

### Virtual Environment Issues

If venv creation fails:
```bash
# Install required packages
sudo apt install python3-venv python3-pip

# Remove old venv and recreate
rm -rf sport_event_bot/venv tournament_bot/venv
./setup_all.sh
```

### Database Connection Issues

```bash
# Test MySQL connection
mysql -u futsal_bot -p futsal_bot
mysql -u tournament_bot -p tournament_bot

# Check MySQL is running
sudo systemctl status mysql

# View MySQL error log
sudo tail -f /var/log/mysql/error.log
```

### Bot Won't Start

```bash
# Check detailed logs
tail -f sport_event_bot/logs/logs.log

# Test bot manually
source sport_event_bot/venv/bin/activate
python -m sport_event_bot.bot
deactivate

# Check .env file
grep TELEGRAM_BOT_TOKEN .env | wc -c  # Should show token is set
```

### Permission Errors

```bash
# Fix ownership
sudo chown -R $USER:$USER /usr/local/tgbot

# Fix permissions
chmod 755 /usr/local/tgbot
chmod 755 /usr/local/tgbot/sport_event_bot
chmod 755 /usr/local/tgbot/tournament_bot
chmod 600 /usr/local/tgbot/.env
chmod +x /usr/local/tgbot/*.sh
chmod +x /usr/local/tgbot/*/setup_venv.sh
```

## 🔄 Updates

### Update Bot Code

```bash
cd /usr/local/tgbot

# Stop services
sudo systemctl stop sport-event-bot tournament-bot

# Pull updates
git pull

# Reinstall dependencies if needed
cd sport_event_bot && source venv/bin/activate && pip install -r ../requirements.txt && deactivate
cd ../tournament_bot && source venv/bin/activate && pip install -r ../requirements.txt && deactivate

# Start services
sudo systemctl start sport-event-bot tournament-bot
```

## 📝 Backup

### Database Backup

```bash
# Create backup directory
mkdir -p ~/backups

# Backup Sport Event Bot database
mysqldump -u futsal_bot -p futsal_bot > ~/backups/futsal_bot_$(date +%Y%m%d).sql

# Backup Tournament Bot database
mysqldump -u tournament_bot -p tournament_bot > ~/backups/tournament_bot_$(date +%Y%m%d).sql
```

### Automated Daily Backups

```bash
crontab -e
```

Add:
```cron
# Daily database backups at 2 AM
0 2 * * * mysqldump -u futsal_bot -pYOUR_PASSWORD futsal_bot > ~/backups/futsal_bot_$(date +\%Y\%m\%d).sql
0 2 * * * mysqldump -u tournament_bot -pYOUR_PASSWORD tournament_bot > ~/backups/tournament_bot_$(date +\%Y\%m\%d).sql

# Clean old backups (keep 30 days)
0 3 * * * find ~/backups -name "*.sql" -mtime +30 -delete
```

---

**Your bots are now deployed and running! 🎉**

For bot-specific usage instructions, see:
- [Sport Event Bot Documentation](sport_event_bot/README.md)
- [Tournament Bot Documentation](tournament_bot/README.md)
