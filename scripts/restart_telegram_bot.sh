#!/bin/bash

# 텔레그램 봇 재기동 스크립트
# 사용법: ./restart_telegram_bot.sh [옵션]
# 옵션:
#   --no-logs    : 로그를 표시하지 않음
#   --quick      : 빠른 재시작 (대기 시간 단축)
#   --verbose    : 상세한 정보 표시

set -e  # 에러 발생 시 스크립트 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# 옵션 파싱
SHOW_LOGS=true
QUICK_MODE=false
VERBOSE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-logs)
            SHOW_LOGS=false
            shift
            ;;
        --quick)
            QUICK_MODE=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            echo "사용법: $0 [옵션]"
            echo "옵션:"
            echo "  --no-logs    로그를 표시하지 않음"
            echo "  --quick      빠른 재시작 (대기 시간 단축)"
            echo "  --verbose    상세한 정보 표시"
            echo "  -h, --help   도움말 표시"
            exit 0
            ;;
        *)
            echo -e "${RED}❌ 알 수 없는 옵션: $1${NC}"
            exit 1
            ;;
    esac
done

# 프로젝트 루트 경로 (스크립트 위치 기반)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/venv"
BOT_SCRIPT="$PROJECT_ROOT/run_telegram_bot.py"
LOG_FILE="$PROJECT_ROOT/logs/telegram_bot.log"

# 헤더 출력
echo -e "${CYAN}${BOLD}🤖 네이버포스트 텔레그램 봇 재기동 스크립트${NC}"
echo -e "${CYAN}==============================================${NC}"
echo -e "프로젝트 경로: ${BLUE}$PROJECT_ROOT${NC}"
echo -e "로그 파일: ${BLUE}$LOG_FILE${NC}"

# 1. 기존 봇 프로세스 종료
echo -e "\n${YELLOW}🛑 [1/6] 기존 텔레그램 봇 프로세스 확인 및 종료${NC}"

# Python 봇 프로세스 찾기 (더 정확한 패턴)
BOT_PIDS=$(pgrep -f "run_telegram_bot\.py" 2>/dev/null || true)

if [ -n "$BOT_PIDS" ]; then
    echo -e "${YELLOW}   📱 기존 봇 프로세스 발견: ${BOLD}$BOT_PIDS${NC}"

    if [ "$VERBOSE" = true ]; then
        echo -e "${CYAN}   프로세스 상세 정보:${NC}"
        ps aux | head -1
        ps aux | grep "[r]un_telegram_bot.py" || true
    fi

    echo -e "${YELLOW}   우아한 종료 시도 (SIGTERM)...${NC}"
    kill -TERM $BOT_PIDS 2>/dev/null || true

    # 종료 대기 시간 설정
    if [ "$QUICK_MODE" = true ]; then
        WAIT_TIME=3
    else
        WAIT_TIME=6
    fi

    echo -e "${YELLOW}   종료 대기 중... (${WAIT_TIME}초)${NC}"
    sleep $WAIT_TIME

    # 여전히 실행 중이면 강제 종료
    REMAINING_PIDS=$(pgrep -f "run_telegram_bot\.py" 2>/dev/null || true)
    if [ -n "$REMAINING_PIDS" ]; then
        echo -e "${RED}   ⚠️  우아한 종료 실패, 강제 종료 시도...${NC}"
        kill -KILL $REMAINING_PIDS 2>/dev/null || true
        sleep 2

        # 최종 확인
        FINAL_CHECK=$(pgrep -f "run_telegram_bot\.py" 2>/dev/null || true)
        if [ -n "$FINAL_CHECK" ]; then
            echo -e "${RED}   ❌ 프로세스 종료 실패! 수동으로 종료하세요: kill -9 $FINAL_CHECK${NC}"
            exit 1
        fi
    fi

    echo -e "${GREEN}   ✅ 기존 봇 프로세스 종료 완료${NC}"
else
    echo -e "${GREEN}   ✅ 실행 중인 봇 프로세스 없음${NC}"
fi

# 2. 환경 검증
echo -e "\n${YELLOW}🔍 [2/6] 환경 검증${NC}"

# 가상환경 확인
if [ ! -d "$VENV_PATH" ]; then
    echo -e "${RED}   ❌ 가상환경이 존재하지 않습니다: $VENV_PATH${NC}"
    exit 1
fi
echo -e "${GREEN}   ✅ 가상환경 확인됨${NC}"

# Python 실행파일 확인
PYTHON_BIN="$VENV_PATH/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    echo -e "${RED}   ❌ Python 실행파일이 존재하지 않습니다: $PYTHON_BIN${NC}"
    exit 1
fi
echo -e "${GREEN}   ✅ Python 실행파일 확인됨${NC}"

# 봇 스크립트 확인
if [ ! -f "$BOT_SCRIPT" ]; then
    echo -e "${RED}   ❌ 봇 스크립트가 존재하지 않습니다: $BOT_SCRIPT${NC}"
    exit 1
fi
echo -e "${GREEN}   ✅ 봇 스크립트 확인됨${NC}"

# 환경 설정 파일 확인
ENV_FILE="$PROJECT_ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}   ❌ 환경 설정 파일이 존재하지 않습니다: $ENV_FILE${NC}"
    exit 1
fi

# 텔레그램 봇 토큰 확인
if ! grep -q "TELEGRAM_BOT_TOKEN=" "$ENV_FILE" || ! grep -q -v "TELEGRAM_BOT_TOKEN=$" "$ENV_FILE"; then
    echo -e "${RED}   ❌ TELEGRAM_BOT_TOKEN이 설정되지 않았습니다${NC}"
    exit 1
fi
echo -e "${GREEN}   ✅ 환경 설정 파일 확인됨${NC}"

# 3. 로그 디렉토리 준비
echo -e "\n${YELLOW}📁 [3/6] 로그 디렉토리 준비${NC}"
mkdir -p "$(dirname "$LOG_FILE")"
echo -e "${GREEN}   ✅ 로그 디렉토리 준비 완료${NC}"

# 4. DNS 연결성 검사
echo -e "\n${YELLOW}🌐 [4/6] Telegram API 연결성 검사${NC}"
if getent hosts api.telegram.org > /dev/null 2>&1; then
    echo -e "${GREEN}   ✅ api.telegram.org 연결 가능${NC}"
else
    echo -e "${RED}   ⚠️  api.telegram.org DNS 조회 실패${NC}"
    echo -e "${YELLOW}   Telegram 연결에 문제가 있을 수 있습니다${NC}"
fi

# 5. 봇 시작
echo -e "\n${YELLOW}🚀 [5/6] 텔레그램 봇 시작${NC}"
cd "$PROJECT_ROOT"

# 백그라운드에서 봇 실행
echo -e "${YELLOW}   봇 시작 중...${NC}"
nohup env PYTHONUNBUFFERED=1 "$PYTHON_BIN" "$BOT_SCRIPT" > "$LOG_FILE" 2>&1 &
BOT_PID=$!

echo -e "${GREEN}   ✅ 봇 시작됨 (PID: ${BOLD}$BOT_PID${NC}${GREEN})${NC}"

# 6. 시작 확인
echo -e "\n${YELLOW}⏳ [6/6] 봇 초기화 확인${NC}"

# 초기화 대기 시간 설정
if [ "$QUICK_MODE" = true ]; then
    INIT_WAIT=5
else
    INIT_WAIT=10
fi

echo -e "${YELLOW}   초기화 대기 중... (${INIT_WAIT}초)${NC}"
sleep $INIT_WAIT

# 프로세스가 여전히 실행 중인지 확인
if kill -0 $BOT_PID 2>/dev/null; then
    echo -e "\n${GREEN}${BOLD}🎉 텔레그램 봇 재기동 성공!${NC}"

    echo -e "\n${BLUE}📋 봇 정보:${NC}"
    echo -e "   ${CYAN}PID:${NC} $BOT_PID"
    echo -e "   ${CYAN}로그 파일:${NC} $LOG_FILE"
    echo -e "   ${CYAN}프로젝트 경로:${NC} $PROJECT_ROOT"

    # 프로세스 정보 표시
    if [ "$VERBOSE" = true ]; then
        echo -e "\n${BLUE}🔍 프로세스 상세 정보:${NC}"
        ps aux | head -1
        ps aux | grep "[r]un_telegram_bot.py" || true
    fi

    # 로그 표시
    if [ "$SHOW_LOGS" = true ] && [ -f "$LOG_FILE" ]; then
        echo -e "\n${BLUE}📄 최근 로그 (마지막 15줄):${NC}"
        echo -e "${CYAN}=================================${NC}"
        tail -n 15 "$LOG_FILE" 2>/dev/null || echo "로그 파일을 읽을 수 없습니다."
        echo -e "${CYAN}=================================${NC}"
    fi

    echo -e "\n${GREEN}💡 유용한 명령어:${NC}"
    echo -e "   ${CYAN}로그 실시간 모니터링:${NC} tail -f $LOG_FILE"
    echo -e "   ${CYAN}봇 프로세스 확인:${NC} ps aux | grep run_telegram_bot.py"
    echo -e "   ${CYAN}봇 수동 종료:${NC} kill $BOT_PID"
    echo -e "   ${CYAN}빠른 재시작:${NC} $0 --quick"

else
    echo -e "\n${RED}${BOLD}❌ 봇 시작 실패!${NC}"
    echo -e "\n${RED}로그 파일을 확인하세요:${NC}"
    echo -e "${CYAN}tail -n 30 $LOG_FILE${NC}"

    if [ -f "$LOG_FILE" ]; then
        echo -e "\n${YELLOW}마지막 로그:${NC}"
        tail -n 20 "$LOG_FILE"
    fi

    exit 1
fi

echo -e "\n${CYAN}${BOLD}🤖 봇 재기동 스크립트 완료!${NC}"
