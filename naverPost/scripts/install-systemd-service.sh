#!/bin/bash
# Installation script for naverPost Telegram Bot systemd service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_FILE="naverpost-bot.service"

echo "🤖 Installing naverPost Telegram Bot systemd service..."

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    echo "❌ Please do not run this script as root. Run with regular user."
    exit 1
fi

# Check if service file exists
if [[ ! -f "$SCRIPT_DIR/$SERVICE_FILE" ]]; then
    echo "❌ Service file not found: $SCRIPT_DIR/$SERVICE_FILE"
    exit 1
fi

# Check if project directory has correct structure
if [[ ! -f "$PROJECT_DIR/run_telegram_bot.py" ]]; then
    echo "❌ Project structure invalid. run_telegram_bot.py not found in $PROJECT_DIR"
    exit 1
fi

# Update service file with correct paths and user
TEMP_SERVICE="/tmp/$SERVICE_FILE.tmp"
sed "s|/home/mini/dev/naverPost|$PROJECT_DIR|g" "$SCRIPT_DIR/$SERVICE_FILE" > "$TEMP_SERVICE"
sed -i "s|User=mini|User=$USER|g" "$TEMP_SERVICE"
sed -i "s|Group=mini|Group=$USER|g" "$TEMP_SERVICE"

echo "📋 Service configuration:"
echo "   Project directory: $PROJECT_DIR"
echo "   User: $USER"
echo "   Service file: $SERVICE_FILE"

# Install service file
echo "🔧 Installing service file..."
sudo cp "$TEMP_SERVICE" "/etc/systemd/system/$SERVICE_FILE"
rm "$TEMP_SERVICE"

# Reload systemd
echo "🔄 Reloading systemd..."
sudo systemctl daemon-reload

# Enable service
echo "✅ Enabling service..."
sudo systemctl enable "$SERVICE_FILE"

echo ""
echo "🎉 Installation completed!"
echo ""
echo "Commands to manage the service:"
echo "   Start:   sudo systemctl start naverpost-bot"
echo "   Stop:    sudo systemctl stop naverpost-bot"
echo "   Status:  sudo systemctl status naverpost-bot"
echo "   Logs:    sudo journalctl -u naverpost-bot -f"
echo "   Restart: sudo systemctl restart naverpost-bot"
echo ""
echo "To start the service now:"
echo "   sudo systemctl start naverpost-bot"