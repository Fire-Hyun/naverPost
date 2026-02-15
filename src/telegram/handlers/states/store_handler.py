"""
Store name input handler for conversation flow
"""

from typing import Optional
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup

from .base_state_handler import BaseStateHandler
from ...models.session import TelegramSession, ConversationState, LocationInfo
from ...services.store_name_resolver import get_store_name_resolver, ResolutionStatus


class StoreNameHandler(BaseStateHandler):
    """상호명 입력 처리 핸들러"""

    async def handle_input(
        self,
        update: Update,
        session: TelegramSession,
        text: str
    ) -> Optional[ConversationState]:
        """상호명 입력 처리"""

        # 취소 명령 처리
        if text.lower() in ['/cancel', '취소', '중단']:
            await self.safe_reply_text(
                update,
                "상호명 입력을 취소했습니다. 아래 '시작하기' 버튼으로 다시 시작해주세요.",
                reply_markup=self.responses.create_start_keyboard()
            )
            return None

        # 위치 공유 관련 응답 처리
        if text in ["직접 입력하겠습니다", "수동 입력", "직접 입력"]:
            await self.safe_reply_text(
                update,
                "📝 상호명을 직접 입력해주세요.\n"
                "예: 스타벅스 강남역점"
            )
            return None

        # 사용자 입력 저장
        session.raw_store_name = text

        # 사용자별 로깅
        await self.log_user_activity(update, 'store_name_input', store_name=text)

        # 위치 정보 확인 (텔레그램 Location 메시지에서 추출)
        if update.message.location:
            session.location = LocationInfo(
                lat=update.message.location.latitude,
                lng=update.message.location.longitude,
                source="telegram_location"
            )

        # 상호명 보정 시도
        await self.safe_reply_text(update, "🔍 상호명을 확인하고 있습니다...")

        resolver = get_store_name_resolver()
        result = await resolver.resolve_store_name(session)

        if result.status == ResolutionStatus.SUCCESS:
            # 성공: 보정된 상호명 저장
            session.resolved_store_name = result.resolved_name

            # 상호명 보정 로깅
            await self.log_user_activity(
                update, 'store_name_resolved',
                raw_name=text,
                resolved_name=result.resolved_name
            )

            confirmation_msg = resolver.get_user_confirmation_message(result)
            await self.safe_reply_text(update, f"✅ {confirmation_msg}")
            await self.safe_reply_text(update, self.responses.store_name_confirmed_request_images())

            return ConversationState.WAITING_IMAGES

        elif result.status == ResolutionStatus.NEEDS_LOCATION:
            # 위치 정보 필요
            await self._request_location(update, session, result.error_message)
            return None

        elif result.status == ResolutionStatus.INVALID_FORMAT:
            # 형식 오류
            await self.safe_reply_text(update, f"❌ {result.error_message}")
            return None

        elif result.status == ResolutionStatus.NOT_FOUND:
            # 검색 결과 없음 - 재입력 요청
            await self.safe_reply_text(update, f"❌ {result.error_message}")
            await self.safe_reply_text(update, "정확한 상호명을 다시 입력해주세요.")
            return None

        else:  # API_ERROR
            # API 오류 - 재시도 요청
            await self.safe_reply_text(update, f"⚠️ {result.error_message}")
            await self.safe_reply_text(update, "잠시 후 다시 시도해주세요.")
            return None

    async def handle_location(
        self,
        update: Update,
        session: TelegramSession
    ) -> Optional[ConversationState]:
        """위치 메시지 처리"""
        from telegram import ReplyKeyboardRemove

        # 위치 정보 저장
        session.location = LocationInfo(
            lat=update.message.location.latitude,
            lng=update.message.location.longitude,
            source="telegram_location"
        )

        if session.raw_store_name:
            # 상호명 입력 후 위치가 온 경우 - 상호명 보정 재시도
            await self.safe_reply_text(
                update,
                "📍 위치 정보를 받았습니다. 상호명을 다시 확인해보겠습니다...",
                reply_markup=ReplyKeyboardRemove()
            )

            resolver = get_store_name_resolver()
            result = await resolver.resolve_store_name(session)

            if result.status == ResolutionStatus.SUCCESS:
                session.resolved_store_name = result.resolved_name

                confirmation_msg = resolver.get_user_confirmation_message(result)
                await self.safe_reply_text(update, f"✅ {confirmation_msg}")
                await self.safe_reply_text(update, self.responses.store_name_confirmed_request_images())

                return ConversationState.WAITING_IMAGES
            else:
                await self.safe_reply_text(update, f"❌ {result.error_message}")
                if result.status == ResolutionStatus.NOT_FOUND:
                    await self.safe_reply_text(update, "정확한 상호명을 다시 입력해주세요.")
                return None
        else:
            # 상호명 없이 위치만 온 경우
            await self.safe_reply_text(
                update,
                "📍 위치 정보를 받았습니다. 이제 상호명을 입력해주세요.",
                reply_markup=ReplyKeyboardRemove()
            )
            return None

    async def _request_location(self, update: Update, session: TelegramSession, message: str):
        """위치 정보 요청"""
        location_button = KeyboardButton("📍 현재 위치 공유", request_location=True)
        keyboard = [[location_button], ["직접 입력하겠습니다"]]
        reply_markup = ReplyKeyboardMarkup(
            keyboard,
            one_time_keyboard=True,
            resize_keyboard=True
        )

        await self.safe_reply_text(
            update,
            f"📍 {message}",
            reply_markup=reply_markup
        )