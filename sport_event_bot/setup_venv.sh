#!/bin/bash
# Setup script for Sport Event Bot virtual environment

set -e

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BOT_DIR"

echo "🔧 Setting up Sport Event Bot environment..."

# Check if python3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed"
    exit 1
fi

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "📚 Installing dependencies..."
if [ -f "../requirements.txt" ]; then
    pip install -r ../requirements.txt
else
    echo "❌ Error: requirements.txt not found"
    exit 1
fi

echo "✅ Sport Event Bot environment setup complete!"
echo ""
echo "To activate the environment, run:"
echo "  source $BOT_DIR/venv/bin/activate"
