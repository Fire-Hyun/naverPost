"""
Review input handler for conversation flow
"""

from typing import Optional
from telegram import Update

from .base_state_handler import BaseStateHandler
from ...models.session import TelegramSession, ConversationState
from ...constants import MIN_REVIEW_LENGTH
from ...utils.formatters import ProgressSummaryBuilder


class ReviewInputHandler(BaseStateHandler):
    """감상평 입력 처리 핸들러"""

    async def handle_input(
        self,
        update: Update,
        session: TelegramSession,
        text: str
    ) -> Optional[ConversationState]:
        """감상평 입력 처리"""

        # 이미지 대기 중이고 이미지가 없으면 이미지 대기 메시지
        if session.state == ConversationState.WAITING_IMAGES and not session.images:
            await self.safe_reply_text(update, self.responses.waiting_for_images())
            return None

        # 감상평 길이 검증
        if len(text) < MIN_REVIEW_LENGTH:
            await self.safe_reply_text(
                update,
                self.responses.review_too_short(len(text), MIN_REVIEW_LENGTH)
            )
            return None

        # 세션에 감상평 저장
        session.personal_review = text

        # 사용자별 로깅
        await self.log_user_activity(update, 'review_submitted', length=len(text))

        await self.safe_reply_text(update, self.responses.review_confirmed())

        # 다음 상태로 이동
        return ConversationState.WAITING_ADDITIONAL

    async def handle_additional_input(
        self,
        update: Update,
        session: TelegramSession,
        text: str
    ) -> Optional[ConversationState]:
        """추가 스크립트 입력 처리"""
        from ...constants import VALIDATION_MESSAGES

        # 사용자별 로깅용 참조
        user_logger_needed = True

        if text.lower() in VALIDATION_MESSAGES['skip_keywords']:
            session.additional_script = ""
            if user_logger_needed:
                await self.log_user_activity(update, 'additional_content', has_content=False)
        else:
            session.additional_script = text
            if user_logger_needed:
                await self.log_user_activity(update, 'additional_content', has_content=True)

        # 요약 메시지
        summary = ProgressSummaryBuilder.build_summary(session)
        await self.safe_reply_text(
            update,
            self.responses.ready_to_generate(summary),
            reply_markup=self.responses.create_generation_keyboard(),
            parse_mode='Markdown'
        )

        return ConversationState.READY_TO_GENERATE