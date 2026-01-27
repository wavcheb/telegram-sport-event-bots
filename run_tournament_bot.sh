#!/bin/bash
# Tournament Bot Startup Script

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "tournament_bot/venv" ]; then
    echo "❌ Error: Virtual environment not found!"
    echo "Please run: cd tournament_bot && ./setup_venv.sh"
    exit 1
fi

# Activate virtual environment
source tournament_bot/venv/bin/activate

# Run the tournament bot
echo "🚀 Starting Tournament Bot..."
python -m tournament_bot.bot "$@"
