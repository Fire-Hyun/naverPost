"""
Telegram session manager integration tests.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("telegram")

from src.config.settings import Settings
from src.telegram.models.session import (
    active_sessions,
    account_session_lock,
    create_session,
    delete_session,
    resolve_session_for_request,
    REASON_SESSION_NOT_CREATED,
    REASON_SESSION_PROCESS_BOUND,
    REASON_SESSION_KEY_MISMATCH,
)
from src.telegram.utils.session_validator import SessionValidator


@pytest.fixture(autouse=True)
def _session_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "DATA_DIR", tmp_path)
    active_sessions.clear()
    yield
    active_sessions.clear()


@pytest.mark.asyncio
async def test_validator_recovers_persisted_session_without_missing_error():
    user_id = 9991001
    create_session(user_id)
    # 프로세스 재시작 시나리오: 메모리 세션 상실
    active_sessions.clear()

    update = Mock()
    update.update_id = 101
    update.effective_user.id = user_id
    update.effective_chat.id = user_id
    update.message.reply_text = AsyncMock()
    update.effective_message = update.message

    session = await SessionValidator.validate_and_get_session(update, None, require_session=True)
    assert session is not None
    update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_per_account_lock_serializes_concurrent_requests():
    user_id = 9991002
    timeline: list[str] = []

    async def worker(name: str):
        async with account_session_lock(user_id, f"req-{name}"):
            timeline.append(f"start-{name}")
            await asyncio.sleep(0.05)
            timeline.append(f"end-{name}")

    await asyncio.gather(worker("a"), worker("b"))

    start_a = timeline.index("start-a")
    end_a = timeline.index("end-a")
    start_b = timeline.index("start-b")
    end_b = timeline.index("end-b")
    assert end_a < start_b or end_b < start_a


def test_resolve_session_supports_missing_and_recovery_reasons():
    user_id = 9991003

    # 1) 세션 미생성
    missing, reason_missing, _ = resolve_session_for_request(
        account_id=user_id,
        chat_id=user_id,
        request_id="req-missing",
        require_existing=True,
    )
    assert missing is None
    assert reason_missing == REASON_SESSION_NOT_CREATED

    # 2) persisted 상태에서 복구
    create_session(user_id)
    active_sessions.clear()
    recovered, reason_recovered, _ = resolve_session_for_request(
        account_id=user_id,
        chat_id=user_id,
        request_id="req-recover",
        require_existing=True,
    )
    assert recovered is not None
    assert reason_recovered == REASON_SESSION_PROCESS_BOUND

    # 3) 세션 키 불일치
    delete_session(user_id)
    create_session(7772000)
    mismatch, reason_mismatch, _ = resolve_session_for_request(
        account_id=user_id,
        chat_id=7772000,
        request_id="req-mismatch",
        require_existing=True,
    )
    assert mismatch is None
    assert reason_mismatch == REASON_SESSION_KEY_MISMATCH
