#!/bin/bash
# 24시간 안정성 보장을 위한 모니터링 시스템 설정

echo "🛡️ 24시간 텔레그램 봇 안정성 보장 시스템 설정"
echo "=================================================="

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo ""
echo "1️⃣ 로그 디렉토리 생성..."
mkdir -p logs

echo ""
echo "2️⃣ 크론잡 설정..."
echo "기존 크론잡 백업..."
crontab -l > crontab_backup_$(date +%Y%m%d_%H%M%S).txt 2>/dev/null || echo "기존 크론잡 없음"

echo "새 모니터링 크론잡 추가..."
(crontab -l 2>/dev/null; cat << EOF
# 네이버 포스트 텔레그램 봇 24시간 안정성 모니터링

# 5분마다 봇 헬스체크
*/5 * * * * cd $PROJECT_ROOT && python3 etc_scripts/monitor_bot_health.py --one-shot >> logs/health_check.log 2>&1

# 1시간마다 DNS 헬스체크
0 * * * * cd $PROJECT_ROOT && python3 etc_scripts/fix_dns_issues.py --diagnose-only >> logs/dns_check.log 2>&1

# 매일 새벽 2시 종합 점검
0 2 * * * cd $PROJECT_ROOT && python3 etc_scripts/test_stabilization_system.py --quick >> logs/daily_check.log 2>&1

# 매주 월요일 새벽 3시 전체 시스템 테스트
0 3 * * 1 cd $PROJECT_ROOT && python3 etc_scripts/test_stabilization_system.py >> logs/weekly_test.log 2>&1

# 로그 로테이션 (매일 새벽 1시)
0 1 * * * find $PROJECT_ROOT/logs -name "*.log" -mtime +7 -delete
EOF
) | crontab -

echo "크론잡 설정 완료!"
echo ""
echo "설정된 크론잡:"
crontab -l | grep -A 20 "네이버 포스트"

echo ""
echo "3️⃣ 로그로테이트 설정..."
sudo tee /etc/logrotate.d/naverpost-bot << EOF
$PROJECT_ROOT/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 mini mini
}
EOF

echo ""
echo "4️⃣ 시스템 모니터링 대시보드 생성..."
cat << 'EOF' > etc_scripts/dashboard.py
#!/usr/bin/env python3
"""간단한 봇 상태 대시보드"""
import json
import time
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def get_service_status():
    try:
        result = subprocess.run(['systemctl', 'is-active', 'naverpost-bot.service'],
                              capture_output=True, text=True)
        return result.stdout.strip()
    except:
        return "unknown"

def get_recent_logs():
    try:
        result = subprocess.run(['journalctl', '-u', 'naverpost-bot.service', '--since', '10 minutes ago', '-n', '5'],
                              capture_output=True, text=True)
        return result.stdout
    except:
        return "로그를 가져올 수 없습니다."

def main():
    print("🤖 네이버 포스트 텔레그램 봇 대시보드")
    print("=" * 50)

    status = get_service_status()
    status_emoji = "✅" if status == "active" else "❌"

    print(f"서비스 상태: {status_emoji} {status}")
    print(f"현재 시간: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 헬스체크 로그 확인
    health_log = PROJECT_ROOT / "logs" / "health_check.log"
    if health_log.exists():
        with open(health_log) as f:
            lines = f.readlines()
            recent_lines = lines[-5:] if lines else []
            print(f"\n📊 최근 헬스체크 (최근 5개):")
            for line in recent_lines:
                print(f"  {line.strip()}")

    print(f"\n📝 최근 로그:")
    recent_logs = get_recent_logs()
    for line in recent_logs.split('\n')[-5:]:
        if line.strip():
            print(f"  {line}")

    print(f"\n🔧 유용한 명령어:")
    print(f"  상태 확인: sudo systemctl status naverpost-bot.service")
    print(f"  재시작: sudo systemctl restart naverpost-bot.service")
    print(f"  실시간 로그: sudo journalctl -u naverpost-bot.service -f")
    print(f"  헬스체크: python3 etc_scripts/monitor_bot_health.py --one-shot")

if __name__ == "__main__":
    main()
EOF

chmod +x etc_scripts/dashboard.py

echo ""
echo "5️⃣ 알림 시스템 설정 (슬랙 웹훅 - 선택사항)..."
cat << 'EOF' > etc_scripts/send_alert.py
#!/usr/bin/env python3
"""봇 상태 알림 시스템 (슬랙/이메일)"""
import json
import requests
import os
from datetime import datetime

# 설정 (.env 파일에서 읽기)
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')  # 슬랙 웹훅 URL
ALERT_EMAIL = os.getenv('ALERT_EMAIL')  # 알림 이메일

def send_slack_alert(message, emoji="🤖", severity="warning"):
    """슬랙 알림 전송"""
    if not SLACK_WEBHOOK_URL:
        return

    color = {
        "error": "#ff0000",    # 빨간색
        "warning": "#ffaa00",  # 주황색
        "success": "#00ff00",  # 초록색
    }.get(severity, "#ffaa00")

    payload = {
        "text": f"{emoji} 네이버 포스트 봇 알림",
        "attachments": [{
            "color": color,
            "fields": [{
                "title": "상태",
                "value": message,
                "short": False
            }, {
                "title": "시간",
                "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "short": True
            }]
        }]
    }

    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        return response.status_code == 200
    except:
        return False

def send_bot_down_alert():
    """봇 다운 알림"""
    message = "⚠️ 텔레그램 봇이 다운되었습니다. 자동 재시작을 시도합니다."
    send_slack_alert(message, "🚨", "error")

def send_bot_restart_alert():
    """봇 재시작 알림"""
    message = "✅ 텔레그램 봇이 재시작되었습니다."
    send_slack_alert(message, "🔄", "success")

def send_health_alert(issues):
    """헬스체크 이슈 알림"""
    message = f"⚠️ 봇 헬스체크 이슈 발견:\n" + "\n".join(f"• {issue}" for issue in issues)
    send_slack_alert(message, "🏥", "warning")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        alert_type = sys.argv[1]
        if alert_type == "down":
            send_bot_down_alert()
        elif alert_type == "restart":
            send_bot_restart_alert()
        elif alert_type == "test":
            send_slack_alert("테스트 알림입니다.", "🧪", "success")
EOF

chmod +x etc_scripts/send_alert.py

echo ""
echo "✅ 24시간 안정성 보장 시스템 설정 완료!"
echo ""
echo "📊 사용 가능한 명령어:"
echo "  대시보드 보기: python3 etc_scripts/dashboard.py"
echo "  헬스체크: python3 etc_scripts/monitor_bot_health.py --one-shot"
echo "  테스트 알림: python3 etc_scripts/send_alert.py test"
echo ""
echo "📁 로그 파일들:"
echo "  헬스체크: logs/health_check.log"
echo "  DNS 체크: logs/dns_check.log"
echo "  일일 점검: logs/daily_check.log"
echo "  주간 테스트: logs/weekly_test.log"
echo ""
echo "🔔 슬랙 알림을 원하면 .env 파일에 SLACK_WEBHOOK_URL을 추가하세요"
