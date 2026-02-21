#!/usr/bin/env bash
set -euo pipefail

# 네이버Post 웹서버 재기동 스크립트 (WSL/Linux용)
# - venv가 있으면 venv로 실행
# - 기존 프로세스(포트 점유/모듈 실행)를 종료한 뒤 재시작
# - stdout/stderr는 logs/webserver.out 로 저장

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# 포트 설정 우선순위:
# 1) 실행 시 환경변수 WEB_PORT
# 2) .env의 WEB_PORT
# 3) 기본값 8000
PORT="${WEB_PORT:-}"
if [[ -z "${PORT:-}" ]] && [[ -f "$ROOT_DIR/.env" ]]; then
  PORT="$(grep -E '^WEB_PORT=' "$ROOT_DIR/.env" | tail -n 1 | cut -d= -f2 | tr -d '"' | tr -d "'" || true)"
fi
PORT="${PORT:-8000}"
LOG_FILE="${WEB_LOG_FILE:-$ROOT_DIR/logs/webserver.out}"

mkdir -p "$ROOT_DIR/logs"

PY="$ROOT_DIR/venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

echo "[restart_web] root=$ROOT_DIR port=$PORT python=$PY"

echo "[restart_web] stopping existing server (if any)"

# 1) 포트를 리슨 중인 프로세스가 있으면 종료
if command -v ss >/dev/null 2>&1; then
  PIDS="$(
    ss -tlnp 2>/dev/null \
      | awk -v p=":$PORT" '
          $4 ~ p {
            line=$0
            while (match(line, /pid=[0-9]+/)) {
              pid=substr(line, RSTART+4, RLENGTH-4)
              print pid
              line=substr(line, RSTART+RLENGTH)
            }
          }
        ' \
      | sort -u || true
  )"
else
  PIDS=""
fi

if [[ -n "${PIDS:-}" ]]; then
  echo "[restart_web] killing pids listening on :$PORT -> $PIDS"
  # shellcheck disable=SC2086
  kill $PIDS 2>/dev/null || true
  sleep 1
  # 아직 살아있으면 강제 종료
  for pid in $PIDS; do
    if kill -0 "$pid" 2>/dev/null; then
      echo "[restart_web] pid $pid still alive; killing -9"
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
fi

# 2) 혹시 남아있는 모듈 실행 프로세스도 종료
pkill -f "python3 -m src.web.app" 2>/dev/null || true
pkill -f "venv/bin/python3 -m src.web.app" 2>/dev/null || true

sleep 1

echo "[restart_web] starting server"
echo "[restart_web] log -> $LOG_FILE"

nohup "$PY" -m src.web.app >>"$LOG_FILE" 2>&1 &

sleep 1

if command -v ss >/dev/null 2>&1; then
  if ss -tlnp 2>/dev/null | awk -v p=":$PORT" '$4 ~ p {found=1} END{exit !found}'; then
    echo "[restart_web] OK: listening on :$PORT"
    exit 0
  fi
fi

echo "[restart_web] WARN: port check failed. See log: $LOG_FILE"
exit 0
