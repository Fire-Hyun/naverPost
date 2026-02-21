"""
Session validation utilities
"""

from typing import Optional
import logging
from telegram import Update
from telegram.ext import ContextTypes

from ..models.session import (
    TelegramSession,
    delete_session,
    resolve_session_for_request,
    update_session,
    REASON_SESSION_NOT_CREATED,
    REASON_SESSION_EVICTED,
    REASON_SESSION_KEY_MISMATCH,
    REASON_SESSION_PROCESS_BOUND,
)
from ..models.responses import ResponseTemplates
from ..constants import DEFAULT_SESSION_TIMEOUT

logger = logging.getLogger(__name__)


class SessionValidator:
    """세션 검증 관련 공통 기능"""

    @staticmethod
    async def validate_and_get_session(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        require_session: bool = True
    ) -> Optional[TelegramSession]:
        """
        세션을 검증하고 반환합니다.

        Args:
            update: Telegram update object
            context: Telegram context
            require_session: 세션이 필수인지 여부

        Returns:
            TelegramSession 또는 None (세션이 없거나 만료된 경우)
        """
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id if update.effective_chat else None
        request_id = f"upd-{getattr(update, 'update_id', 'na')}"
        # 테스트 Mock 환경에서 effective_message가 자동 생성 Mock이 될 수 있어
        # message를 우선 사용한다.
        reply_target = getattr(update, "message", None) or getattr(update, "effective_message", None)
        session, reason_code, debug_path = resolve_session_for_request(
            account_id=user_id,
            chat_id=chat_id,
            request_id=request_id,
            require_existing=require_session,
        )
        responses = ResponseTemplates()

        if not session:
            if require_session:
                msg = (
                    f"ACTIVE_SESSION_MISSING reason_code={reason_code} "
                    f"accountId={user_id} requestId={request_id} debugPath={debug_path or '-'}"
                )
                if reason_code in {
                    REASON_SESSION_NOT_CREATED,
                    REASON_SESSION_EVICTED,
                    REASON_SESSION_KEY_MISMATCH,
                    REASON_SESSION_PROCESS_BOUND,
                }:
                    logger.error(msg)
                if reply_target:
                    await reply_target.reply_text(
                        responses.no_active_session(),
                        reply_markup=responses.create_start_keyboard()
                    )
            return None

        if session.is_expired(DEFAULT_SESSION_TIMEOUT):
            # 만료된 세션 정리
            SessionValidator._cleanup_expired_session(user_id, session)
            if require_session:
                if reply_target:
                    await reply_target.reply_text(
                        responses.session_expired(),
                        reply_markup=responses.create_start_keyboard()
                    )
            return None

        # 활동 시간 업데이트
        session.update_activity()
        update_session(session)
        return session

    @staticmethod
    def _cleanup_expired_session(user_id: int, session: TelegramSession):
        """만료된 세션 정리"""
        # 이미지 핸들러를 통한 파일 정리는 필요시 별도 처리
        delete_session(user_id)
