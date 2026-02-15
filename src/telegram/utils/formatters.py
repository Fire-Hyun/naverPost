"""
Content formatting utilities
"""

from ..models.session import TelegramSession


class ProgressSummaryBuilder:
    """진행 상황 요약 생성"""

    @staticmethod
    def build_summary(session: TelegramSession) -> str:
        """세션 정보를 요약으로 변환"""
        summary_parts = []

        if session.visit_date:
            summary_parts.append(f"📅 방문 날짜: {session.visit_date}")

        if session.category:
            summary_parts.append(f"📂 카테고리: {session.category}")

        if session.resolved_store_name:
            summary_parts.append(f"🏪 상호명: {session.resolved_store_name}")
        elif session.raw_store_name:
            summary_parts.append(f"🏪 상호명: {session.raw_store_name} (확인중)")

        if session.images:
            summary_parts.append(f"📸 사진 수: {len(session.images)}장")

        if session.personal_review:
            summary_parts.append(f"📝 감상평: {len(session.personal_review)}자")

        additional_status = "있음" if session.additional_script else "없음"
        summary_parts.append(f"➕ 추가 내용: {additional_status}")

        return "\n".join(summary_parts) if summary_parts else "아직 입력된 정보가 없습니다."