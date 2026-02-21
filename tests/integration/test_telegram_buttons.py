"""
Telegram button UX integration tests.

목표:
- /start 없이 시작하기 버튼으로 시작 가능
- 마지막 단계에서 완료하기 버튼 노출
- 완료하기 버튼 클릭으로 생성 플로우 실행
"""

import sys
import types
from pathlib import Path
from unittest.mock import Mock, AsyncMock

import pytest

# Ensure project root is importable during direct pytest runs.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.telegram.constants import ACTION_START, ACTION_DONE
from src.telegram.handlers.conversation import ConversationHandler
from src.telegram.models.responses import ResponseTemplates
from src.telegram.models.session import (
    TelegramSession,
    ConversationState,
    create_session,
    delete_session,
    get_session,
)
from src.telegram.utils.session_validator import SessionValidator


def _inline_callbacks(markup) -> list[str]:
    callbacks = []
    for row in markup.inline_keyboard:
        for button in row:
            callbacks.append(button.callback_data)
    return callbacks


@pytest.fixture(autouse=True)
def _cleanup_test_session():
    # 테스트 간 세션 누수 방지
    delete_session(777001)
    yield
    delete_session(777001)


def test_start_keyboard_payload_contains_action_start():
    """시작 버튼 키보드 payload가 올바른 callback_data를 갖는지 검증"""
    keyboard = ResponseTemplates.create_start_keyboard()
    assert ACTION_START in _inline_callbacks(keyboard)


@pytest.mark.asyncio
async def test_no_session_text_path_shows_start_button():
    """세션이 없을 때 텍스트 입력해도 시작 버튼이 함께 오는지 검증"""
    update = Mock()
    update.effective_user.id = 777001
    update.message.reply_text = AsyncMock()

    session = await SessionValidator.validate_and_get_session(update, None, require_session=True)
    assert session is None

    kwargs = update.message.reply_text.call_args.kwargs
    assert "reply_markup" in kwargs
    assert ACTION_START in _inline_callbacks(kwargs["reply_markup"])


@pytest.mark.asyncio
async def test_done_button_appears_in_ready_state():
    """입력 완료 단계에서 완료하기 버튼이 노출되는지 검증"""
    handler = ConversationHandler(Mock())
    update = Mock()
    update.effective_user.id = 777001
    update.message.reply_text = AsyncMock()

    session = TelegramSession(
        user_id=777001,
        state=ConversationState.WAITING_ADDITIONAL,
        visit_date="20260214",
        category="패션",
        resolved_store_name="자라 강남점",
        images=["/tmp/a.jpg"],
        personal_review="충분히 긴 감상평입니다. " * 5,
    )

    await handler._handle_additional_input(update, session, "없음")

    assert session.state == ConversationState.READY_TO_GENERATE
    kwargs = update.message.reply_text.call_args.kwargs
    assert "reply_markup" in kwargs
    assert ACTION_DONE in _inline_callbacks(kwargs["reply_markup"])


@pytest.mark.asyncio
async def test_start_button_callback_moves_to_date_step():
    """시작하기 버튼 클릭 시 날짜 입력 단계 프롬프트로 이동하는지 검증"""
    handler = ConversationHandler(Mock())
    session = create_session(777001)

    query = Mock()
    query.data = ACTION_START
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()

    update = Mock()
    update.callback_query = query

    await handler.handle_callback_query(update, None, session)

    text = query.edit_message_text.call_args.args[0]
    kwargs = query.edit_message_text.call_args.kwargs
    assert "방문 날짜" in text
    assert "reply_markup" in kwargs
    assert "date_today" in _inline_callbacks(kwargs["reply_markup"])
    refreshed_session = get_session(777001)
    assert refreshed_session is not None
    assert refreshed_session.state == ConversationState.WAITING_DATE


@pytest.mark.asyncio
async def test_done_button_callback_triggers_generation():
    """완료하기 버튼 클릭 시 생성/제출 핸들러가 실제로 호출되는지 검증"""
    generate_blog_async = AsyncMock(return_value={"success": True})

    bot = Mock()
    bot.blog_service.generate_blog_from_session = generate_blog_async

    handler = ConversationHandler(bot)
    session = create_session(777001)
    session.state = ConversationState.READY_TO_GENERATE
    session.visit_date = "20260214"
    session.category = "패션"
    session.resolved_store_name = "자라 강남점"
    session.images = ["/tmp/a.jpg"]
    session.personal_review = "충분히 긴 감상평입니다. " * 5

    query = Mock()
    query.data = ACTION_DONE
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = Mock()
    query.from_user = Mock()

    update = Mock()
    update.callback_query = query

    await handler.handle_callback_query(update, None, session)

    generate_blog_async.assert_awaited_once()
    # 세션이 여전히 유효한 상태 전환 경로인지 확인
    assert get_session(777001) is not None
