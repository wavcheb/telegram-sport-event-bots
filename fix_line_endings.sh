#!/bin/bash
# Script to fix line endings for all shell scripts
# Run this if you get "cannot execute: required file not found" error

echo "🔧 Fixing line endings in shell scripts..."

# Check if dos2unix is available
if ! command -v dos2unix &> /dev/null; then
    echo "📦 dos2unix not found. Installing..."

    # Detect package manager
    if command -v apt &> /dev/null; then
        sudo apt update && sudo apt install -y dos2unix
    elif command -v yum &> /dev/null; then
        sudo yum install -y dos2unix
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y dos2unix
    else
        echo "❌ Could not install dos2unix automatically."
        echo "Please install it manually and run this script again."
        exit 1
    fi
fi

# Fix line endings
echo "🔄 Converting line endings to Unix format (LF)..."
find . -name "*.sh" -type f -exec dos2unix {} \; 2>/dev/null

# Make scripts executable
echo "🔐 Setting executable permissions..."
chmod +x setup_all.sh run_*.sh 2>/dev/null
chmod +x sport_event_bot/setup_venv.sh tournament_bot/setup_venv.sh 2>/dev/null

echo "✅ Done! Line endings fixed."
echo ""
echo "You can now run:"
echo "  ./setup_all.sh"
