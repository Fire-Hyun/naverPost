#!/usr/bin/env python3
"""
Verification script for Telegram bot installation and configuration
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

def check_telegram_dependencies():
    """Check if Telegram bot dependencies are installed"""
    try:
        import telegram
        from telegram.ext import ApplicationBuilder
        print("✅ python-telegram-bot is installed")
        return True
    except ImportError:
        print("❌ python-telegram-bot not installed")
        print("   Run: pip install python-telegram-bot==20.7 aiohttp>=3.8.0")
        return False

def check_telegram_module():
    """Check if Telegram bot module can be imported"""
    try:
        from src.telegram.models.session import TelegramSession, ConversationState
        from src.telegram.models.responses import ResponseTemplates
        from src.telegram.handlers.conversation import ConversationHandler
        from src.telegram.handlers.image_handler import ImageHandler
        from src.telegram.config.telegram_settings import TelegramSettings
        print("✅ All Telegram bot modules import successfully")
        return True
    except Exception as e:
        print(f"❌ Error importing Telegram modules: {e}")
        return False

def check_telegram_bot_class():
    """Check if main bot class can be imported with dependencies"""
    try:
        from src.telegram.bot import NaverPostTelegramBot
        print("✅ NaverPostTelegramBot can be imported")
        return True
    except ImportError as e:
        error_text = str(e)
        if "No module named 'telegram'" in error_text:
            print("❌ NaverPostTelegramBot requires Telegram dependencies")
            print("   Run: pip install python-telegram-bot==20.7 aiohttp>=3.8.0")
            return False
        else:
            print(f"❌ Error importing NaverPostTelegramBot: {error_text}")
            return False

def check_configuration():
    """Check Telegram bot configuration"""
    try:
        from src.telegram.config.telegram_settings import TelegramSettings
        from src.config.settings import Settings

        validation = TelegramSettings.validate_configuration()

        print("📋 Telegram bot configuration status:")
        print(f"   Bot Token: {'Set' if Settings.TELEGRAM_BOT_TOKEN else 'Not set'}")
        print(f"   Admin User ID: {'Set' if Settings.TELEGRAM_ADMIN_USER_ID else 'Not set'}")
        print(f"   Public Access: {Settings.TELEGRAM_ALLOW_PUBLIC}")
        print(f"   Session Timeout: {Settings.TELEGRAM_SESSION_TIMEOUT}s")

        if not validation["is_valid"]:
            print("\n⚠️  Configuration issues:")
            for error in validation["errors"]:
                print(f"   - {error}")
        else:
            print("✅ Configuration is valid")

        return validation["is_valid"]

    except Exception as e:
        print(f"❌ Error checking configuration: {e}")
        return False

def check_existing_integration():
    """Check integration with existing naverPost modules"""
    try:
        from src.storage.data_manager import data_manager
        from src.content.blog_generator import DateBasedBlogGenerator

        # Test that required methods exist
        assert hasattr(data_manager, 'create_posting_session')
        assert hasattr(data_manager, 'save_uploaded_images')

        generator = DateBasedBlogGenerator()
        assert hasattr(generator, 'generate_from_session_data')

        print("✅ Integration with existing naverPost system verified")
        return True

    except Exception as e:
        print(f"❌ Integration check failed: {e}")
        return False

def test_session_functionality():
    """Test basic session functionality"""
    try:
        from src.telegram.models.session import create_session, get_session

        # Create a test session
        session = create_session(12345)
        retrieved = get_session(12345)

        assert session is retrieved
        assert session.user_id == 12345

        # Test data conversion
        session.visit_date = "20260212"
        session.category = "맛집"
        session.personal_review = "Test review"

        user_exp = session.to_user_experience_dict()
        assert user_exp["category"] == "맛집"
        assert user_exp["visit_date"] == "20260212"

        print("✅ Session functionality test passed")
        return True

    except Exception as e:
        print(f"❌ Session functionality test failed: {e}")
        return False

def show_next_steps():
    """Show next steps for setup"""
    print("\n🚀 Next Steps:")
    print("\n1. Install dependencies (if not already installed):")
    print("   pip install python-telegram-bot==20.7 aiohttp>=3.8.0")
    print("\n2. Create a Telegram bot:")
    print("   - Message @BotFather on Telegram")
    print("   - Use /newbot to create a new bot")
    print("   - Copy the bot token")
    print("\n3. Configure the bot:")
    print("   - Add TELEGRAM_BOT_TOKEN to your .env file")
    print("   - Optionally set TELEGRAM_ADMIN_USER_ID for access control")
    print("\n4. Run the bot:")
    print("   python3 etc_scripts/run_telegram_bot.py")
    print("\n5. Test the bot:")
    print("   - Start a chat with your bot on Telegram")
    print("   - Send /start to begin")

def main():
    """Run all verification checks"""
    print("🔍 Verifying Telegram Bot Installation and Configuration\n")

    checks = [
        ("Telegram dependencies", check_telegram_dependencies),
        ("Telegram modules", check_telegram_module),
        ("Telegram bot class", check_telegram_bot_class),
        ("Configuration", check_configuration),
        ("Existing system integration", check_existing_integration),
        ("Session functionality", test_session_functionality),
    ]

    passed = 0
    total = len(checks)

    for name, check_func in checks:
        print(f"\n📋 Checking {name}:")
        try:
            if check_func():
                passed += 1
            else:
                print(f"   ❌ {name} check failed")
        except Exception as e:
            print(f"   ❌ {name} check error: {e}")

    print(f"\n📊 Verification Results: {passed}/{total} checks passed")

    if passed == total:
        print("🎉 All checks passed! Telegram bot is ready to use.")
        print("\nTo start the bot, run: python3 etc_scripts/run_telegram_bot.py")
    else:
        print(f"⚠️  {total - passed} checks failed. Please fix the issues above.")
        show_next_steps()

    return 0 if passed == total else 1

if __name__ == "__main__":
    exit(main())
