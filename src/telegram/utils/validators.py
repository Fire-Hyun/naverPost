"""
Input validation utilities
"""

from typing import Optional, Tuple
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

# 미래 날짜 허용 여부
ALLOW_FUTURE_DATE = True

# 기본 타임존
DEFAULT_TIMEZONE = "Asia/Seoul"


def parse_visit_date(
    input_text: str,
    tz: str = DEFAULT_TIMEZONE,
) -> Tuple[Optional[str], Optional[str]]:
    """
    사용자 입력을 방문 날짜(YYYYMMDD)로 변환한다.

    지원 입력:
        - "오늘", "today"
        - "어제", "yesterday"
        - "YYYYMMDD" (예: 20260212)
        - "YYYY-MM-DD" (예: 2026-02-12)

    Args:
        input_text: 사용자 입력 문자열
        tz: 타임존 문자열 (기본: Asia/Seoul)

    Returns:
        (date_str, None) 성공 시 YYYYMMDD 형식 문자열
        (None, error_message) 실패 시 에러 메시지
    """
    text = input_text.strip().lower()

    if not text:
        return None, "날짜를 입력해주세요."

    zone = ZoneInfo(tz)
    now = datetime.now(zone)
    today = now.date()

    # 키워드 처리
    keyword_map = {
        "오늘": today,
        "today": today,
        "어제": today - timedelta(days=1),
        "yesterday": today - timedelta(days=1),
    }

    if text in keyword_map:
        return keyword_map[text].strftime("%Y%m%d"), None

    # YYYY-MM-DD 형식 → YYYYMMDD로 정규화
    normalized = text.replace("-", "")

    # 숫자 8자리 검증
    if len(normalized) != 8 or not normalized.isdigit():
        return None, (
            "날짜 형식이 올바르지 않습니다.\n"
            "다음 형식을 사용해주세요:\n"
            "• YYYYMMDD (예: 20260212)\n"
            "• YYYY-MM-DD (예: 2026-02-12)\n"
            "• '오늘', '어제'"
        )

    # 실제 존재하는 날짜인지 검증 (윤년 등)
    try:
        parsed = datetime.strptime(normalized, "%Y%m%d").date()
    except ValueError:
        return None, f"존재하지 않는 날짜입니다: {text}"

    # 미래 날짜 정책
    if not ALLOW_FUTURE_DATE and parsed > today:
        return None, f"미래 날짜는 입력할 수 없습니다: {text}"

    return normalized, None


class DateValidator:
    """날짜 검증 관련 기능 (하위 호환용)"""

    @staticmethod
    def parse_date_input(text: str) -> Optional[str]:
        """
        사용자 입력을 날짜 형식으로 변환 (하위 호환)

        내부적으로 parse_visit_date()를 호출한다.
        """
        date_str, _ = parse_visit_date(text)
        return date_str