# ⚽🏆 Sport Event Bots - Multi-Platform Sports Bots Collection

A comprehensive collection of bots for managing sports events and tournaments across Telegram and MAX Messenger. Each bot is fully independent with its own configuration and can share a database for cross-platform features.

## 📦 Available Bots

### 🏃 Sport Event Bot
Telegram bot for organizing sports events (football/futsal) with participant registration, payment tracking, and attendance statistics.
Use [existing bot](https://t.me/nashfootballbot) @nashfootballbot or make own selfhosted bot.

**Key Features:**
- Event management with date/time parsing
- Participant registration with inline buttons
- Payment tracking with 💰 emoji
- Attendance statistics and penalties
- Multi-language support (RU, UK, PT, AR, EN)

**[📖 Full Documentation](sport_event_bot/README.md)**

### 🏆 Tournament Bot
Telegram bot for managing sports tournaments with automatic standings calculation using Round-Robin algorithm.
Use [existing bot](https://t.me/nashtournamentbot) @nashtournamentbot or make own selfhosted bot.

**Key Features:**
- Round-Robin tournament system
- Automatic standings calculation (3-1-0 points)
- Multiple rounds support (1-4 rounds)
- Interactive match entry with buttons
- Result editing with recalculation
- Early tournament finish option

**[📖 Full Documentation](tournament_bot/README.md)**

### 📱 MAX Sport Event Bot
MAX Messenger bot for organizing sports events. Can link with Telegram Sport Event Bot for cross-platform participant management.

**Key Features:**
- Event management with participant registration
- Payment tracking
- Cross-platform chat linking with Telegram
- Participant synchronization across platforms
- Russian-only interface

**[📖 Full Documentation](max_sporteventbot/README.md)**

## 🔗 Cross-Platform Features

Sport Event Bot (Telegram) and MAX Sport Event Bot can share a database and link chats:

- **Shared Database**: Both bots use the same MySQL database with `platform` field separation
- **Chat Linking**: Link Telegram and MAX chats with `/link` command
- **Participant Sync**: See participants from both platforms in event messages
- **Event Copy**: Copy events between platforms with `/event_copy`
- **Real-Time Sync**: When participants register in one platform, the message in linked chat updates automatically (requires cross-tokens in .env)

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- MySQL 5.7+ or MariaDB 10.3+
- Telegram Bot Tokens (from [@BotFather](https://t.me/botfather))

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/wavcheb/telegram-sport-event-bots.git
   cd telegram-sport-event-bots
   ```

2. **Setup virtual environments**

   Each bot uses its own isolated virtual environment:
   ```bash
   # Quick setup for all bots
   ./setup_all.sh

   # Or setup individually
   cd sport_event_bot && ./setup_venv.sh
   cd ../tournament_bot && ./setup_venv.sh
   ```

   **⚠️ If you get "cannot execute: required file not found" error:**
   ```bash
   chmod +x fix_line_endings.sh
   ./fix_line_endings.sh
   ```
   This fixes Windows line ending issues on Linux.

3. **Configure databases**

   Create databases:
   ```bash
   mysql -u root -p
   CREATE DATABASE futsal_bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'futsal_bot'@'localhost' IDENTIFIED BY 'password';
   GRANT ALL PRIVILEGES ON futsal_bot.* TO 'futsal_bot'@'localhost';

   CREATE DATABASE tournament_bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'tournament_bot'@'localhost' IDENTIFIED BY 'password';
   GRANT ALL PRIVILEGES ON tournament_bot.* TO 'tournament_bot'@'localhost';
   ```

4. **Configure environment** (each bot has its own `.env.example`)
   ```bash
   cd sport_event_bot && cp .env.example .env && nano .env
   cd ../max_sporteventbot && cp .env.example .env && nano .env
   cd ../tournament_bot && cp .env.example .env && nano .env
   ```

   Secure the file:
   ```bash
   chmod 600 .env
   ```

5. **Run the bots**
   ```bash
   # Run Sport Event Bot
   ./run_sport_event_bot.sh

   # Run Tournament Bot (in another terminal)
   ./run_tournament_bot.sh
   ```

**For production deployment**, see [DEPLOY.md](DEPLOY.md) for complete instructions including systemd services.

## 📁 Project Structure

```
telegram-sport-event-bots/
├── cloudflare-workers/       # CF Worker for Telegram API proxy
├── sport_event_bot/          # Telegram Sport Event Bot
│   ├── bot.py               # Main bot logic
│   ├── db_mysql.py          # Database operations
│   ├── run.sh               # Standalone run script
│   ├── setup_venv.sh        # Virtual environment setup
│   ├── locale/              # Translations (RU, UK, PT, AR)
│   └── README.md            # Bot documentation
├── max_sporteventbot/        # MAX Sport Event Bot
│   ├── bot.py               # Main bot logic
│   ├── db_mysql.py          # Database operations
│   ├── run.sh               # Standalone run script
│   ├── setup_venv.sh        # Virtual environment setup
│   ├── requirements.txt     # MAX bot dependencies
│   └── README.md            # Bot documentation
├── tournament_bot/           # Tournament Bot
│   ├── bot.py               # Main bot logic
│   ├── db_tournament.py     # Database operations
│   ├── tournament_logic.py  # Tournament algorithms
│   ├── setup_venv.sh        # Virtual environment setup
│   └── README.md            # Bot documentation
├── run_sport_event_bot.sh   # Sport Event Bot launcher
├── run_max_sport_event_bot.sh # MAX Bot launcher
├── run_tournament_bot.sh    # Tournament Bot launcher
├── setup_all.sh             # Setup all bots at once
├── requirements.txt         # Python dependencies
├── INSTALL.md               # Detailed installation guide
├── DEPLOY.md                # Production deployment guide
└── README.md                # This file
```

## 🔧 Configuration

Configuration is centralized in `.env` file:
- **TELEGRAM_BOT_TOKEN**: Telegram bot token from @BotFather
- **MAX_BOT_TOKEN**: MAX Messenger bot token
- **MYSQL_HOST/DATABASE/USER/PASSWORD**: Database credentials

### Deployment Options

**Option 1: Monorepo** - All bots in one directory
```bash
cd telegram-sport-event-bots
./run_sport_event_bot.sh
./run_max_sport_event_bot.sh
```

**Option 2: Standalone** - Each bot in separate directory
```bash
# Copy to separate directories
cp -r sport_event_bot /usr/local/tgbot/sportevent
cp -r max_sporteventbot /usr/local/maxbot/sporteventbot

# Run standalone
cd /usr/local/tgbot/sportevent && ./run.sh
cd /usr/local/maxbot/sporteventbot && ./run.sh
```

### Shared Database for Cross-Platform

For cross-platform features (chat linking, participant sync), use the same database:

```env
# Both bots use the same database
MYSQL_DATABASE=futsal_bot
```

Bots are separated by `platform` field (`telegram` / `max`).

### Why Separate Virtual Environments?

- **Isolation**: Dependencies don't conflict between bots
- **Security**: Each bot runs in its own isolated Python environment
- **Updates**: Update one bot's dependencies without affecting the other
- **Deployment**: Deploy bots separately or together
- **Compliance**: Follows Python best practices and PEP 668

## 📚 Documentation

- **[Sport Event Bot Documentation](sport_event_bot/README.md)** - Telegram bot for event management
- **[MAX Sport Event Bot Documentation](max_sporteventbot/README.md)** - MAX Messenger bot for events
- **[Tournament Bot Documentation](tournament_bot/README.md)** - Tournament management
- **[Installation Guide](INSTALL.md)** - Step-by-step setup instructions
- **[Deployment Guide](DEPLOY.md)** - Production deployment with systemd

## 🛠️ Development

### Running as Python Modules

```bash
# Sport Event Bot
python3 -m sport_event_bot.bot

# Tournament Bot
python3 -m tournament_bot.bot
```

### Project Architecture

Each bot is a self-contained Python package:
- `__init__.py` - Package initialization
- `bot.py` - Main bot logic and handlers
- `db_*.py` - Database operations
- Configuration files in bot directory

### Adding New Bots

To add a new bot to the collection:
1. Create a new directory (e.g., `new_bot/`)
2. Add `__init__.py` and `bot.py`
3. Create `setup_venv.sh`, `run.sh` and `logs/` directory
4. Add startup script `run_new_bot.sh` in root
5. Add bot token variable to `.env.example`
6. Update this README

## 🤝 Integration

Both bots can run simultaneously:
- Use separate MySQL databases
- Use different bot tokens
- Independent message handlers
- No conflicts or dependencies

## 📝 Requirements

See [requirements.txt](requirements.txt) for full list of dependencies:
- python-telegram-bot >= 22.0
- mysql-connector-python
- loguru
- parsedatetime
- recurrent

## 🐛 Troubleshooting

### General Issues

- **Database connection fails**: Check MySQL credentials in `.env`
- **Bot doesn't start**: Verify TELEGRAM_BOT_TOKEN in `.env`
- **Permission errors**: Check file permissions with `chmod +x run_*.sh`

### Bot-Specific Issues

See individual bot documentation:
- [Sport Event Bot Troubleshooting](sport_event_bot/README.md#-troubleshooting)
- [Tournament Bot Troubleshooting](tournament_bot/README.md#-troubleshooting)

## 👥 Contributing

Contributions are welcome! To contribute:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is provided as-is for sports communities.

## 🙏 Credits

- **Sport Event Bot**: Originally created by KMiNT21 (2022), updated by wavcheb (2024)
- **Tournament Bot**: Created for sports communities (2025)
- **Project restructuring**: Organized into modular architecture (2025)

## 💬 Support

For bugs and feature requests:
- Open an issue on GitHub
- Check bot-specific documentation
- Review troubleshooting sections

---

**Ready to organize your sports events and tournaments? Get started with the [Installation Guide](INSTALL.md)! ⚽🏆**
