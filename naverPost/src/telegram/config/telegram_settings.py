"""
Telegram bot specific configuration and validation
"""

from typing import Dict, List, Optional
from pathlib import Path
import os

from src.config.settings import Settings


class TelegramSettings:
    """텔레그램 봇 전용 설정 및 검증"""

    @classmethod
    def validate_configuration(cls) -> Dict[str, any]:
        """텔레그램 봇 설정 전체 검증"""
        validation_result = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "config": {}
        }

        # 필수 설정 검증
        if not Settings.TELEGRAM_BOT_TOKEN:
            validation_result["errors"].append("TELEGRAM_BOT_TOKEN is required")
            validation_result["is_valid"] = False

        # 토큰 형식 검증 (기본적인 형식만)
        if Settings.TELEGRAM_BOT_TOKEN and not cls._is_valid_bot_token(Settings.TELEGRAM_BOT_TOKEN):
            validation_result["errors"].append("TELEGRAM_BOT_TOKEN format appears invalid")
            validation_result["is_valid"] = False

        # 관리자 ID 검증
        if Settings.TELEGRAM_ADMIN_USER_ID and not cls._is_valid_user_id(Settings.TELEGRAM_ADMIN_USER_ID):
            validation_result["warnings"].append("TELEGRAM_ADMIN_USER_ID format may be invalid")

        # 디렉토리 접근 권한 검증
        temp_dir = Path(Settings.DATA_DIR) / "telegram_temp"
        try:
            temp_dir.mkdir(exist_ok=True, parents=True)
            validation_result["config"]["temp_dir"] = str(temp_dir)
        except Exception as e:
            validation_result["errors"].append(f"Cannot create temp directory: {e}")
            validation_result["is_valid"] = False

        # 기존 시스템과의 호환성 검증
        compatibility_check = cls._check_system_compatibility()
        if not compatibility_check["is_compatible"]:
            validation_result["errors"].extend(compatibility_check["errors"])
            validation_result["is_valid"] = False

        validation_result["warnings"].extend(compatibility_check.get("warnings", []))

        # 설정 값 정리
        validation_result["config"].update({
            "bot_token_masked": cls._mask_token(Settings.TELEGRAM_BOT_TOKEN),
            "admin_user_id": Settings.TELEGRAM_ADMIN_USER_ID,
            "allow_public": Settings.TELEGRAM_ALLOW_PUBLIC,
            "session_timeout": Settings.TELEGRAM_SESSION_TIMEOUT,
            "max_images": Settings.MAX_IMAGES_PER_POST,
            "max_file_size_mb": Settings.MAX_FILE_SIZE_MB
        })

        return validation_result

    @classmethod
    def _is_valid_bot_token(cls, token: str) -> bool:
        """봇 토큰 형식 검증"""
        # Telegram 봇 토큰은 일반적으로 "숫자:문자열" 형식
        parts = token.split(":")
        if len(parts) != 2:
            return False

        bot_id, secret = parts
        return bot_id.isdigit() and len(secret) >= 35

    @classmethod
    def _is_valid_user_id(cls, user_id_str: str) -> bool:
        """사용자 ID 형식 검증"""
        try:
            user_id = int(user_id_str)
            return user_id > 0
        except (ValueError, TypeError):
            return False

    @classmethod
    def _mask_token(cls, token: str) -> str:
        """토큰을 마스킹하여 안전하게 표시"""
        if not token:
            return "Not set"

        if len(token) < 10:
            return "*" * len(token)

        return token[:10] + "*" * (len(token) - 10)

    @classmethod
    def _check_system_compatibility(cls) -> Dict[str, any]:
        """기존 시스템과의 호환성 검증"""
        result = {
            "is_compatible": True,
            "errors": [],
            "warnings": []
        }

        # 필수 모듈 가져오기 테스트
        required_modules = [
            "src.config.settings",
            "src.storage.data_manager",
            "src.content.blog_generator"
        ]

        for module_name in required_modules:
            try:
                __import__(module_name)
            except ImportError as e:
                result["errors"].append(f"Cannot import required module {module_name}: {e}")
                result["is_compatible"] = False

        # 데이터 매니저 접근 테스트
        try:
            from src.storage.data_manager import data_manager
            # 간단한 검증만 수행
            if not hasattr(data_manager, 'create_posting_session'):
                result["errors"].append("DataManager missing required method: create_posting_session")
                result["is_compatible"] = False
        except Exception as e:
            result["errors"].append(f"DataManager compatibility issue: {e}")
            result["is_compatible"] = False

        # 블로그 생성기 호환성 테스트
        try:
            from src.content.blog_generator import DateBasedBlogGenerator
            generator = DateBasedBlogGenerator()
            if not hasattr(generator, 'generate_from_session_data'):
                result["errors"].append("BlogGenerator missing required method: generate_from_session_data")
                result["is_compatible"] = False
        except Exception as e:
            result["errors"].append(f"BlogGenerator compatibility issue: {e}")
            result["is_compatible"] = False

        return result

    @classmethod
    def get_startup_info(cls) -> str:
        """시작 시 표시할 설정 정보"""
        validation = cls.validate_configuration()

        info_lines = [
            "🤖 Telegram Bot Configuration:",
            f"   Token: {validation['config'].get('bot_token_masked', 'Not set')}",
            f"   Admin User: {validation['config'].get('admin_user_id', 'Not set')}",
            f"   Public Access: {validation['config'].get('allow_public', False)}",
            f"   Session Timeout: {validation['config'].get('session_timeout', 1800)}s",
            f"   Max Images: {validation['config'].get('max_images', 10)}",
            f"   Max File Size: {validation['config'].get('max_file_size_mb', 50)}MB"
        ]

        if validation["warnings"]:
            info_lines.append("\n⚠️  Warnings:")
            for warning in validation["warnings"]:
                info_lines.append(f"   - {warning}")

        if validation["errors"]:
            info_lines.append("\n❌ Errors:")
            for error in validation["errors"]:
                info_lines.append(f"   - {error}")

        return "\n".join(info_lines)

    @classmethod
    def create_sample_env(cls) -> str:
        """샘플 .env 설정 생성"""
        return """
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTuVwxyZ
TELEGRAM_ADMIN_USER_ID=123456789
TELEGRAM_ALLOW_PUBLIC=false
TELEGRAM_SESSION_TIMEOUT=1800
"""