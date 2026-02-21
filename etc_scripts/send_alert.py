#!/usr/bin/env python3
"""봇 상태 알림 시스템 (슬랙/이메일)"""
import json
import requests
import os
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)

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
