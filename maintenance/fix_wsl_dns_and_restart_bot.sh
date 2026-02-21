#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[1/5] Configure /etc/wsl.conf to stop auto resolv.conf generation"
sudo cp /etc/wsl.conf /etc/wsl.conf.bak.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
sudo tee /etc/wsl.conf >/dev/null <<'EOF'
[boot]
systemd=true

[user]
default=mini

[network]
generateResolvConf=false
EOF

echo "[2/5] Replace /etc/resolv.conf with public DNS"
sudo rm -f /etc/resolv.conf
sudo tee /etc/resolv.conf >/dev/null <<'EOF'
nameserver 1.1.1.1
nameserver 8.8.8.8
options timeout:2 attempts:2 rotate
EOF
sudo chmod 644 /etc/resolv.conf

echo "[3/5] Verify DNS and Telegram API reachability"
getent hosts api.telegram.org || true
curl -I --max-time 8 https://api.telegram.org || true

echo "[4/5] Restart Telegram bot"
cd "$PROJECT_DIR"
pkill -f "run_telegram_bot.py" || true
nohup env PYTHONUNBUFFERED=1 ./venv/bin/python etc_scripts/run_telegram_bot.py > logs/telegram_bot.out 2>&1 &
sleep 3

echo "[5/5] Show bot process and recent logs"
if command -v rg >/dev/null 2>&1; then
  ps -ef | rg '[r]un_telegram_bot.py' || true
else
  ps -ef | grep -E '[r]un_telegram_bot.py' || true
fi
tail -n 80 logs/telegram_bot.out || true

echo
echo "If DNS still reverts, run 'wsl --shutdown' in Windows PowerShell, reopen WSL, then rerun this script."
