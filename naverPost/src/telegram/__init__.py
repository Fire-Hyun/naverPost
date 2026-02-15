"""Telegram bot module for naverPost system"""

# Conditional import to avoid dependency issues during development
try:
    from .bot import NaverPostTelegramBot
    __all__ = ['NaverPostTelegramBot']
except ImportError as e:
    # Telegram dependencies not available
    __all__ = []

    def NaverPostTelegramBot():
        raise ImportError(
            "Telegram bot dependencies not available. "
            "Please install with: pip install python-telegram-bot==20.7 aiohttp>=3.8.0"
        )