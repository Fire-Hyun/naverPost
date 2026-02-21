# Observability Guide — 네이버 포스터 구조화 로그

세션/로그인/에디터 파이프라인의 관측성(Observability) 문서입니다.

---

## 1. Stage 정의표

| Stage 키 (`stage` 필드) | 이벤트 이름 | 발생 위치 |
|---|---|---|
| `SESSION_INIT` | `session_init` | `createPersistentSession()` 완료 직후 |
| `LOGIN_CHECK` | `login_check` | `classifyLoginPhase()` 직후 |
| `AUTO_LOGIN_ATTEMPT` | `auto_login_attempt` | 자동 로그인 각 케이스 |
| `SESSION_PERSIST` | `session_persist` | `persistSessionState()` 성공/실패 |
| `DONE` | `outcome_summary` | `emitReport()` 직전 (성공/실패 양쪽) |

---

## 2. 이벤트 로그 스키마

모든 구조화 로그는 다음 공통 필드를 가집니다:

```json
{
  "run_id": "r-20260222-abcd",
  "job_id": "job-1234",
  "stage": "SESSION_INIT"
}
```

`job_id`는 `NAVER_JOB_KEY` 환경변수가 설정된 경우에만 포함됩니다.

### session_init

```json
{
  "run_id": "r-20260222-abcd",
  "stage": "SESSION_INIT",
  "profile_dir": "/home/user/.naver_profile",
  "context_mode": "persistent",
  "headless": true,
  "storage_state_exists": true,
  "storage_state_load_reason": null,
  "storage_state_cookie_count": 12,
  "storage_state_age_seconds": 3600,
  "singleton_lock_found": false,
  "elapsed_ms": 1850
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `profile_dir` | string | Playwright 프로필 디렉토리 경로 |
| `context_mode` | `"persistent"` \| `"new_context"` | 브라우저 컨텍스트 모드 |
| `headless` | boolean | 헤드리스 여부 |
| `storage_state_exists` | boolean | storageState 파일 존재 여부 |
| `storage_state_load_reason` | string \| null | 로드 실패 시 이유 |
| `storage_state_cookie_count` | number | 로드된 쿠키 수 |
| `storage_state_age_seconds` | number | storageState 파일 경과 시간 (-1: 미존재) |
| `singleton_lock_found` | boolean | Chrome SingletonLock 파일 존재 여부 |
| `elapsed_ms` | number | 브라우저 런치 소요 시간 (ms) |

---

### login_check

```json
{
  "run_id": "r-20260222-abcd",
  "stage": "LOGIN_CHECK",
  "url": "https://blog.naver.com/write",
  "login_phase": "LOGGED_OUT",
  "signal": "login_form_visible",
  "cooldown_active": false,
  "cooldown_remaining_sec": 0,
  "consecutive_failures": 0,
  "headless": true
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `login_phase` | `"LOGGED_IN"` \| `"LOGGED_OUT"` \| `"CHALLENGE_DETECTED"` \| `"AMBIGUOUS"` | 로그인 단계 |
| `signal` | string | detectLoginState 시그널 |
| `cooldown_active` | boolean | 쿨다운 활성 여부 |
| `cooldown_remaining_sec` | number | 쿨다운 남은 시간 (초) |
| `consecutive_failures` | number | 연속 실패 횟수 |

---

### auto_login_attempt

```json
{
  "run_id": "r-20260222-abcd",
  "stage": "AUTO_LOGIN_ATTEMPT",
  "attempted": true,
  "result": "success",
  "skipped_reason": null,
  "blocked_reason": null,
  "duration_ms": 3200,
  "headless": false,
  "url": "https://nid.naver.com/nidlogin.login"
}
```

| `result` 값 | 의미 |
|---|---|
| `"pending"` | 로그인 시도 시작 |
| `"success"` | 로그인 성공 |
| `"failed"` | 로그인 실패 (blocked_reason 참고) |
| `"blocked"` | 도전(captcha/약관) 감지로 차단 |
| `"skipped"` | 헤드리스 정책/최대시도 초과로 건너뜀 |

---

### session_persist

```json
{
  "run_id": "r-20260222-abcd",
  "stage": "SESSION_PERSIST",
  "cookie_count": 12,
  "file_size_bytes": 4096,
  "success": true
}
```

실패 케이스:

```json
{
  "run_id": "r-20260222-abcd",
  "stage": "SESSION_PERSIST",
  "success": false,
  "error": "Error: EACCES: permission denied"
}
```

---

### outcome_summary

```json
{
  "run_id": "r-20260222-abcd",
  "stage": "DONE",
  "final_status": "SUCCESS",
  "final_reason_code": null,
  "post_dir": "blog_result_20260222",
  "total_elapsed_ms": 45200
}
```

---

## 3. 운영 grep 예시

```bash
# 특정 run_id의 모든 구조화 로그 추적
grep '"run_id":"r-20260222-abcd"' logs/20260222/naver.log | jq .

# LOGIN_CHECK 단계만 필터링
grep 'login_check:' logs/20260222/naver.log

# 실패한 auto_login_attempt 검색
grep 'auto_login_attempt:' logs/20260222/naver.log | \
  grep '"result":"failed"'

# 쿨다운 활성 상태 검색
grep 'login_check:' logs/20260222/naver.log | \
  python3 -c "import sys,json; [print(json.loads(l.split('login_check: ')[1])) for l in sys.stdin if 'cooldown_active\":true' in l]"

# outcome_summary 성공/실패 집계
grep 'outcome_summary:' logs/20260222/naver.log | \
  grep -oP '"final_status":"[^"]*"' | sort | uniq -c
```

---

## 4. 아티팩트 경로 규칙

```
logs/
  YYYYMMDD/
    run_<NAVER_RUN_ID>/
      <stage>/          ← getRunArtifactDir(stage) 반환 경로
        screenshot.png
        page.html
        ...
    naver.log           ← 일별 롤오버 텍스트 로그
```

`getRunArtifactDir('EDITOR_READY')` 호출 시:
- `NAVER_RUN_ID=r-abc` → `logs/20260222/run_r-abc/EDITOR_READY/`
- `NAVER_RUN_ID` 미설정 → `logs/20260222/run_norun/EDITOR_READY/`

---

## 5. 로그 노이즈 축소 목록

| 이전 패턴 | 변경 후 |
|---|---|
| `[session]` 텍스트 5줄 (backend/cookies_loaded/storage_state_loaded 등) | 기존 유지 + `session_init` 구조화 1줄 병행 |
| `[auto_login_attempt]` 텍스트 로그 (log.error/warn) | `auto_login_attempt` 구조화 로그로 교체 |
| timeout_report.json에 run_id 없음 | `run_id`, `job_id` 필드 추가 |

---

## 6. 샘플 로그

### 성공 시나리오

```
[INFO][naver] session_init: {"run_id":"r-abc","stage":"SESSION_INIT","profile_dir":"/home/user/.np","context_mode":"persistent","headless":true,"storage_state_exists":true,"storage_state_load_reason":null,"storage_state_cookie_count":12,"storage_state_age_seconds":7200,"singleton_lock_found":false,"elapsed_ms":1823}
[INFO][naver] login_check: {"run_id":"r-abc","stage":"LOGIN_CHECK","url":"https://blog.naver.com/PostWriteForm.naver","login_phase":"LOGGED_IN","signal":"editor_ready","cooldown_active":false,"cooldown_remaining_sec":0,"consecutive_failures":0,"headless":true}
[INFO][naver] outcome_summary: {"run_id":"r-abc","stage":"DONE","final_status":"SUCCESS","final_reason_code":null,"post_dir":"my_post_dir","total_elapsed_ms":42100}
```

### 차단(CAPTCHA) 시나리오

```
[INFO][naver] login_check: {"run_id":"r-xyz","stage":"LOGIN_CHECK","url":"https://nid.naver.com/login/captcha","login_phase":"CHALLENGE_DETECTED","signal":"captcha_page","cooldown_active":false,"cooldown_remaining_sec":0,"consecutive_failures":2,"headless":true}
[INFO][naver] auto_login_attempt: {"run_id":"r-xyz","stage":"AUTO_LOGIN_ATTEMPT","attempted":false,"skipped_reason":null,"result":"blocked","blocked_reason":"CAPTCHA_DETECTED","duration_ms":0,"headless":true,"url":"https://nid.naver.com/login/captcha"}
[INFO][naver] outcome_summary: {"run_id":"r-xyz","stage":"DONE","final_status":"FAILED","final_reason_code":"CAPTCHA_DETECTED","post_dir":"my_post_dir","total_elapsed_ms":8300}
```

### 타임아웃 시나리오

```
[INFO][naver] session_init: {"run_id":"r-t01","stage":"SESSION_INIT","profile_dir":"/tmp/np","context_mode":"persistent","headless":true,"storage_state_exists":false,"storage_state_load_reason":"file_not_found","storage_state_cookie_count":0,"storage_state_age_seconds":-1,"singleton_lock_found":true,"elapsed_ms":3200}
[INFO][naver] login_check: {"run_id":"r-t01","stage":"LOGIN_CHECK","url":"https://blog.naver.com/write","login_phase":"LOGGED_OUT","signal":"login_form_visible","cooldown_active":false,"cooldown_remaining_sec":0,"consecutive_failures":0,"headless":true}
[INFO][naver] auto_login_attempt: {"run_id":"r-t01","stage":"AUTO_LOGIN_ATTEMPT","attempted":true,"result":"pending","skipped_reason":null,"blocked_reason":null,"duration_ms":0,"headless":true,"url":"https://nid.naver.com/nidlogin.login","reason_for_attempt":"logged_out_form_visible"}
[INFO][naver] auto_login_attempt: {"run_id":"r-t01","stage":"AUTO_LOGIN_ATTEMPT","attempted":true,"result":"failed","skipped_reason":null,"blocked_reason":"LOGIN_FORM_STILL_VISIBLE","duration_ms":18500,"headless":true,"url":"https://nid.naver.com/nidlogin.login"}
[INFO][naver] outcome_summary: {"run_id":"r-t01","stage":"DONE","final_status":"FAILED","final_reason_code":"SESSION_BLOCKED_LOGIN_STUCK","post_dir":"my_post_dir","total_elapsed_ms":32000}
```
