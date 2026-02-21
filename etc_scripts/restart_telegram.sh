#!/usr/bin/env bash
set -euo pipefail

SERVICE="naverpost-bot.service"

echo "[restart_telegram] restarting: ${SERVICE}"
if ! sudo -n true 2>/dev/null; then
  echo "[restart_telegram] WARN: sudo requires password. Configure sudoers NOPASSWD for systemctl restart ${SERVICE}"
fi

sudo systemctl restart "${SERVICE}"

echo "[restart_telegram] checking status..."
sudo systemctl is-active --quiet "${SERVICE}"

echo "[restart_telegram] OK: ${SERVICE} is active"
