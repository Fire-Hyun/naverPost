"""
Session validation utilities
"""

from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes

from ..models.session import TelegramSession, get_session, delete_session
from ..models.responses import ResponseTemplates
from ..constants import DEFAULT_SESSION_TIMEOUT


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
        session = get_session(user_id)
        responses = ResponseTemplates()

        if not session:
            if require_session:
                await update.message.reply_text(
                    responses.no_active_session(),
                    reply_markup=responses.create_start_keyboard()
                )
            return None

        if session.is_expired(DEFAULT_SESSION_TIMEOUT):
            # 만료된 세션 정리
            SessionValidator._cleanup_expired_session(user_id, session)
            if require_session:
                await update.message.reply_text(
                    responses.session_expired(),
                    reply_markup=responses.create_start_keyboard()
                )
            return None

        # 활동 시간 업데이트
        session.update_activity()
        return session

    @staticmethod
    def _cleanup_expired_session(user_id: int, session: TelegramSession):
        """만료된 세션 정리"""
        # 이미지 핸들러를 통한 파일 정리는 필요시 별도 처리
        delete_session(user_id)
