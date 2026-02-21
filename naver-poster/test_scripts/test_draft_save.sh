#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <post_dir>"
  echo "Example: $0 ../data/20260214(자라)"
  exit 1
fi

POST_DIR="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOG_DIR="${PROJECT_ROOT}/artifacts/integration"
mkdir -p "${LOG_DIR}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/draft_save_test_${TIMESTAMP}.log"

echo "[INFO] 임시저장 통합 테스트 시작"
echo "[INFO] post_dir=${POST_DIR}"
echo "[INFO] log_file=${LOG_FILE}"

(
  cd "${PROJECT_ROOT}"
  if [[ -x "${PROJECT_ROOT}/node_modules/.bin/tsx" ]]; then
    "${PROJECT_ROOT}/node_modules/.bin/tsx" test_scripts/integration/test_naver_draft_save.ts --dir "${POST_DIR}"
  elif [[ -f "${PROJECT_ROOT}/dist/cli/post_to_naver.js" ]]; then
    out="$(node "${PROJECT_ROOT}/dist/cli/post_to_naver.js" --dir "${POST_DIR}" 2>&1 || true)"
    echo "${out}"
    echo "${out}" | grep -q "NAVER_POST_RESULT_JSON:" || { echo "[FAIL] 결과 JSON 마커 없음"; exit 1; }
  else
    npx --no-install tsx test_scripts/integration/test_naver_draft_save.ts --dir "${POST_DIR}"
  fi
) | tee "${LOG_FILE}"

echo "[PASS] 임시저장 통합 테스트 완료"
