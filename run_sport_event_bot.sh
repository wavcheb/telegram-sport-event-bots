#!/bin/bash
# Sport Event Bot Startup Script

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Error: Virtual environment not found!"
    echo "Please run: ./setup.sh"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

# Run the sport event bot
echo "🚀 Starting Sport Event Bot..."
python -m sport_event_bot.bot "$@"
