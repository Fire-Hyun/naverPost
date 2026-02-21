"""
안전한 텔레그램 메시지 포매팅 유틸리티
"""

import re
from typing import Optional


class TelegramMessageFormatter:
    """텔레그램 메시지 안전 포매팅 클래스"""

    # Markdown에서 이스케이프해야 할 특수문자들
    MARKDOWN_ESCAPE_CHARS = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']

    @staticmethod
    def escape_markdown_v2(text: str) -> str:
        """MarkdownV2용 특수문자 이스케이프"""
        if not text:
            return text

        # MarkdownV2에서 이스케이프해야 할 문자들
        escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']

        for char in escape_chars:
            text = text.replace(char, f'\\{char}')

        return text

    @staticmethod
    def escape_markdown_basic(text: str) -> str:
        """기본 Markdown용 특수문자 이스케이프"""
        if not text:
            return text

        # 기본 Markdown에서 문제가 되는 주요 문자들만 처리
        replacements = {
            '*': '\\*',
            '_': '\\_',
            '[': '\\[',
            ']': '\\]',
            '`': '\\`',
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        return text

    @staticmethod
    def safe_format_message(text: str, parse_mode: Optional[str] = 'Markdown') -> tuple[str, Optional[str]]:
        """
        안전한 메시지 포매팅

        의도적인 Markdown 포매팅(**bold** 등)을 보존하면서,
        길이 제한만 적용한다. escape_markdown_basic은 의도적 포매팅까지
        파괴하므로 사용하지 않는다.

        Returns:
            tuple: (formatted_text, safe_parse_mode)
        """
        if not text:
            return text, parse_mode

        if parse_mode == 'Markdown':
            # 기본 Markdown: 의도적 포매팅을 그대로 전달
            # Telegram 기본 Markdown에서는 *bold*, _italic_ 사용
            # escape는 하지 않음 (의도적 포매팅 파괴 방지)
            return text, parse_mode
        elif parse_mode == 'MarkdownV2':
            return text, parse_mode
        else:
            return text, parse_mode

    @staticmethod
    def convert_to_html(text: str) -> str:
        """Markdown을 HTML로 변환"""
        # 기본적인 Markdown → HTML 변환
        html_text = text

        # Bold 변환: **text** → <b>text</b>
        html_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html_text)

        # Italic 변환: *text* → <i>text</i>
        html_text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', html_text)

        # Code 변환: `text` → <code>text</code>
        html_text = re.sub(r'`([^`]+)`', r'<code>\1</code>', html_text)

        return html_text

    @staticmethod
    def strip_markdown(text: str) -> str:
        """Markdown 문법 제거하여 plain text로 변환"""
        # Markdown 문법 제거
        plain_text = text

        # Bold 제거: **text** → text
        plain_text = re.sub(r'\*\*(.*?)\*\*', r'\1', plain_text)

        # Italic 제거: *text* → text
        plain_text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'\1', plain_text)

        # Code 제거: `text` → text
        plain_text = re.sub(r'`([^`]+)`', r'\1', plain_text)

        # Link 제거: [text](url) → text
        plain_text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', plain_text)

        # 기타 특수문자 정리
        plain_text = re.sub(r'[_*`\[\]()]', '', plain_text)

        return plain_text

    @staticmethod
    def truncate_message(text: str, max_length: int = 4096) -> str:
        """텔레그램 메시지 길이 제한 처리"""
        if len(text) <= max_length:
            return text

        # 메시지가 너무 길면 잘라내고 "..." 추가
        truncated = text[:max_length-10] + "\n...(생략)"
        return truncated


# 편의 함수들
def safe_reply_text(message, text: str, parse_mode: str = 'Markdown', **kwargs):
    """안전한 텔레그램 메시지 전송"""
    safe_text, safe_parse_mode = TelegramMessageFormatter.safe_format_message(text, parse_mode)

    # 길이 제한 처리
    safe_text = TelegramMessageFormatter.truncate_message(safe_text)

    return message.reply_text(safe_text, parse_mode=safe_parse_mode, **kwargs)


async def safe_reply_text_async(message, text: str, parse_mode: str = 'Markdown', **kwargs):
    """안전한 비동기 텔레그램 메시지 전송 (Markdown 실패 시 plain text 폴백)"""
    import logging
    _logger = logging.getLogger(__name__)

    safe_text, safe_parse_mode = TelegramMessageFormatter.safe_format_message(text, parse_mode)

    # 길이 제한 처리
    safe_text = TelegramMessageFormatter.truncate_message(safe_text)

    try:
        return await message.reply_text(safe_text, parse_mode=safe_parse_mode, **kwargs)
    except Exception as e:
        # Markdown 파싱 실패 시 plain text 폴백
        _logger.warning(f"Markdown reply failed ({e}), falling back to plain text")
        fallback_text = TelegramMessageFormatter.strip_markdown(text)
        fallback_text = TelegramMessageFormatter.truncate_message(fallback_text)
        return await message.reply_text(fallback_text, parse_mode=None, **kwargs)