# Login Policy v2

> 적용 버전: 2026-02 이후
> 핵심 원칙: **세션 재사용 우선, 실패 시 즉시 수동 개입 구조**

---

## 1. 정책 개요

### v1 (이전 방식)
- headless 자동 자격증명 입력 허용
- CAPTCHA 감지 → GUI fallback (`attemptInteractiveLoginFallback`) 시도
- worker가 `validateSession()` 사전 게이트 보유

### v2 (현재)
- **headless 자격증명 자동 입력 기본 비활성화** (`enabledInHeadless: false`)
- **CAPTCHA/보안 감지 → 즉시 `BLOCKED_LOGIN`** (fallback 없음)
- **worker는 job 오케스트레이션 전용** — 세션 검증은 `post_to_naver` 내부 `ensureLoggedIn`이 단독 담당
- **동일 run 내 자격증명 시도 1회 제한** (`session.autoLoginAttempted`)

---

## 2. 로그인 상태 머신 (LoginPhase)

```
현재 페이지 상태
      │
      ▼
┌─────────────────┐
│ detectLoginState │
└────────┬────────┘
         │
   logged_in? ──────────────────────────────► LOGGED_IN ► OK (진행)
         │ no
         ▼
┌──────────────────────┐
│ detectLoginBlockSignals │
└──────────┬───────────┘
           │
   CAPTCHA / 2FA / 기기인증?
           │ yes
           ▼
   CHALLENGE_DETECTED ──────────────────────► 즉시 cooldown 저장 + SessionBlockedError
           │ no
           │
   로그인 폼 (hasLoginForm)?
           │ yes
           ▼
       LOGGED_OUT
           │
           ├── headless && !enabledInHeadless ──► SessionBlockedError (자격증명 SKIP)
           │
           ├── session.autoLoginAttempted=true ──► SessionBlockedError (2회 시도 방지)
           │
           └── 자격증명 1회 시도 (autoLoginAttempted=true 마킹 후)
                    │
                    ├── 성공 ──► OK
                    └── 실패 ──► cooldown 저장 + SessionBlockedError
           │ no form
           ▼
        AMBIGUOUS ──────────────────────────► SessionBlockedError (상태 불명)
```

---

## 3. reason_code 매핑표

| 상태 | 원인 | reason_code | cooldown | 수동 복구 필요? |
|------|------|-------------|----------|-----------------|
| CHALLENGE_DETECTED | CAPTCHA 감지 | `CAPTCHA_DETECTED` | **12시간** | ✅ |
| CHALLENGE_DETECTED | 2FA/기기인증 | `TWO_FACTOR_REQUIRED` | **24시간** | ✅ |
| CHALLENGE_DETECTED | 보안 확인 | `SECURITY_CHECK_REQUIRED` | **24시간** | ✅ |
| CHALLENGE_DETECTED | 약관 동의 | `TERMS_AGREEMENT_REQUIRED` | **24시간** | ✅ |
| LOGGED_OUT + headless | 자격증명 입력 비활성화 | `SESSION_BLOCKED_LOGIN_STUCK` | 기존 cooldown | ✅ |
| LOGGED_OUT + autoLoginAttempted | 2회 시도 방지 | `SESSION_BLOCKED_LOGIN_STUCK` | 기존 cooldown | ✅ |
| LOGGED_OUT + 자격증명 실패 | 로그인 폼 여전히 보임 | `LOGIN_FORM_STILL_VISIBLE` | **15분** | ⚠️ |
| AMBIGUOUS | 상태 불명 | `SESSION_BLOCKED_LOGIN_STUCK` | 기존 cooldown | ✅ |
| SESSION_EXPIRED (worker) | 로그인 리다이렉트 | `SESSION_EXPIRED` | — | ✅ |
| SECURITY_CHALLENGE (worker) | CAPTCHA 등 | `SECURITY_CHALLENGE` | — | ✅ |

---

## 4. Worker 동작

Worker는 **job 오케스트레이션만** 담당합니다. 세션 상태 직접 확인 없음.

```
processNextJob()
      │
      ▼
executeUploadJob(job)  ← post_to_naver.js 서브프로세스 실행
      │
      ├── ok=true ────────────────────────────► COMPLETED + notifyUser("업로드 성공")
      │
      ├── reasonCode=SECURITY_CHALLENGE ──────► 즉시 BLOCKED_LOGIN
      │                                         notifyAdmin(수동 interactiveLogin 안내)
      │                                         notifyUser("BLOCKED_LOGIN")
      │
      ├── reasonCode=SESSION_EXPIRED ─────────► BLOCKED_LOGIN
      │                                         notifyAdmin(재로그인 안내)
      │                                         notifyUser("BLOCKED_LOGIN")
      │
      └── 기타 실패 ────────────────────────── ► FAILED + notifyUser(reasonCode)
```

**제거된 동작 (v1 → v2):**
- ~~`validateSessionForWorker()` 사전 게이트~~ — 제거됨
- ~~`attemptInteractiveLoginFallback()` GUI 세션 복구~~ — 제거됨
- ~~`captchaFallbackAttempted` 기반 2차 시도~~ — 제거됨

---

## 5. AutoLoginPolicy 설정

`SessionOptions.autoLoginPolicy` 로 제어합니다.

```typescript
const DEFAULT_AUTO_LOGIN_POLICY = {
  enabledInHeadless: false,      // headless에서 자격증명 자동 입력 비활성화
  maxAttemptsPerRun: 1,          // 동일 프로세스 run당 최대 시도 횟수
  maxAttemptsPerSixHours: 1,     // 6시간 내 최대 시도 횟수 (cooldown 연동)
};
```

**headless에서 자격증명 입력을 허용하려면:**

```typescript
const session = await openNaverSession({
  userDataDir: './profiles/myaccount',
  headless: true,
  autoLoginPolicy: { enabledInHeadless: true },
});
```

> ⚠️ 일반 운영에서는 `enabledInHeadless: true` 설정 금지.
> CAPTCHA 루프를 유발하며, 보안 위험이 있습니다.

---

## 6. Cooldown 파일

세션 차단 시 `{userDataDir}/session_cooldown.json` 에 저장됩니다.

```json
{
  "cooldownUntilTs": 1740123456789,
  "lastBlockedAt": "2026-02-22T00:00:00.000Z",
  "lastReason": "CAPTCHA_DETECTED",
  "attemptCount": 1
}
```

cooldown이 활성화된 동안 `ensureLoggedIn`은 즉시 `SessionBlockedError`를 던집니다.

---

## 7. 복구 절차 (BLOCKED_LOGIN 해제)

Worker가 `BLOCKED_LOGIN`으로 전환한 경우:

### Step 1: 인터랙티브 로그인 실행

```bash
# naver-poster 디렉토리에서
node dist/cli/post_to_naver.js --interactiveLogin
```

브라우저 창이 열리면:
1. CAPTCHA / 2FA / 기기인증 완료
2. 네이버 블로그 작성 페이지까지 진행 확인
3. 터미널에서 **Enter** 키 입력

### Step 2: cooldown 초기화

```bash
# 수동으로 cooldown 파일 삭제 (또는 만료 대기)
rm .secrets/*/session_cooldown.json
```

### Step 3: Worker 재개

```bash
node dist/cli/worker.js --resume
```

또는 worker가 이미 실행 중이면 `--resume` 없이 다음 폴링 주기에 자동 감지.

---

## 8. 로그 시그니처

```
[auto_login_policy] enabled_in_headless=false max_attempts_per_run=1 headless=true cooldown_active=false
[auto_login_attempt] attempted=false result=skipped blocked_reason=HEADLESS_CREDENTIAL_LOGIN_DISABLED
[auto_login_attempt] attempted=true headless=false reason_for_attempt=logged_out_form_visible
[auto_login_attempt] result=success login_signal=writer_iframe
[auto_login_attempt] result=failed login_blocked_reason=LOGIN_FORM_STILL_VISIBLE
[worker] CAPTCHA/보안 감지: job=job_xxx → 즉시 BLOCKED_LOGIN (운영자 수동 개입 필요)
```

---

## 9. 관련 파일

| 파일 | 역할 |
|------|------|
| `src/naver/session.ts` | `ensureLoggedIn`, `classifyLoginPhase`, `AutoLoginPolicy` |
| `src/worker/worker_service.ts` | Job 오케스트레이션, BLOCKED_LOGIN 전환 |
| `src/cli/post_to_naver.ts` | CLI 진입점, `--interactiveLogin` 모드 |
| `src/cli/worker.ts` | Worker 진입점, headless 강제 설정 |
| `test_scripts/unit/login_policy_v2.test.ts` | 정책 단위 테스트 4케이스 |
| `test_scripts/unit/captcha_headless_fallback.test.ts` | headless 결정 + CAPTCHA 즉시 차단 테스트 |
