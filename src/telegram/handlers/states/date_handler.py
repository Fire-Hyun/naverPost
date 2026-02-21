"""
Date input handler for conversation flow
"""

import logging
from typing import Optional
from telegram import Update

from .base_state_handler import BaseStateHandler
from ...models.session import TelegramSession, ConversationState
from ...utils.validators import parse_visit_date
from ...utils import get_user_logger

logger = logging.getLogger(__name__)


class DateInputHandler(BaseStateHandler):
    """방문 날짜 입력 처리 핸들러"""

    async def handle_input(
        self,
        update: Update,
        session: TelegramSession,
        text: str
    ) -> Optional[ConversationState]:
        """방문 날짜 입력 처리"""
        user_id = update.effective_user.id
        user_logger = get_user_logger(user_id)

        logger.info(f"[user={user_id}] visit_date_input: raw={text!r}")

        visit_date, error_msg = parse_visit_date(text)

        if not visit_date:
            logger.info(f"[user={user_id}] visit_date_parse_fail: raw={text!r}, error={error_msg}")
            user_logger.error(f"날짜 파싱 실패: input={text!r}, error={error_msg}")
            await self.safe_reply_text(
                update,
                self.responses.invalid_date_format(error_msg),
            )
            return None  # 상태 변경 없음, 재입력 요구

        logger.info(f"[user={user_id}] visit_date_parsed: {visit_date}")

        # 세션에 날짜 저장
        session.visit_date = visit_date

        # 사용자별 로깅
        user_logger.info(f"방문 날짜 입력: {visit_date}")

        # 카테고리 인라인 키보드 생성
        reply_markup = self.responses.create_category_keyboard(self.settings.SUPPORTED_CATEGORIES)

        await self.safe_reply_text(
            update,
            f"✅ 방문 날짜: {visit_date}\n\n카테고리를 선택해주세요:",
            reply_markup=reply_markup,
        )

        # 다음 상태로 이동
        return ConversationState.WAITING_CATEGORY