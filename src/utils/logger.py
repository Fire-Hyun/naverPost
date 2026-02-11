"""
네이버 블로그 포스팅 자동화 시스템 로깅 모듈
시스템 전체에서 사용할 구조화된 로깅을 제공합니다.
"""

import sys
from pathlib import Path
from loguru import logger
from src.config.settings import Settings

def setup_logger():
    """로거 초기 설정"""

    # 기본 로거 제거
    logger.remove()

    # 콘솔 출력 설정
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        level=Settings.LOG_LEVEL,
        colorize=True
    )

    # 파일 출력 설정
    log_file = Settings.LOG_FILE
    log_file.parent.mkdir(exist_ok=True)

    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        compression="zip"
    )

    return logger

def get_logger(name: str):
    """모듈별 로거 획득"""
    return logger.bind(name=name)

# 기본 로거 설정
setup_logger()

# 각 모듈별 로거
blog_logger = get_logger("blog")
web_logger = get_logger("web")
content_logger = get_logger("content")
quality_logger = get_logger("quality")
naver_logger = get_logger("naver")
storage_logger = get_logger("storage")