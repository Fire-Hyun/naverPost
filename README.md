# 🤖 네이버 블로그 포스팅 자동화 시스템

![Phase](https://img.shields.io/badge/Phase%204-네이버%20자동%20포스팅%20진행중-yellow)
![AI](https://img.shields.io/badge/AI-GPT--4%20Powered-blue)
![Quality](https://img.shields.io/badge/Quality-Auto%20Verified-success)
![Code](https://img.shields.io/badge/Code-9000%2B%20Lines-orange)
![AntiHallucination](https://img.shields.io/badge/Anti--Hallucination-Enabled-critical)
![Telegram](https://img.shields.io/badge/Telegram-Bot%20Ready-blue)
![Playwright](https://img.shields.io/badge/Playwright-Blog%20Automation-brightgreen)

사용자의 실제 사진과 경험담을 기반으로 **OpenAI GPT-4**를 활용해 고품질 블로그 포스트를 자동 생성하고, **실시간 품질 검증**을 통해 네이버 정책을 준수하는 자연스러운 블로그 글을 제공하는 완전 자동화 시스템입니다.

## ⚡ 현재 이용 가능한 주요 기능

🌟 **AI 블로그 글 완전 자동 생성** - OpenAI GPT-4 기반
📊 **실시간 품질 검증** - 네이버 정책 준수 자동 확인
#️⃣ **지능형 해시태그 생성** - 카테고리별 맞춤 태그
🏪 **지능형 상호명 보정** - 위치 기반 자동 상호명 검증 및 보정
🚀 **완전 자동화 워크플로우** - 데이터 입력부터 네이버 임시저장까지 원클릭
📅 **체계적 데이터 관리** - 날짜별 포스팅 관리
🎯 **개인 경험 보장** - 60% 이상 개인 경험 비율 자동 검증
🤖 **텔레그램 봇 인터페이스** - 모바일에서 간편하게 블로그 작성

## 🚀 현재 구현 상태

**Phase 1 (기본 인프라): 100% 완료 ✅**
- ✅ 완전한 웹 인터페이스 구현
- ✅ 이미지 업로드 시스템 작동
- ✅ 사용자 경험 데이터 수집
- ✅ 파일 저장 및 메타데이터 관리
- ✅ API 엔드포인트 구현
- ✅ 로깅 및 예외 처리 시스템

**Phase 2 (AI 콘텐츠 생성): 100% 완료 🎉**
- ✅ OpenAI GPT-4 기반 블로그 글 자동 생성
- ✅ 해시태그 자동 생성 및 정제 시스템
- ✅ 사용자 경험 중심의 자연스러운 글 작성
- ✅ 콘텐츠 구조 최적화
- ✅ 날짜 기반 데이터 관리 시스템
- ✅ **입력 충분성 체크 & 보강 모드** — 입력이 부족하면 네이버 블로그 검색으로 자동 보강
- ✅ **사실 날조 방지 프롬프트** — 입력에 없는 가격/영업시간/주차 등 AI 임의 단정 차단
- ✅ **이미지 마커 번호화** — `[사진1]`~`[사진N]` 장면 전환 매핑, 연속 사진 방지
- ✅ **날조 사실 위험 감지** — 품질 메트릭에서 자동 감점

**Phase 3 (품질 검증 시스템): 100% 완료 🎉**
- ✅ 개인 경험 비율 자동 검증 (60% 이상 개인 경험 보장)
- ✅ 키워드 밀도 및 분포 분석 (2% 이하 자연스러운 배치)
- ✅ 네이버 저품질 알고리즘 회피 로직
- ✅ AI 전형 문구 탐지 및 필터링
- ✅ 실시간 품질 점수 계산 (통합 스코어링 시스템)
- ✅ 종합 품질 보고서 및 개선 권장사항

**Phase 3.5 (텔레그램 봇 통합): 100% 완료 🤖**
- ✅ 완전한 텔레그램 봇 구현 (1,400+ 라인)
- ✅ 다단계 대화형 인터페이스
- ✅ 기존 AI 파이프라인 완벽 통합
- ✅ 이미지 업로드 및 검증 시스템
- ✅ 세션 관리 및 보안 기능
- ✅ 실시간 품질 검증 연동

**Phase 4 (통합 자동화 워크플로우): 95% 완료 🎉**
- ✅ 완전 통합 워크플로우 서비스 구현 (`BlogWorkflowService`)
- ✅ 데이터 검증 → AI 생성 → 품질 검증 → 네이버 임시저장 파이프라인
- ✅ TypeScript + Playwright 기반 네이버 자동화 (`naver-poster/`)
- ✅ 실시간 진행상황 모니터링 (SSE 스트리밍)
- ✅ 텔레그램 봇 완전 자동화 통합
- ✅ 웹 API 엔드포인트 (/api/workflow/*)
- ✅ 새로운 웹 인터페이스 (/static/workflow.html)
- 🔄 naver-poster와 Python 서비스 연동 최종 검증

**현재 사용 가능한 기능:**
- 🚀 **완전 자동화 워크플로우** (입력 → 검증 → 생성 → 네이버 임시저장)
- 🌟 **AI 블로그 글 자동 생성** (OpenAI GPT-4 활용)
- 🌟 **지능형 해시태그 자동 생성** (카테고리별 맞춤 태그)
- 🏪 **위치 기반 상호명 보정** (네이버/카카오 API 연동)
- 📊 **실시간 품질 검증** (네이버 정책 준수 확인)
- 🤖 **텔레그램 봇 완전 자동화** (모바일 최적화)
- 🌐 **새로운 웹 워크플로우 인터페이스** (/static/workflow.html)
- ✅ 실시간 진행상황 모니터링 (SSE 스트리밍)
- ✅ 날짜별 체계적 데이터 관리

## 🎯 주요 특징

- **🤖 완전 자동화된 AI 블로그 생성**: OpenAI GPT-4 기반으로 사용자의 실제 경험을 자연스러운 블로그 글로 변환
- **🎯 개인 경험 중심 보장**: 60% 이상 개인 경험 비율 자동 검증으로 진정성 있는 콘텐츠 보장
- **🛡️ 네이버 저품질 방지**: 네이버 블로그의 저품질 판정 알고리즘을 정교하게 회피하는 시스템
- **🏪 지능형 상호명 보정**: 네이버/카카오 지역검색 API를 활용한 위치 기반 상호명 자동 검증 및 보정
- **📍 위치 정보 자동 추출**: 이미지 EXIF GPS 데이터 및 텔레그램 위치 공유를 통한 자동 위치 인식
- **#️⃣ 지능형 해시태그 생성**: 카테고리, 위치, 감정을 분석한 맞춤형 해시태그 자동 생성 및 정제
- **📊 실시간 품질 스코어링**: 네이버 정책 준수, 키워드 품질, 개인 진정성을 종합한 실시간 품질 점수
- **📅 체계적 데이터 관리**: 날짜별 디렉토리 구조로 체계적인 포스팅 데이터 관리
- **🌐 직관적 웹 인터페이스**: 드래그앤드롭 이미지 업로드와 간편한 경험 정보 입력
- **🔄 배치 처리 지원**: 여러 포스팅을 한 번에 생성하고 품질 검증

## 🏗️ 시스템 아키텍처

### 구현 완료된 모듈 ✅
```
naverPost/
├── src/
│   ├── web/                    ✅ FastAPI 웹 인터페이스
│   │   ├── app.py              ✅ 메인 애플리케이션 (5.2KB)
│   │   ├── routes/             ✅ API 엔드포인트
│   │   │   └── upload.py       ✅ 이미지 업로드 API (8.0KB)
│   │   └── static/             ✅ 프론트엔드
│   │       └── index.html      ✅ 반응형 웹 인터페이스 (16KB)
│   ├── content/                🎉 AI 콘텐츠 생성 엔진 (Phase 2)
│   │   ├── models.py           ✅ Pydantic 데이터 모델 (10.7KB)
│   │   ├── blog_generator.py   🎉 블로그 글 생성 로직 (1100+ 라인)
│   │   │                       ├─ 해시태그 자동 생성 및 정제
│   │   │                       ├─ OpenAI GPT-4 블로그 글 생성
│   │   │                       ├─ 입력 충분성 체크 & 보강 모드 발동
│   │   │                       ├─ 사실 날조 방지 프롬프트 시스템
│   │   │                       ├─ [사진N] 번호화 마커 & 연속 사진 방지
│   │   │                       ├─ 날조 사실 위험 감지 메트릭
│   │   │                       └─ 날짜 기반 배치 처리
│   │   ├── review_collector.py ✅ 네이버 블로그 검색 API 리뷰 스니펫 수집 (신규)
│   │   │                       ├─ 상호명+지역 검색 → 공통 키워드 추출
│   │   │                       ├─ 수치/가격 등 오류 리스크 표현 자동 제외
│   │   │                       └─ "후기에서 자주 보임" 형태 자연어 스니펫 반환
│   │   └── experience_processor.py ✅ 사용자 경험 처리
│   ├── quality/                🎉 품질 검증 모듈 (Phase 3)
│   │   ├── content_checker.py  🎉 개인 경험 비율 자동 검증 (530 라인)
│   │   ├── naver_validator.py  🎉 네이버 저품질 방지 알고리즘
│   │   ├── keyword_analyzer.py 🎉 키워드 밀도 분석
│   │   └── unified_scorer.py   🎉 통합 품질 점수 계산 (450 라인)
│   ├── storage/                ✅ 데이터 저장 관리
│   │   └── data_manager.py     ✅ 파일 및 메타데이터 관리 (13KB)
│   ├── config/                 ✅ 설정 관리
│   │   └── settings.py         ✅ 환경변수 및 설정 (5.3KB)
│   ├── utils/                  ✅ 공통 유틸리티
│   │   ├── logger.py           ✅ 구조화된 로깅 (1.4KB)
│   │   ├── exceptions.py       ✅ 전용 예외 처리 (6.5KB)
│   │   └── date_manager.py     🎉 날짜 기반 디렉토리 관리 (343 라인)
│   ├── external/               🎉 외부 정보 수집
│   │   └── info_collector.py   ✅ 보조 정보 수집 모듈
│   ├── telegram/               🤖 텔레그램 봇 인터페이스 (새로운!)
│   │   ├── bot.py              ✅ 메인 봇 애플리케이션 (420 라인)
│   │   ├── handlers/           ✅ 대화 및 이미지 핸들러
│   │   │   ├── conversation.py ✅ 다단계 대화 처리 (190 라인)
│   │   │   ├── image_handler.py ✅ 이미지 업로드 처리 (140 라인)
│   │   │   └── utils.py        ✅ 유틸리티 함수 (120 라인)
│   │   ├── models/             ✅ 세션 및 응답 모델
│   │   │   ├── session.py      ✅ 세션 상태 관리 (140 라인)
│   │   │   └── responses.py    ✅ 응답 템플릿 (200 라인)
│   │   └── config/             ✅ 봇 전용 설정
│   │       └── telegram_settings.py ✅ 설정 검증 (150 라인)
│   └── naver/                  🔄 (레거시 - naver-poster로 대체)
├── naver-poster/               🚀 네이버 블로그 자동 포스팅 (Phase 4 - TypeScript)
│   ├── src/
│   │   ├── cli/
│   │   │   └── post_to_naver.ts 🚀 CLI 진입점 (7단계 워크플로우)
│   │   ├── naver/
│   │   │   ├── editor.ts       🚀 에디터 제어 (iframe EditorContext 패턴)
│   │   │   ├── session.ts      ✅ 세션 관리 (Persistent Context)
│   │   │   ├── place.ts        🚀 장소 검색/첨부
│   │   │   └── exif.ts         ✅ EXIF GPS 추출
│   │   └── utils/
│   │       ├── logger.ts       ✅ 컬러 로깅 + 실패 스크린샷
│   │       └── parser.ts       ✅ blog_result.md 파서 (10개 테스트 통과)
│   ├── tests/
│   │   └── parser.test.ts      ✅ 유닛 테스트 (10/10 통과)
│   ├── package.json            ✅ Playwright, Commander 등
│   └── tsconfig.json           ✅ ES2020 + DOM
├── data/                       ✅ 생성 데이터 저장소 (yyyyMMdd(상호명) 형식)
├── uploads/                    ✅ 사용자 업로드 파일
├── templates/                  ✅ 글 생성 템플릿
├── scripts/                    ✅ 테스트/검증/디버그 스크립트
│   ├── test_structure.py       ✅ 구조 검증 스크립트
│   ├── test_generate.py        ✅ 종합 생성 테스트
│   ├── test_blog_generation.py ✅ 블로그 생성 테스트
│   ├── test_quality_validation.py ✅ 품질 검증 테스트
│   ├── test_keyword_analysis.py ✅ 키워드 분석 테스트
│   ├── test_content_checker.py ✅ 콘텐츠 검증 테스트
│   ├── test_unified_scorer.py  ✅ 통합 스코어링 테스트
│   └── test_telegram_integration.py 🤖 텔레그램 통합 테스트
├── etc_scripts/                ✅ 운영(cron/systemd/배치) 스크립트
│   ├── run_telegram_bot.py     🤖 텔레그램 봇 실행 엔트리포인트
│   ├── start_bot_with_health_check.py ✅ 시작 전 DNS/네트워크 헬스체크
│   ├── monitor_bot_health.py   ✅ 주기 헬스 모니터링
│   ├── fix_dns_issues.py       ✅ DNS 진단/복구
│   ├── restart_telegram.sh ✅ 텔레그램 봇 재기동
│   ├── restart_web.sh          ✅ 웹 서버 재기동
│   ├── naverpost-bot.service   ✅ systemd 서비스 파일
│   └── install-systemd-service.sh ✅ 서비스 설치 스크립트
├── maintenance/                ✅ 일회성 fix/migrate 스크립트 보관
│   ├── fix_wsl_dns_and_restart_bot.sh
│   ├── fix_telegram_bot.sh
│   └── rename_directories.py
├── tests/                      ✅ (pytest 등) 테스트 디렉토리
├── requirements.txt            ✅ 의존성 목록 (텔레그램 봇 포함)
├── .env.example                ✅ 환경설정 템플릿
└── (기타 파일들)
```

### 남은 구현 작업 📋
```
naver-poster/                   📋 네이버 블로그 자동 포스팅 (Phase 4 - 75% 완료)
├── 장소 선택 셀렉터 미세조정    🔄 단일 결과 UI 대응
├── 임시저장 실전 테스트         🔄 실제 임시저장 동작 검증
└── 에러 복구/재시도 로직        📋 구현 예정
```

## 🚀 설치 및 설정

### 1. 환경 요구사항

- Python 3.8+
- Chrome 브라우저 (Selenium 자동화용)
- OpenAI API 키
- 네이버 계정

### 2. 설치

```bash
# 저장소 클론
git clone <repository-url>
cd naverPost

# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 3. 환경설정

```bash
# .env 파일 생성
cp .env.example .env
```

`.env` 파일을 편집하여 필수 설정값을 입력하세요:

```env
# OpenAI API 설정
OPENAI_API_KEY=your_openai_api_key_here

# 네이버 계정 정보
NAVER_USERNAME=your_naver_username
NAVER_PASSWORD=your_naver_password
NAVER_BLOG_URL=https://blog.naver.com/your_blog_id

# 웹 서버 설정
WEB_PORT=8000
WEB_DEBUG=true

# Telegram Bot 설정 (선택사항)
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_ADMIN_USER_ID=123456789
TELEGRAM_ALLOW_PUBLIC=false
TELEGRAM_SESSION_TIMEOUT=1800

# 장소 검색 API 설정 (상호명 보정용)
PLACE_SEARCH_PROVIDER=naver  # "naver" 또는 "kakao"

# 네이버 지역검색 API (provider가 naver인 경우 필수)
NAVER_CLIENT_ID=your_naver_client_id
NAVER_CLIENT_SECRET=your_naver_client_secret

# 카카오 로컬 API (provider가 kakao인 경우 필수)
KAKAO_REST_API_KEY=your_kakao_rest_api_key
```

### 4. 실행

#### 웹 서버 실행
```bash
# 프로젝트 구조 검증 (선택사항)
python3 scripts/test_structure.py

# 웹 서버 시작
uvicorn src.web.app:app --host 0.0.0.0 --port 8000 --reload

# 또는 Python 모듈로 실행
python3 -m src.web.app
```

#### Telegram Bot 실행 🤖
```bash
# Telegram Bot 의존성 설치
pip install python-telegram-bot==20.7 aiohttp>=3.8.0

# Telegram Bot 실행
python3 etc_scripts/run_telegram_bot.py

# 또는 모듈로 실행
python3 -m src.telegram
```

### 4-1. 웹 서버 재기동(스크립트)

개발 중 서버를 빠르게 재기동하려면 아래 스크립트를 사용하세요. (WSL/Linux)

```bash
./etc_scripts/restart_web.sh
```

- 기본 포트는 `.env`의 `WEB_PORT`(기본 8000)를 따릅니다.
- 로그는 `logs/webserver.out`에 저장됩니다.

브라우저에서 `http://localhost:8000`에 접속하여 웹 인터페이스를 사용할 수 있습니다.

### 4-2. 스크립트 디렉토리 정책

- 운영/자동실행: `etc_scripts/`
- 테스트/검증: `scripts/`
- 일회성 보수: `maintenance/`

경로 변경 내역과 crontab 예시는 `docs/scripts.md`를 참고하세요.

### 5-1. 새로운 자동화 워크플로우 웹 인터페이스 🚀

**완전 자동화된 웹 인터페이스**를 통해 데이터 입력부터 네이버 임시저장까지 원클릭으로 처리할 수 있습니다:

```bash
# 웹 서버 실행 후 접속
http://localhost:8000/static/workflow.html
```

#### 🎯 새로운 웹 인터페이스 주요 기능:

- **📝 완전한 입력 폼**: 날짜, 카테고리, 상호명, 감상평 등 모든 필드 지원
- **🔍 실시간 입력 검증**: 감상평 글자수, 필수 필드 등 즉시 확인
- **📊 실시간 진행상황**: Server-Sent Events로 워크플로우 진행률 실시간 표시
- **📈 품질 점수 시각화**: 생성된 블로그의 품질 점수를 그래프로 확인
- **📤 네이버 업로드 상태**: 임시저장 성공/실패 상태 즉시 확인
- **⏹️ 취소 기능**: 진행 중인 워크플로우 언제든 취소 가능

### 5. 기본 기능 테스트

웹 서버가 실행된 후 다음 기능들을 테스트할 수 있습니다:

- **메인 페이지**: `http://localhost:8000`
- **헬스 체크**: `http://localhost:8000/health`
- **API 문서**: `http://localhost:8000/docs` (FastAPI 자동 생성)

## 🤖 Telegram Bot 인터페이스 (새로운!)

### 텔레그램으로 블로그 포스팅 자동 생성하기 ✨

웹 인터페이스 외에도 **텔레그램 봇**을 통해 블로그 포스팅을 생성할 수 있습니다. 모든 기존 AI 파이프라인과 품질 검증 시스템을 그대로 활용하면서, 편리한 모바일 환경에서 블로그를 작성할 수 있습니다.

#### 🚀 텔레그램 봇 설정

1. **봇 생성**
   - 텔레그램에서 [@BotFather](https://t.me/botfather)와 대화
   - `/newbot` 명령으로 새 봇 생성
   - 봇 토큰 복사

2. **환경 설정**
   ```bash
   # .env 파일에 추가
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTuVwxyZ
   TELEGRAM_ADMIN_USER_ID=123456789  # (선택) 특정 사용자만 허용
   TELEGRAM_ALLOW_PUBLIC=false       # (선택) 공개 접근 허용 여부
   ```

3. **봇 실행**
   ```bash
   python3 etc_scripts/run_telegram_bot.py
   ```

#### 📱 사용법

1. **시작**: `/start` - 새 블로그 포스팅 작성 시작
2. **날짜 입력**: `20260212` 또는 `오늘`
3. **카테고리 선택**: 제공되는 키보드에서 선택
4. **상호명 입력**: 방문한 업체명 (예: "스타벅스", "스타벅스 강남점")
5. **사진 업로드**: 여러 장 업로드 가능 (GPS 정보 자동 추출)
6. **감상평 작성**: 최소 50자 이상의 개인 경험
7. **추가 내용**: 참고할 추가 정보 (선택사항)
8. **생성 완료**: `/done` - 자동으로 블로그 글 생성

#### 🎯 주요 기능

- **✅ 기존 AI 파이프라인 완전 호환**: 웹 인터페이스와 동일한 품질
- **🏪 지능형 상호명 보정**: 위치 기반 자동 상호명 검증 및 보정
- **📍 자동 위치 인식**: 이미지 GPS + 텔레그램 위치 공유 지원
- **📸 다중 이미지 업로드**: 최대 10장, 50MB까지 지원
- **🤖 대화형 인터페이스**: 단계별 안내와 실시간 검증
- **📊 실시간 품질 검증**: 생성 즉시 품질 점수 확인
- **🔒 접근 제어**: 관리자만 사용하거나 공개 모드 선택 가능
- **⏱️ 세션 관리**: 자동 세션 타임아웃 및 임시 파일 정리

#### 💬 대화 예시

```
사용자: /start
봇: 🤖 네이버 블로그 자동 생성 봇입니다!
    방문 날짜를 입력해주세요.
    형식: YYYYMMDD (예: 20260212)

사용자: 오늘
봇: ✅ 방문 날짜: 20260212
    카테고리를 선택해주세요:
    [맛집] [제품] [호텔] [여행] [뷰티] [패션] [IT] [기타]

사용자: 맛집
봇: ✅ 카테고리: 맛집
    🏪 방문한 상호명을 입력해주세요.
    예시:
    • 스타벅스
    • 스타벅스 강남역점
    • 맥도날드 홍대점

    지점명을 정확히 모르면 브랜드명만 입력해도 됩니다.

사용자: 스타벅스 강남점
봇: 🔍 상호명을 확인하고 있습니다...
    ✅ 🏪 상호명: 스타벅스 강남역점 (확실)
    📍 주소: 서울시 강남구 강남대로 123
    📏 거리: 50m

    📸 이제 사진을 업로드해주세요 (여러 장 가능).
    업로드가 완료되면 감상평을 입력해주세요.

사용자: [사진 업로드]
봇: ✅ 이미지가 업로드되었습니다! (1/10)
    방문 후 감상평을 자유롭게 작성해주세요.

사용자: 강남에서 먹은 파스타가 정말 맛있었어요. 크림소스가 부드럽고 면발도 쫄깃했습니다. 친구와 함께 갔는데 분위기도 좋아서 대화하기 편했어요.
봇: ✅ 감상평이 저장되었습니다.
    📝 블로그 작성 시 참고할 추가 내용을 입력해주세요.
    (없으면 '없음' 또는 'skip'을 입력하세요)

사용자: 없음
봇: 📋 입력된 정보 확인:
    📅 방문 날짜: 20260212
    📂 카테고리: 맛집
    📸 사진 수: 1장
    📝 감상평: 89자
    ➕ 추가 내용: 없음

    ✅ 모든 정보 입력이 완료되었습니다!
    /done 명령어를 입력하면 블로그 글이 자동 생성됩니다.

사용자: /done
봇: 🚀 블로그 자동화를 시작합니다...

    🔍 **데이터 검증** (1/5)
    입력 데이터를 검증하고 있습니다...
    진행률: 20.0%

    🤖 **블로그 생성** (3/5)
    AI를 사용하여 블로그를 생성하고 있습니다...
    진행률: 60.0%

    📊 **품질 검증** (4/5)
    생성된 블로그의 품질을 검증하고 있습니다...
    진행률: 80.0%

    📤 **네이버 업로드** (5/5)
    네이버 블로그에 임시저장하고 있습니다...
    진행률: 100.0%

    🎉 **블로그 자동화 완료!**

    📝 **생성 결과:**
    • 글자 수: 1,247자
    • 품질 점수: 0.87 (VERY_GOOD)

    📊 **품질 세부 점수:**
    • 네이버 정책 준수: 0.89
    • 키워드 품질: 0.85
    • 개인 경험 진정성: 0.88
    • 기술적 품질: 0.86

    📤 **네이버 업로드:** 임시저장 완료!
    📁 **저장 위치:** 20260212(스타벅스강남역점)
```

#### 🎮 봇 명령어

- `/start` - 새 블로그 포스팅 작성 시작
- `/done` - 입력 완료 후 블로그 글 생성
- `/cancel` - 현재 작업 취소
- `/status` - 현재 진행 상황 확인
- `/help` - 도움말 보기

#### ⚙️ 기술 특징

- **🔄 기존 시스템 재사용**: `DateBasedDataManager`, `DateBasedBlogGenerator` 완전 호환
- **📱 모바일 최적화**: 텔레그램의 사용자 친화적 인터페이스 활용
- **🛡️ 보안 고려**: 사용자 인증, 임시 파일 자동 정리, 세션 타임아웃
- **🎯 품질 보장**: 웹 버전과 동일한 AI 파이프라인 및 품질 검증

#### 🛠️ 최근 안정화 작업 (2026-02-13)

- 텔레그램 봇 import 호환성 수정 (`python-telegram-bot==20.7` 기준)
  - `src/telegram/bot.py`에서 `Application` import 경로 정정
- 백그라운드 정리 작업 시작/종료 방식 개선
  - `post_init`/`post_shutdown` 훅으로 cleanup task 수명주기 관리
- 텔레그램 검증 스크립트 오진 개선
  - `scripts/verify_telegram_setup.py`에서 단순 문자열 매칭 대신 실제 import 오류 구분
- 세션 기반 블로그 생성 오류 수정
  - `DateBasedDataManager.load_metadata()` 누락 메서드 추가
- 위치 정보 검증 오류 수정
  - `LocationInfo.source` 값 `user_input` -> `text`로 수정
- WSL DNS 복구/재기동 자동화 스크립트 추가
  - `maintenance/fix_wsl_dns_and_restart_bot.sh`
  - `api.telegram.org` 해석 문제 대응 및 봇 재시작 절차 자동화

## 💡 현재 사용 가능한 기능

### 1. 이미지 업로드 ✅ (완전 구현)
- **드래그 앤 드롭** 또는 **파일 선택**을 통한 이미지 업로드
- **최대 10개** 이미지, 각 파일당 **최대 50MB**
- **지원 형식**: JPG, JPEG, PNG, GIF, WebP
- **실시간 미리보기** 및 개별 이미지 삭제 기능
- **파일 크기 및 형식 자동 검증**

### 2. 사용자 경험 정보 입력 ✅ (완전 구현)
- **카테고리 선택**: 맛집, 제품, 호텔, 여행, 뷰티, 패션, IT, 기타
- **개인 감상평**: 최소 50자 이상의 상세한 경험 작성
- **추가 정보**:
  - 위치 정보
  - 별점 (1-5점)
  - 방문/사용 날짜
  - 동행자 정보 (혼자/가족/친구/연인/동료)
  - 해시태그 (쉼표로 구분)
  - 추가 메모
- **실시간 입력 검증** 및 오류 피드백

### 3. 데이터 저장 및 관리 ✅ (완전 구현)
- **프로젝트 단위**로 데이터 관리
- **JSON 기반** 메타데이터 저장
- **이미지 파일** 안전한 저장 및 서빙
- **프로젝트 생성/조회/삭제** 기능
- **저장소 통계** 제공

### 4. 웹 API ✅ (완전 구현)
- **RESTful API** 엔드포인트
- **자동 API 문서** (FastAPI Swagger)
- **파일 업로드 API**
- **데이터 검증 API**
- **상태 확인 API**

## 🔜 다음 구현 예정 기능

### Phase 5: 통합 고도화
- 배치 처리 스케줄링 기능
- 사용자 대시보드 및 포스팅 통계
- 성능 모니터링 및 캐싱 최적화
- 에러 복구 및 자동 재시도 로직 강화

## 📊 품질 검증 시스템

### 저품질 방지 전략

1. **콘텐츠 구조 최적화**
   - 개인 경험담 비율: 60% 이상
   - 키워드 자연스러운 배치 (밀도 2% 이하)
   - 문장 구조 다양성 보장

2. **네이버 정책 준수**
   - AI 전형 문구 탐지 및 제거
   - 상업적 목적 표현 자동 필터링
   - 자연스러운 개인 경험 중심 작성

3. **실시간 품질 모니터링**
   - 생성 과정에서 실시간 점수 계산
   - 기준 미달 시 자동 재생성
   - 사용자 피드백 기반 개선

## 🔧 구현된 API 엔드포인트

### 시스템 상태
```bash
GET /                          # 메인 페이지
GET /health                    # 시스템 헬스 체크
GET /docs                      # API 문서 (Swagger UI)
```

### 이미지 업로드
```bash
POST /api/upload/images        # 다중 이미지 업로드
Content-Type: multipart/form-data

# 응답 예시:
{
  "success": true,
  "message": "2개 이미지가 성공적으로 업로드되었습니다",
  "uploaded_files": [
    {
      "original_filename": "photo.jpg",
      "saved_path": "/uploads/images/uuid-filename.jpg",
      "file_size": 1024000,
      "url": "/uploads/images/uuid-filename.jpg"
    }
  ]
}
```

### 사용자 경험 데이터
```bash
POST /api/user-experience      # 사용자 경험 데이터 생성
Content-Type: application/x-www-form-urlencoded

DELETE /api/upload/images/{filename}  # 이미지 삭제
```

### 설정 및 상태
```bash
GET /api/uploads/status        # 업로드 설정 정보
GET /api/categories           # 지원 카테고리 목록
```

### 워크플로우 API (새로운!)
```bash
POST /api/workflow/start      # 자동화 워크플로우 시작
GET /api/workflow/status/{id} # 워크플로우 상태 조회
GET /api/workflow/stream/{id} # 진행상황 실시간 스트리밍 (SSE)
POST /api/workflow/cancel/{id} # 워크플로우 취소
GET /api/workflow/list        # 활성 워크플로우 목록
DELETE /api/workflow/cleanup  # 완료된 워크플로우 정리
GET /api/workflow/health      # 워크플로우 시스템 상태

# 워크플로우 시작 예시:
{
  "visit_date": "20260212",
  "category": "맛집",
  "store_name": "스타벅스 강남역점",
  "personal_review": "오늘 방문한 카페는 정말 좋았습니다...",
  "rating": 5,
  "companion": "친구",
  "auto_upload_to_naver": true
}

# 응답 예시:
{
  "success": true,
  "workflow_id": "uuid-here",
  "message": "워크플로우가 시작되었습니다"
}
```

### 정적 파일 서빙
```bash
GET /static/*                 # 프론트엔드 파일
GET /static/workflow.html     # 새로운 자동화 워크플로우 인터페이스
GET /uploads/*                # 업로드된 이미지 파일
```

## 🚀 AI 블로그 생성 사용법

### 1. 완전한 블로그 글 자동 생성 🌟

현재 구현된 AI 블로그 생성 시스템을 사용하여 고품질 블로그 글을 자동으로 생성할 수 있습니다.

#### 기본 사용법
```python
from src.content.blog_generator import DateBasedBlogGenerator

# AI 블로그 생성기 초기화
generator = DateBasedBlogGenerator()

# 특정 날짜의 포스팅 데이터로부터 블로그 생성
result = generator.generate_from_session_data("20240212")

if result["success"]:
    print(f"블로그 글이 생성되었습니다: {result['blog_file_path']}")
    print(f"생성된 글자 수: {result['metadata']['actual_length']}")
else:
    print(f"생성 실패: {result['error']}")
```

#### 배치 처리로 여러 블로그 동시 생성
```python
# 여러 날짜의 블로그를 한 번에 생성
date_directories = ["20240212", "20240213", "20240214"]
batch_result = generator.batch_generate_blogs(date_directories)

print(f"총 {batch_result['summary']['total_processed']}개 중 "
      f"{batch_result['summary']['successful']}개 성공")
```

### 2. 실시간 품질 검증 📊

생성된 블로그 글의 품질을 실시간으로 검증할 수 있습니다.

```python
from src.quality.unified_scorer import UnifiedQualityScorer

# 품질 검증기 초기화
scorer = UnifiedQualityScorer()

# 종합 품질 분석 실행
quality_result = scorer.calculate_unified_score(
    generated_content=generated_blog_text,
    original_review=user_original_review,
    target_keywords=["맛집", "강남", "파스타"],
    category="맛집"
)

# 사용자 친화적 보고서 생성
report = scorer.get_quality_report(quality_result)
print(report)
```

#### 품질 분석 결과 예시
```
=== 📊 블로그 콘텐츠 품질 분석 보고서 ===

🎯 종합 점수: 0.847 (VERY_GOOD)
✅ 전체 통과: 통과
🏛️ 네이버 정책: 준수

📈 세부 점수:
• 네이버 정책 준수: 0.89 (35%)
• 키워드 품질: 0.82 (25%)
• 개인 경험 진정성: 0.85 (25%)
• 기술적 품질: 0.78 (15%)

✅ 매우 좋은 품질입니다. 발행 가능한 수준입니다.
```

### 3. 해시태그 자동 생성 #️⃣

사용자 입력을 분석하여 최적화된 해시태그를 자동으로 생성합니다.

```python
from src.content.blog_generator import HashtagGenerator
from src.content.models import UserDirectInput, LocationInfo

# 해시태그 생성기 초기화
hashtag_generator = HashtagGenerator()

# 사용자 입력 정보
user_input = UserDirectInput(
    category="맛집",
    personal_review="강남에서 먹은 파스타가 정말 맛있었어요. 크림소스가 진짜 부드럽고...",
    rating=5,
    companion="친구"
)

# 위치 정보
location_info = LocationInfo(
    detected_location="강남역",
    confidence=0.9
)

# 해시태그 후보 생성
candidates = hashtag_generator.generate_candidate_hashtags(
    user_input, location_info, ["파스타", "크림소스", "이탈리안"]
)

# 해시태그 정제 및 최종 선택
refined_result = hashtag_generator.refine_hashtags(candidates)
print("최종 해시태그:", refined_result.final_tags)
# 출력: ['#맛집', '#강남', '#파스타', '#친구와함께', '#강추', '#이탈리안']
```

### 4. 날짜 기반 데이터 관리 📅

체계적인 날짜별 포스팅 데이터 관리 시스템을 활용할 수 있습니다.

```python
from src.utils.date_manager import date_manager

# 오늘 날짜로 새 디렉토리 생성
today = "20240212"
date_dir = date_manager.create_date_directory(today)

# 메타데이터 저장
user_data = {
    "category": "맛집",
    "rating": 5,
    "personal_review": "정말 맛있었어요...",
    "images": ["image1.jpg", "image2.jpg"]
}
date_manager.save_metadata(today, user_data)

# 모든 날짜 디렉토리 조회
all_directories = date_manager.list_date_directories()
print("생성된 포스팅 디렉토리:", all_directories)
```

### 5. 통합 테스트 실행 🧪

구현된 다양한 테스트를 실행하여 시스템을 검증할 수 있습니다.

```bash
# 블로그 생성 기능 테스트
python scripts/test_blog_generation.py

# 품질 검증 시스템 테스트
python scripts/test_quality_validation.py

# 키워드 분석 테스트
python scripts/test_keyword_analysis.py

# 통합 스코어링 테스트
python scripts/test_unified_scorer.py

# 전체 시스템 통합 테스트
python scripts/test_generate.py

# 텔레그램 봇 통합 테스트
python scripts/test_telegram_integration.py

# 텔레그램 시작/완료 버튼 UX 검증 테스트
pytest tests/integration/test_telegram_buttons.py -v

# 🚀 **새로운!** 완전 자동화 워크플로우 통합 테스트
python scripts/test_integrated_workflow.py

# 네이버 임시저장 UI 검증 통합 테스트 (로그인 세션 필요)
cd naver-poster
bash naver-poster/scripts/test_draft_save.sh "../data/20260214(자라)"
# 또는
TEST_DRAFT_DIR="../data/20260214(자라)" npx tsx tests/integration/test_naver_draft_save.ts
```

## 🧪 테스트 및 검증

### 시스템 구조 검증
```bash
# 프로젝트 구조 및 모듈 임포트 테스트
python3 scripts/test_structure.py
```

### 웹 서버 테스트
```bash
# 서버 실행 후 다음 URL들로 테스트
curl http://localhost:8000/health           # 헬스 체크
curl http://localhost:8000/api/categories   # 카테고리 목록
curl http://localhost:8000/api/uploads/status  # 업로드 설정
```

### 웹 인터페이스 테스트
1. `http://localhost:8000` 접속
2. 이미지 파일 드래그 앤 드롭 테스트
3. 사용자 경험 정보 입력 테스트
4. 브라우저 개발자 도구에서 네트워크 요청 확인

### 향후 테스트 (구현 예정)
```bash
# 단위 테스트 (Phase 2 이후)
pytest tests/

# 특정 모듈 테스트
pytest tests/test_content_generation.py
pytest tests/test_quality_validation.py
pytest tests/test_naver_automation.py
```

## 📝 개발 현황 및 로드맵

### Phase 1: 기본 인프라 🎉 **100% 완료**
- [x] **프로젝트 구조 생성** - 모듈화된 완전한 아키텍처
- [x] **설정 시스템 구현** - 환경변수 기반 중앙 설정 관리
- [x] **웹 인터페이스 구축** - FastAPI + Bootstrap 반응형 UI
- [x] **데이터 모델 정의** - Pydantic 기반 10개 데이터 모델
- [x] **파일 업로드 시스템** - 드래그앤드롭 지원 이미지 업로드
- [x] **저장 관리 시스템** - 프로젝트 단위 데이터 관리
- [x] **로깅 및 예외 처리** - 구조화된 시스템 전체 모니터링
- [x] **API 엔드포인트** - RESTful API 7개 엔드포인트
- [x] **테스트 도구** - 구조 검증 및 기능 테스트
- [x] **문서화** - 포괄적인 README 및 API 문서

### Phase 2: AI 콘텐츠 생성 🎉 **100% 완료**
- [x] OpenAI API 연동 및 고도화된 프롬프트 엔지니어링
- [x] 사용자 경험 기반 자연스러운 글 생성 로직
- [x] 해시태그 자동 생성 및 정제 시스템
- [x] 카테고리별 맞춤 글 작성 (맛집, 제품, 여행 등)
- [x] 글 길이 및 톤 조절 시스템 (1200자 내외, 자연스러운 말투)
- [x] 날짜 기반 배치 처리 시스템
- [x] AI 전형 문구 자동 필터링 (확대: 정리하자면, 소개해드릴게요, 총평, 결론적으로 등)
- [x] 사용자 경험 처리 모듈 완료
- [x] **입력 충분성 체크** — 6개 필드(메뉴/맛/분위기/접근성/가격/아쉬운점) 자동 점수화
- [x] **보강 모드** — 점수 부족 시 네이버 블로그 검색 API로 리뷰 스니펫 자동 수집
- [x] **사실 날조 방지** — 입력에 없는 가격/영업시간/주차 등 AI 임의 단정 시스템 프롬프트에서 차단
- [x] **이미지 마커 번호화** — `(사진)` → `[사진1]`~`[사진N]` 장면 전환 매핑, 연속 사진 금지
- [x] **날조 사실 위험 감지 메트릭** — 품질 점수에서 자동 감점

### Phase 3: 품질 검증 시스템 🎉 **100% 완료**
- [x] 네이버 저품질 알고리즘 분석 및 회피 로직
- [x] 키워드 밀도 및 분포 자동 분석 (2% 이하 자연스러운 배치)
- [x] AI 전형 문구 탐지 및 실시간 필터링
- [x] 개인 경험 비율 자동 검증 (60% 이상 보장)
- [x] 통합 품질 점수 실시간 계산 (네이버 정책 준수 기준)
- [x] 종합 품질 보고서 및 개선 권장사항 생성
- [x] 감정 진정성 분석 및 평가

### Phase 3.5: 텔레그램 봇 통합 🤖 **100% 완료**
- [x] 완전한 텔레그램 봇 아키텍처 설계 및 구현
- [x] 다단계 대화형 인터페이스 (ConversationHandler)
- [x] 이미지 업로드 및 검증 시스템 (ImageHandler)
- [x] 세션 상태 관리 및 타임아웃 처리
- [x] 기존 AI 파이프라인 완벽 통합 (DateBasedBlogGenerator)
- [x] 기존 데이터 매니저 재사용 (DateBasedDataManager)
- [x] 보안 및 접근 제어 기능
- [x] 응답 템플릿 및 사용자 경험 최적화
- [x] 통합 테스트 및 검증 시스템

### Phase 4: 네이버 블로그 연동 🔄 **20% 완료**
- [x] Selenium WebDriver 기본 구조 설정
- [ ] 네이버 로그인 자동화 (2단계 인증 포함)
- [ ] 블로그 포스팅 자동화
- [ ] 이미지 업로드 및 배치 자동화
- [ ] 카테고리 및 태그 자동 설정

### Phase 5: 통합 및 고도화 📋 **최종 단계**
- [ ] 전체 워크플로우 통합 및 최적화
- [ ] 배치 처리 및 스케줄링 기능
- [ ] 성능 모니터링 및 최적화
- [ ] 에러 복구 및 재시도 로직 강화
- [ ] 사용자 대시보드 및 통계 기능

## 📊 구현 통계

| 항목 | 수량 | 상태 |
|------|------|------|
| 총 코드 라인 수 | **7,000+** | 🎉 |
| Python 모듈 | **35개** | 🎉 |
| API 엔드포인트 | 7개 | ✅ |
| 데이터 모델 | 12개 | ✅ |
| 예외 클래스 | 15개 | ✅ |
| 환경 설정 변수 | 34+ | ✅ |
| 테스트 스크립트 | **8개** | 🎉 |
| 품질 검증 시스템 | **4개 모듈** | 🎉 |
| AI 생성 엔진 | **완전 구현** | 🎉 |
| 해시태그 생성기 | **지능형 시스템** | 🎉 |
| 통합 스코어링 | **실시간 계산** | 🎉 |
| **텔레그램 봇** | **완전 구현** | 🤖 |

## 🎯 현재 상태 및 다음 단계 가이드

### 📍 **현재 완료 상태 (2026-02-12 기준)**

**✅ 완전히 사용 가능한 기능:**
1. **🌐 웹 인터페이스**:
   - 드래그 앤 드롭 이미지 업로드
   - 사용자 경험 정보 입력
   - 실시간 API 통신

2. **🤖 텔레그램 봇 인터페이스**:
   - 완전한 대화형 블로그 작성 시스템
   - 모바일 최적화 사용자 경험
   - 웹 버전과 100% 동일한 AI 파이프라인

3. **🧠 AI 콘텐츠 생성 엔진**:
   - OpenAI GPT-4 기반 자동 블로그 글 생성
   - 지능형 해시태그 생성 및 정제
   - 개인 경험 중심 자연스러운 글 작성

4. **📊 실시간 품질 검증**:
   - 네이버 저품질 알고리즘 회피
   - 키워드 밀도 자동 최적화
   - 개인 경험 비율 60% 이상 보장
   - 종합 품질 점수 및 상세 보고서

### 🚀 **즉시 사용 방법**

```bash
# 웹 서버 방식
uvicorn src.web.app:app --host 0.0.0.0 --port 8000 --reload

# 텔레그램 봇 방식 (추천)
python3 etc_scripts/run_telegram_bot.py
```

### 📋 **다음 개발 단계 (우선순위 순)**

#### **1단계: 네이버 블로그 자동 포스팅 완성 🎯**
- **목표**: 생성된 블로그 글을 네이버 블로그에 자동 업로드
- **진행률**: 20% 완료
- **남은 작업**:
  ```
  src/naver/blog_automator.py      - 자동 포스팅 로직 완성
  src/naver/selenium_handler.py    - 웹 자동화 완료
  네이버 로그인 자동화 (2단계 인증 포함)
  이미지 업로드 및 배치 자동화
  카테고리 및 태그 자동 설정
  ```

#### **2단계: 통합 워크플로우 완성 ⚡**
- **목표**: 텔레그램 → AI 생성 → 품질 검증 → 네이버 업로드 완전 자동화
- **예상 효과**: 사용자가 텔레그램에서 한 번만 입력하면 자동으로 네이버 블로그 포스팅 완료

#### **3단계: 고도화 및 최적화 🔧**
- **배치 처리 시스템**: 여러 포스팅 동시 생성 및 업로드
- **스케줄링 기능**: 예약 포스팅 및 자동 발행
- **사용자 대시보드**: 포스팅 통계 및 품질 분석
- **성능 최적화**: 캐싱 및 비동기 처리

#### **4단계: 추가 기능 확장 🌟**
- **다중 플랫폼 지원**: 티스토리, 브런치 등 추가
- **AI 모델 다양화**: 다양한 LLM 모델 지원
- **고급 SEO 최적화**: 검색 최적화 기능 강화
- **협업 기능**: 팀 단위 블로그 관리

### 🎖️ **개발 우선순위 가이드**

**⭐ 최우선 (Phase 4)**:
- 네이버 블로그 자동 포스팅 완성
- 전체 워크플로우 통합 테스트

**⭐⭐ 고우선 (Phase 5)**:
- 배치 처리 및 스케줄링
- 에러 복구 및 재시도 로직

**⭐⭐⭐ 중우선 (확장 기능)**:
- 사용자 대시보드
- 성능 모니터링 시스템

### 💡 **개발 권장사항**

1. **Phase 4 집중**: 현재 AI 엔진이 완벽하므로 자동 포스팅만 완성하면 완전한 시스템
2. **기존 구조 활용**: 현재 아키텍처가 확장성 있게 설계되어 있어 추가 기능 개발 용이
3. **텔레그램 봇 우선**: 모바일 환경에서 가장 편리한 사용자 경험 제공

## 🛡️ 보안 고려사항

- 네이버 계정 정보는 환경변수로 안전하게 관리
- API 키 노출 방지
- 파일 업로드 보안 검증
- 로그인 실패 시 지수 백오프 적용

## 🤝 기여하기

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 `LICENSE` 파일을 참조하세요.

## 🔍 문제 해결

### Phase 1 관련 문제 해결

1. **서버 실행 실패**
   ```bash
   # 의존성 설치 확인
   pip install -r requirements.txt

   # Python 버전 확인 (3.8+ 필요)
   python --version

   # 포트 충돌 확인
   netstat -tulpn | grep :8000
   ```

2. **모듈 임포트 오류**
   ```bash
   # 프로젝트 루트에서 실행하는지 확인
   pwd  # /path/to/naverPost 여야 함

   # 의존성 재설치
   pip install --upgrade -r requirements.txt
   ```

3. **이미지 업로드 실패**
   - 파일 크기: 최대 50MB 확인
   - 지원 형식: JPG, JPEG, PNG, GIF, WebP
   - 디스크 용량 확인
   - 브라우저 개발자 도구에서 네트워크 요청 확인

4. **환경설정 문제**
   ```bash
   # .env 파일 존재 확인
   ls -la .env

   # 설정 값 확인
   python3 -c "from src.config.settings import Settings; print(Settings.WEB_PORT)"
   ```

### 로그 확인

```bash
# 로그 디렉토리 생성 확인
mkdir -p logs

# 서버 실행 로그 (실시간)
tail -f logs/naverpost.log

# Python 실행 시 오류 확인
python3 -c "import src.web.app" 2>&1
```

### 구조 검증

```bash
# 전체 시스템 구조 검증
python3 scripts/test_structure.py

# 개별 모듈 테스트
python3 -c "from src.config.settings import Settings; print('Settings OK')"
python3 -c "from src.utils.exceptions import BlogSystemError; print('Exceptions OK')"
python3 -c "from src.storage.data_manager import DataManager; print('DataManager OK')"
```

### 텔레그램 봇 관련 문제 해결

1. **봇 실행 실패**
   ```bash
   # 텔레그램 의존성 설치 확인
   pip install python-telegram-bot==20.7 aiohttp>=3.8.0

   # 봇 설정 검증
   python3 scripts/verify_telegram_setup.py

   # 봇 재기동 (권장)
   ./etc_scripts/restart_telegram.sh

   # 프로세스/로그 확인
   pgrep -af "[r]un_telegram_bot.py"
   tail -n 120 logs/telegram_bot.out

   # 환경변수 확인
   echo $TELEGRAM_BOT_TOKEN
   ```

   WSL 환경에서 `Timed out` 또는 `api.telegram.org` DNS 오류가 나면:
   ```bash
   ./maintenance/fix_wsl_dns_and_restart_bot.sh
   ```

   DNS 연결 상태 빠른 점검:
   ```bash
   getent hosts api.telegram.org
   ```

2. **봇 토큰 오류**
   - @BotFather에서 토큰 재발급
   - .env 파일에 정확한 토큰 설정 확인
   - 토큰 형식: `123456789:ABCdefGhIJKlmNoPQRsTuVwxyZ`

3. **이미지 업로드 실패**
   - 임시 디렉토리 권한 확인: `data/telegram_temp/`
   - 파일 크기 제한: 최대 50MB, 최소 100KB
   - 지원 형식: JPG, PNG, GIF, WebP

4. **`/done`에서 메타데이터 관련 오류**
   - 증상: `'DateBasedDataManager' object has no attribute 'load_metadata'`
   - 조치: `src/storage/data_manager.py`의 `load_metadata()` 위임 메서드 반영 버전 사용

5. **`/done`에서 LocationInfo 검증 오류**
   - 증상: `source ... exif, text, none` 검증 실패
   - 조치: `src/content/blog_generator.py`에서 `LocationInfo(source="text")` 사용 버전 반영

### 향후 구현될 기능 관련 (Phase 4+)

1. **네이버 자동 포스팅 개발 시 참고사항**
   - Selenium WebDriver 버전 호환성
   - 네이버 2단계 인증 처리
   - 동적 로딩 요소 대기 시간 조정

2. **성능 최적화 고려사항**
   - AI API 호출 캐싱 전략
   - 이미지 처리 비동기화
   - 데이터베이스 도입 검토

## 📊 **현재 개발 완료 상태 요약 (2026-02-16)**

### ✅ **완전 구현 완료**
- **Phase 1**: 기본 인프라 (웹 서버, API, 데이터 관리)
- **Phase 2**: AI 콘텐츠 생성 엔진 (OpenAI GPT-4 통합)
- **Phase 3**: 실시간 품질 검증 시스템
- **Phase 3.5**: 텔레그램 봇 통합 (1,400+ 라인 신규 코드)

### 🔄 **최근 주요 업데이트 (2026-02-16): 콘텐츠 생성 시스템 전면 개편**

AI가 입력에 없는 사실(가격, 주차, 영업시간 등)을 임의로 단정하는 문제를 해결하고, 입력이 부족할 때 자동 보강하는 시스템을 도입했습니다.

**변경 파일:**
- `src/content/blog_generator.py` — 프롬프트, 충분성 체크, 후처리, 품질 메트릭 전면 개편
- `src/content/review_collector.py` — 신규 (네이버 블로그 검색 API 리뷰 수집)

**핵심 변경 내역:**

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| 사실 범위 | AI가 가격/시간/주차 등을 추측해서 작성 | 입력에 없는 사실은 절대 쓰지 않도록 프롬프트에서 차단 |
| 아쉬운 점 | 항상 "솔직한 아쉬운 점 1개 포함" 강제 | 사용자가 명시한 경우에만 포함, 없으면 생략 |
| 이미지 마커 | `(사진)` 번호 없이 삽입 | `[사진1]`~`[사진N]` 번호화, 장면 전환 매핑 |
| 연속 사진 | 제한 없음 | 연속 사진 금지 (앞뒤 최소 1문단 텍스트) |
| 입력 부족 | 대응 없음 | 충분성 점수화 → 8점 미만 시 네이버 블로그 검색으로 보강 |
| 보강 서술 | 없음 | "후기에서 자주 보이더라" 형태의 2차 서술만 허용 |
| 품질 메트릭 | 기본 3개 | `image_marker_count`, `has_consecutive_photos`, `fabricated_fact_risk` 추가 |
| AI 전형 표현 | 5개 패턴 | 9개 패턴 (정리하자면, 소개해드릴게요, 총평, 결론적으로 추가) |

**충분성 체크 점수 산정:**
- 필드 매칭 (메뉴/맛/분위기/접근성/가격/아쉬운점): 각 2점 (최대 12점)
- 사진 수: min(장수, 6) 점
- 텍스트 길이 300자 초과: +2점
- **8점 미만이면 보강 모드 발동** → `NaverReviewCollector`가 네이버 블로그 검색 API로 스니펫 수집

### 🚀 **즉시 사용 가능**
```bash
# 두 가지 방식 모두 완전 동작
python3 -m src.web.app           # 웹 인터페이스
python3 etc_scripts/run_telegram_bot.py      # 텔레그램 봇 (추천)
```

### 📋 **다음 개발 목표**
**Phase 4**: 네이버 블로그 자동 포스팅 (95% 완료)
- 목표: 텔레그램에서 입력만 하면 네이버 블로그 자동 업로드까지 완성
- naver-poster 장소 셀렉터 미세조정 및 에러 복구 로직 남음

### 🎯 **현재 시스템 강점**
- **7,000+ 라인의 안정적인 코드베이스**
- **완전한 AI 파이프라인 (GPT-4 + 품질 검증 + 사실 날조 방지)**
- **입력 부족 시 자동 보강 (네이버 블로그 검색 API)**
- **모바일 친화적 텔레그램 인터페이스**
- **확장 가능한 모듈 구조**

## 📞 지원

- Issues: GitHub Issues를 통해 버그 신고 및 기능 요청
- Documentation: 프로젝트 Wiki 참조
- Email: 개발자 연락처

---

**주의사항**: 이 도구는 교육 및 개인 사용 목적으로 제작되었습니다. 네이버 블로그 이용약관을 준수하여 사용하시기 바랍니다.
