"""
네이버 블로그 포스팅 자동화 시스템 메인 웹 애플리케이션
FastAPI 기반 웹 서버를 제공합니다.
"""

import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import Settings
from src.utils.logger import web_logger
from src.utils.exceptions import BlogSystemError, ConfigurationError
from src.web.routes.upload import router as upload_router

# 설정 검증
def validate_configuration():
    """필수 설정 값 검증"""
    missing_keys = []
    validation_result = Settings.validate_required_keys()

    for key, is_valid in validation_result.items():
        if not is_valid:
            missing_keys.append(key)

    if missing_keys:
        raise ConfigurationError(
            "필수 설정 값이 누락되었습니다",
            missing_keys=missing_keys
        )

# 필요한 디렉토리 생성
Settings.create_directories()

# 설정 검증
try:
    validate_configuration()
    web_logger.info("Configuration validation passed")
except ConfigurationError as e:
    web_logger.error(f"Configuration validation failed: {e}")
    # 개발 환경에서는 경고만 표시하고 계속 진행
    if not Settings.WEB_DEBUG:
        raise

# Lifespan 이벤트 핸들러
@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 시작 및 종료 이벤트 처리"""
    # Startup
    web_logger.info(f"Starting Naver Blog Automation System on {Settings.WEB_HOST}:{Settings.WEB_PORT}")
    web_logger.info(f"Debug mode: {Settings.WEB_DEBUG}")
    yield
    # Shutdown
    web_logger.info("Shutting down Naver Blog Automation System")

# FastAPI 앱 생성
app = FastAPI(
    title="네이버 블로그 포스팅 자동화 시스템",
    description="사용자 경험 기반 고품질 블로그 포스트 생성 및 자동 업로드",
    version="1.0.0",
    servers=[{"url": f"http://{Settings.WEB_HOST}:{Settings.WEB_PORT}"}],
    lifespan=lifespan,
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 개발 환경용, 운영에서는 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 서빙 (HTML, CSS, JS)
static_dir = Settings.PROJECT_ROOT / "src" / "web" / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 업로드된 이미지 서빙
uploads_dir = Settings.UPLOADS_DIR
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# 라우터 등록
app.include_router(upload_router, prefix="/api", tags=["upload"])

@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "message": "네이버 블로그 포스팅 자동화 시스템",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    """헬스 체크 엔드포인트"""
    try:
        # 기본적인 설정 및 디렉토리 검증
        Settings.create_directories()

        return {
            "status": "healthy",
            "config": {
                "openai_configured": bool(Settings.OPENAI_API_KEY),
                "naver_configured": bool(Settings.NAVER_USERNAME and Settings.NAVER_PASSWORD),
                "directories_ready": True
            }
        }
    except Exception as e:
        web_logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """요청 유효성 검사 실패 처리"""
    web_logger.error(
        "Validation error on %s %s. body=%s errors=%s",
        request.method,
        request.url.path,
        exc.body,
        exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({"detail": exc.errors(), "message": "요청 데이터가 올바르지 않습니다"}),
    )

@app.exception_handler(BlogSystemError)
async def blog_system_exception_handler(request: Request, exc: BlogSystemError) -> JSONResponse:
    """블로그 시스템 예외 처리"""
    web_logger.error(f"Blog system error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "system_error",
            "message": exc.message,
            "step": exc.step,
            "details": exc.details
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """일반 예외 처리"""
    web_logger.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "서버 내부 오류가 발생했습니다"
        }
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.web.app:app",
        host=Settings.WEB_HOST,
        port=Settings.WEB_PORT,
        reload=Settings.WEB_DEBUG
    )