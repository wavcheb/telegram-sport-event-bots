#!/bin/bash
# Run MAX Sport Event Bot

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
BOT_DIR="$SCRIPT_DIR/max_sporteventbot"

# Create logs directory
mkdir -p "$BOT_DIR/logs"

# Activate virtual environment if exists
if [ -d "$BOT_DIR/venv" ]; then
    source "$BOT_DIR/venv/bin/activate"
elif [ -d "$SCRIPT_DIR/venv" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Note: .env is loaded by python-dotenv in bot.py
# No need to export here - avoids issues with special characters in passwords

# Change to bot directory and run
cd "$BOT_DIR"
exec python bot.py 2>&1 | tee -a "logs/systemd.log"
