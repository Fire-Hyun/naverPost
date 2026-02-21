#!/bin/bash

# 텔레그램 봇 상태 확인 스크립트
# 사용법: ./check_bot_status.sh [옵션]
# 옵션:
#   --logs       : 최근 로그 표시 (기본 20줄)
#   --logs=N     : 최근 N줄의 로그 표시
#   --watch      : 실시간 로그 모니터링

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# 옵션 파싱
SHOW_LOGS=false
LOG_LINES=20
WATCH_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --logs)
            SHOW_LOGS=true
            shift
            ;;
        --logs=*)
            SHOW_LOGS=true
            LOG_LINES="${1#*=}"
            shift
            ;;
        --watch)
            WATCH_MODE=true
            shift
            ;;
        -h|--help)
            echo "사용법: $0 [옵션]"
            echo "옵션:"
            echo "  --logs       최근 로그 표시 (기본 20줄)"
            echo "  --logs=N     최근 N줄의 로그 표시"
            echo "  --watch      실시간 로그 모니터링"
            echo "  -h, --help   도움말 표시"
            exit 0
            ;;
        *)
            echo -e "${RED}❌ 알 수 없는 옵션: $1${NC}"
            exit 1
            ;;
    esac
done

# 프로젝트 루트 경로
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="$PROJECT_ROOT/logs/telegram_bot.log"
BOT_PATTERN="run_telegram_bot\\.py|start_bot_with_health_check\\.py"
SYSTEMD_SERVICE="naverpost-bot.service"

echo -e "${CYAN}${BOLD}🔍 텔레그램 봇 상태 확인${NC}"
echo -e "${CYAN}========================${NC}"

# 0. systemd 서비스 상태 확인
echo -e "\n${YELLOW}🧭 서비스 실행 경로:${NC}"
if systemctl list-unit-files --type=service 2>/dev/null | awk '{print $1}' | grep -qx "$SYSTEMD_SERVICE"; then
    if systemctl is-active --quiet "$SYSTEMD_SERVICE"; then
        echo -e "${GREEN}   ✅ systemd 서비스 활성: ${BOLD}$SYSTEMD_SERVICE${NC}"
    else
        echo -e "${YELLOW}   ⚠️  systemd 서비스 비활성: ${BOLD}$SYSTEMD_SERVICE${NC}"
    fi
else
    echo -e "${CYAN}   systemd 서비스 미사용(수동 실행 모드)${NC}"
fi

# 1. 프로세스 상태 확인
echo -e "\n${YELLOW}📱 봇 프로세스 상태:${NC}"
BOT_PIDS=$(pgrep -f "$BOT_PATTERN" 2>/dev/null || true)

if [ -n "$BOT_PIDS" ]; then
    echo -e "${GREEN}   ✅ 실행 중 (PID: ${BOLD}$BOT_PIDS${NC}${GREEN})${NC}"

    # 프로세스 상세 정보
    echo -e "\n${BLUE}📊 프로세스 상세 정보:${NC}"
    ps aux | head -1
    ps aux | grep -E "run_telegram_bot.py|start_bot_with_health_check.py" | grep -v grep

    # 프로세스 실행 시간
    echo -e "\n${BLUE}⏱️  실행 시간:${NC}"
    ps -o pid,etime,cmd -p $BOT_PIDS
else
    echo -e "${RED}   ❌ 실행 중이지 않음${NC}"
fi

# 2. 로그 파일 정보
echo -e "\n${YELLOW}📄 로그 파일 정보:${NC}"
if [ -f "$LOG_FILE" ]; then
    LOG_SIZE=$(du -h "$LOG_FILE" | cut -f1)
    LOG_MODIFIED=$(stat -c "%y" "$LOG_FILE" 2>/dev/null | cut -d. -f1)
    echo -e "${GREEN}   ✅ 로그 파일 존재${NC}"
    echo -e "   파일 경로: ${CYAN}$LOG_FILE${NC}"
    echo -e "   파일 크기: ${CYAN}$LOG_SIZE${NC}"
    echo -e "   최종 수정: ${CYAN}$LOG_MODIFIED${NC}"
else
    echo -e "${RED}   ❌ 로그 파일 없음: $LOG_FILE${NC}"
fi

# 3. 시스템 리소스 사용량 (봇 프로세스가 실행 중인 경우)
if [ -n "$BOT_PIDS" ]; then
    echo -e "\n${YELLOW}💾 시스템 리소스 사용량:${NC}"
    for pid in $BOT_PIDS; do
        if kill -0 $pid 2>/dev/null; then
            CPU_MEM=$(ps -o pid,pcpu,pmem,vsz,rss -p $pid --no-headers)
            echo -e "   PID: $pid"
            echo -e "   CPU/메모리: ${CYAN}$CPU_MEM${NC}"
        fi
    done
fi

# 4. 네트워크 연결 상태
echo -e "\n${YELLOW}🌐 네트워크 연결 상태:${NC}"
if getent hosts api.telegram.org > /dev/null 2>&1; then
    echo -e "${GREEN}   ✅ api.telegram.org 연결 가능${NC}"
else
    echo -e "${RED}   ❌ api.telegram.org 연결 실패${NC}"
fi

# 5. 최근 로그 표시 (요청 시)
if [ "$SHOW_LOGS" = true ] && [ -f "$LOG_FILE" ]; then
    echo -e "\n${BLUE}📋 최근 로그 (마지막 ${LOG_LINES}줄):${NC}"
    echo -e "${CYAN}=================================${NC}"
    tail -n $LOG_LINES "$LOG_FILE" 2>/dev/null || echo "로그를 읽을 수 없습니다."
    echo -e "${CYAN}=================================${NC}"
fi

# 6. 실시간 로그 모니터링 (요청 시)
if [ "$WATCH_MODE" = true ]; then
    if [ -f "$LOG_FILE" ]; then
        echo -e "\n${YELLOW}👀 실시간 로그 모니터링 시작 (Ctrl+C로 중지):${NC}"
        echo -e "${CYAN}=================================${NC}"
        tail -f "$LOG_FILE"
    else
        echo -e "\n${RED}❌ 로그 파일이 없어 실시간 모니터링을 시작할 수 없습니다.${NC}"
        exit 1
    fi
fi

# 요약
echo -e "\n${BLUE}💡 유용한 명령어:${NC}"
echo -e "   ${CYAN}로그 실시간 모니터링:${NC} $0 --watch"
echo -e "   ${CYAN}최근 로그 확인:${NC} $0 --logs=50"
echo -e "   ${CYAN}봇 재시작:${NC} ./etc_scripts/restart_telegram.sh"
if [ -n "$BOT_PIDS" ]; then
    echo -e "   ${CYAN}봇 수동 종료:${NC} kill $BOT_PIDS"
fi

echo -e "\n${CYAN}${BOLD}✨ 상태 확인 완료!${NC}"
