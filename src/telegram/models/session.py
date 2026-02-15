"""
Telegram bot session state management
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ConversationState(Enum):
    """텔레그램 봇 대화 상태"""
    START = "start"
    WAITING_DATE = "waiting_date"
    WAITING_CATEGORY = "waiting_category"
    WAITING_STORE_NAME = "waiting_store_name"
    WAITING_IMAGES = "waiting_images"
    WAITING_REVIEW = "waiting_review"
    WAITING_ADDITIONAL = "waiting_additional"
    READY_TO_GENERATE = "ready_to_generate"
    GENERATING = "generating"
    COMPLETED = "completed"


@dataclass
class LocationInfo:
    """위치 정보"""
    lat: float
    lng: float
    source: str  # "telegram_location", "exif_gps", "manual"


@dataclass
class TelegramSession:
    """텔레그램 봇 사용자 세션"""
    user_id: int
    state: ConversationState = ConversationState.START
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)

    # 수집된 데이터
    visit_date: Optional[str] = None
    category: Optional[str] = None
    raw_store_name: Optional[str] = None  # 사용자 입력 그대로
    resolved_store_name: Optional[str] = None  # 보정/검증 후 최종값
    location: Optional[LocationInfo] = None  # 위치 정보
    images: List[str] = field(default_factory=list)  # 파일 경로들
    personal_review: Optional[str] = None
    additional_script: Optional[str] = None

    # 생성된 데이터
    date_directory: Optional[str] = None
    blog_generated: bool = False

    def update_activity(self):
        """활동 시간 업데이트"""
        self.last_activity = datetime.now()

    def is_expired(self, timeout_seconds: int = None) -> bool:
        """세션 만료 확인"""
        if timeout_seconds is None:
            from ..constants import DEFAULT_SESSION_TIMEOUT
            timeout_seconds = DEFAULT_SESSION_TIMEOUT

        elapsed = (datetime.now() - self.last_activity).total_seconds()
        return elapsed > timeout_seconds

    def to_user_experience_dict(self) -> Dict[str, Any]:
        """DateBasedDataManager가 예상하는 형식으로 변환"""
        return {
            "category": self.category,
            "store_name": self.resolved_store_name,
            "personal_review": self.personal_review,
            "ai_additional_script": self.additional_script or "",
            "visit_date": self.visit_date,
            "rating": None,  # 텔레그램에서는 수집하지 않음
            "companion": None,  # 텔레그램에서는 수집하지 않음
            "location": self.location.lat if self.location else None,
            "hashtags": []  # AI가 자동으로 생성
        }

    def get_progress_summary(self) -> str:
        """진행 상황 요약 (utils의 ProgressSummaryBuilder 사용)"""
        from ..utils.formatters import ProgressSummaryBuilder
        return ProgressSummaryBuilder.build_summary(self)

    def get_missing_fields(self) -> List[str]:
        """누락된 필수 필드 목록"""
        missing = []

        if not self.visit_date:
            missing.append("방문 날짜")

        if not self.category:
            missing.append("카테고리")

        if not self.resolved_store_name:
            missing.append("상호명")

        if not self.images:
            missing.append("사진")

        if not self.personal_review:
            missing.append("감상평")

        return missing

    def is_ready_for_generation(self) -> bool:
        """블로그 생성 준비 완료 확인"""
        return len(self.get_missing_fields()) == 0


# 전역 세션 저장소 (메모리 내)
active_sessions: Dict[int, TelegramSession] = {}


def get_session(user_id: int) -> Optional[TelegramSession]:
    """사용자 세션 조회"""
    return active_sessions.get(user_id)


def create_session(user_id: int) -> TelegramSession:
    """새 세션 생성"""
    session = TelegramSession(user_id=user_id, state=ConversationState.WAITING_DATE)
    active_sessions[user_id] = session
    return session


def delete_session(user_id: int) -> bool:
    """세션 삭제"""
    if user_id in active_sessions:
        del active_sessions[user_id]
        return True
    return False


def cleanup_expired_sessions(timeout_seconds: int = None) -> int:
    """만료된 세션 정리"""
    if timeout_seconds is None:
        from ..constants import DEFAULT_SESSION_TIMEOUT
        timeout_seconds = DEFAULT_SESSION_TIMEOUT

    expired_users = []

    for user_id, session in active_sessions.items():
        if session.is_expired(timeout_seconds):
            expired_users.append(user_id)

    for user_id in expired_users:
        del active_sessions[user_id]

    return len(expired_users)


def get_active_sessions_count() -> int:
    """활성 세션 수"""
    return len(active_sessions)