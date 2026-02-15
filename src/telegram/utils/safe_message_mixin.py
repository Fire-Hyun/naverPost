"""
Safe message mixin for universal message safety application
"""

import logging
from typing import Optional, Any, Dict
from telegram import Update, CallbackQuery

from .message_formatter import TelegramMessageFormatter, safe_reply_text_async

logger = logging.getLogger(__name__)


class SafeMessageMixin:
    """
    안전한 메시지 전송을 위한 믹스인 클래스
    모든 Telegram 메시지 전송을 안전하게 처리
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logging.getLogger(self.__class__.__name__)

        # Feature flag for safe messaging (can be overridden by settings)
        self.use_safe_messaging = self._get_safe_messaging_setting()

    def _get_safe_messaging_setting(self) -> bool:
        """Safe messaging 설정 가져오기"""
        try:
            from src.config.settings import Settings
            return getattr(Settings, 'USE_SAFE_MESSAGING', True)
        except Exception:
            # 기본값은 True (안전 모드)
            return True

    async def safe_reply_text(
        self,
        update: Update,
        text: str,
        parse_mode: str = 'Markdown',
        **kwargs
    ) -> Any:
        """
        안전한 reply_text 래퍼

        Args:
            update: Telegram update object
            text: 전송할 메시지 텍스트
            parse_mode: 파싱 모드
            **kwargs: 추가 인자들

        Returns:
            메시지 전송 결과
        """
        if not self.use_safe_messaging:
            # 안전 모드가 비활성화된 경우 직접 전송
            return await update.message.reply_text(text, parse_mode=parse_mode, **kwargs)

        try:
            # 안전한 메시지 포매팅 및 전송
            return await safe_reply_text_async(
                update.message,
                text,
                parse_mode=parse_mode,
                **kwargs
            )
        except Exception as e:
            self.logger.error(f"Safe message sending failed: {e}")
            # 실패 시 fallback - plain text로 전송 시도
            try:
                fallback_text = TelegramMessageFormatter.strip_markdown(text)
                return await update.message.reply_text(fallback_text, parse_mode=None, **kwargs)
            except Exception as fallback_error:
                self.logger.error(f"Fallback message sending also failed: {fallback_error}")
                raise

    async def safe_edit_message_text(
        self,
        query: CallbackQuery,
        text: str,
        parse_mode: str = 'Markdown',
        **kwargs
    ) -> Any:
        """
        안전한 edit_message_text 래퍼

        Args:
            query: Callback query object
            text: 편집할 메시지 텍스트
            parse_mode: 파싱 모드
            **kwargs: 추가 인자들

        Returns:
            메시지 편집 결과
        """
        if not self.use_safe_messaging:
            # 안전 모드가 비활성화된 경우 직접 편집
            return await query.edit_message_text(text, parse_mode=parse_mode, **kwargs)

        try:
            # 안전한 메시지 포매팅
            safe_text, safe_parse_mode = TelegramMessageFormatter.safe_format_message(text, parse_mode)
            safe_text = TelegramMessageFormatter.truncate_message(safe_text)

            return await query.edit_message_text(safe_text, parse_mode=safe_parse_mode, **kwargs)
        except Exception as e:
            self.logger.error(f"Safe message editing failed: {e}")
            # 실패 시 fallback - plain text로 편집 시도
            try:
                fallback_text = TelegramMessageFormatter.strip_markdown(text)
                return await query.edit_message_text(fallback_text, parse_mode=None, **kwargs)
            except Exception as fallback_error:
                self.logger.error(f"Fallback message editing also failed: {fallback_error}")
                raise

    async def safe_reply_to_effective_message(
        self,
        update: Update,
        text: str,
        parse_mode: str = 'Markdown',
        **kwargs
    ) -> Any:
        """
        안전한 effective_message.reply_text 래퍼

        Args:
            update: Telegram update object
            text: 전송할 메시지 텍스트
            parse_mode: 파싱 모드
            **kwargs: 추가 인자들

        Returns:
            메시지 전송 결과
        """
        if not self.use_safe_messaging:
            # 안전 모드가 비활성화된 경우 직접 전송
            return await update.effective_message.reply_text(text, parse_mode=parse_mode, **kwargs)

        try:
            # 안전한 메시지 포매팅 및 전송
            return await safe_reply_text_async(
                update.effective_message,
                text,
                parse_mode=parse_mode,
                **kwargs
            )
        except Exception as e:
            self.logger.error(f"Safe effective message sending failed: {e}")
            # 실패 시 fallback - plain text로 전송 시도
            try:
                fallback_text = TelegramMessageFormatter.strip_markdown(text)
                return await update.effective_message.reply_text(fallback_text, parse_mode=None, **kwargs)
            except Exception as fallback_error:
                self.logger.error(f"Fallback effective message sending also failed: {fallback_error}")
                raise

    def get_safe_messaging_status(self) -> Dict[str, Any]:
        """현재 안전 메시징 상태 반환"""
        return {
            'use_safe_messaging': self.use_safe_messaging,
            'feature_flag_source': 'settings' if hasattr(self, '_settings_loaded') else 'default'
        }