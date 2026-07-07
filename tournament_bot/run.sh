#!/bin/bash
# Standalone run script for Tournament Bot

set -e

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BOT_DIR"

mkdir -p logs

if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d "../venv" ]; then
    source ../venv/bin/activate
else
    echo "Warning: No virtual environment found. Using system Python."
fi

echo "Starting Tournament Bot..."
exec python bot.py "$@"
