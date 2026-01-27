#!/bin/bash
# Setup script for all bots

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🚀 Setting up telegram-sport-event-bots Project"
echo "================================="
echo ""

# Check if python3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed"
    echo "Install it with: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

# Setup Sport Event Bot
echo "1️⃣  Setting up Sport Event Bot..."
cd "$PROJECT_DIR/sport_event_bot"
if [ ! -f "setup_venv.sh" ]; then
    echo "❌ Error: setup_venv.sh not found in sport_event_bot/"
    exit 1
fi
chmod +x setup_venv.sh
./setup_venv.sh
echo ""

# Setup Tournament Bot
echo "2️⃣  Setting up Tournament Bot..."
cd "$PROJECT_DIR/tournament_bot"
if [ ! -f "setup_venv.sh" ]; then
    echo "❌ Error: setup_venv.sh not found in tournament_bot/"
    exit 1
fi
chmod +x setup_venv.sh
./setup_venv.sh
echo ""

cd "$PROJECT_DIR"

echo "✅ All bots setup complete!"
echo ""
echo "📝 Next steps:"
echo "1. Configure database credentials:"
echo "   - sport_event_bot/db_mysql.py"
echo "   - tournament_bot/db_tournament.py"
echo ""
echo "2. Add bot tokens:"
echo "   - sport_event_bot/token.txt"
echo "   - tournament_bot/token.txt"
echo ""
echo "3. Run bots:"
echo "   ./run_sport_event_bot.sh"
echo "   ./run_tournament_bot.sh"
