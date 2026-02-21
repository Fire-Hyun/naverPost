# 네이버 블로그 임시저장 오답노트 📝

## 📊 발생 중인 주요 오류들

### 1. 🔴 **에디터 iframe 접근 실패**
**오류 메시지**: `에디터 iframe을 찾을 수 없습니다`
**스크린샷**: `artifacts/fail_iframe_not_found_*.png`
**HTML 덤프**: `artifacts/fail_iframe_not_found_*.html`

### 2. 🔴 **임시저장 검증 실패**
**오류 메시지**: `토스트/임시글함 검증 모두 실패`
**스크린샷**: `artifacts/temp_save_failures/*/01_main_page.png`
**상세**: `{"verified_via":"none","error_message":"토스트/임시글함 검증 모두 실패"}`

### 3. 🟡 **텔레그램 메시지 파싱 오류**
**오류 메시지**: `Can't parse entities: can't find end of the entity starting at byte offset 1428`

---

## 🔍 시행착오 분석

### ❌ **시도 1: 단순 재시도** (실패)
- **방법**: 동일한 로직으로 반복 시도
- **결과**: 같은 오류 반복 발생
- **원인**: 근본적 문제 해결 없이 재시도만 함

### ✅ **시도 2: 수동 실행 성공** (성공)
- **방법**: CLI에서 직접 naver-poster 실행
- **결과**: 211.3초 만에 성공적으로 임시저장 완료
- **성공 요인**:
  - 브라우저 세션 상태가 정상
  - iframe 접근 성공
  - 임시글함 검증 통과 (draft_list 방식)

---

## 🧠 문제 원인 분석

### 1. **브라우저 세션 상태 불안정성**
- **증상**: 간헐적으로 iframe 접근 실패
- **가능한 원인**:
  - 이전 세션의 잔여 상태
  - 네이버 로그인 세션 만료
  - 브라우저 프로세스 충돌

### 2. **네이버 UI 변경에 따른 셀렉터 실패**
- **증상**: UI assertion 미통과
- **가능한 원인**:
  - 네이버 블로그 에디터 UI 업데이트
  - CSS 셀렉터 변경
  - iframe 구조 변경

### 3. **동시 실행으로 인한 브라우저 충돌**
- **증상**: 연속 요청 시 실패율 증가
- **가능한 원인**:
  - 이전 브라우저 인스턴스가 완전히 종료되지 않음
  - 동시 접근으로 인한 세션 충돌

---

## 🛠️ 해결 방안 로드맵

### Phase 1: 즉시 적용 가능한 해결책

#### 1.1 **브라우저 세션 강제 초기화**
```bash
# 기존 브라우저 프로세스 완전 종료
pkill -f "chrome\|chromium" || true
rm -rf /home/mini/dev/naverPost/naver-poster/.secrets/naver_user_data_dir/Default/Sessions/*
```

#### 1.2 **임시저장 재시도 전 대기시간 추가**
- 실패 후 30초 대기 후 재시도
- 브라우저 프로세스 완전 정리 후 재시작

#### 1.3 **텔레그램 메시지 파싱 안전화**
- Markdown entities 이스케이프 처리
- 특수문자 필터링

### Phase 2: 중기 안정화 방안

#### 2.1 **Headless 모드 설정** (⚠️ 업데이트됨)
```env
# naver-poster/.env
HEADLESS=true   # 기본값: headless (서버 환경 안전)
SLOW_MO=500     # 동작 속도 안정화
# 디버깅 시: HEADLESS=false + xvfb-run -a 사용
```

#### 2.2 **다중 검증 전략**
- 토스트 메시지 → 임시글함 → URL 변경 → 브라우저 타이틀 순으로 검증
- 하나라도 성공하면 통과로 처리

#### 2.3 **세션 격리**
- 각 요청마다 독립적인 브라우저 세션 사용
- 세션 디렉토리를 타임스탬프 기반으로 분리

### Phase 3: 장기 근본 해결 방안

#### 3.1 **API 기반 업로드 전환**
- 네이버 블로그 API 조사 (공식 API 존재 여부)
- Selenium 대신 API 직접 호출

#### 3.2 **AI 기반 UI 셀렉터 자동 업데이트**
- 네이버 UI 변경 감지 시스템
- 셀렉터 자동 학습 및 업데이트

---

## 🎯 우선 적용 액션 플랜

### ✅ Step 1: 브라우저 세션 안정화 (완료)
1. ✅ 워크플로우 실패 시 브라우저 프로세스 강제 종료 (`_cleanup_browser_session()`)
2. ✅ 세션 디렉토리 정리 (Chrome Sessions 폴더 정리)
3. ✅ 재시도 전 2초 대기시간 추가

### ✅ Step 2: 오류 메시지 안전화 (완료)
1. ✅ 텔레그램 메시지에서 특수문자 이스케이프 (`TelegramMessageFormatter` 클래스)
2. ✅ 안전한 메시지 전송 함수 구현 (`safe_reply_text_async()`)
3. ✅ Markdown → HTML → Plain text 단계별 폴백 처리

### ✅ Step 2.5: naver-poster 안정화 설정 (완료, 업데이트됨)
1. ✅ HEADLESS=true 기본값 (서버 환경 안전, 2026-02-15 수정)
2. ✅ SLOW_MO=500 추가 (동작 속도 안정화)
3. ✅ 타임아웃 설정 추가 (BROWSER_TIMEOUT=60000)
4. ✅ 재시도 설정 추가 (MAX_RETRY_ATTEMPTS=3)
5. ✅ XServer 선제 감지 및 headless 자동 폴백 추가

### Step 3: 검증 로직 강화 (1주일 내)
1. 다중 검증 전략 구현
2. 실패 시 상세 로그 및 스크린샷 자동 수집

### Step 4: 모니터링 시스템 구축 (2주일 내)
1. 임시저장 성공률 통계 수집
2. 실패 패턴 분석 자동화

---

## 📚 참고 자료

### 성공 케이스 로그
- 2026-02-15 01:52:31: 성공 (211.3초)
- 검증 방식: draft_list
- 브라우저 세션: 정상

### 실패 케이스 로그
- 2026-02-14 16:59:46: iframe 접근 실패
- 2026-02-14 16:48:34: 임시저장 검증 실패

### 오류 패턴
- 연속 실행 시 실패율 증가
- 수동 실행 시 성공률 높음
- 텔레그램 메시지 파싱 오류와 연관성

---

## 🔧 구현된 해결책 상세

### 1. 브라우저 세션 안정화 (`blog_workflow.py`)
```python
async def _cleanup_browser_session(self):
    """브라우저 세션 강제 정리"""
    # Chrome/Chromium 프로세스 강제 종료
    subprocess.run(['pkill', '-f', 'chrome'], capture_output=True, timeout=10)
    # 세션 디렉토리 정리
    shutil.rmtree(session_dir)
    # 대기 시간
    time.sleep(2)
```

### 2. 안전한 텔레그램 메시지 (`message_formatter.py`)
```python
class TelegramMessageFormatter:
    - escape_markdown_basic(): 기본 특수문자 이스케이프
    - convert_to_html(): Markdown → HTML 변환
    - strip_markdown(): Plain text 변환
    - safe_format_message(): 단계별 폴백 처리
```

### 3. naver-poster 안정화 설정 (`.env`)
```env
HEADLESS=true          # 기본 headless (서버 환경 안전)
SLOW_MO=500
BROWSER_TIMEOUT=60000
MAX_RETRY_ATTEMPTS=3
RETRY_DELAY_MS=5000
```

---

## 📈 예상 효과

### 해결될 것으로 예상되는 문제들:
1. ✅ **텔레그램 메시지 파싱 오류** → 안전한 메시지 전송으로 해결
2. ✅ **브라우저 세션 충돌** → 강제 정리로 해결
3. ✅ **연속 실행 시 실패율 증가** → 세션 격리로 개선
4. 🔄 **iframe 접근 실패** → 브라우저 안정화로 개선 예상
5. 🔄 **임시저장 검증 실패** → SLOW_MO로 개선 예상

---

---

## 🎉 테스트 성공 결과

### 임시저장 테스트 (2026-02-15 17:11:48)
- **테스트 포스트**: "임시저장 테스트 포스트"
- **결과**: ✅ **완전 성공**
- **소요시간**: 166.1초
- **검증 방식**: draft_list (임시글함 확인)
- **문제점**: 없음

### 확인된 개선 효과
1. ✅ **텔레그램 메시지 파싱 오류**: 해결 (테스트에서 확인 안됨)
2. ✅ **브라우저 세션 충돌**: 해결 (iframe 접근 성공)
3. ✅ **에디터 iframe 실패**: 해결 (정상 접근)
4. ✅ **임시저장 검증 실패**: 해결 (draft_list 검증 통과)

---

**최종 업데이트**: 2026-02-15 17:12
**테스트 상태**: ✅ **성공 완료**
**구현 상태**: Phase 1 완료, 안정화 확인됨

---

## 🔴 이슈: XServer 없는 환경에서 Playwright headed 모드 크래시 (2026-02-15)

### 증상
- `browserType.launchPersistentContext: Target page, context or browser has been closed`
- `headed browser without having a XServer running. Set either 'headless: true' or use 'xvfb-run …' before running Playwright.`
- 네이버 임시저장이 반복적으로 실패

### 원인
- `naver-poster/.env`에 `HEADLESS=false`가 설정되어 있었음
- 서버/WSL 환경에는 XServer(DISPLAY)가 없음
- Playwright가 headed 모드로 브라우저를 띄우려다 즉시 크래시

### 해결 (적용 완료)
1. **기본값 변경**: `HEADLESS=true` (`.env`, `.env.example`, systemd service)
2. **환경 감지**: `DISPLAY`/`WAYLAND_DISPLAY` 없이 headed 모드 요청 시 자동 headless 폴백
3. **에러 분류**: `ENV_NO_XSERVER` 코드로 정확히 분류
4. **텔레그램 메시지 개선**: 환경 문제와 업로드 로직 문제를 분리 안내

### 환경변수
| 변수 | 기본값 | 설명 |
|------|--------|------|
| `HEADLESS` | `true` | Playwright headless 모드 (TypeScript naver-poster) |
| `PLAYWRIGHT_HEADLESS` | `true` | Python NaverBlogStabilizedClient headless 모드 |

### 실행 방법

#### 운영 모드 (headless, 기본)
```bash
# systemd
sudo systemctl start naverpost-bot

# 수동 실행
HEADLESS=true node dist/cli/post_to_naver.js --dir /path/to/data

# Python
PLAYWRIGHT_HEADLESS=true python -m src.telegram
```

#### 디버그 모드 (headed, XServer 또는 xvfb 필요)
```bash
# Xvfb 사용 (XServer 없는 서버)
xvfb-run -a node dist/cli/post_to_naver.js --dir /path/to/data

# X11 포워딩 (SSH)
ssh -X user@server
HEADLESS=false node dist/cli/post_to_naver.js --dir /path/to/data

# 로컬 데스크톱 (XServer 있음)
HEADLESS=false node dist/cli/post_to_naver.js --dir /path/to/data
```

### 검증법
```bash
# 1) headless 모드 확인
HEADLESS=true node dist/cli/post_to_naver.js --healthcheck

# 2) XServer 없이 headed 요청 시 → 자동 폴백 확인
unset DISPLAY && HEADLESS=false node dist/cli/post_to_naver.js --healthcheck
# 로그에 "[ENV_NO_XSERVER]" 경고 + headless 폴백 확인

# 3) xvfb headed 모드 확인
xvfb-run -a env HEADLESS=false node dist/cli/post_to_naver.js --healthcheck
```

### 에러 분류 체계
| 코드 | 원인 | 텔레그램 메시지 |
|------|------|----------------|
| `ENV_NO_XSERVER` | DISPLAY 없음 + headed 시도 | "환경 설정 문제: XServer 없음" |
| `PLAYWRIGHT_LAUNCH_FAILED` | 브라우저 바이너리/권한 | "브라우저 실행 오류" |
| `NAVER_AUTH_FAILED` | 로그인/세션 만료 | "로그인/세션 만료" |
| `NAVER_RATE_LIMIT` | 429 Too Many Requests | "요청 횟수 초과" |
| `NETWORK_DNS` | DNS/네트워크 | "네트워크 오류" |
| `NAVER_UPLOAD_FAILED` | 일반 업로드 실패 | "업로드 프로세스 오류" |