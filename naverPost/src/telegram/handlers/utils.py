"""
Telegram bot utility functions
"""

from pathlib import Path
from typing import Optional
import tempfile
import shutil


class TelegramUtils:
    """텔레그램 봇 유틸리티 함수들"""

    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """바이트를 읽기 쉬운 형식으로 변환"""
        if size_bytes == 0:
            return "0B"

        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1

        return f"{size_bytes:.1f}{size_names[i]}"

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """파일명에서 위험한 문자 제거"""
        import re
        # 파일명에 허용되지 않는 문자 제거
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # 연속된 언더스코어를 하나로 변경
        sanitized = re.sub(r'_+', '_', sanitized)
        # 앞뒤 공백과 점 제거
        sanitized = sanitized.strip(' .')
        # 빈 문자열이면 기본값 사용
        if not sanitized:
            sanitized = "unnamed_file"

        return sanitized

    @staticmethod
    def create_temp_file(suffix: str = "", prefix: str = "telegram_") -> str:
        """임시 파일 생성"""
        temp_file = tempfile.NamedTemporaryFile(
            suffix=suffix,
            prefix=prefix,
            delete=False
        )
        temp_file.close()
        return temp_file.name

    @staticmethod
    def clean_temp_file(file_path: str) -> bool:
        """임시 파일 삭제"""
        try:
            Path(file_path).unlink(missing_ok=True)
            return True
        except Exception:
            return False

    @staticmethod
    def get_file_extension(filename: str) -> str:
        """파일 확장자 추출"""
        return Path(filename).suffix.lower()

    @staticmethod
    def is_image_file(filename: str) -> bool:
        """이미지 파일인지 확인"""
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
        return TelegramUtils.get_file_extension(filename) in image_extensions

    @staticmethod
    def truncate_text(text: str, max_length: int = 4096, suffix: str = "...") -> str:
        """텍스트를 지정된 길이로 자르기 (텔레그램 메시지 길이 제한)"""
        if len(text) <= max_length:
            return text

        return text[:max_length - len(suffix)] + suffix

    @staticmethod
    def escape_markdown(text: str) -> str:
        """텔레그램 마크다운에서 특수 문자 이스케이프"""
        escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        return text

    @staticmethod
    def format_progress_bar(current: int, total: int, width: int = 20) -> str:
        """진행률 바 생성"""
        if total == 0:
            return "░" * width

        progress = current / total
        filled = int(progress * width)
        bar = "█" * filled + "░" * (width - filled)
        percentage = int(progress * 100)

        return f"{bar} {percentage}%"

    @staticmethod
    def validate_user_id(user_id_str: Optional[str]) -> bool:
        """사용자 ID 검증"""
        if not user_id_str:
            return False

        try:
            user_id = int(user_id_str)
            return user_id > 0
        except (ValueError, TypeError):
            return False