#!/usr/bin/env python3
"""
Standalone Telegram bot runner for naverPost system
Unified entry point using TelegramBotService
"""

import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def main():
    """메인 실행 함수"""
    try:
        from src.services.telegram_service import get_telegram_service

        # 통합된 Telegram 서비스 사용
        service = get_telegram_service(
            enable_dns_fallback=True,
            base_retry_delay=10
        )

        return service.run()

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Please make sure all dependencies are installed:")
        print("pip install -r requirements.txt")
        return 1

    except Exception as e:
        print(f"❌ Failed to initialize bot service: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
