#!/usr/bin/env python3
"""간단한 봇 상태 대시보드"""
import os
import json
import time
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)

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
