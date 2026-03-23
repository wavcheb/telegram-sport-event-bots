#!/bin/bash
# Standalone run script for MAX Sport Event Bot
# Works when the bot is installed in a separate directory (e.g., /usr/local/maxbot/sporteventbot)

set -e

# Get the directory where this script is located
BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BOT_DIR"

# Create logs directory if not exists
mkdir -p logs

# Check for virtual environment (in current dir or parent)
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d "../venv" ]; then
    source ../venv/bin/activate
else
    echo "Warning: No virtual environment found. Using system Python."
fi

# Load environment variables from .env (in current dir or parent)
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
elif [ -f "../.env" ]; then
    set -a
    source ../.env
    set +a
fi

echo "Starting MAX Sport Event Bot..."
exec python bot.py "$@"
