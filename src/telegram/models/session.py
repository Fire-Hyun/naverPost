"""
Telegram bot session state management
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import asyncio
import json
import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from src.config.settings import Settings


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
_session_locks: Dict[int, asyncio.Lock] = {}
_session_lock_guard = threading.Lock()
_logger = logging.getLogger(__name__)

REASON_SESSION_NOT_CREATED = "SESSION_NOT_CREATED"
REASON_SESSION_EVICTED = "SESSION_EVICTED"
REASON_SESSION_KEY_MISMATCH = "SESSION_KEY_MISMATCH"
REASON_SESSION_PROCESS_BOUND = "SESSION_PROCESS_BOUND"
REASON_SESSION_OK = "SESSION_OK"

_last_session_event: Dict[int, str] = {}


def _session_store_dir() -> Path:
    base = Settings.DATA_DIR / "telegram_sessions"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _session_file(account_id: int) -> Path:
    return _session_store_dir() / f"{account_id}.json"


def _lock_file(account_id: int) -> Path:
    lock_dir = _session_store_dir() / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / f"{account_id}.lock"


def _get_session_lock(account_id: int) -> asyncio.Lock:
    with _session_lock_guard:
        lock = _session_locks.get(account_id)
        if lock is None:
            lock = asyncio.Lock()
            _session_locks[account_id] = lock
        return lock


def _session_to_dict(session: TelegramSession) -> Dict[str, Any]:
    return {
        "user_id": session.user_id,
        "state": session.state.value,
        "created_at": session.created_at.isoformat(),
        "last_activity": session.last_activity.isoformat(),
        "visit_date": session.visit_date,
        "category": session.category,
        "raw_store_name": session.raw_store_name,
        "resolved_store_name": session.resolved_store_name,
        "location": (
            {
                "lat": session.location.lat,
                "lng": session.location.lng,
                "source": session.location.source,
            } if session.location else None
        ),
        "images": list(session.images),
        "personal_review": session.personal_review,
        "additional_script": session.additional_script,
        "date_directory": session.date_directory,
        "blog_generated": session.blog_generated,
    }


def _session_from_dict(data: Dict[str, Any]) -> TelegramSession:
    session = TelegramSession(
        user_id=int(data["user_id"]),
        state=ConversationState(data.get("state", ConversationState.WAITING_DATE.value)),
        created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
        last_activity=datetime.fromisoformat(data.get("last_activity", datetime.now().isoformat())),
    )
    session.visit_date = data.get("visit_date")
    session.category = data.get("category")
    session.raw_store_name = data.get("raw_store_name")
    session.resolved_store_name = data.get("resolved_store_name")
    location_data = data.get("location")
    if location_data:
        session.location = LocationInfo(
            lat=float(location_data["lat"]),
            lng=float(location_data["lng"]),
            source=str(location_data.get("source", "manual")),
        )
    session.images = list(data.get("images") or [])
    session.personal_review = data.get("personal_review")
    session.additional_script = data.get("additional_script")
    session.date_directory = data.get("date_directory")
    session.blog_generated = bool(data.get("blog_generated", False))
    return session


def _persist_session(session: TelegramSession) -> None:
    payload = _session_to_dict(session)
    target = _session_file(session.user_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)


def _load_persisted_session(account_id: int) -> Optional[TelegramSession]:
    file_path = _session_file(account_id)
    if not file_path.exists():
        return None
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        return _session_from_dict(payload)
    except Exception as exc:
        _logger.warning("Failed to load persisted session account_id=%s error=%s", account_id, exc)
        return None


def _remove_persisted_session(account_id: int) -> None:
    file_path = _session_file(account_id)
    try:
        file_path.unlink(missing_ok=True)
    except Exception:
        pass


def _create_session_debug_artifact(
    account_id: int,
    chat_id: Optional[int],
    request_id: str,
    reason_code: str,
) -> Optional[str]:
    try:
        debug_root = Settings.LOG_DIR / "session_debug"
        debug_root.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%dT%H%M%S_%f")
        path = debug_root / f"{ts}_{account_id}_{reason_code}.json"
        storage_file = _session_file(account_id)
        storage_exists = storage_file.exists()
        lock_path = _lock_file(account_id)
        lock_exists = lock_path.exists()
        lock_payload: Optional[Dict[str, Any]] = None
        lock_age_seconds: Optional[float] = None
        if lock_exists:
            try:
                lock_payload = json.loads(lock_path.read_text(encoding="utf-8"))
                lock_age_seconds = max(0.0, time.time() - lock_path.stat().st_mtime)
            except Exception:
                lock_payload = None
        payload = {
            "timestamp": datetime.now().isoformat(),
            "pid": os.getpid(),
            "request_id": request_id,
            "account_id": account_id,
            "chat_id": chat_id,
            "reason_code": reason_code,
            "active_session_keys": sorted(list(active_sessions.keys())),
            "lock_state": {
                "path": str(lock_path),
                "exists": lock_exists,
                "owner": lock_payload,
                "age_seconds": lock_age_seconds,
            },
            "storage_state": {
                "path": str(storage_file),
                "exists": storage_exists,
                "mtime": storage_file.stat().st_mtime if storage_exists else None,
            },
            "last_session_event": _last_session_event.get(account_id),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)
    except Exception:
        return None


def _acquire_file_lock(account_id: int, request_id: str, timeout_seconds: float = 3.0) -> bool:
    # asyncio.Lock이 단일 프로세스 동시성을 보호하므로, 파일 잠금은 한 번만 시도한다.
    # time.sleep으로 이벤트 루프를 차단하지 않도록 재시도 루프를 제거했다.
    target = _lock_file(account_id)
    try:
        fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps({"pid": os.getpid(), "request_id": request_id, "ts": datetime.now().isoformat()}))
        return True
    except FileExistsError:
        return False


def _release_file_lock(account_id: int) -> None:
    try:
        _lock_file(account_id).unlink(missing_ok=True)
    except Exception:
        pass


def get_session(user_id: int) -> Optional[TelegramSession]:
    """사용자 세션 조회"""
    session = active_sessions.get(user_id)
    if session:
        return session

    restored = _load_persisted_session(user_id)
    if restored:
        active_sessions[user_id] = restored
        _last_session_event[user_id] = "restored_from_persisted_store"
        return restored
    return None


def create_session(user_id: int) -> TelegramSession:
    """새 세션 생성"""
    session = TelegramSession(user_id=user_id, state=ConversationState.WAITING_DATE)
    active_sessions[user_id] = session
    _persist_session(session)
    _last_session_event[user_id] = "created"
    return session


def delete_session(user_id: int) -> bool:
    """세션 삭제"""
    if user_id in active_sessions:
        del active_sessions[user_id]
        _remove_persisted_session(user_id)
        _last_session_event[user_id] = "deleted"
        return True
    _remove_persisted_session(user_id)
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
        _remove_persisted_session(user_id)
        _last_session_event[user_id] = "expired_cleanup"

    return len(expired_users)


def get_active_sessions_count() -> int:
    """활성 세션 수"""
    return len(active_sessions)


def touch_session(user_id: int) -> None:
    session = active_sessions.get(user_id)
    if not session:
        return
    session.update_activity()
    _persist_session(session)


def update_session(session: TelegramSession) -> None:
    active_sessions[session.user_id] = session
    _persist_session(session)
    _last_session_event[session.user_id] = "updated"


def resolve_session_for_request(
    account_id: int,
    chat_id: Optional[int],
    request_id: str,
    require_existing: bool = True,
) -> tuple[Optional[TelegramSession], str, Optional[str]]:
    session = active_sessions.get(account_id)
    if session and not session.is_expired():
        session.update_activity()
        _persist_session(session)
        return session, REASON_SESSION_OK, None

    if session and session.is_expired():
        delete_session(account_id)

    restored = _load_persisted_session(account_id)
    if restored and not restored.is_expired():
        active_sessions[account_id] = restored
        restored.update_activity()
        _persist_session(restored)
        _last_session_event[account_id] = "recovered_from_storage"
        return restored, REASON_SESSION_PROCESS_BOUND, None

    if chat_id is not None and chat_id in active_sessions and chat_id != account_id:
        debug_path = _create_session_debug_artifact(account_id, chat_id, request_id, REASON_SESSION_KEY_MISMATCH)
        return None, REASON_SESSION_KEY_MISMATCH, debug_path

    if require_existing:
        reason = _last_session_event.get(account_id)
        if reason in {"deleted", "expired_cleanup"}:
            code = REASON_SESSION_EVICTED
        else:
            code = REASON_SESSION_NOT_CREATED
        debug_path = _create_session_debug_artifact(account_id, chat_id, request_id, code)
        return None, code, debug_path

    created = create_session(account_id)
    created.update_activity()
    _persist_session(created)
    return created, REASON_SESSION_NOT_CREATED, None


@asynccontextmanager
async def account_session_lock(account_id: int, request_id: str):
    lock = _get_session_lock(account_id)
    await lock.acquire()
    file_lock = _acquire_file_lock(account_id, request_id)
    try:
        yield
    finally:
        if file_lock:
            _release_file_lock(account_id)
        lock.release()
