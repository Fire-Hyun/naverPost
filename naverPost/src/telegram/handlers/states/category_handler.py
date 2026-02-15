"""
Category selection handler for conversation flow
"""

from typing import Optional
from telegram import Update, ReplyKeyboardRemove

from .base_state_handler import BaseStateHandler
from ...models.session import TelegramSession, ConversationState


class CategorySelectionHandler(BaseStateHandler):
    """카테고리 선택 처리 핸들러"""

    async def handle_input(
        self,
        update: Update,
        session: TelegramSession,
        text: str
    ) -> Optional[ConversationState]:
        """카테고리 선택 처리"""

        if text not in self.settings.SUPPORTED_CATEGORIES:
            await self.safe_reply_text(
                update,
                self.responses.invalid_category(self.settings.SUPPORTED_CATEGORIES)
            )
            return None  # 상태 변경 없음, 재입력 요구

        # 세션에 카테고리 저장
        session.category = text

        # 사용자별 로깅
        await self.log_user_activity(update, 'category_selected', category=text)

        await self.safe_reply_text(
            update,
            self.responses.category_confirmed_request_store_name(text),
            reply_markup=ReplyKeyboardRemove()
        )

        # 다음 상태로 이동
        return ConversationState.WAITING_STORE_NAME