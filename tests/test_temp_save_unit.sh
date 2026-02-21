#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}/naver-poster"

echo "[UNIT] temp-save state machine tests"
npm test -- --runInBand tests/temp_save_state_machine.test.ts

echo "[UNIT] editor/parser regression tests"
npm test -- --runInBand tests/editor_text_input.test.ts tests/parser.test.ts

echo "[UNIT] PASS"

