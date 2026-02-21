# naver-poster

WSL(Linux) 환경에서 Playwright로 네이버 블로그 업로드를 자동화하는 프로젝트입니다.

## 운영 원칙
- Windows Chrome 원격 디버깅/프로필 공유 방식은 사용하지 않습니다.
- 세션 유지는 WSL 내부에서 생성한 `storageState(state.json)`로만 처리합니다.
- CAPTCHA/2FA/보안확인은 우회하지 않으며, 필요 시 수동 로그인으로 상태를 갱신합니다.

## 빠른 시작
1. 의존성 설치
```bash
npm install
npx playwright install chromium
```

2. 환경파일 준비
```bash
cp .env.example .env
```

3. 1회 로그인 후 세션 저장
```bash
node etc_scripts/auth_save_state.js --headful
```

4. 업로드 실행
```bash
POST_TITLE="제목" POST_BODY="본문" node etc_scripts/post_upload.js --headless
```

## 기존 CLI 유지
기존 진입점은 그대로 사용 가능합니다.
```bash
npm run build
node dist/cli/post_to_naver.js --help
```

## WSL 전용 세션 플로우 (권장)
아래 순서로 WSL 내부 세션만 사용합니다.

1. 인터랙티브 로그인(반드시 GUI/headful)
```bash
node dist/cli/post_to_naver.js --interactiveLogin
```
- 성공 로그 기준:
  - `로그인 확인됨`
  - `세션 저장 완료`

2. 업로드 실행(임시저장 또는 발행)
```bash
node dist/cli/post_to_naver.js --dir="/path/to/post" --draft
node dist/cli/post_to_naver.js --dir="/path/to/post" --publish
```

3. 세션 재사용 점검 예시
```bash
node dist/cli/post_to_naver.js --interactiveLogin
node dist/cli/post_to_naver.js --dir="./sample_post_dir" --draft
```

4. 실데이터 임시저장 테스트 예시
```bash
node dist/cli/post_to_naver.js --dir="20260214(하이디라오 제주도점)" --draft
```
- 위 경로가 현재 디렉토리에 없으면 `./data/20260214(하이디라오 제주도점)`를 자동 탐색합니다.
- 저장 후 확인 경로: `네이버 블로그 관리 > 글관리 > 임시저장 글`
- 성공 시 콘솔에 `draft URL` 또는 `draft ID`가 함께 출력될 수 있습니다.

## 실행 커맨드(요약)
```bash
node dist/cli/post_to_naver.js --interactiveLogin
node dist/cli/post_to_naver.js --dir="20260214(하이디라오 제주도점)" --draft
```

## 운영형 Worker 모드
텔레그램 요청 처리 경로(worker)에서는 `interactiveLogin`을 절대 호출하지 않습니다.
worker는 항상 headless 무인 모드로 동작합니다.

1. 최초 1회 세션 확보(관리자 수동)
```bash
node dist/cli/post_to_naver.js --interactiveLogin
```

2. 워커 상시 실행(headless 고정)
```bash
node dist/cli/worker.js --headless --poll=15
```

3. BLOCKED_LOGIN 재개(수동 1회)
```bash
node dist/cli/worker.js --resume --once
```
또는 상시 재개 모드:
```bash
node dist/cli/worker.js --resume
```

4. 동작 흐름
- 텔레그램 메시지/이미지 수신 -> 파일 기반 큐(`.secrets/worker_job_queue.json`)에 job 적재
- worker가 큐를 소비해 기본 `draft` 업로드 수행
- 세션 만료/보안확인 발생 시 job 상태를 `BLOCKED_LOGIN`으로 전환
- 관리자 텔레그램 알림 발송 후 세션 복구 시 자동/수동 재개

5. 텔레그램 요청 메시지 포맷 예시(텍스트+이미지)
- 이미지 1장 이상 첨부 + 캡션(또는 텍스트):
```text
TITLE: 하이디라오 제주도점 재방문
BODY: 발렌타인데이 방문 후기입니다. 좌석/소스/서비스 중심으로 정리해 주세요.
MODE: draft
STORE_NAME: 하이디라오 제주도점
```
- 발행은 명시적 요청일 때만:
```text
TITLE: 발행 테스트
BODY: 관리자 승인된 건입니다.
MODE: publish
```
- 안전 기본값: `MODE` 미지정 시 `draft`

## 트러블슈팅
- WSLg/GUI 불가:
  - 에러: `[WSLG_UNAVAILABLE]` 또는 `[ENV_NO_GUI]`
  - 조치: Windows 11에서 WSLg 활성화, `wsl --update` 실행 후 WSL 재시작
- 세션 없음/만료:
  - 증상: `SESSION_PRECHECK_FAILED` + `reason=SESSION_EXPIRED_OR_MISSING`
  - 조치: `node dist/cli/post_to_naver.js --interactiveLogin` 재실행
- 보안확인(캡차/2FA/추가인증/약관):
  - 증상: `reason=CAPTCHA_DETECTED|TWO_FACTOR_REQUIRED|SECURITY_CONFIRM_REQUIRED|AGREEMENT_REQUIRED`
  - 조치: interactiveLogin으로 수동 확인 완료 후 다시 실행
- 진단 코드(`실행 실패` 시 로그 출력):
  - `a`: GUI 불가(WSLg 미작동) / headless 강제 문제
  - `b`: 세션 만료/쿠키 무효
  - `c`: 보안확인/캡차/2FA 리디렉트
  - `d`: 셀렉터 변경/에디터 로딩 실패
- 실패 아티팩트:
  - `artifacts/` 하위 스크린샷/HTML
  - `logs/navertimeoutdebug/` 하위 상세 디버그 리포트
- worker reason code:
  - `SESSION_EXPIRED`: 로그인 리다이렉트/세션 만료
  - `SECURITY_CHALLENGE`: 캡차/2FA/기기인증/보안확인
  - `SELECTOR_BROKEN`: 에디터/버튼 셀렉터 불일치
  - `NETWORK_ERROR`: 네트워크/타임아웃

## 스크립트
- `etc_scripts/auth_save_state.js`
  - WSL 브라우저에서 로그인/동의 완료 후 `state.json` 저장
  - 실패 시 `artifacts/auth_save_state_failed_*.png` 저장
- `etc_scripts/post_upload.js`
  - `state.json` 로드 후 글쓰기 페이지 진입/제목/본문 입력/임시저장 클릭
  - state 파일 없음/만료 시 `save_state.js` 재실행 안내
  - 실패 시 `artifacts/upload_failed_*.png` 저장
- `scripts/post/selectors.example.json`
  - 셀렉터 분리 파일(사이트 변경 시 이 파일만 수정)

## NPM 명령
- `npm run auth:save-state`
- `npm run post:upload`
- `npm run build`
- `npm run test:unit`
- `npm run test:integration`
- `npm run test:e2e`
- `npm run verify:flow`
- `npm run gate`
- `node dist/cli/post_to_naver.js --help`

## 수정 후 게이트
코드 수정 후 아래 게이트를 통과해야 완료로 간주합니다.

```bash
npm run gate
```

게이트 순서:
1. `build`
2. `test:unit`
3. `test:integration`
4. `verify:flow` (필수 체크리스트)
5. `test:e2e` (full flow once)

운영 체크리스트 원칙:
- SUCCESS 로그는 실제 DOM/리스트 검증 통과 후에만 출력
- `networkidle` 단독 성공 판정 금지
- 모든 stage 타임박스 적용
- `unknown/unclassified` 대신 reason_code 명시
- 새 기능 추가 시 단위 테스트 1개 이상 추가

## Legacy
Windows 경유 실험 스크립트는 사용 중지 상태로 `legacy/windows/`에 격리했습니다.
