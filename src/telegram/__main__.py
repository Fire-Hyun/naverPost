#!/usr/bin/env python3
"""
Telegram bot module entry point
Unified entry point using TelegramBotService
"""

if __name__ == "__main__":
    try:
        from ..services.telegram_service import get_telegram_service

        # 통합된 Telegram 서비스 사용 (모듈 모드에서는 단순 실행)
        service = get_telegram_service(
            enable_dns_fallback=True,
            retry_delay=10
        )

        exit(service.run_once())  # 모듈 모드에서는 한 번만 실행

    except KeyboardInterrupt:
        print("\nBot stopped by user")
        exit(0)
    except Exception as e:
        print(f"Failed to start bot: {e}")
        exit(1)