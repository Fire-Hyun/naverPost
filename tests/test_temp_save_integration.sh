#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <dir1> [dir2] [dir3]"
  echo "Example: $0 data/20260212(장어) data/20260212(하이디라오 제주도점) data/20260214(자라)"
  exit 1
fi

DIRS_CSV="$(printf "%s," "$@" | sed 's/,$//')"

echo "[INTEGRATION] build naver-poster"
(cd naver-poster && npm run build)

echo "[INTEGRATION] run sample draft-save scenarios"
(cd naver-poster && npx --no-install tsx tests/integration/test_temp_save_samples.ts --dirs "${DIRS_CSV}")

echo "[INTEGRATION] 3-run stability check on first sample"
python3 scripts/repro_temp_save_from_data.py --dir "$1" --runs 3

echo "[INTEGRATION] PASS"

