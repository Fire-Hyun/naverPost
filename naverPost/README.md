# 네이버 블로그 포스팅 자동화 시스템

사용자의 실제 사진과 경험담을 기반으로 고품질 블로그 포스트를 자동 생성하고, 네이버 블로그에 자동 업로드하는 시스템입니다.

## 🚀 현재 구현 상태

**Phase 1 (기본 인프라): 100% 완료 ✅**
- ✅ 완전한 웹 인터페이스 구현
- ✅ 이미지 업로드 시스템 작동
- ✅ 사용자 경험 데이터 수집
- ✅ 파일 저장 및 메타데이터 관리
- ✅ API 엔드포인트 구현
- ✅ 로깅 및 예외 처리 시스템

**현재 사용 가능한 기능:**
- 웹 브라우저를 통한 이미지 업로드 (드래그앤드롭 지원)
- 사용자 경험 정보 입력 (카테고리, 감상평, 위치, 별점 등)
- 업로드된 데이터의 저장 및 관리
- 실시간 상태 피드백

**개발 진행 예정:**
- Phase 2: AI 콘텐츠 생성 엔진 (OpenAI 연동)
- Phase 3: 품질 검증 시스템
- Phase 4: 네이버 블로그 자동 포스팅

## 🎯 주요 특징

- **사용자 경험 중심**: 실제 사용자 경험과 사진을 기반으로 자연스러운 블로그 글 생성
- **저품질 콘텐츠 방지**: 네이버 블로그의 저품질 판정 알고리즘을 회피하는 고품질 콘텐츠 생성
- **웹 기반 인터페이스**: 간편한 이미지 업로드와 사용자 경험 입력
- **자동화된 포스팅**: 네이버 블로그 자동 로그인 및 포스팅 업로드
- **품질 검증 시스템**: 실시간 콘텐츠 품질 검증 및 피드백

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
│   ├── content/                ✅ 데이터 모델링
│   │   └── models.py           ✅ Pydantic 데이터 모델 (10.7KB)
│   ├── storage/                ✅ 데이터 저장 관리
│   │   └── data_manager.py     ✅ 파일 및 메타데이터 관리 (13KB)
│   ├── config/                 ✅ 설정 관리
│   │   └── settings.py         ✅ 환경변수 및 설정 (5.3KB)
│   └── utils/                  ✅ 공통 유틸리티
│       ├── logger.py           ✅ 구조화된 로깅 (1.4KB)
│       └── exceptions.py       ✅ 전용 예외 처리 (6.5KB)
├── data/                       ✅ 생성 데이터 저장소
├── uploads/                    ✅ 사용자 업로드 파일
├── templates/                  ✅ 글 생성 템플릿 (준비됨)
├── tests/                      ✅ 테스트 디렉토리
├── requirements.txt            ✅ 의존성 목록
├── .env.example                ✅ 환경설정 템플릿
└── test_structure.py           ✅ 구조 검증 스크립트
```

### 다음 단계 구현 예정 🔄
```
│   ├── content/                🔄 AI 콘텐츠 생성 엔진
│   │   ├── blog_generator.py   📋 블로그 글 생성 로직
│   │   └── experience_processor.py 📋 사용자 경험 처리
│   ├── quality/                📋 품질 검증 모듈
│   │   ├── naver_validator.py  📋 네이버 저품질 방지
│   │   └── content_checker.py  📋 콘텐츠 품질 검증
│   ├── naver/                  📋 네이버 블로그 연동
│   │   ├── blog_automator.py   📋 자동 포스팅
│   │   └── selenium_handler.py 📋 웹 자동화
│   └── external/               📋 외부 정보 수집
│       └── info_collector.py   📋 보조 정보 수집
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
```

### 4. 실행

```bash
# 프로젝트 구조 검증 (선택사항)
python3 test_structure.py

# 웹 서버 시작
uvicorn src.web.app:app --host 0.0.0.0 --port 8000 --reload

# 또는 Python 모듈로 실행
python -m src.web.app
```

브라우저에서 `http://localhost:8000`에 접속하여 웹 인터페이스를 사용할 수 있습니다.

### 5. 기본 기능 테스트

웹 서버가 실행된 후 다음 기능들을 테스트할 수 있습니다:

- **메인 페이지**: `http://localhost:8000`
- **헬스 체크**: `http://localhost:8000/health`
- **API 문서**: `http://localhost:8000/docs` (FastAPI 자동 생성)

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

### Phase 2: AI 콘텐츠 생성 (다음 단계)
- OpenAI GPT 기반 블로그 글 자동 생성
- 사용자 경험 중심의 자연스러운 글 작성
- 외부 정보와 개인 경험의 최적 비율 조합

### Phase 3: 품질 검증 시스템
- 네이버 저품질 콘텐츠 판정 알고리즘 회피
- 키워드 밀도 및 문장 구조 분석
- 실시간 품질 점수 계산

### Phase 4: 네이버 블로그 자동 포스팅
- Selenium 기반 웹 자동화
- 네이버 계정 자동 로그인
- 이미지 첨부 및 글 업로드

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

### 정적 파일 서빙
```bash
GET /static/*                 # 프론트엔드 파일
GET /uploads/*                # 업로드된 이미지 파일
```

## 🧪 테스트 및 검증

### 시스템 구조 검증
```bash
# 프로젝트 구조 및 모듈 임포트 테스트
python3 test_structure.py
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

### Phase 2: AI 콘텐츠 생성 🔄 **다음 단계**
- [ ] OpenAI API 연동 및 프롬프트 엔지니어링
- [ ] 사용자 경험 기반 글 생성 로직
- [ ] 외부 정보 수집 및 통합
- [ ] 카테고리별 맞춤 템플릿 구현
- [ ] 글 길이 및 톤 조절 시스템

### Phase 3: 품질 검증 시스템 📋 **Phase 2 완료 후**
- [ ] 네이버 저품질 알고리즘 분석 및 회피 로직
- [ ] 키워드 밀도 및 문장 구조 검증
- [ ] AI 전형 문구 탐지 및 필터링
- [ ] 개인 경험 비율 자동 검증
- [ ] 품질 점수 실시간 계산

### Phase 4: 네이버 블로그 연동 📋 **Phase 3 완료 후**
- [ ] Selenium WebDriver 설정 및 최적화
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
| 총 코드 라인 수 | 1,000+ | ✅ |
| Python 모듈 | 11개 | ✅ |
| API 엔드포인트 | 7개 | ✅ |
| 데이터 모델 | 10개 | ✅ |
| 예외 클래스 | 15개 | ✅ |
| 환경 설정 변수 | 30+ | ✅ |
| 테스트 스크립트 | 1개 | ✅ |
| 문서 페이지 | 3개 | ✅ |

## 🎯 다음 단계 가이드

현재 Phase 1이 완료된 상태에서 다음과 같이 진행할 수 있습니다:

1. **즉시 사용 가능**: 이미지 업로드 및 데이터 수집 시스템
2. **개발 계속**: Phase 2 AI 콘텐츠 생성 모듈 구현
3. **테스트 환경**: 현재 웹 인터페이스로 데이터 수집 테스트 가능
4. **확장 준비**: 모든 기반 시설이 구축되어 빠른 기능 추가 가능

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
python3 test_structure.py

# 개별 모듈 테스트
python3 -c "from src.config.settings import Settings; print('Settings OK')"
python3 -c "from src.utils.exceptions import BlogSystemError; print('Exceptions OK')"
python3 -c "from src.storage.data_manager import DataManager; print('DataManager OK')"
```

### 향후 구현될 기능 관련 (Phase 2+)

1. **OpenAI API 오류** (구현 예정)
   - API 키 확인 및 크레딧 잔액 확인
   - 네트워크 연결 상태 점검

2. **네이버 로그인 실패** (구현 예정)
   - 계정 정보 확인
   - 보안 설정 (2단계 인증 등) 확인

## 📞 지원

- Issues: GitHub Issues를 통해 버그 신고 및 기능 요청
- Documentation: 프로젝트 Wiki 참조
- Email: 개발자 연락처

---

**주의사항**: 이 도구는 교육 및 개인 사용 목적으로 제작되었습니다. 네이버 블로그 이용약관을 준수하여 사용하시기 바랍니다.