#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <dir_with_1_image> <dir_with_5_images>"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DIR1="$1"
DIR5="$2"

cd "${PROJECT_ROOT}"

TSX_BIN="${PROJECT_ROOT}/node_modules/.bin/tsx"
DIST_CLI="${PROJECT_ROOT}/dist/cli/post_to_naver.js"

if [[ -x "${TSX_BIN}" ]]; then
  "${TSX_BIN}" test_scripts/integration/smoke_test_post_draft_with_images.ts --dir1 "${DIR1}" --dir5 "${DIR5}"
  exit 0
fi

if [[ ! -f "${DIST_CLI}" ]]; then
  echo "[FAIL] tsx와 dist CLI를 모두 찾지 못했습니다."
  exit 1
fi

run_case() {
  local name="$1"
  local dir="$2"
  local extra_env="${3:-}"

  echo "[SMOKE] start: ${name}"
  local output=""
  if [[ -n "${extra_env}" ]]; then
    output="$(env ${extra_env} node "${DIST_CLI}" --dir "${dir}" 2>&1 || true)"
  else
    output="$(node "${DIST_CLI}" --dir "${dir}" 2>&1 || true)"
  fi
  echo "${output}"

  local marker="NAVER_POST_RESULT_JSON:"
  local line
  line="$(echo "${output}" | grep "${marker}" | tail -n 1 || true)"
  if [[ -z "${line}" ]]; then
    echo "[FAIL] ${name}: 결과 JSON 마커를 찾지 못했습니다."
    return 1
  fi

  python3 - "$name" "$line" <<'PY'
import json
import sys

name = sys.argv[1]
line = sys.argv[2]
marker = "NAVER_POST_RESULT_JSON:"
payload = line.split(marker, 1)[1].strip()
report = json.loads(payload)
print(f"[SMOKE] {name} overall={report.get('overall_status')} image={report.get('image_summary', {}).get('status')}")
PY
}

run_case "single-image-draft" "${DIR1}"
run_case "five-images-draft" "${DIR5}"
run_case "simulated-upload-timeout" "${DIR1}" "SIMULATE_IMAGE_UPLOAD_FAILURE=timeout"
run_case "parallel-multi-image-order" "${DIR5}"
