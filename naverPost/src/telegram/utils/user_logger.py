"""
User-specific logging utility for Telegram bot
"""

import os
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path

from src.config.settings import Settings


class UserLogger:
    """사용자별 로그 관리"""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.settings = Settings
        self._setup_logger()

    def _setup_logger(self):
        """사용자별 로거 설정"""
        # 로그 디렉토리 생성
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        # 사용자별 로그 파일 경로
        self.log_file_path = log_dir / f"telegram_bot_{self.user_id}.log"

        # 로거 이름
        logger_name = f"telegram_bot_user_{self.user_id}"
        self.logger = logging.getLogger(logger_name)

        # 이미 핸들러가 설정되어 있으면 중복 설정 방지
        if self.logger.handlers:
            return

        # 로그 레벨 설정
        self.logger.setLevel(logging.INFO)

        # 파일 핸들러 설정
        file_handler = logging.FileHandler(
            self.log_file_path,
            encoding='utf-8',
            mode='a'
        )

        # 로그 포맷 설정
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)

        # 핸들러 추가
        self.logger.addHandler(file_handler)

        # 상위 로거로 전파 방지
        self.logger.propagate = False

    def info(self, message: str):
        """정보 로그"""
        self.logger.info(message)

    def error(self, message: str):
        """에러 로그"""
        self.logger.error(message)

    def warning(self, message: str):
        """경고 로그"""
        self.logger.warning(message)

    def debug(self, message: str):
        """디버그 로그"""
        self.logger.debug(message)

    def log_session_start(self):
        """세션 시작 로그"""
        self.info("=== 새 블로그 작성 세션 시작 ===")

    def log_session_cancel(self):
        """세션 취소 로그"""
        self.info(">>> 세션이 취소되었습니다")

    def log_date_input(self, date: str):
        """날짜 입력 로그"""
        self.info(f"방문 날짜 입력: {date}")

    def log_category_selected(self, category: str):
        """카테고리 선택 로그"""
        self.info(f"카테고리 선택: {category}")

    def log_store_name_input(self, store_name: str):
        """상호명 입력 로그"""
        self.info(f"상호명 입력: {store_name}")

    def log_store_name_resolved(self, raw_name: str, resolved_name: str):
        """상호명 보정 로그"""
        self.info(f"상호명 보정 완료: '{raw_name}' → '{resolved_name}'")

    def log_image_uploaded(self, count: int, filename: Optional[str] = None):
        """이미지 업로드 로그"""
        msg = f"이미지 업로드 완료 ({count}장)"
        if filename:
            msg += f" - {filename}"
        self.info(msg)

    def log_review_submitted(self, length: int):
        """감상평 제출 로그"""
        self.info(f"감상평 입력 완료 ({length}자)")

    def log_additional_content(self, has_content: bool):
        """추가 내용 로그"""
        status = "있음" if has_content else "없음"
        self.info(f"추가 내용: {status}")

    def log_generation_start(self):
        """블로그 생성 시작 로그"""
        self.info(">>> 블로그 자동 생성 시작")

    def log_generation_step(self, step: str, details: Optional[str] = None):
        """블로그 생성 단계별 로그"""
        msg = f"  단계: {step}"
        if details:
            msg += f" - {details}"
        self.info(msg)

    def log_generation_success(self, file_path: str, length: str):
        """블로그 생성 성공 로그"""
        self.info(f">>> 블로그 생성 완료: {file_path} ({length})")

    def log_generation_error(self, error: str):
        """블로그 생성 오류 로그"""
        self.error(f">>> 블로그 생성 실패: {error}")

    def log_naver_upload_start(self):
        """네이버 업로드 시작 로그"""
        self.info(">>> 네이버 블로그 업로드 시작")

    def log_naver_upload_success(self, post_url: Optional[str] = None):
        """네이버 업로드 성공 로그"""
        msg = ">>> 네이버 블로그 업로드 완료"
        if post_url:
            msg += f": {post_url}"
        self.info(msg)

    def log_naver_upload_error(self, error: str):
        """네이버 업로드 오류 로그"""
        self.error(f">>> 네이버 블로그 업로드 실패: {error}")

    def log_quality_check(self, score: float, issues: Optional[list] = None):
        """품질 검사 로그"""
        msg = f"품질 검사 완료: 점수 {score}/100"
        if issues:
            msg += f", 이슈 {len(issues)}개"
        self.info(msg)

    def log_workflow_step(self, step_name: str, status: str, details: Optional[str] = None):
        """워크플로 단계 로그"""
        msg = f"워크플로 [{step_name}]: {status}"
        if details:
            msg += f" - {details}"
        self.info(msg)

    def get_recent_logs(self, lines: int = 50) -> list:
        """최근 로그 라인 반환"""
        try:
            if not self.log_file_path.exists():
                return []

            with open(self.log_file_path, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()

            # 최근 N줄 반환
            return all_lines[-lines:] if len(all_lines) > lines else all_lines

        except Exception as e:
            self.error(f"로그 읽기 오류: {e}")
            return []

    def clear_logs(self):
        """로그 파일 초기화"""
        try:
            if self.log_file_path.exists():
                self.log_file_path.unlink()
            self.info("=== 로그 파일 초기화 ===")
        except Exception as e:
            self.error(f"로그 초기화 오류: {e}")


# 전역 로거 인스턴스 캐시
_user_loggers = {}

def get_user_logger(user_id: int) -> UserLogger:
    """사용자별 로거 인스턴스 반환 (싱글톤 패턴)"""
    if user_id not in _user_loggers:
        _user_loggers[user_id] = UserLogger(user_id)
    return _user_loggers[user_id]