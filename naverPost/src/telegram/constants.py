"""
Telegram bot constants and configuration
"""

# Session timeouts (seconds)
DEFAULT_SESSION_TIMEOUT = 1800  # 30 minutes
CLEANUP_INTERVAL = 3600  # 1 hour

# Image validation
MIN_IMAGE_SIZE_BYTES = 100 * 1024  # 100KB
MIN_REVIEW_LENGTH = 50  # characters
TEMP_FILE_CLEANUP_HOURS = 24

# File handling
SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
MIME_TYPE_MAPPING = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp'
}

# Validation messages
VALIDATION_MESSAGES = {
    'invalid_date_formats': ['오늘', 'today'],
    'skip_keywords': ['없음', 'skip', 'no', ''],
}

# Emoji constants for consistency
EMOJIS = {
    'robot': '🤖',
    'check': '✅',
    'cross': '❌',
    'calendar': '📅',
    'folder': '📂',
    'camera': '📸',
    'memo': '📝',
    'plus': '➕',
    'gear': '🔧',
    'chart': '📊',
    'exclamation': '❗',
    'refresh': '🔄',
    'file': '📄',
    'warning': '⚠️'
}

# Inline callback actions
ACTION_START = "action_start"
ACTION_DONE = "action_done"
ACTION_HELP = "show_help"
ACTION_CANCEL_CURRENT = "cancel_current"
ACTION_CHECK_STATUS = "check_status"
