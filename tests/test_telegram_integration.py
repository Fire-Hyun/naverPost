#!/usr/bin/env python3
"""
Test script for Telegram bot integration without external dependencies
"""

import sys
import os
from pathlib import Path
import pytest

# Add project root to path (scripts/ 아래로 이동했기 때문)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)


def _require_telegram_dependency():
    """telegram 패키지가 없으면 관련 테스트를 건너뜁니다."""
    pytest.importorskip("telegram", reason="python-telegram-bot dependency is not installed")

def test_basic_imports():
    """Test imports that don't require telegram library"""
    _require_telegram_dependency()
    try:
        # Test configuration
        from src.config.settings import Settings
        print("✅ Settings import successful")

        # Test session models (no telegram dependency)
        from src.telegram.models.session import (
            TelegramSession, ConversationState,
            get_session, create_session, delete_session
        )
        print("✅ Session models import successful")

        # Test response templates
        from src.telegram.models.responses import ResponseTemplates
        print("✅ Response templates import successful")

        # Test settings
        from src.telegram.config.telegram_settings import TelegramSettings
        print("✅ Telegram settings import successful")

    except Exception as e:
        print(f"❌ Import error: {e}")
        import traceback
        traceback.print_exc()
        raise AssertionError(f"Import test failed: {e}") from e

def test_session_functionality():
    """Test session management functionality"""
    _require_telegram_dependency()
    try:
        from src.telegram.models.session import TelegramSession, ConversationState, create_session

        # Create a test session
        session = create_session(12345)
        assert session.user_id == 12345
        assert session.state == ConversationState.WAITING_DATE
        print("✅ Session creation works")

        # Test data conversion
        session.visit_date = "20260212"
        session.category = "맛집"
        session.personal_review = "정말 맛있었어요! 특히 파스타가 일품이었습니다."
        session.additional_script = "재방문 의사 있음"

        user_exp = session.to_user_experience_dict()
        assert user_exp["category"] == "맛집"
        assert user_exp["visit_date"] == "20260212"
        print("✅ Data conversion works")

        # Test progress summary
        summary = session.get_progress_summary()
        assert "맛집" in summary
        assert "20260212" in summary
        print("✅ Progress summary works")

        # Test missing fields
        session.images = []  # No images
        missing = session.get_missing_fields()
        assert "사진" in missing
        print("✅ Missing fields detection works")

    except Exception as e:
        print(f"❌ Session functionality error: {e}")
        import traceback
        traceback.print_exc()
        raise AssertionError(f"Session functionality test failed: {e}") from e

def test_response_templates():
    """Test response template functionality"""
    _require_telegram_dependency()
    try:
        from src.telegram.models.responses import ResponseTemplates

        # Test various templates
        welcome = ResponseTemplates.welcome_message()
        assert "네이버 블로그" in welcome
        print("✅ Welcome message template works")

        invalid_date = ResponseTemplates.invalid_date_format()
        assert "YYYYMMDD" in invalid_date
        print("✅ Invalid date template works")

        missing_fields = ResponseTemplates.missing_fields(["방문 날짜", "카테고리"])
        assert "방문 날짜" in missing_fields
        assert "카테고리" in missing_fields
        print("✅ Missing fields template works")

    except Exception as e:
        print(f"❌ Response template error: {e}")
        import traceback
        traceback.print_exc()
        raise AssertionError(f"Response template test failed: {e}") from e

def test_configuration_validation():
    """Test configuration validation"""
    _require_telegram_dependency()
    try:
        from src.telegram.config.telegram_settings import TelegramSettings
        from src.config.settings import Settings

        # Test validation without actual token
        validation = TelegramSettings.validate_configuration()
        assert "is_valid" in validation
        assert "errors" in validation
        print("✅ Configuration validation structure works")

        # Test startup info generation
        info = TelegramSettings.get_startup_info()
        assert "Telegram Bot Configuration" in info
        print("✅ Startup info generation works")

    except Exception as e:
        print(f"❌ Configuration validation error: {e}")
        import traceback
        traceback.print_exc()
        raise AssertionError(f"Configuration validation test failed: {e}") from e

def test_existing_integration():
    """Test integration with existing system components"""
    _require_telegram_dependency()
    try:
        # Test that we can import existing modules
        from src.storage.data_manager import data_manager
        print("✅ Data manager import successful")

        from src.content.blog_generator import DateBasedBlogGenerator
        generator = DateBasedBlogGenerator()
        print("✅ Blog generator import successful")

        # Test that required methods exist
        assert hasattr(data_manager, 'create_posting_session')
        assert hasattr(data_manager, 'save_uploaded_images')
        print("✅ Data manager has required methods")

        assert hasattr(generator, 'generate_from_session_data')
        print("✅ Blog generator has required methods")

    except Exception as e:
        print(f"❌ Existing integration error: {e}")
        import traceback
        traceback.print_exc()
        raise AssertionError(f"Existing integration test failed: {e}") from e

def main():
    """Run all tests"""
    print("🧪 Testing Telegram bot integration...\n")

    tests = [
        ("Basic imports", test_basic_imports),
        ("Session functionality", test_session_functionality),
        ("Response templates", test_response_templates),
        ("Configuration validation", test_configuration_validation),
        ("Existing system integration", test_existing_integration),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        print(f"\n📋 Testing {test_name}:")
        if test_func():
            print(f"✅ {test_name} passed")
            passed += 1
        else:
            print(f"❌ {test_name} failed")
            failed += 1

    print(f"\n📊 Test Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 All integration tests passed!")
        print("\n📝 Next steps:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Set TELEGRAM_BOT_TOKEN in .env file")
        print("3. Run: python etc_scripts/run_telegram_bot.py")
        return 0
    else:
        print("❌ Some tests failed. Please fix issues before proceeding.")
        return 1

if __name__ == "__main__":
    exit(main())
