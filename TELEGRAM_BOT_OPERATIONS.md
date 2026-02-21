# 🤖 텔레그램 봇 24시간 안정 운영 가이드

## 🚀 일상적인 모니터링 명령어

### 빠른 상태 확인
```bash
# 📊 통합 대시보드
python3 etc_scripts/dashboard.py

# ⚡ 봇 헬스체크
python3 etc_scripts/monitor_bot_health.py --one-shot

# 🔍 서비스 상태
sudo systemctl status naverpost-bot.service
```

### 실시간 모니터링
```bash
# 📝 실시간 로그
sudo journalctl -u naverpost-bot.service -f

# 📈 시스템 리소스 모니터링
top -p $(pgrep -f naverpost)

# 🌐 네트워크 연결 확인
ss -tulpn | grep python
```

## 🛠️ 문제 해결 명령어

### 일반적인 재시작
```bash
# 🔄 서비스 재시작
sudo systemctl restart naverpost-bot.service

# 📊 재시작 후 상태 확인 (5초 대기)
sleep 5 && sudo systemctl status naverpost-bot.service
```

### DNS 문제 해결
```bash
# 🔍 DNS 진단
python3 etc_scripts/fix_dns_issues.py --diagnose-only

# 🛠️ DNS 자동 복구
python3 etc_scripts/fix_dns_issues.py

# 🧪 DNS 헬스 테스트
python3 -c "
import asyncio
from src.utils.dns_health_checker import check_dns_health
result = asyncio.run(check_dns_health())
print('DNS OK:', result)
"
```

### 메모리/성능 문제
```bash
# 📊 메모리 사용량 확인
ps aux | grep telegram | head -5

# 🧹 시스템 정리
sudo systemctl daemon-reload
sudo systemctl reset-failed naverpost-bot.service

# 🚀 완전 재시작 (서비스 + 의존성)
sudo systemctl stop naverpost-bot.service
sleep 3
sudo systemctl start naverpost-bot.service
```

### 로그 분석
```bash
# ⚠️ 최근 에러 로그 확인
sudo journalctl -u naverpost-bot.service --since "1 hour ago" | grep -E "(ERROR|CRITICAL|Exception)"

# 📅 특정 날짜 로그
sudo journalctl -u naverpost-bot.service --since "2024-02-15 09:00" --until "2024-02-15 10:00"

# 📊 로그 통계
sudo journalctl -u naverpost-bot.service --since today | grep -c "ERROR"
```

## 📋 정기적인 유지보수

### 일일 점검 (매일 아침 권장)
```bash
# 📊 대시보드 확인
python3 etc_scripts/dashboard.py

# 🏥 헬스체크 리포트
python3 etc_scripts/monitor_bot_health.py --one-shot

# 📁 로그 파일 크기 확인
du -sh logs/*.log 2>/dev/null || echo "로그 파일 없음"
```

### 주간 점검 (매주 월요일 권장)
```bash
# 🧪 전체 시스템 테스트
python3 etc_scripts/test_stabilization_system.py --quick

# 🔄 서비스 설정 리로드
sudo systemctl daemon-reload

# 📊 지난 주 통계
sudo journalctl -u naverpost-bot.service --since "7 days ago" | grep -c "Started\|Stopped"
```

### 월간 정기보수
```bash
# 📦 의존성 업데이트
source venv/bin/activate && pip list --outdated

# 🧹 오래된 로그 정리
find logs/ -name "*.log" -mtime +30 -delete

# 💾 설정 백업
cp etc_scripts/naverpost-bot-fixed.service "backups/naverpost-bot-$(date +%Y%m%d).service"
```

## 🚨 응급 상황 대응

### 봇이 완전히 응답하지 않을 때
```bash
echo "🚨 응급 복구 시퀀스 시작..."

# 1. 서비스 강제 중지
sudo systemctl kill naverpost-bot.service
sudo systemctl stop naverpost-bot.service

# 2. 프로세스 완전 종료
pkill -f "telegram\|naverpost" || true

# 3. DNS 및 네트워크 복구
python3 etc_scripts/fix_dns_issues.py

# 4. 서비스 재시작
sudo systemctl start naverpost-bot.service

# 5. 상태 확인
sleep 10
python3 etc_scripts/dashboard.py
```

### 메모리 누수 의심시
```bash
# 📊 메모리 사용량 모니터링 (1분간)
for i in {1..6}; do
    echo "$(date): $(ps aux | grep -E 'telegram|naverpost' | grep -v grep | awk '{sum+=$6} END {print sum/1024 " MB"}')"
    sleep 10
done

# 🔄 메모리 정리를 위한 재시작
sudo systemctl restart naverpost-bot.service
```

### 네트워크 연결 문제
```bash
# 🌐 네트워크 연결성 테스트
curl -I https://api.telegram.org
curl -I https://openapi.naver.com

# 📡 DNS 서버 테스트
nslookup api.telegram.org
nslookup openapi.naver.com

# 🔧 네트워크 인터페이스 확인
ip addr show
```

## 📊 성능 모니터링

### 실시간 성능 지표
```bash
# 🖥️ CPU/메모리 사용률
top -p $(pgrep -f naverpost) -n 1

# 💾 디스크 사용량
df -h /home/mini/dev/naverPost

# 🌐 네트워크 트래픽
iftop -i $(ip route get 8.8.8.8 | awk '{print $5}' | head -1) -t -s 10
```

### 성능 기준치
- **메모리 사용량**: < 500MB (정상), > 800MB (주의)
- **CPU 사용률**: < 10% (정상), > 50% (주의)
- **디스크 사용량**: < 80% (정상), > 90% (주의)
- **응답시간**: < 5초 (정상), > 15초 (주의)

## 🔔 알림 설정

### 슬랙 알림 설정
```bash
# .env 파일에 추가
echo 'SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL' >> .env

# 테스트 알림 전송
python3 etc_scripts/send_alert.py test
```

### 이메일 알림 설정
```bash
# 시스템 메일 설정 확인
which mail || sudo apt install mailutils

# 테스트 이메일 전송
echo "봇 상태 테스트" | mail -s "NaverPost Bot Status" your-email@example.com
```

## 📈 업타임 목표

- **일일 가용성**: > 99% (14분 이하 다운타임)
- **주간 가용성**: > 99.5% (50분 이하 다운타임)
- **월간 가용성**: > 99.9% (43분 이하 다운타임)

---

## 🆘 도움이 필요할 때

### 로그 수집 (문제 신고용)
```bash
# 📊 종합 진단 정보 수집
cat << 'EOF' > collect_diagnostic_info.sh
#!/bin/bash
mkdir -p diagnostic_$(date +%Y%m%d_%H%M%S)
cd diagnostic_$(date +%Y%m%d_%H%M%S)

echo "📊 시스템 정보 수집 중..."
systemctl status naverpost-bot.service > service_status.txt
journalctl -u naverpost-bot.service --since "1 hour ago" > recent_logs.txt
python3 ../etc_scripts/monitor_bot_health.py --one-shot > health_check.txt 2>&1
python3 ../etc_scripts/dashboard.py > dashboard.txt 2>&1
ps aux | grep -E "telegram|naverpost" > processes.txt
df -h > disk_usage.txt
free -h > memory_usage.txt

echo "✅ 진단 정보가 $(pwd) 에 저장되었습니다."
EOF

chmod +x collect_diagnostic_info.sh
bash collect_diagnostic_info.sh
```

### 복구 우선순위
1. **🚨 응급**: 봇 완전 다운 → 응급 복구 시퀀스
2. **⚠️ 주의**: 성능 저하 → 메모리/CPU 점검
3. **📊 관찰**: 간헐적 오류 → 로그 분석 및 모니터링 강화

**24시간 안정 운영을 위해 매일 대시보드를 확인하고, 주간 점검을 빠뜨리지 마세요!** 🚀