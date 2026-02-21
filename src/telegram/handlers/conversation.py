"""
Telegram bot conversation handling
"""

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, CallbackQuery
from telegram.ext import ContextTypes

from src.config.settings import Settings
from ..models.session import TelegramSession, ConversationState, LocationInfo, update_session
from ..models.responses import ResponseTemplates
from ..utils.validators import parse_visit_date
from ..utils.formatters import ProgressSummaryBuilder
from ..utils import get_user_logger
from ..utils.safe_message_mixin import SafeMessageMixin
from .states import (
    DateInputHandler,
    CategorySelectionHandler,
    StoreNameHandler,
    ReviewInputHandler
)
from ..constants import MIN_REVIEW_LENGTH
from ..constants import ACTION_START, ACTION_DONE, ACTION_CHECK_STATUS, ACTION_CANCEL_CURRENT, ACTION_HELP
from ..services.store_name_resolver import get_store_name_resolver, ResolutionStatus


class ConversationHandler(SafeMessageMixin):
    """텔레그램 봇 대화 핸들러"""

    def __init__(self, bot):
        super().__init__()  # Initialize SafeMessageMixin
        self.bot = bot
        self.settings = Settings
        self.responses = ResponseTemplates()

        # Initialize state-specific handlers
        self.date_handler = DateInputHandler(bot, Settings)
        self.category_handler = CategorySelectionHandler(bot, Settings)
        self.store_handler = StoreNameHandler(bot, Settings)
        self.review_handler = ReviewInputHandler(bot, Settings)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, session: TelegramSession):
        """상태에 따른 텍스트 메시지 처리"""
        import logging
        logger = logging.getLogger(__name__)

        text = update.message.text.strip()
        session.update_activity()

        user_id = update.effective_user.id
        user_logger = get_user_logger(user_id)

        # 상태별 처리 - 새로운 state handlers 사용
        next_state = None

        try:
            if session.state == ConversationState.WAITING_DATE:
                logger.info(f"[user={user_id}] date input: raw={text!r}, state={session.state.value}")
                next_state = await self.date_handler.handle_input(update, session, text)
            elif session.state == ConversationState.WAITING_CATEGORY:
                next_state = await self.category_handler.handle_input(update, session, text)
            elif session.state == ConversationState.WAITING_STORE_NAME:
                next_state = await self.store_handler.handle_input(update, session, text)
            elif session.state == ConversationState.WAITING_IMAGES:
                next_state = await self._handle_waiting_images(update, session, text)
            elif session.state == ConversationState.WAITING_REVIEW:
                next_state = await self.review_handler.handle_input(update, session, text)
            elif session.state == ConversationState.WAITING_ADDITIONAL:
                next_state = await self.review_handler.handle_additional_input(update, session, text)
            else:
                await self.safe_reply_text(update, self.responses.unknown_state())

            # 상태 업데이트
            if next_state is not None:
                session.state = next_state
            update_session(session)

        except Exception as e:
            logger.error(
                f"[user={user_id}] handle_message error: state={session.state.value}, "
                f"text={text!r}, error={e}",
                exc_info=True,
            )
            user_logger.error(
                f"[HANDLE_MESSAGE] {type(e).__name__}: {e} (state={session.state.value}, input={text!r})"
            )
            raise  # error_handler에서 사용자 메시지 전송

    async def _handle_date_input(self, update: Update, session: TelegramSession, text: str):
        """방문 날짜 입력 처리"""
        visit_date, error_msg = parse_visit_date(text)

        if not visit_date:
            await self.safe_reply_text(update, self.responses.invalid_date_format(error_msg))
            return

        session.visit_date = visit_date
        session.state = ConversationState.WAITING_CATEGORY

        # 사용자별 로깅
        user_logger = get_user_logger(update.effective_user.id)
        user_logger.log_date_input(visit_date)

        # 카테고리 인라인 키보드 생성
        reply_markup = self.responses.create_category_keyboard(self.settings.SUPPORTED_CATEGORIES)

        await self.safe_reply_text(
            update,
            f"✅ **방문 날짜:** {visit_date}\n\n**카테고리를 선택해주세요:**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    def _create_category_keyboard(self):
        """카테고리 선택 키보드 생성"""
        categories = self.settings.SUPPORTED_CATEGORIES
        return [[KeyboardButton(cat)] for cat in categories]

    async def _handle_category_input(self, update: Update, session: TelegramSession, text: str):
        """카테고리 선택 처리"""
        if text not in self.settings.SUPPORTED_CATEGORIES:
            await update.message.reply_text(
                self.responses.invalid_category(self.settings.SUPPORTED_CATEGORIES)
            )
            return

        session.category = text
        session.state = ConversationState.WAITING_STORE_NAME

        # 사용자별 로깅
        user_logger = get_user_logger(update.effective_user.id)
        user_logger.log_category_selected(text)

        await update.message.reply_text(
            self.responses.category_confirmed_request_store_name(text),
            reply_markup=ReplyKeyboardRemove()
        )

    async def _handle_store_name_input(self, update: Update, session: TelegramSession, text: str):
        """상호명 입력 처리"""
        # 취소 명령 처리
        if text.lower() in ['/cancel', '취소', '중단']:
            await update.message.reply_text(
                "상호명 입력을 취소했습니다. 아래 '시작하기' 버튼으로 다시 시작해주세요.",
                reply_markup=self.responses.create_start_keyboard()
            )
            return

        # 위치 공유 관련 응답 처리
        if text in ["직접 입력하겠습니다", "수동 입력", "직접 입력"]:
            await update.message.reply_text(
                "📝 상호명을 직접 입력해주세요.\n"
                "예: 스타벅스 강남역점"
            )
            return

        # 사용자 입력 저장
        session.raw_store_name = text

        # 사용자별 로깅
        user_logger = get_user_logger(update.effective_user.id)
        user_logger.log_store_name_input(text)

        # 위치 정보 확인 (텔레그램 Location 메시지에서 추출)
        if update.message.location:
            session.location = LocationInfo(
                lat=update.message.location.latitude,
                lng=update.message.location.longitude,
                source="telegram_location"
            )

        # 상호명 보정 시도
        await update.message.reply_text("🔍 상호명을 확인하고 있습니다...")

        resolver = get_store_name_resolver()
        result = await resolver.resolve_store_name(session)

        if result.status == ResolutionStatus.SUCCESS:
            # 성공: 보정된 상호명 저장
            session.resolved_store_name = result.resolved_name
            session.state = ConversationState.WAITING_IMAGES

            # 상호명 보정 로깅
            user_logger.log_store_name_resolved(raw_name=text, resolved_name=result.resolved_name)

            confirmation_msg = resolver.get_user_confirmation_message(result)
            await update.message.reply_text(f"✅ {confirmation_msg}")
            await update.message.reply_text(self.responses.store_name_confirmed_request_images())

        elif result.status == ResolutionStatus.NEEDS_LOCATION:
            # 위치 정보 필요
            await self._request_location(update, session, result.error_message)

        elif result.status == ResolutionStatus.INVALID_FORMAT:
            # 형식 오류
            await update.message.reply_text(f"❌ {result.error_message}")

        elif result.status == ResolutionStatus.NOT_FOUND:
            # 검색 결과 없음 - 재입력 요청
            await update.message.reply_text(f"❌ {result.error_message}")
            await update.message.reply_text("정확한 상호명을 다시 입력해주세요.")

        else:  # API_ERROR
            # API 오류 - 재시도 요청
            await update.message.reply_text(f"⚠️ {result.error_message}")
            await update.message.reply_text("잠시 후 다시 시도해주세요.")

    async def _request_location(self, update: Update, session: TelegramSession, message: str):
        """위치 정보 요청"""
        # 위치 공유 키보드 생성
        from telegram import KeyboardButton, ReplyKeyboardMarkup

        location_button = KeyboardButton("📍 현재 위치 공유", request_location=True)
        keyboard = [[location_button], ["직접 입력하겠습니다"]]
        reply_markup = ReplyKeyboardMarkup(
            keyboard,
            one_time_keyboard=True,
            resize_keyboard=True
        )

        await update.message.reply_text(
            f"📍 {message}",
            reply_markup=reply_markup
        )

    async def _handle_waiting_images(self, update: Update, session: TelegramSession, text: str):
        """이미지 대기 중 텍스트 입력 처리"""
        if not session.images:
            await update.message.reply_text(self.responses.waiting_for_images())
            return

        # 이미지가 있으면 감상평 입력으로 처리
        await self._handle_review_input(update, session, text)

    async def _handle_review_input(self, update: Update, session: TelegramSession, text: str):
        """감상평 입력 처리"""
        if len(text) < MIN_REVIEW_LENGTH:
            await update.message.reply_text(
                self.responses.review_too_short(len(text), MIN_REVIEW_LENGTH)
            )
            return

        session.personal_review = text
        session.state = ConversationState.WAITING_ADDITIONAL

        # 사용자별 로깅
        user_logger = get_user_logger(update.effective_user.id)
        user_logger.log_review_submitted(length=len(text))

        await update.message.reply_text(self.responses.review_confirmed())

    async def _handle_additional_input(self, update: Update, session: TelegramSession, text: str):
        """추가 스크립트 입력 처리"""
        from ..constants import VALIDATION_MESSAGES

        # 사용자별 로깅
        user_logger = get_user_logger(update.effective_user.id)

        if text.lower() in VALIDATION_MESSAGES['skip_keywords']:
            session.additional_script = ""
            user_logger.log_additional_content(False)
        else:
            session.additional_script = text
            user_logger.log_additional_content(True)

        session.state = ConversationState.READY_TO_GENERATE

        # 요약 메시지
        summary = ProgressSummaryBuilder.build_summary(session)
        await update.message.reply_text(
            self.responses.ready_to_generate(summary),
            reply_markup=self.responses.create_generation_keyboard(),
            parse_mode='Markdown'
        )

    async def handle_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE, session: TelegramSession):
        """위치 메시지 처리"""
        from telegram import ReplyKeyboardRemove

        # 위치 정보 저장
        session.location = LocationInfo(
            lat=update.message.location.latitude,
            lng=update.message.location.longitude,
            source="telegram_location"
        )

        if session.state == ConversationState.WAITING_STORE_NAME and session.raw_store_name:
            # 상호명 입력 대기 중이고 이미 상호명이 입력된 경우 - 상호명 보정 재시도
            await update.message.reply_text(
                "📍 위치 정보를 받았습니다. 상호명을 다시 확인해보겠습니다...",
                reply_markup=ReplyKeyboardRemove()
            )

            resolver = get_store_name_resolver()
            result = await resolver.resolve_store_name(session)

            if result.status == ResolutionStatus.SUCCESS:
                session.resolved_store_name = result.resolved_name
                session.state = ConversationState.WAITING_IMAGES

                confirmation_msg = resolver.get_user_confirmation_message(result)
                await update.message.reply_text(f"✅ {confirmation_msg}")
                await update.message.reply_text(self.responses.store_name_confirmed_request_images())

            else:
                await update.message.reply_text(f"❌ {result.error_message}")
                if result.status == ResolutionStatus.NOT_FOUND:
                    await update.message.reply_text("정확한 상호명을 다시 입력해주세요.")

        elif session.state == ConversationState.WAITING_STORE_NAME:
            # 상호명 입력 대기 중 - 위치만 받은 경우
            await update.message.reply_text(
                "📍 위치 정보를 받았습니다. 이제 상호명을 입력해주세요.",
                reply_markup=ReplyKeyboardRemove()
            )

        else:
            # 다른 상태에서 위치가 온 경우
            await update.message.reply_text(
                "📍 위치 정보를 받았지만 지금은 위치가 필요한 단계가 아닙니다.",
                reply_markup=ReplyKeyboardRemove()
            )
        update_session(session)

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE, session: TelegramSession):
        """버튼 클릭 (CallbackQuery) 처리"""
        query = update.callback_query
        await query.answer()  # 버튼 클릭 응답

        callback_data = query.data

        # 콜백 데이터에 따른 처리
        if callback_data in (ACTION_START, "start_new_blog"):
            await self._handle_start_new_blog(query, session)

        elif callback_data in (ACTION_DONE, "generate_blog"):
            await self._handle_generate_blog_button(query, session)

        elif callback_data == ACTION_CHECK_STATUS:
            await self._handle_check_status(query, session)

        elif callback_data == ACTION_CANCEL_CURRENT:
            await self._handle_cancel_current(query, session)

        elif callback_data == ACTION_HELP:
            await self._handle_show_help(query)

        elif callback_data.startswith("category_"):
            category = callback_data.replace("category_", "")
            await self._handle_category_button(query, session, category)

        elif callback_data == "date_today":
            await self._handle_date_today(query, session)

        elif callback_data == "date_yesterday":
            await self._handle_date_yesterday(query, session)

        elif callback_data == "show_review_tips":
            await self._handle_show_review_tips(query)

        elif callback_data.startswith("confirm_"):
            action = callback_data.replace("confirm_", "")
            await self._handle_confirm_action(query, session, action)

        elif callback_data.startswith("cancel_"):
            action = callback_data.replace("cancel_", "")
            await self._handle_cancel_action(query, session, action)

        else:
            await query.edit_message_text("❓ 알 수 없는 버튼입니다.")

    async def _handle_start_new_blog(self, query: CallbackQuery, session: TelegramSession):
        """새 블로그 작성 시작"""
        from ..models.session import ConversationState, delete_session, create_session

        # 기존 세션 정리
        delete_session(session.user_id)

        # 새 세션 생성
        new_session = create_session(session.user_id)

        await query.edit_message_text(
            "📅 **방문 날짜를 입력해주세요**\n\n"
            "형식: YYYYMMDD 또는 YYYY-MM-DD (예: 20260212)\n"
            "'오늘', '어제'도 입력 가능합니다.\n"
            "또는 아래 버튼을 사용하세요.",
            reply_markup=self.responses.create_date_input_keyboard(),
            parse_mode='Markdown'
        )

    async def _handle_generate_blog_button(self, query: CallbackQuery, session: TelegramSession):
        """블로그 생성 버튼 처리"""
        # 세션 검증
        missing_fields = session.get_missing_fields()
        if missing_fields:
            await query.edit_message_text(
                f"❌ **필수 정보가 누락되었습니다:**\n\n" +
                "\n".join(f"• {field}" for field in missing_fields) +
                "\n\n필요한 정보를 모두 입력한 후 다시 시도해주세요.",
                reply_markup=self.responses.create_main_menu_keyboard(),
                parse_mode='Markdown'
            )
            return

        # 사용자별 로깅
        user_logger = get_user_logger(session.user_id)
        user_logger.log_generation_start()

        # 생성 시작
        await query.edit_message_text(
            "🚀 **블로그 자동화를 시작합니다...**",
            reply_markup=self.responses.create_cancel_keyboard(),
            parse_mode='Markdown'
        )

        # bot의 blog_service 직접 사용 (중복 생성 방지)
        await self.bot.blog_service.generate_blog_from_session(query.message, session)

    async def _handle_check_status(self, query: CallbackQuery, session: TelegramSession):
        """상태 확인"""
        summary = session.get_progress_summary()
        missing_fields = session.get_missing_fields()

        status_text = f"📊 **현재 진행 상태:**\n\n{summary}"

        if missing_fields:
            status_text += f"\n\n❗ **누락된 정보:**\n" + "\n".join(f"• {field}" for field in missing_fields)
        else:
            status_text += "\n\n✅ 모든 정보가 입력되었습니다!"

        keyboard = self.responses.create_generation_keyboard() if not missing_fields else self.responses.create_main_menu_keyboard()

        await query.edit_message_text(
            status_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    async def _handle_cancel_current(self, query: CallbackQuery, session: TelegramSession):
        """현재 작업 취소"""
        from ..models.session import delete_session

        delete_session(session.user_id)

        await query.edit_message_text(
            "❌ **현재 작업이 취소되었습니다.**\n\n새로 시작하려면 아래 버튼을 누르세요.",
            reply_markup=self.responses.create_start_keyboard(),
            parse_mode='Markdown'
        )

    async def _handle_show_help(self, query: CallbackQuery):
        """도움말 표시"""
        help_text = self.responses.help_message()

        await query.edit_message_text(
            help_text,
            reply_markup=self.responses.create_start_keyboard(),
            parse_mode='Markdown'
        )

    async def _handle_category_button(self, query: CallbackQuery, session: TelegramSession, category: str):
        """카테고리 버튼 처리"""
        session.category = category
        session.state = ConversationState.WAITING_STORE_NAME

        await query.edit_message_text(
            f"✅ **카테고리:** {category}\n\n" +
            self.responses.category_confirmed_request_store_name(category),
            parse_mode='Markdown'
        )

    async def _handle_date_today(self, query: CallbackQuery, session: TelegramSession):
        """오늘 날짜 사용"""
        today, _ = parse_visit_date("오늘")
        session.visit_date = today
        session.state = ConversationState.WAITING_CATEGORY

        # 사용자별 로깅
        user_logger = get_user_logger(query.from_user.id)
        user_logger.info(f"방문 날짜 입력: {today} (오늘 버튼)")

        await query.edit_message_text(
            f"✅ 방문 날짜: {today}\n\n카테고리를 선택해주세요:",
            reply_markup=self.responses.create_category_keyboard(self.settings.SUPPORTED_CATEGORIES),
        )

    async def _handle_date_yesterday(self, query: CallbackQuery, session: TelegramSession):
        """어제 날짜 사용"""
        yesterday, _ = parse_visit_date("어제")
        session.visit_date = yesterday
        session.state = ConversationState.WAITING_CATEGORY

        # 사용자별 로깅
        user_logger = get_user_logger(query.from_user.id)
        user_logger.info(f"방문 날짜 입력: {yesterday} (어제 버튼)")

        await query.edit_message_text(
            f"✅ 방문 날짜: {yesterday}\n\n카테고리를 선택해주세요:",
            reply_markup=self.responses.create_category_keyboard(self.settings.SUPPORTED_CATEGORIES),
        )

    async def _handle_show_review_tips(self, query: CallbackQuery):
        """감상평 작성 팁 표시"""
        tips_text = (
            "💡 **감상평 작성 팁:**\n\n"
            "• **개인 경험 중심으로 작성**하세요\n"
            "• **구체적인 느낌과 생각**을 포함하세요\n"
            "• **최소 50자 이상** 작성해주세요\n"
            "• **방문 당시의 분위기**를 묘사해보세요\n"
            "• **추천하고 싶은 이유**를 적어주세요\n\n"
            "예시: '오늘 친구와 함께 방문했는데 분위기가 정말 좋았어요...'"
        )

        await query.answer(tips_text, show_alert=True)

    async def _handle_confirm_action(self, query: CallbackQuery, session: TelegramSession, action: str):
        """확인 액션 처리"""
        await query.edit_message_text(
            f"✅ **{action} 확인되었습니다.**",
            reply_markup=self.responses.create_main_menu_keyboard(),
            parse_mode='Markdown'
        )

    async def _handle_cancel_action(self, query: CallbackQuery, session: TelegramSession, action: str):
        """취소 액션 처리"""
        await query.edit_message_text(
            f"❌ **{action}이(가) 취소되었습니다.**",
            reply_markup=self.responses.create_main_menu_keyboard(),
            parse_mode='Markdown'
        )
