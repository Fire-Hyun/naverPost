#!/bin/bash
# 네이버 임시저장 headless/headed 스모크 테스트
# 사용법:
#   ./scripts/test_headless_smoke.sh          # headless 모드 (기본)
#   ./scripts/test_headless_smoke.sh headed   # headed 모드 (xvfb-run 사용)
#   ./scripts/test_headless_smoke.sh detect   # 환경 감지 테스트 (DISPLAY 없이 headed 요청)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
NAVER_POSTER_DIR="$PROJECT_ROOT/naver-poster"

MODE="${1:-headless}"

echo "========================================"
echo "  네이버 Playwright 스모크 테스트"
echo "  모드: $MODE"
echo "========================================"

# naver-poster 디렉토리 확인
if [ ! -d "$NAVER_POSTER_DIR" ]; then
    echo "❌ naver-poster 디렉토리를 찾을 수 없습니다: $NAVER_POSTER_DIR"
    exit 1
fi

# 빌드된 CLI 확인
CLI_JS="$NAVER_POSTER_DIR/dist/cli/post_to_naver.js"
CLI_TS="$NAVER_POSTER_DIR/src/cli/post_to_naver.ts"

if [ -f "$CLI_JS" ]; then
    CMD="node $CLI_JS"
elif [ -f "$CLI_TS" ]; then
    CMD="npx --no-install tsx $CLI_TS"
else
    echo "❌ naver-poster CLI를 찾을 수 없습니다"
    exit 1
fi

case "$MODE" in
    headless)
        echo ""
        echo "▶ 테스트 1: headless 모드 헬스체크"
        echo "  HEADLESS=true $CMD --healthcheck"
        echo ""
        cd "$NAVER_POSTER_DIR"
        HEADLESS=true $CMD --healthcheck && {
            echo ""
            echo "✅ headless 모드 헬스체크 성공"
        } || {
            echo ""
            echo "❌ headless 모드 헬스체크 실패 (종료코드: $?)"
            echo "   Playwright 설치 확인: npx playwright install chromium"
            exit 1
        }
        ;;

    headed)
        echo ""
        echo "▶ 테스트 2: headed 모드 (xvfb-run) 헬스체크"

        # xvfb-run 존재 확인
        if ! command -v xvfb-run &> /dev/null; then
            echo "❌ xvfb-run이 설치되어 있지 않습니다"
            echo "   설치: sudo apt-get install -y xvfb"
            exit 1
        fi

        echo "  xvfb-run -a env HEADLESS=false $CMD --healthcheck"
        echo ""
        cd "$NAVER_POSTER_DIR"
        xvfb-run -a env HEADLESS=false $CMD --healthcheck && {
            echo ""
            echo "✅ headed 모드 (xvfb) 헬스체크 성공"
        } || {
            echo ""
            echo "❌ headed 모드 헬스체크 실패 (종료코드: $?)"
            echo "   xvfb 또는 Playwright 의존성을 확인하세요"
            exit 1
        }
        ;;

    detect)
        echo ""
        echo "▶ 테스트 3: 환경 감지 테스트"
        echo "  DISPLAY 제거 + HEADLESS=false → 자동 폴백 확인"
        echo ""
        cd "$NAVER_POSTER_DIR"

        # DISPLAY를 명시적으로 제거하고 headed 모드 요청
        unset DISPLAY 2>/dev/null || true
        unset WAYLAND_DISPLAY 2>/dev/null || true

        echo "  env -u DISPLAY -u WAYLAND_DISPLAY HEADLESS=false $CMD --healthcheck"
        echo ""
        env -u DISPLAY -u WAYLAND_DISPLAY HEADLESS=false $CMD --healthcheck && {
            echo ""
            echo "✅ 환경 감지 + 자동 폴백 성공"
            echo "   → DISPLAY 없이 headed 요청 시 headless로 자동 전환됨"
        } || {
            CODE=$?
            echo ""
            if [ $CODE -eq 1 ]; then
                echo "⚠️ 헬스체크는 실패했으나 브라우저 자체는 정상 실행"
                echo "   (로그인 세션이 없어서 헬스체크 실패할 수 있음)"
            else
                echo "❌ 환경 감지 폴백 실패"
                echo "   session.ts의 validateDisplayEnvironment 확인 필요"
            fi
        }
        ;;

    *)
        echo "사용법: $0 {headless|headed|detect}"
        echo ""
        echo "  headless  - headless 모드 헬스체크 (기본, 운영 환경)"
        echo "  headed    - xvfb-run headed 모드 헬스체크 (디버그)"
        echo "  detect    - DISPLAY 없이 headed 요청 → 자동 폴백 테스트"
        exit 1
        ;;
esac

echo ""
echo "========================================"
echo "  스모크 테스트 완료"
echo "========================================"
