#!/bin/bash
set -e

echo "🚀 네이버 포스트 텔레그램 봇 긴급 복구 시작"
echo "==============================================="

# 현재 디렉토리 확인
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo ""
echo "1️⃣ 현재 상태 확인..."
echo "Current directory: $(pwd)"
echo "Service status:"
systemctl status naverpost-bot.service --no-pager || true

echo ""
echo "2️⃣ 서비스 중지 및 초기화..."
sudo systemctl stop naverpost-bot.service || true
sudo systemctl disable naverpost-bot.service || true

echo ""
echo "3️⃣ 의존성 설치..."
echo "Installing Python dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install dnspython==2.4.2
pip install playwright aiofiles aiohttp pydantic>=2.0.0
pip install python-telegram-bot>=20.0.0

echo ""
echo "4️⃣ Playwright 브라우저 설치..."
playwright install chromium

echo ""
echo "5️⃣ 권한 설정..."
chmod +x etc_scripts/start_bot_with_health_check.py
chmod +x etc_scripts/fix_dns_issues.py
chmod +x etc_scripts/run_telegram_bot.py

echo ""
echo "6️⃣ DNS 헬스체크..."
echo "Checking DNS health..."
python etc_scripts/fix_dns_issues.py --diagnose-only || true

echo ""
echo "7️⃣ 서비스 파일 업데이트..."
sudo cp etc_scripts/naverpost-bot-fixed.service /etc/systemd/system/naverpost-bot.service
sudo systemctl daemon-reload

echo ""
echo "8️⃣ 서비스 활성화 및 시작..."
sudo systemctl enable naverpost-bot.service
sudo systemctl start naverpost-bot.service

echo ""
echo "9️⃣ 상태 확인..."
sleep 5
sudo systemctl status naverpost-bot.service --no-pager

echo ""
echo "🔟 로그 확인..."
echo "Recent logs:"
sudo journalctl -u naverpost-bot.service --since "1 minute ago" -n 10

echo ""
echo "✅ 복구 완료! 봇 상태를 확인해주세요."
echo ""
echo "📊 추가 모니터링 명령어:"
echo "  - 실시간 로그: sudo journalctl -u naverpost-bot.service -f"
echo "  - 상태 확인: sudo systemctl status naverpost-bot.service"
echo "  - 재시작: sudo systemctl restart naverpost-bot.service"
