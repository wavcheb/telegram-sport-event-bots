#!/bin/bash
# Setup script for the Sport Event Bot

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "🚀 Setting up Sport Event Bot"
echo "=============================="
echo ""

# Check if python3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed"
    echo "On Ubuntu/Debian, install with: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv and install dependencies
echo "📥 Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "📝 Next steps:"
echo "1. Configure environment:"
echo "   cp .env.example .env"
echo "   nano .env (Add your TELEGRAM_BOT_TOKEN)"
echo ""
echo "2. Run the bot:"
echo "   source venv/bin/activate"
echo "   python3 -m sport_event_bot.bot"
echo ""
echo "For production deployment (Render/OCI), see INSTRUCTIONS.md"
