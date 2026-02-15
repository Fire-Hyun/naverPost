"""
Base state handler for conversation flow
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from telegram import Update
from telegram.ext import ContextTypes

from ...models.session import TelegramSession, ConversationState
from ...models.responses import ResponseTemplates
from ...utils.safe_message_mixin import SafeMessageMixin
from ...utils import get_user_logger


class BaseStateHandler(SafeMessageMixin, ABC):
    """모든 상태 핸들러의 기본 클래스"""

    def __init__(self, bot, settings):
        super().__init__()  # Initialize SafeMessageMixin
        self.bot = bot
        self.settings = settings
        self.responses = ResponseTemplates()

    @abstractmethod
    async def handle_input(
        self,
        update: Update,
        session: TelegramSession,
        text: str
    ) -> Optional[ConversationState]:
        """
        입력을 처리하고 다음 상태를 반환

        Args:
            update: Telegram update object
            session: 현재 사용자 세션
            text: 사용자 입력 텍스트

        Returns:
            다음 상태 (None이면 상태 변경 없음)
        """
        pass

    async def log_user_activity(self, update: Update, action: str, **kwargs):
        """사용자 활동 로깅"""
        user_logger = get_user_logger(update.effective_user.id)
        if hasattr(user_logger, f'log_{action}'):
            log_method = getattr(user_logger, f'log_{action}')
            log_method(**kwargs)

    def get_user_id(self, update: Update) -> int:
        """사용자 ID 추출"""
        return update.effective_user.id

    async def send_error_response(self, update: Update, error_message: str):
        """에러 응답 전송"""
        await self.safe_reply_text(update, f"❌ {error_message}")

    async def send_success_response(self, update: Update, message: str):
        """성공 응답 전송"""
        await self.safe_reply_text(update, f"✅ {message}")

    async def send_info_response(self, update: Update, message: str):
        """정보 응답 전송"""
        await self.safe_reply_text(update, f"ℹ️ {message}")