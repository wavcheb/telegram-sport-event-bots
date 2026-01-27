# ⚽ Sport Event Bot

Telegram bot for organizing sports events (football/futsal) with participant registration, payment tracking, and attendance statistics.

## 🌟 Features

- **Event Management**: Create, update, and close events with automatic date/time parsing
- **Participant Registration**: Users can register/unregister for events with one click
- **Player Limits**: Set maximum participants with automatic reserve list
- **Guest Players**: Add legionnaire/guest players who aren't in the chat
- **Payment Tracking**: Track who has paid with 💰 emoji indicator
- **Attendance Statistics**: Track registrations and penalties for no-shows
- **Multi-language Support**: Russian, Ukrainian, Portuguese, Arabic, and English
- **Interactive Buttons**: Inline keyboard for quick actions

## 📋 Requirements

- Python 3.11+
- MySQL 5.7+ or MariaDB 10.3+
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/wavcheb/telegram-sport-event-bots.git
cd telegram-sport-event-bots
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

Or using virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Database

Create MySQL database and user:

```sql
CREATE DATABASE futsal_bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'futsal_bot'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON futsal_bot.* TO 'futsal_bot'@'localhost';
FLUSH PRIVILEGES;
```

Update database credentials in `sport_event_bot/db_mysql.py`:

```python
MYSQL_CFG = {
    'host': 'localhost',
    'database': 'futsal_bot',
    'user': 'futsal_bot',
    'password': 'your_password',
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci',
}
```

The bot will automatically create tables on first run.

### 4. Configure Bot Token

Create `sport_event_bot/token.txt` file with your Telegram Bot Token:

```bash
echo "YOUR_BOT_TOKEN" > sport_event_bot/token.txt
```

Get your token from [@BotFather](https://t.me/botfather):
1. Send `/newbot` to BotFather
2. Follow instructions to create your bot
3. Copy the token and save it to `sport_event_bot/token.txt`

### 5. Run the Bot

```bash
./run_sport_event_bot.sh
```

Or directly with Python:
```bash
python3 -m sport_event_bot.bot
```

The bot will start and show:
```
INFO     | __main__:main:622 - Telegram Futsal Bot is starting...
INFO     | __main__:main:626 - Bot is running...
```

## 📖 Bot Commands

### Event Management

- `/event_add TEXT` - Create new event with description
  - Example: `/event_add Football tomorrow at 18:00, max 14 players`
  - Supports natural language date parsing
  - Can specify player limit in description

- `/event_remove` - Close the current event

- `/event_update TEXT` - Change event description

- `/event_datetime DATE TIME` - Set/update event date and time
  - Example: `/event_datetime 2024-01-30 18:00`
  - Example: `/event_datetime tomorrow 14:30`

- `/limit NUMBER` - Set maximum number of players
  - Example: `/limit 14`

### Participation

- `/add` or click **+ Apply for participation** button
- `/remove` or click **- Revoke application** button
- `/add_leg` or click **+ Apply friend or legioneer** - Add guest player
- `/rem_leg` or click **- Remove last friend or legioneer** - Remove guest player

### Payment

- `/pay` or click **💰 Payment confirmed** button - Mark payment as confirmed
- Only registered participants can confirm payment

### Statistics & Administration

- `/stat` - Show statistics for all chat members (registrations/penalties)
- `/fix` - Finalize event and increment attendance counters
- `/penalty USERID` - Add penalty for no-show without notification
  - Find USERID using `/stat` command
  - Example: `/penalty 123456789`

- `/info` - Show current event details
- `/help` - Show list of available commands

## 🗄️ Database Schema

The bot uses MySQL with 5 main tables:

- **Users**: User profiles (id, first_name, last_name, username)
- **Chats**: Chat/group information and latest bot message
- **Events**: Event details (description, datetime, player limit, status)
- **Participants**: Event registrations with payment status
- **Revoked**: Cancelled registrations history
- **Penalties**: Penalty tracking table

## 🌍 Supported Languages

- 🇷🇺 Russian (ru)
- 🇺🇦 Ukrainian (uk)
- 🇧🇷 Portuguese (pt-br)
- 🇸🇦 Arabic (ar)
- 🇬🇧 English (en) - default

Language is detected automatically from user's Telegram settings.

## 🛠️ Development

### Project Structure

```
telegram-sport-event-bots/
├── sport_event_bot/          # Sport Event Bot module
│   ├── __init__.py          # Package initialization
│   ├── bot.py               # Main bot logic and handlers
│   ├── db_mysql.py          # Database operations
│   ├── token.txt            # Bot token (create this)
│   ├── token.txt.example    # Token file template
│   ├── babel.cfg            # Babel configuration for i18n
│   ├── messages.pot         # Translation template
│   ├── locale/              # Translation files
│   │   ├── ar/             # Arabic translations
│   │   ├── pt/             # Portuguese translations
│   │   ├── ru/             # Russian translations
│   │   └── ua/             # Ukrainian translations
│   └── logs/                # Log files
├── tournament_bot/           # Tournament Bot module
│   ├── __init__.py          # Package initialization
│   ├── bot.py               # Main bot logic
│   ├── db_tournament.py     # Database operations
│   ├── tournament_logic.py  # Tournament algorithms
│   ├── token.txt            # Bot token (create this)
│   ├── token.txt.example    # Token file template
│   └── logs/                # Log files
├── run_sport_event_bot.sh   # Sport Event Bot startup script
├── run_tournament_bot.sh    # Tournament Bot startup script
├── requirements.txt          # Python dependencies
├── README.md                # Sport Event Bot documentation
└── README_TOURNAMENT.md     # Tournament Bot documentation
```

### Adding New Translations

1. Extract translatable strings:
```bash
pybabel extract -F babel.cfg -o messages.pot .
```

2. Create new language:
```bash
pybabel init -i messages.pot -d locale -l fr
```

3. Update existing translations:
```bash
pybabel update -i messages.pot -d locale
```

4. Compile translations:
```bash
pybabel compile -d locale
```

## 🐛 Troubleshooting

### Bot doesn't respond

- Check if bot is running: `ps aux | grep sport_event_bot`
- Check logs: `tail -f sport_event_bot/logs/logs.log`
- Verify bot token is correct in `sport_event_bot/token.txt`
- Ensure bot is added to the group and has admin rights

### Database connection errors

- Verify MySQL is running: `systemctl status mysql`
- Check credentials in `sport_event_bot/db_mysql.py`
- Ensure database and user exist
- Test connection: `mysql -u futsal_bot -p futsal_bot`

### "Column 'event_id' cannot be null" error

This was fixed in recent updates. Make sure you're using the latest version:
```bash
git pull origin main
```

### Language detection issues

If users see wrong language:
- Bot uses Telegram's `language_code` from user profile
- Default fallback is Russian (can be changed in code)
- English users see original text (no translation needed)

## 📝 Recent Fixes

**Version 2.0 (January 2025)**:
- ✅ Fixed "Column 'event_id' cannot be null" errors
- ✅ Fixed "Data truncated for column datetime" errors
- ✅ Fixed "invalid literal for int()" in penalty command
- ✅ Improved datetime handling (uses current time when parsing fails)
- ✅ Fixed language detection (handles None values)
- ✅ Reduced log spam (filters user messages, handles English properly)

## 👥 Contributing

Pull requests are welcome! For major changes, please open an issue first.

## 📄 License

This project is provided as-is for sports communities.

## 🙏 Credits

- Originally created by KMiNT21 (2022)
- Updated by wavcheb (2024)
- Refactored and improved by Grok (2025)

## 💬 Support

For bugs and feature requests, please open an issue on GitHub.

---

**Enjoy organizing your sports events! ⚽🏆**
