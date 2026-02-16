"""
Main Telegram bot application for naverPost system
"""

import asyncio
import logging
from typing import Optional
from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

from src.config.settings import Settings

from .models.session import (
    TelegramSession, ConversationState, active_sessions,
    get_session, create_session, delete_session
)
from .models.responses import ResponseTemplates
from .handlers.conversation import ConversationHandler as TelegramConversationHandler
from .handlers.image_handler import ImageHandler
from .service_layer import BlogGenerationService, SessionManagementService, MaintenanceService
from .utils.session_validator import SessionValidator
from .utils.helpers import AccessControl
from .utils import get_user_logger
from .utils.safe_message_mixin import SafeMessageMixin
from .constants import (
    DEFAULT_SESSION_TIMEOUT, CLEANUP_INTERVAL,
    ACTION_START, ACTION_HELP, ACTION_CANCEL_CURRENT
)


class NaverPostTelegramBot(SafeMessageMixin):
    """네이버 블로그 자동화 텔레그램 봇"""

    def __init__(self):
        super().__init__()  # Initialize SafeMessageMixin
        self.settings = Settings
        self.responses = ResponseTemplates()
        self._cleanup_task: Optional[asyncio.Task] = None

        # 핵심 컴포넌트 초기화
        self.image_handler = ImageHandler(self)
        self.conversation_handler = TelegramConversationHandler(self)

        # 서비스 레이어 초기화
        self.blog_service = BlogGenerationService(self.image_handler)
        self.session_service = SessionManagementService(self.image_handler)
        self.maintenance_service = MaintenanceService(
            self.image_handler,
            self.settings.TELEGRAM_SESSION_TIMEOUT
        )

        # 설정 검증
        telegram_validation = self.settings.validate_telegram_keys()
        if not telegram_validation["TELEGRAM_BOT_TOKEN"]:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

        # 로깅 설정
        self._setup_logging()

    def _setup_logging(self):
        """로깅 설정"""
        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            level=getattr(logging, self.settings.LOG_LEVEL.upper())
        )
        self.logger = logging.getLogger(__name__)

    def build_application(self) -> Application:
        """텔레그램 애플리케이션 빌드"""
        application = (
            ApplicationBuilder()
            .token(self.settings.TELEGRAM_BOT_TOKEN)
            .post_init(self._on_post_init)
            .post_shutdown(self._on_post_shutdown)
            .build()
        )

        # 명령어 핸들러
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("done", self.done_command))
        application.add_handler(CommandHandler("cancel", self.cancel_command))
        application.add_handler(CommandHandler("status", self.status_command))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("log", self.log_command))

        # 버튼 클릭 핸들러
        application.add_handler(CallbackQueryHandler(self.handle_callback_query))

        # 메시지 핸들러
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        application.add_handler(MessageHandler(filters.PHOTO, self.handle_image))
        application.add_handler(MessageHandler(filters.LOCATION, self.handle_location))

        # 에러 핸들러
        application.add_error_handler(self.error_handler)

        return application

    async def _on_post_init(self, application: Application):
        """애플리케이션 초기화 이후 백그라운드 작업 시작"""
        self._cleanup_task = asyncio.create_task(self.cleanup_task())
        self.logger.info("Cleanup background task started")

    async def _on_post_shutdown(self, application: Application):
        """애플리케이션 종료 시 백그라운드 작업 정리"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        self.logger.info("Cleanup background task stopped")

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/start 명령어 - 새 세션 초기화"""
        user_id = update.effective_user.id

        # 보안 확인
        if not AccessControl.is_user_allowed(user_id, self.settings):
            await update.message.reply_text(self.responses.access_denied())
            return

        # 기존 세션 정리
        if user_id in active_sessions:
            self.session_service.cleanup_user_session(user_id)

        # 새 세션 생성
        session = create_session(user_id)
        self.logger.info(f"New session created for user {user_id}")

        # 사용자별 로깅
        user_logger = get_user_logger(user_id)
        user_logger.log_session_start()

        await update.message.reply_text(
            self.responses.welcome_message(),
            reply_markup=self.responses.create_start_keyboard(),
            parse_mode='Markdown'
        )

    async def done_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/done 명령어 - 블로그 생성 실행"""
        session = await SessionValidator.validate_and_get_session(update, context)
        if not session:
            return

        # 세션 검증 및 블로그 생성
        if await self.session_service.validate_session_for_generation(update, session):
            await self.blog_service.generate_blog_from_session(update, session)

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/cancel 명령어 - 현재 세션 취소"""
        user_id = update.effective_user.id
        session = get_session(user_id)

        if session:
            # 사용자별 로깅
            user_logger = get_user_logger(user_id)
            user_logger.log_session_cancel()

            self.image_handler.cleanup_temp_files(user_id)
            delete_session(user_id)
            await update.message.reply_text(self.responses.session_canceled())
        else:
            await update.message.reply_text(self.responses.no_active_session())

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/status 명령어 - 현재 진행 상태 확인"""
        user_id = update.effective_user.id
        session = get_session(user_id)

        if not session:
            await update.message.reply_text(self.responses.no_active_session())
            return

        summary = session.get_progress_summary()
        missing_fields = session.get_missing_fields()

        await update.message.reply_text(
            self.responses.status_message(summary, missing_fields)
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/help 명령어 - 도움말"""
        await update.message.reply_text(
            self.responses.help_message(),
            reply_markup=self.responses.create_start_keyboard(),
            parse_mode='Markdown'
        )

    async def log_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/log 명령어 - 블로그 포스팅 로그 확인"""
        user_id = update.effective_user.id

        # 보안 확인
        if not AccessControl.is_user_allowed(user_id, self.settings):
            await update.message.reply_text(self.responses.access_denied())
            return

        try:
            # 사용자별 로거에서 로그 가져오기
            user_logger = get_user_logger(user_id)
            recent_lines = user_logger.get_recent_logs(lines=50)

            if not recent_lines:
                await update.message.reply_text(
                    "📋 아직 로그가 없습니다.\n"
                    "블로그 작성을 시작하면 로그가 기록됩니다."
                )
                return

            log_content = ''.join(recent_lines)

            # 텔레그램 메시지 길이 제한 고려 (4096자)
            if len(log_content) > 4000:
                log_content = "... (생략) ...\n" + log_content[-3800:]

            await update.message.reply_text(
                f"📋 **최근 블로그 포스팅 로그** (최근 50줄)\n\n"
                f"```\n{log_content}```",
                parse_mode='Markdown'
            )

        except Exception as e:
            self.logger.error(f"Error reading log file: {e}")
            await update.message.reply_text(
                "❌ 로그를 읽는 중 오류가 발생했습니다.\n"
                f"오류: {str(e)}"
            )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """텍스트 메시지를 대화 핸들러로 라우팅"""
        session = await SessionValidator.validate_and_get_session(update, context)
        if not session:
            return

        await self.conversation_handler.handle_message(update, context, session)

    async def handle_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """이미지 메시지를 이미지 핸들러로 라우팅"""
        session = await SessionValidator.validate_and_get_session(update, context)
        if not session:
            return

        await self.image_handler.handle_image(update, context, session)

    async def handle_location(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """위치 메시지를 대화 핸들러로 라우팅"""
        session = await SessionValidator.validate_and_get_session(update, context)
        if not session:
            return

        await self.conversation_handler.handle_location(update, context, session)

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """버튼 클릭 (CallbackQuery) 메시지를 대화 핸들러로 라우팅"""
        user_id = update.effective_user.id

        # 보안 확인
        if not AccessControl.is_user_allowed(user_id, self.settings):
            await update.callback_query.answer("접근 권한이 없습니다.", show_alert=True)
            return

        # 세션 검증 - CallbackQuery용
        session = get_session(user_id)

        # 특별한 콜백들은 세션이 없어도 허용 (시작/도움말/취소)
        allowed_without_session = [ACTION_START, ACTION_HELP, ACTION_CANCEL_CURRENT, 'start_new_blog']

        if not session and update.callback_query.data not in allowed_without_session:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                self.responses.no_active_session(),
                reply_markup=self.responses.create_start_keyboard()
            )
            return

        # 세션이 있는 경우 만료 확인
        if session and session.is_expired(DEFAULT_SESSION_TIMEOUT):
            delete_session(user_id)
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                self.responses.session_expired(),
                reply_markup=self.responses.create_start_keyboard()
            )
            return

        # 새 세션이 필요한 경우 생성 (start_new_blog)
        if not session and update.callback_query.data in allowed_without_session:
            session = create_session(user_id)

        await self.conversation_handler.handle_callback_query(update, context, session)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """에러 핸들러"""
        self.logger.error(f"Exception while handling update: {context.error}")

        # 사용자에게 에러 메시지 전송 (업데이트가 있는 경우만)
        if update and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "죄송합니다. 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
                )
            except Exception:
                pass  # 에러 메시지 전송도 실패한 경우 무시

    async def cleanup_task(self):
        """주기적 정리 작업"""
        while True:
            try:
                await self.maintenance_service.run_periodic_cleanup()
                # 주기적 실행
                await asyncio.sleep(CLEANUP_INTERVAL)

            except Exception as e:
                self.logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(CLEANUP_INTERVAL)  # 에러가 발생해도 계속 실행

    def run(self):
        """봇 실행"""
        application = self.build_application()

        self.logger.info(f"Starting Telegram bot with token: {self.settings.TELEGRAM_BOT_TOKEN[:10]}...")

        # 봇 실행
        application.run_polling(
            drop_pending_updates=True,
            timeout=30,
            read_timeout=30,
            write_timeout=30,
            connect_timeout=30,
            pool_timeout=30,
            close_loop=False,
            stop_signals=None,
        )
