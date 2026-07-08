# ⚽ Sport Event Bot

Telegram bot for organizing sports events (any game such as football, volleyball, poker etc.) with participant registration, payment tracking, and attendance statistics.

## 🌟 Features

- **Event Management**: Create, update, and close events with automatic date/time parsing
- **Participant Registration**: Users can register/unregister for events with one click
- **Player Limits**: Set maximum participants with automatic reserve list
- **Guest Players**: Add legionnaire/guest players who aren't in the chat
- **Payment Tracking**: Track who has paid with 💰 emoji indicator
- **Payment Link**: Embed payment URL in event - shown as inline button
- **Payment Log**: Auto-published to Telegraph page, updated after each payment (or to your own page via `PAYMENTS_PAGE_URL`)
- **Attendance Statistics**: Track registrations and penalties for no-shows
- **Multi-language Support**: Russian, Ukrainian, Portuguese, Arabic, and English
- **Interactive Buttons**: Inline keyboard for quick actions
- **Cross-Platform MAX Sync**: Link chats with MAX Sport Event Bot (`/link`, `/unlink`); set `MAX_BOT_TOKEN` in `.env` for real-time updates of linked MAX chat messages
- **Blocked Regions Support**: Access Telegram API via a Cloudflare Worker proxy (`TG_API_URL`) or a SOCKS/HTTP proxy (`TELEGRAM_PROXY`)

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

The easiest way — use the setup script (creates a virtual environment and installs everything):

```bash
cd sport_event_bot
./setup_venv.sh
```

Or manually:

```bash
cd sport_event_bot
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

Database credentials are configured in `.env` file (see Step 4).

The bot will automatically create tables on first run.

### 4. Configure Environment

Create `.env` file from template inside the `sport_event_bot/` directory:

```bash
cd sport_event_bot   # if not already there
cp .env.example .env
nano .env
```

Set your values:

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
MYSQL_HOST=localhost
MYSQL_DATABASE=futsal_bot
MYSQL_USER=futsal_bot
MYSQL_PASSWORD=your_password_here
```

Get your token from [@BotFather](https://t.me/botfather):
1. Send `/newbot` to BotFather
2. Follow instructions to create your bot
3. Copy the token to `.env` file

Secure the file:
```bash
chmod 600 .env
```

### 5. Run the Bot

```bash
./run.sh
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
- `/payments` - Show payment log (published to Telegraph)

**Payment URL support**: Include a URL in `/event_add` text and it will be extracted as a payment link button:
```
/event_add Football Saturday 18:00 https://send.monobank.ua/jar/xxx
```
This creates an event with description "Football Saturday 18:00" and shows a 💳 Payment link button.

### Statistics & Administration

- `/stat` - Show statistics for all chat members (registrations/penalties)
- `/fix` - Finalize event and increment attendance counters
- `/penalty USERID` - Add penalty for no-show without notification
  - Find USERID using `/stat` command
  - Example: `/penalty 123456789`

- `/info` - Show current event details
- `/help` - Show list of available commands

### Cross-Platform Chat Linking

- `/link` - Link this Telegram chat with a MAX Messenger chat (generates a secret code to enter in the MAX bot)
- `/unlink` - Unlink the chat

## 🗄️ Database Schema

The bot uses MySQL with 9 tables:

- **Users**: User profiles (id, first_name, last_name, username)
- **Chats**: Chat/group information and latest bot message
- **Events**: Event details (description, datetime, player limit, status)
- **Participants**: Event registrations with payment status
- **Revoked**: Cancelled registrations history
- **Penalties**: Penalty tracking table
- **PaymentLog**: Payment confirmation log
- **ChatLinks**: Cross-platform (Telegram ↔ MAX) chat links
- **EventLinks**: Cross-platform event links

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
sport_event_bot/              # Self-contained Sport Event Bot
├── __init__.py              # Package initialization
├── bot.py                   # Main bot logic and handlers
├── db_mysql.py              # Database operations
├── telegraph.py             # Telegraph API for payment logs
├── .env.example             # Environment config template
├── .env                     # Your config (create from .env.example)
├── requirements.txt         # Python dependencies
├── run.sh                   # Run script
├── setup_venv.sh            # Virtual environment setup
├── sport-event-bot.service       # Systemd system service
├── sport-event-bot-user.service  # Systemd user service
├── babel.cfg                # Babel configuration for i18n
├── messages.pot             # Translation template
├── locale/                  # Translation files
│   ├── ar/                 # Arabic translations
│   ├── pt/                 # Portuguese translations
│   ├── ru/                 # Russian translations
│   └── uk/                 # Ukrainian translations
├── logs/                    # Log files (created at runtime)
└── README.md                # This file
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
- Verify bot token is correct in `sport_event_bot/.env` (`TELEGRAM_BOT_TOKEN`); `token.txt` is a legacy fallback used only when the env variable is not set
- Ensure bot is added to the group and has admin rights

### Database connection errors

- Verify MySQL is running: `systemctl status mysql`
- Check credentials in `sport_event_bot/.env`
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
