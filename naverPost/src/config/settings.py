"""
네이버 블로그 포스팅 자동화 시스템 설정 관리 모듈
모든 설정값과 상수를 중앙에서 관리합니다.
"""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent.parent

class Settings:
    """전역 설정 클래스"""

    # 프로젝트 루트 경로
    PROJECT_ROOT: Path = PROJECT_ROOT

    # API 키
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # 네이버 계정 정보
    NAVER_USERNAME: str = os.getenv("NAVER_USERNAME", "")
    NAVER_PASSWORD: str = os.getenv("NAVER_PASSWORD", "")
    NAVER_BLOG_URL: str = os.getenv("NAVER_BLOG_URL", "")  # https://blog.naver.com/your_blog_id

    # 웹 서버 설정 (예외처리 강화)
    WEB_HOST: str = os.getenv("WEB_HOST", "0.0.0.0")


    # 안전한 환경변수 파싱으로 설정 (모듈 로드 시점에 실행)
    try:
        WEB_PORT: int = int(os.getenv("WEB_PORT", "8000"))
    except (ValueError, TypeError):
        WEB_PORT: int = 8000

    WEB_DEBUG: bool = os.getenv("WEB_DEBUG", "false").lower() == "true"

    # 경로 설정 (예외처리 강화)
    try:
        DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data")))
    except (ValueError, TypeError, OSError):
        DATA_DIR: Path = PROJECT_ROOT / "data"

    try:
        UPLOADS_DIR: Path = Path(os.getenv("UPLOADS_DIR", str(PROJECT_ROOT / "uploads")))
    except (ValueError, TypeError, OSError):
        UPLOADS_DIR: Path = PROJECT_ROOT / "uploads"

    try:
        TEMPLATES_DIR: Path = Path(os.getenv("TEMPLATES_DIR", str(PROJECT_ROOT / "templates")))
    except (ValueError, TypeError, OSError):
        TEMPLATES_DIR: Path = PROJECT_ROOT / "templates"

    # 로깅 설정
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    try:
        LOG_DIR: Path = Path(os.getenv("LOG_DIR", str(PROJECT_ROOT / "logs")))
    except (ValueError, TypeError, OSError):
        LOG_DIR: Path = PROJECT_ROOT / "logs"

    try:
        LOG_FILE: Path = Path(os.getenv("LOG_FILE", str(PROJECT_ROOT / "logs" / "naverpost.log")))
    except (ValueError, TypeError, OSError):
        LOG_FILE: Path = PROJECT_ROOT / "logs" / "naverpost.log"

    # API 호출 안정성 설정 (예외처리 강화)
    try:
        API_TIMEOUT: float = float(os.getenv("API_TIMEOUT", "30.0"))
    except (ValueError, TypeError):
        API_TIMEOUT: float = 30.0

    try:
        API_MAX_RETRIES: int = int(os.getenv("API_MAX_RETRIES", "3"))
    except (ValueError, TypeError):
        API_MAX_RETRIES: int = 3

    try:
        API_RETRY_DELAY: float = float(os.getenv("API_RETRY_DELAY", "1.0"))
    except (ValueError, TypeError):
        API_RETRY_DELAY: float = 1.0

    # 파일 처리 설정
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))  # 이미지 파일 최대 크기
    ALLOWED_IMAGE_EXTENSIONS: List[str] = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
    MAX_IMAGES_PER_POST: int = int(os.getenv("MAX_IMAGES_PER_POST", "10"))

    # 블로그 콘텐츠 설정
    MIN_CONTENT_LENGTH: int = int(os.getenv("MIN_CONTENT_LENGTH", "1000"))  # 최소 글자 수
    MAX_CONTENT_LENGTH: int = int(os.getenv("MAX_CONTENT_LENGTH", "2000"))  # 최대 글자 수
    TARGET_KEYWORD_DENSITY: float = float(os.getenv("TARGET_KEYWORD_DENSITY", "0.015"))  # 1.5%
    MIN_PERSONAL_EXPERIENCE_RATIO: float = float(os.getenv("MIN_PERSONAL_EXPERIENCE_RATIO", "0.6"))  # 60%

    # 품질 검증 설정
    MIN_QUALITY_SCORE: float = float(os.getenv("MIN_QUALITY_SCORE", "0.7"))  # 최소 품질 점수(0~1, 70도 허용)
    QUALITY_SOFT_FAIL_MARGIN: float = float(os.getenv("QUALITY_SOFT_FAIL_MARGIN", "0.1"))  # 권장 기준 미달 허용폭
    MIN_NAVER_COMPLIANCE_SCORE: float = float(os.getenv("MIN_NAVER_COMPLIANCE_SCORE", "80.0"))  # 네이버 정책 준수 점수
    QUALITY_RULES_FILE: Path = Path(os.getenv("QUALITY_RULES_FILE", PROJECT_ROOT / "config" / "quality_rules.yml"))

    # Selenium 설정
    SELENIUM_HEADLESS: bool = os.getenv("SELENIUM_HEADLESS", "true").lower() == "true"
    SELENIUM_IMPLICIT_WAIT: int = int(os.getenv("SELENIUM_IMPLICIT_WAIT", "10"))
    SELENIUM_PAGE_LOAD_TIMEOUT: int = int(os.getenv("SELENIUM_PAGE_LOAD_TIMEOUT", "30"))

    # Playwright 설정 (기본 headless=true, 서버 환경 안전)
    PLAYWRIGHT_HEADLESS: bool = os.getenv("PLAYWRIGHT_HEADLESS", os.getenv("HEADLESS", "true")).lower() == "true"

    # 자동화 안전성 설정
    POST_ACTION_DELAY: float = float(os.getenv("POST_ACTION_DELAY", "2.0"))  # 동작 간 지연 시간
    LOGIN_RETRY_COUNT: int = int(os.getenv("LOGIN_RETRY_COUNT", "3"))
    LOGIN_RETRY_DELAY: float = float(os.getenv("LOGIN_RETRY_DELAY", "5.0"))

    # 콘텐츠 카테고리
    SUPPORTED_CATEGORIES: List[str] = [
        "맛집", "제품", "호텔", "여행", "뷰티", "패션", "IT", "기타"
    ]

    # OpenAI 모델 설정 (예외처리 강화)
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4")

    try:
        OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
        if not (0.0 <= OPENAI_TEMPERATURE <= 2.0):
            OPENAI_TEMPERATURE = 0.7
    except (ValueError, TypeError):
        OPENAI_TEMPERATURE: float = 0.7

    try:
        OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "2000"))
        if OPENAI_MAX_TOKENS <= 0:
            OPENAI_MAX_TOKENS = 2000
    except (ValueError, TypeError):
        OPENAI_MAX_TOKENS: int = 2000

    # Telegram Bot 설정 (예외처리 강화)
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_ADMIN_USER_ID: Optional[str] = os.getenv("TELEGRAM_ADMIN_USER_ID")
    TELEGRAM_ALLOW_PUBLIC: bool = os.getenv("TELEGRAM_ALLOW_PUBLIC", "false").lower() == "true"

    try:
        TELEGRAM_SESSION_TIMEOUT: int = int(os.getenv("TELEGRAM_SESSION_TIMEOUT", "1800"))
        if TELEGRAM_SESSION_TIMEOUT <= 0:
            TELEGRAM_SESSION_TIMEOUT = 1800
    except (ValueError, TypeError):
        TELEGRAM_SESSION_TIMEOUT: int = 1800

    # 안전한 메시지 전송 사용 여부 (기본: True)
    USE_SAFE_MESSAGING: bool = os.getenv("USE_SAFE_MESSAGING", "true").lower() == "true"

    # 장소 검색 API 설정
    PLACE_SEARCH_PROVIDER: str = os.getenv("PLACE_SEARCH_PROVIDER", "naver").lower()  # "naver" or "kakao"

    # 네이버 지역검색 API
    NAVER_CLIENT_ID: str = os.getenv("NAVER_CLIENT_ID", "")
    NAVER_CLIENT_SECRET: str = os.getenv("NAVER_CLIENT_SECRET", "")

    # 카카오 로컬 API
    KAKAO_REST_API_KEY: str = os.getenv("KAKAO_REST_API_KEY", "")

    # 네이버 지도 API
    NAVER_MAP_CLIENT_ID: str = os.getenv("NAVER_MAP_CLIENT_ID", "")
    NAVER_MAP_CLIENT_SECRET: str = os.getenv("NAVER_MAP_CLIENT_SECRET", "")

    @classmethod
    def validate_required_keys(cls) -> Dict[str, bool]:
        """필수 설정 값 검증"""
        return {
            "OPENAI_API_KEY": bool(cls.OPENAI_API_KEY),
            "NAVER_USERNAME": bool(cls.NAVER_USERNAME),
            "NAVER_PASSWORD": bool(cls.NAVER_PASSWORD),
            "NAVER_BLOG_URL": bool(cls.NAVER_BLOG_URL),
        }

    @classmethod
    def validate_telegram_keys(cls) -> Dict[str, bool]:
        """Telegram bot 설정 값 검증"""
        return {
            "TELEGRAM_BOT_TOKEN": bool(cls.TELEGRAM_BOT_TOKEN),
        }

    @classmethod
    def create_directories(cls):
        """
        필요한 디렉토리 생성 (예외처리 강화)

        Raises:
            OSError: 디렉토리 생성 실패
        """
        directories = [
            cls.DATA_DIR,
            cls.DATA_DIR / "posts",
            cls.DATA_DIR / "metadata",
            cls.UPLOADS_DIR,
            cls.UPLOADS_DIR / "images",
            cls.TEMPLATES_DIR,
            cls.LOG_FILE.parent,  # logs 디렉토리
        ]

        created = []
        failed = []

        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                created.append(str(directory))
            except PermissionError as e:
                import logging
                logging.error(f"Permission denied creating directory {directory}: {e}")
                failed.append(str(directory))
            except OSError as e:
                import logging
                logging.error(f"OS error creating directory {directory}: {e}")
                failed.append(str(directory))
            except Exception as e:
                import logging
                logging.error(f"Unexpected error creating directory {directory}: {e}")
                failed.append(str(directory))

        if failed:
            import logging
            logging.warning(f"Failed to create {len(failed)} directories: {', '.join(failed)}")
            # 중요 디렉토리 생성 실패 시 예외 발생
            critical_dirs = [str(cls.DATA_DIR), str(cls.UPLOADS_DIR)]
            if any(fail_dir in failed for fail_dir in critical_dirs):
                raise OSError(f"Failed to create critical directories: {failed}")

        if created:
            import logging
            logging.info(f"Successfully created {len(created)} directories")

    @classmethod
    def get_upload_path(cls, filename: str) -> Path:
        """업로드 파일 경로 생성"""
        return cls.UPLOADS_DIR / "images" / filename

    @classmethod
    def get_post_data_path(cls, post_id: str) -> Path:
        """포스트 데이터 경로 생성"""
        return cls.DATA_DIR / "posts" / f"{post_id}.json"

    @classmethod
    def get_metadata_path(cls, post_id: str) -> Path:
        """메타데이터 경로 생성"""
        return cls.DATA_DIR / "metadata" / f"{post_id}_meta.json"

    @classmethod
    def is_valid_image_extension(cls, filename: str) -> bool:
        """이미지 파일 확장자 검증"""
        return Path(filename).suffix.lower() in cls.ALLOWED_IMAGE_EXTENSIONS
