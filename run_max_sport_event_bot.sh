#!/bin/bash
# Run MAX Sport Event Bot

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
BOT_DIR="$SCRIPT_DIR/max_sporteventbot"

# Activate virtual environment if exists
if [ -d "$BOT_DIR/venv" ]; then
    source "$BOT_DIR/venv/bin/activate"
elif [ -d "$SCRIPT_DIR/venv" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

# Load environment variables from .env if exists
if [ -f "$BOT_DIR/.env" ]; then
    export $(grep -v '^#' "$BOT_DIR/.env" | xargs)
elif [ -f "$SCRIPT_DIR/.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
fi

# Change to parent directory (to allow module import) and run
cd "$SCRIPT_DIR"
exec python max_sporteventbot/bot.py 2>&1 | tee -a "$BOT_DIR/logs/systemd.log"
