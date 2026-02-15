#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/mini/dev/naverPost"
LOG_FILE="$PROJECT_DIR/logs/telegram_bot.out"
PYTHON_BIN="$PROJECT_DIR/venv/bin/python3"

cd "$PROJECT_DIR"
mkdir -p logs

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[ERROR] Python venv not found: $PYTHON_BIN"
  exit 1
fi

echo "[1/3] Stop existing telegram bot process"
pkill -f "[r]un_telegram_bot.py" || true
sleep 1

echo "[2/3] Start telegram bot with venv python"
nohup env PYTHONUNBUFFERED=1 "$PYTHON_BIN" run_telegram_bot.py >"$LOG_FILE" 2>&1 &
sleep 2

echo "[3/3] Process/Log check"
ps -ef | rg "[r]un_telegram_bot.py" || true
tail -n 80 "$LOG_FILE" || true

echo
echo "[diag] DNS check for Telegram API"
getent hosts api.telegram.org || echo "DNS lookup failed: api.telegram.org"
