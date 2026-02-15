"""
Input validation utilities
"""

from typing import Optional
from datetime import datetime


class DateValidator:
    """날짜 검증 관련 기능"""

    @staticmethod
    def parse_date_input(text: str) -> Optional[str]:
        """
        사용자 입력을 날짜 형식으로 변환

        Args:
            text: 사용자 입력 (YYYYMMDD 또는 '오늘', 'today')

        Returns:
            YYYYMMDD 형식 문자열 또는 None (유효하지 않은 경우)
        """
        text = text.strip().lower()

        # '오늘' 또는 'today' 처리
        if text in ['오늘', 'today']:
            return datetime.now().strftime('%Y%m%d')

        # YYYYMMDD 형식 검증
        if DateValidator._is_valid_date_format(text):
            return text

        return None

    @staticmethod
    def _is_valid_date_format(date_str: str) -> bool:
        """날짜 형식 검증 (YYYYMMDD)"""
        if len(date_str) != 8 or not date_str.isdigit():
            return False

        try:
            datetime.strptime(date_str, '%Y%m%d')
            return True
        except ValueError:
            return False