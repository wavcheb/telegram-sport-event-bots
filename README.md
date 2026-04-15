# ⚽ Sport Event Bot

A Telegram bot for organizing sports events and tournaments with participant registration, payment tracking, and statistics.

Originally created by KMiNT21 (2022), updated by wavcheb (2024), and refactored for PostgreSQL (2025).

## 🚀 Quick Start

1.  **Clone the repository**:
    ```bash
    git clone <your-repo-url>
    cd tg-sport-event-bot
    ```

2.  **Configure `.env`**:
    ```bash
    cp .env.example .env
    # Add your TELEGRAM_BOT_TOKEN
    ```

3.  **Setup & Run**:
    ```bash
    ./setup.sh
    python3 -m sport_event_bot.bot
    ```

For detailed instructions on production deployment (Render, OCI, AWS), see [INSTRUCTIONS.md](INSTRUCTIONS.md).

## 📦 Features
- **Event management**: Date/time parsing for future matches.
- **Participant registration**: Interactive inline buttons for (+) Apply and (-) Revoke.
- **Payment tracking**: Confirm payments with a 💰 emoji.
- **Multi-language support**: RU, UK, PT, AR, EN.
- **PostgreSQL**: Native support for Neon.tech.

## 📁 Project Structure
- `sport_event_bot/`: Core bot package.
- `requirements.txt`: Python package dependencies.
- `.env.example`: Configuration template.
- `INSTRUCTIONS.md`: Detailed setup and deployment guide.

## 🤝 Support
For bugs and feature requests, open an issue on GitHub.
