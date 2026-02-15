"""
General helper utilities
"""

from telegram import Update
from ..models.responses import ResponseTemplates


class ContentTypeDetector:
    """파일 타입 감지"""

    @staticmethod
    def get_mime_type(file_extension: str) -> str:
        """파일 확장자로 MIME 타입 결정"""
        from ..constants import MIME_TYPE_MAPPING
        return MIME_TYPE_MAPPING.get(file_extension.lower(), 'image/jpeg')

    @staticmethod
    def is_supported_image_extension(extension: str) -> bool:
        """지원되는 이미지 확장자인지 확인"""
        from ..constants import SUPPORTED_IMAGE_EXTENSIONS
        return extension.lower() in SUPPORTED_IMAGE_EXTENSIONS


class ErrorHandler:
    """에러 처리 공통 기능"""

    @staticmethod
    async def handle_unexpected_error(
        update: Update,
        error: Exception,
        logger,
        context_info: str = ""
    ):
        """예상치 못한 에러 처리"""
        error_msg = str(error)
        logger.error(f"Unexpected error {context_info}: {error_msg}")

        if update and update.effective_message:
            try:
                responses = ResponseTemplates()
                await update.effective_message.reply_text(
                    responses.unknown_error(error_msg)
                )
            except Exception:
                # 메시지 전송도 실패한 경우 로깅만 수행
                logger.error("Failed to send error message to user")


class AccessControl:
    """접근 권한 제어"""

    @staticmethod
    def is_user_allowed(user_id: int, settings) -> bool:
        """사용자 접근 권한 확인"""
        # 공개 모드인 경우 모든 사용자 허용
        if settings.TELEGRAM_ALLOW_PUBLIC:
            return True

        # 관리자 ID가 설정된 경우 해당 사용자만 허용
        if settings.TELEGRAM_ADMIN_USER_ID:
            return str(user_id) == settings.TELEGRAM_ADMIN_USER_ID

        # 기본적으로 허용 (제한이 설정되지 않은 경우)
        return True