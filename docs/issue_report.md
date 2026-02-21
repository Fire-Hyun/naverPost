# naver-poster 임시저장 정체/타임아웃 근본 원인 보고서 (2026-02-17)

## 1) 근본 원인

- 정체/실패 단계 확정:
  - `text_blocks_insert` 단계 고정 타임아웃 오탐
  - `DraftProgressWatchdog` heartbeat 미연결 오작동
  - `clickTempSave` 단계 클릭+성공대기를 한 단계에 묶은 20초 제한
  - `session_preflight` 30초 제한으로 로그인 페이지 체류 시 조기 실패
  - 대용량(이미지 10장+)에서 `text_blocks_insert` 상한(`240s`) 및 프로세스 워치독(`300s`) 과소 설정
  - Telegram polling 중복 인스턴스로 `getUpdates Conflict` 발생
- 디버그 근거 (`naver-poster/logs/navertimeoutdebug`):
  - `2026-02-16T23-48-31-509Z`: `stage_timeout_text_blocks_insert_30s`
  - `2026-02-16T23-51-58-678Z`: `stage_watchdog_watchdog_start_60315ms`
  - `2026-02-16T23-55-22-757Z`, `2026-02-16T23-59-04-308Z`: `stage_timeout_text_blocks_insert_144s`
  - `2026-02-17T00-07-27-884Z`: `stage_timeout_draft_click_20s`
- 서버 장애(HTTP 5xx)보다는 클라이언트 단계 설계 문제:
  - 이미지 업로드 1장당 실측 35초 내외인데 상위 단계 예산이 30초/144초로 과소
  - stage watchdog은 진행 로그가 있어도 heartbeat 미연결로 60초 후 오작동 종료
  - 임시저장 클릭 단계가 성공 신호 대기까지 포함해 단계 분리가 불명확
  - 느린 로그인/리다이렉트 상황에서 `session_preflight`가 30초 내 실패
  - 봇 중복 실행 시 업로드 상태 전달/폴링 안정성이 저하됨

## 2) 수정 내용

- 상태머신/유틸 추가:
  - `naver-poster/src/naver/temp_save_state_machine.ts`
  - 추가 기능:
    - `DraftProgressWatchdog`
    - `runDraftStage(...)`
    - `computeInsertBlocksTimeoutSeconds(...)`
    - `normalizeBlockSequenceForDraft(...)`
    - `buildImageUploadPlan(...)`
    - `isTempSaveSuccessSignal(...)`
- `text_blocks_insert` 타임아웃 정책 개선:
  - 고정 30초 제거
  - 블록/이미지 수 기반 동적 timeout budget 적용
  - 예: `data/20260212(장어)` 실행 시 `228s` 예산 산출 로그 확인
- watchdog 구조 수정:
  - `touchWatchdog(...)`에서 `stageWatchdog.heartbeat(...)` 동기화
  - 진행 로그가 있으면 stage watchdog이 오작동하지 않도록 수정
- 임시저장 클릭/검증 단계 분리:
  - `clickTempSave(...)`는 기본적으로 버튼 클릭만 수행
  - 성공 신호 대기는 `verifyTempSaveWithRetry(...)` 단계에서 수행
  - 타임아웃 분리:
    - `NAVER_DRAFT_CLICK_TIMEOUT_MS` (기본 45000)
    - `NAVER_DRAFT_VERIFY_TIMEOUT_MS` (기본 45000)
- 세션 사전검증 타임아웃 상향:
  - `NAVER_SESSION_PREFLIGHT_TIMEOUT_SECONDS` (기본 90초)
  - 느린 로그인 리다이렉트 환경에서 조기 실패 방지
- 대용량 업로드 타임아웃 구조 개선:
  - `src/services/blog_workflow.py`
    - 이미지 수 기반 `adaptive_upload_timeout` 도입
    - subprocess 실행 env에 다음 값 강제 주입:
      - `NAVER_UPLOAD_TIMEOUT_SECONDS`
      - `NAVER_PROCESS_WATCHDOG_SECONDS`
      - `NAVER_INSERT_BLOCKS_TIMEOUT_MAX_SECONDS`
  - `naver-poster/src/cli/post_to_naver.ts`
    - 프로세스 워치독 기본값 상향(최소 600초 보장, 기본 900초)
    - block insert 상한 기본값 상향 및 최소 600초 보장
- 워크플로우(naver-poster subprocess) 보강:
  - `src/services/blog_workflow.py`에서 naver-poster 실행 시 안정 타임아웃 env 주입
  - `src/services/blog_workflow.py`에서 `dist` stale 감지 시 자동 `npm run build`
  - 사용자 에러 메시지 디버그 경로를 `naver-poster/logs/navertimeoutdebug/*`로 정정
- Telegram 단일 인스턴스 락:
  - `src/services/telegram_service.py`에 `/tmp/naverpost_telegram_bot.lock` 도입
  - 동일 호스트 중복 polling 실행을 차단하여 `Conflict(getUpdates)` 재발 방지
- 디버그 저장 경로 표준화 유지:
  - `naver-poster/logs/navertimeoutdebug/{timestamp}/`

## 3) 테스트

- Unit:
  - `bash scripts/test_temp_save_unit.sh`
  - 통과: 상태머신/파서/에디터 관련 테스트 PASS
- Integration(실데이터):
  - 재현 스크립트: `scripts/repro_temp_save_from_data.py`
  - 실행:
    - `python3 scripts/repro_temp_save_from_data.py --dir 'data/20260212(장어)' --runs 1`
    - `python3 scripts/repro_temp_save_from_data.py --dir 'data/20260212(장어)' --runs 3`
  - 결과:
    - 1회: `SUCCESS_FULL`, `draft_ok=True`, `stepF=success`
    - 3회: `3/3 runs succeeded`
- 통합 스크립트:
  - `scripts/test_temp_save_integration.sh` 추가(빌드 + 샘플 + 3회 안정성)
- 실운영 경로 검증:
  - `BlogWorkflowService._upload_to_naver('20260212(하이디라오 제주도점)_4', ...)` 직접 실행
  - 결과:
    - `SUCCESS=True`
    - `OVERALL=SUCCESS_FULL`
    - `draft_summary.success=True`
    - `steps.F.status=success`

## 4) 재발 방지 정책

- 단계 타임아웃:
  - 고정 상수 대신 데이터 규모 기반 budget (`insertBlocks`)
  - 클릭/검증을 분리해 단계별 실패 원인 분명화
- 무한 대기 방지:
  - 모든 대기에 timeout 명시 유지
  - 실패 시 즉시 에러 + 디버그 아티팩트 저장
- 디버그 아티팩트 자동수집:
  - screenshot, page/frame HTML, URL, active element, reason JSON
- 셀렉터 변경 대응:
  - 임시저장 성공 판정은 공통 matcher(`isTempSaveSuccessSignal`)로 단일화
  - 클릭 전략 다중화 + 실패 시 artifacts 저장

## 5) 주요 변경 파일

- `naver-poster/src/naver/temp_save_state_machine.ts`
- `naver-poster/src/cli/post_to_naver.ts`
- `naver-poster/src/naver/editor.ts`
- `naver-poster/src/naver/temp_save_verifier.ts`
- `naver-poster/src/naver/session.ts`
- `naver-poster/tests/temp_save_state_machine.test.ts`
- `naver-poster/tests/integration/test_temp_save_samples.ts`
- `scripts/repro_temp_save_from_data.py`
- `scripts/test_temp_save_unit.sh`
- `scripts/test_temp_save_integration.sh`

## 6) 2026-02-17 14:08 세션 정체 재발 원인/조치

- 재발 원인:
  - `session_preflight`가 `https://www.naver.com` 경유로 로그인 판정을 수행하면서, 느린 리다이렉트/DOM 상태에서 정체가 반복됨.
  - 타임아웃 발생 시 디버그 수집 루틴이 다시 페이지 평가(`page.content/evaluate`)에서 지연되어 종료가 늦어지는 경로가 존재함.
- 근본 조치:
  - `naver-poster/src/naver/session.ts`
    - 로그인 판정을 write 페이지 기준으로 재구성 (`detectLoginState`, `classifyLoginState`).
    - 세션 만료 감지 즉시 환경변수 `NAVER_ID/NAVER_PW`로 자동 로그인 수행.
    - 고정 `waitForTimeout(6000/8000)` 제거, 조건 기반 wait로 전환.
    - `loadOrCreateSession`/`preflightSessionForUpload`를 동일한 즉시 복구 경로로 통합.
  - `naver-poster/src/cli/post_to_naver.ts`
    - watchdog heartbeat를 로그 문구가 아니라 고정 `log_activity` 신호로 변경해 stage 오염/오탐 방지.
- 검증:
  - `npm run build` 성공
  - `npm test -- --runInBand tests/session_state.test.ts` 성공 (4/4)
  - 실데이터 실행에서 `session_preflight`가 0.6초 내 통과하고, 세션 만료 시 자동 로그인 후 본문/이미지 삽입 단계까지 정상 진행 확인.
