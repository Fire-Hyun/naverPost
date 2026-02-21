# Script Layout and Path Migration (2026-02-16)

## Directory Policy

- `scripts/`: 단위/통합 테스트, 로컬 검증/디버그 스크립트
- `etc_scripts/`: 운영 엔트리포인트(crontab/systemd/배치)
- `maintenance/`: 일회성 fix/migrate 스크립트
- `src/`: 실행 스크립트가 import 하는 비즈니스 모듈

## Classification Snapshot

- 운영 사용(A): `etc_scripts/*.py`, `etc_scripts/*.sh`, `etc_scripts/*.service`
- 테스트/검증(B): `scripts/test_*.py`, `scripts/integration_test.py`, `scripts/test_headless_smoke.sh`
- 일회성 fix(C): `maintenance/fix_telegram_bot.sh`, `maintenance/fix_wsl_dns_and_restart_bot.sh`, `maintenance/rename_directories.py`
- 폐기/대체(D): 루트 실행 스크립트 및 `scripts/` 내 운영용 파일(아래 이동 목록 참조)

## Migration / Move List

- `run_telegram_bot.py` -> `etc_scripts/run_telegram_bot.py`
- `scripts/monitor_bot_health.py` -> `etc_scripts/monitor_bot_health.py`
- `scripts/fix_dns_issues.py` -> `etc_scripts/fix_dns_issues.py`
- `scripts/test_stabilization_system.py` -> `etc_scripts/test_stabilization_system.py`
- `scripts/restart_telegram_bot.sh` -> `etc_scripts/restart_telegram.sh`
- `scripts/restart_web.sh` -> `etc_scripts/restart_web.sh`
- `scripts/install-systemd-service.sh` -> `etc_scripts/install-systemd-service.sh`
- `scripts/naverpost-bot.service` -> `etc_scripts/naverpost-bot.service`
- `scripts/fix_wsl_dns_and_restart_bot.sh` -> `maintenance/fix_wsl_dns_and_restart_bot.sh`
- `test_refactoring_regression.py` -> `scripts/test_refactoring_regression.py`

## Crontab Update

현재 crontab:

```cron
# 네이버 포스트 텔레그램 봇 24시간 안정성 모니터링
*/5 * * * * cd /home/mini/dev/naverPost && python3 etc_scripts/monitor_bot_health.py --one-shot >> logs/health_check.log 2>&1
0 * * * * cd /home/mini/dev/naverPost && python3 etc_scripts/fix_dns_issues.py --diagnose-only >> logs/dns_check.log 2>&1
0 2 * * * cd /home/mini/dev/naverPost && python3 etc_scripts/test_stabilization_system.py --quick >> logs/daily_check.log 2>&1
0 3 * * 1 cd /home/mini/dev/naverPost && python3 etc_scripts/test_stabilization_system.py >> logs/weekly_test.log 2>&1
0 1 * * * find /home/mini/dev/naverPost/logs -name "*.log" -mtime +7 -delete
```

diff 산출물:

- `docs/crontab.before.2026-02-16.txt`
- `docs/crontab.after.2026-02-16.txt`
- `docs/crontab.diff.2026-02-16.patch`

## Sub-Script Path Impact Fixes

- `etc_scripts/restart_telegram.sh`: `sudo systemctl restart naverpost-bot.service`
- `etc_scripts/setup_24h_monitoring.sh`: 생성되는 cron 경로 전부 `etc_scripts/*`로 고정
- `maintenance/fix_wsl_dns_and_restart_bot.sh`: 봇 재시작 경로 `etc_scripts/run_telegram_bot.py`
- `etc_scripts/naverpost-bot.service`: `ExecStart` -> `/home/mini/dev/naverPost/etc_scripts/start_bot_with_health_check.py`
- `etc_scripts/install-systemd-service.sh`: 구조 검증 경로 `etc_scripts/run_telegram_bot.py`

## Runtime Path Standardization

- 운영 Python 엔트리포인트(`etc_scripts/*.py`)에 공통 적용:
  - `Path(__file__).resolve().parent.parent` 기반 `project_root`
  - `sys.path.insert(0, str(project_root))`
  - `os.chdir(project_root)`
- 운영/테스트 shell 엔트리포인트는 `dirname "$0"` 기반 `PROJECT_ROOT` 계산 후 `cd`

## Verification Summary

- 구문/컴파일:
  - `python -m py_compile etc_scripts/*.py scripts/*.py` 통과
  - `bash -n etc_scripts/*.sh maintenance/*.sh scripts/test_headless_smoke.sh` 통과
- 운영 엔트리포인트 드라이런:
  - `./venv/bin/python3 etc_scripts/fix_dns_issues.py --diagnose-only` 통과(Exit 0)
  - `./venv/bin/python3 etc_scripts/test_stabilization_system.py --quick` 통과(Exit 0)
  - `./venv/bin/python3 etc_scripts/monitor_bot_health.py --one-shot` 실행됨(Exit 1, 사유: 봇 프로세스 미실행)
- 테스트 스크립트:
  - `python3 scripts/test_structure.py` 통과
  - `pytest -q scripts/test_naver_upload_pipeline_state.py` 통과(3 passed)

## One-Off Script Caution

- `maintenance/` 스크립트는 DNS/systemd/네트워크를 변경할 수 있으므로 수동 실행만 권장
- 자동 실행(cron/systemd) 경로에는 포함하지 않음

## Temp Save Repro/Test Scripts (2026-02-17)

- `scripts/repro_temp_save_from_data.py`
  - 실데이터(`data/YYYYMMDD(...)`) 기반 임시저장 재현 실행
  - 예: `python3 scripts/repro_temp_save_from_data.py --dir 'data/20260212(장어)' --runs 3`
- `scripts/test_temp_save_unit.sh`
  - 임시저장 상태머신/파서/에디터 단위 테스트 실행
- `scripts/test_temp_save_integration.sh`
  - 통합 테스트 실행(빌드 + 샘플 통합 시나리오 + 3회 안정성 검증)

관련 분석 보고서:

- `docs/issue_report.md`
