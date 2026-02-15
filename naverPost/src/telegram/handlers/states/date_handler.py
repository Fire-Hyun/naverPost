"""
Date input handler for conversation flow
"""

from typing import Optional
from telegram import Update

from .base_state_handler import BaseStateHandler
from ...models.session import TelegramSession, ConversationState
from ...utils.validators import DateValidator


class DateInputHandler(BaseStateHandler):
    """방문 날짜 입력 처리 핸들러"""

    async def handle_input(
        self,
        update: Update,
        session: TelegramSession,
        text: str
    ) -> Optional[ConversationState]:
        """방문 날짜 입력 처리"""

        visit_date = DateValidator.parse_date_input(text)

        if not visit_date:
            await self.safe_reply_text(update, self.responses.invalid_date_format())
            return None  # 상태 변경 없음, 재입력 요구

        # 세션에 날짜 저장
        session.visit_date = visit_date

        # 사용자별 로깅
        await self.log_user_activity(update, 'date_input', visit_date=visit_date)

        # 카테고리 인라인 키보드 생성
        reply_markup = self.responses.create_category_keyboard(self.settings.SUPPORTED_CATEGORIES)

        await self.safe_reply_text(
            update,
            f"✅ **방문 날짜:** {visit_date}\n\n**카테고리를 선택해주세요:**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        # 다음 상태로 이동
        return ConversationState.WAITING_CATEGORY