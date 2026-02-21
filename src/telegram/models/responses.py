"""
Telegram bot response templates
"""

from typing import List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from ..constants import ACTION_START, ACTION_DONE, ACTION_HELP, ACTION_CANCEL_CURRENT, ACTION_CHECK_STATUS


class ResponseTemplates:
    """텔레그램 봇 응답 템플릿 모음"""

    @staticmethod
    def welcome_message() -> str:
        """환영 메시지"""
        return (
            "🤖 **네이버 블로그 자동 생성 봇**에 오신 것을 환영합니다!\n\n"
            "✨ **주요 기능:**\n"
            "• AI 기반 고품질 블로그 자동 생성\n"
            "• 위치 기반 상호명 자동 보정\n"
            "• 실시간 품질 검증\n"
            "• 네이버 블로그 자동 임시저장\n\n"
            "👇 **아래 버튼을 눌러 시작하세요!**"
        )

    @staticmethod
    def access_denied() -> str:
        """접근 거부 메시지"""
        return "죄송합니다. 이 봇은 허가된 사용자만 사용할 수 있습니다."

    @staticmethod
    def session_expired() -> str:
        """세션 만료 메시지"""
        return "세션이 만료되었습니다. 아래 '시작하기' 버튼으로 다시 시작해주세요."

    @staticmethod
    def no_active_session() -> str:
        """활성 세션 없음 메시지"""
        return "활성 세션이 없습니다. 아래 '시작하기' 버튼을 눌러 시작해주세요."

    @staticmethod
    def invalid_date_format(detail: str = None) -> str:
        """잘못된 날짜 형식 메시지"""
        if detail:
            return f"❌ {detail}"
        return (
            "❌ 날짜 형식이 올바르지 않습니다.\n"
            "다음 형식을 사용해주세요:\n"
            "• YYYYMMDD (예: 20260212)\n"
            "• YYYY-MM-DD (예: 2026-02-12)\n"
            "• '오늘', '어제'"
        )

    @staticmethod
    def date_confirmed(date: str) -> str:
        """날짜 확인 메시지"""
        return f"✅ 방문 날짜: {date}\n\n카테고리를 선택해주세요:"

    @staticmethod
    def invalid_category(valid_categories: List[str]) -> str:
        """잘못된 카테고리 메시지"""
        return (
            f"❌ 지원하지 않는 카테고리입니다.\n"
            f"다음 중에서 선택해주세요: {', '.join(valid_categories)}"
        )

    @staticmethod
    def category_confirmed(category: str) -> str:
        """카테고리 확인 메시지 (기존)"""
        return (
            f"✅ 카테고리: {category}\n\n"
            "📸 사진을 업로드해주세요 (여러 장 가능).\n"
            "업로드가 완료되면 감상평을 입력해주세요."
        )

    @staticmethod
    def category_confirmed_request_store_name(category: str) -> str:
        """카테고리 확인 후 상호명 요청 메시지"""
        return (
            f"✅ 카테고리: {category}\n\n"
            "🏪 방문한 상호명을 입력해주세요.\n"
            "예시:\n"
            "• 스타벅스\n"
            "• 스타벅스 강남역점\n"
            "• 맥도날드 홍대점\n\n"
            "지점명을 정확히 모르면 브랜드명만 입력해도 됩니다."
        )

    @staticmethod
    def waiting_for_images() -> str:
        """이미지 대기 메시지"""
        return (
            "📸 먼저 사진을 업로드해주세요.\n"
            "사진 업로드 후 감상평을 입력하시면 됩니다."
        )

    @staticmethod
    def image_uploaded(current_count: int, max_count: int) -> str:
        """이미지 업로드 완료 메시지"""
        return (
            f"✅ 이미지가 업로드되었습니다! ({current_count}/{max_count})\n\n"
            f"{'더 많은 사진을 올리거나 ' if current_count < max_count else ''}"
            "방문 후 감상평을 자유롭게 작성해주세요."
        )

    @staticmethod
    def image_limit_reached(max_count: int) -> str:
        """이미지 한도 초과 메시지"""
        return f"❌ 이미지는 최대 {max_count}장까지 업로드할 수 있습니다."

    @staticmethod
    def image_invalid() -> str:
        """잘못된 이미지 메시지"""
        return (
            "❌ 이미지가 유효하지 않거나 너무 큽니다.\n"
            "지원 형식: JPG, PNG, GIF, WEBP\n"
            "최대 크기: 50MB, 최소 크기: 100KB"
        )

    @staticmethod
    def image_upload_error(error: str) -> str:
        """이미지 업로드 오류 메시지"""
        return f"❌ 이미지 업로드 중 오류가 발생했습니다: {error}"

    @staticmethod
    def review_too_short(current_length: int, min_length: int = 50) -> str:
        """감상평 너무 짧음 메시지"""
        return (
            f"❌ 감상평이 너무 짧습니다.\n"
            f"최소 {min_length}자 이상 입력해주세요. (현재: {current_length}자)"
        )

    @staticmethod
    def review_confirmed() -> str:
        """감상평 확인 메시지"""
        return (
            f"✅ 감상평이 저장되었습니다.\n\n"
            "📝 블로그 작성 시 참고할 추가 내용을 입력해주세요.\n"
            "(없으면 '없음' 또는 'skip'을 입력하세요)"
        )

    @staticmethod
    def ready_to_generate(summary: str) -> str:
        """생성 준비 완료 메시지"""
        return (
            f"📋 **입력된 정보 확인:**\n\n{summary}\n\n"
            "✅ **모든 정보 입력이 완료되었습니다!**\n"
            "👇 아래 버튼을 눌러 AI 블로그 자동 생성을 시작하세요."
        )

    @staticmethod
    def missing_fields(fields: List[str]) -> str:
        """누락된 필드 메시지"""
        return (
            f"❌ 다음 정보가 누락되었습니다:\n" +
            "\n".join(f"• {field}" for field in fields) +
            "\n\n필요한 정보를 모두 입력한 뒤, 아래 '완료하기' 버튼을 눌러주세요."
        )

    @staticmethod
    def generation_started() -> str:
        """생성 시작 메시지"""
        return "🔄 블로그 글을 생성하고 있습니다. 잠시만 기다려주세요..."

    @staticmethod
    def generation_success(directory: str, length: str) -> str:
        """생성 성공 메시지"""
        return (
            f"✅ 블로그 글 생성이 완료되었습니다!\n\n"
            f"📁 저장 위치: {directory}\n"
            f"📄 파일: blog_result.md\n"
            f"📊 글자 수: {length}\n\n"
            f"생성된 글을 확인하신 후 네이버 블로그에 업로드하세요."
        )

    @staticmethod
    def generation_failed(error: str) -> str:
        """생성 실패 메시지"""
        return (
            f"❌ 블로그 글 생성에 실패했습니다.\n"
            f"오류: {error}"
        )

    @staticmethod
    def unknown_state() -> str:
        """알 수 없는 상태 메시지"""
        return "알 수 없는 상태입니다. 아래 '시작하기' 버튼으로 다시 시작해주세요."

    @staticmethod
    def unknown_error(error: str) -> str:
        """일반 오류 메시지"""
        return f"❌ 오류가 발생했습니다: {error}"

    @staticmethod
    def help_message() -> str:
        """도움말 메시지"""
        return (
            "🤖 네이버 블로그 자동 생성 봇 도움말\n\n"
            "📋 사용법:\n"
            "1. 시작하기 버튼 - 새 블로그 포스트 작성 시작\n"
            "2. 날짜 입력 (YYYYMMDD, YYYY-MM-DD, '오늘', '어제')\n"
            "3. 카테고리 선택\n"
            "4. 상호명 입력 (예: '스타벅스 강남점')\n"
            "5. 사진 업로드 (여러 장 가능, GPS 자동 추출)\n"
            "6. 감상평 입력\n"
            "7. 추가 내용 입력 (선택사항)\n"
            "8. 완료하기 버튼 - AI 블로그 글 생성 및 네이버 임시저장\n\n"
            "🔧 명령어:\n"
            "• 버튼 사용을 기본으로 권장합니다\n"
            "• /start, /done 명령어는 백업용으로 계속 지원됩니다\n"
            "• /cancel - 현재 세션 취소\n"
            "• /status - 현재 진행 상태 확인\n"
            "• /help - 이 도움말 보기\n\n"
            "🏪 상호명 기능:\n"
            "• 지점명 자동 보정 (위치 기반)\n"
            "• 이미지 GPS 정보 자동 추출\n"
            "• 네이버/카카오 지역검색 연동"
        )

    @staticmethod
    def session_canceled() -> str:
        """세션 취소 메시지"""
        return "❌ 현재 세션이 취소되었습니다. 새로 시작하려면 아래 '시작하기' 버튼을 눌러주세요."

    @staticmethod
    def status_message(summary: str, missing_fields: List[str]) -> str:
        """상태 확인 메시지"""
        status = f"📊 현재 진행 상태:\n\n{summary}"

        if missing_fields:
            status += f"\n\n❗ 누락된 정보:\n" + "\n".join(f"• {field}" for field in missing_fields)
        else:
            status += "\n\n✅ 모든 정보가 입력되었습니다! 아래 '완료하기' 버튼으로 생성하세요."

        return status

    @staticmethod
    def wrong_step_for_images() -> str:
        """이미지 업로드 단계 아님 메시지"""
        return (
            "지금은 이미지를 받을 수 있는 단계가 아닙니다.\n"
            "먼저 날짜와 카테고리를 입력해주세요."
        )

    @staticmethod
    def store_name_confirmed_request_images() -> str:
        """상호명 확인 후 사진 요청 메시지"""
        return (
            "📸 이제 사진을 업로드해주세요 (여러 장 가능).\n"
            "업로드가 완료되면 감상평을 입력해주세요."
        )

    # ========== 버튼 생성 메서드들 ==========

    @staticmethod
    def create_start_keyboard() -> InlineKeyboardMarkup:
        """시작 버튼 키보드 생성"""
        keyboard = [
            [InlineKeyboardButton("🚀 시작하기", callback_data=ACTION_START)],
            [InlineKeyboardButton("📋 도움말", callback_data=ACTION_HELP)]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def create_main_menu_keyboard() -> InlineKeyboardMarkup:
        """메인 메뉴 키보드 생성"""
        keyboard = [
            [InlineKeyboardButton("✏️ 새 블로그 작성", callback_data=ACTION_START)],
            [InlineKeyboardButton("📊 진행 상태 확인", callback_data=ACTION_CHECK_STATUS)],
            [InlineKeyboardButton("❌ 현재 작업 취소", callback_data=ACTION_CANCEL_CURRENT)],
            [InlineKeyboardButton("📋 도움말", callback_data=ACTION_HELP)]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def create_generation_keyboard() -> InlineKeyboardMarkup:
        """블로그 생성 버튼 키보드 생성"""
        keyboard = [
            [InlineKeyboardButton("✅ 완료하기", callback_data=ACTION_DONE)],
            [InlineKeyboardButton("📊 현재 상태 확인", callback_data=ACTION_CHECK_STATUS)],
            [InlineKeyboardButton("❌ 작업 취소", callback_data=ACTION_CANCEL_CURRENT)]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def create_cancel_keyboard() -> InlineKeyboardMarkup:
        """취소 전용 키보드 생성 (생성 진행 중)"""
        keyboard = [
            [InlineKeyboardButton("⏹️ 진행 중인 작업 취소", callback_data="cancel_generation")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def create_completion_keyboard() -> InlineKeyboardMarkup:
        """작업 완료 후 키보드 생성"""
        keyboard = [
            [InlineKeyboardButton("✏️ 새 블로그 작성", callback_data=ACTION_START)],
            [InlineKeyboardButton("📁 결과 확인", callback_data="check_last_result")],
            [InlineKeyboardButton("📋 도움말", callback_data=ACTION_HELP)]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def create_category_keyboard(categories: List[str]) -> InlineKeyboardMarkup:
        """카테고리 선택 인라인 키보드 생성"""
        keyboard = []
        for category in categories:
            keyboard.append([InlineKeyboardButton(f"📂 {category}", callback_data=f"category_{category}")])

        # 뒤로 가기 버튼 추가
        keyboard.append([InlineKeyboardButton("⬅️ 뒤로 가기", callback_data="back_to_date")])

        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def create_date_input_keyboard() -> InlineKeyboardMarkup:
        """날짜 입력 도움 키보드 생성"""
        keyboard = [
            [InlineKeyboardButton("📅 오늘 날짜 사용", callback_data="date_today")],
            [InlineKeyboardButton("📅 어제 날짜 사용", callback_data="date_yesterday")],
            [InlineKeyboardButton("❌ 취소", callback_data="cancel_current")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def create_location_request_keyboard() -> ReplyKeyboardMarkup:
        """위치 공유 요청 키보드 생성"""
        keyboard = [
            [KeyboardButton("📍 현재 위치 공유", request_location=True)],
            ["직접 입력하겠습니다", "❌ 건너뛰기"]
        ]
        return ReplyKeyboardMarkup(
            keyboard,
            one_time_keyboard=True,
            resize_keyboard=True,
            input_field_placeholder="위치를 공유하거나 직접 입력해주세요"
        )

    @staticmethod
    def create_review_input_keyboard() -> InlineKeyboardMarkup:
        """감상평 입력 도움 키보드 생성"""
        keyboard = [
            [InlineKeyboardButton("💡 작성 팁 보기", callback_data="show_review_tips")],
            [InlineKeyboardButton("⬅️ 이전 단계", callback_data="back_to_images")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def create_confirmation_keyboard(action: str) -> InlineKeyboardMarkup:
        """확인/취소 키보드 생성"""
        keyboard = [
            [InlineKeyboardButton("✅ 확인", callback_data=f"confirm_{action}")],
            [InlineKeyboardButton("❌ 취소", callback_data=f"cancel_{action}")]
        ]
        return InlineKeyboardMarkup(keyboard)
