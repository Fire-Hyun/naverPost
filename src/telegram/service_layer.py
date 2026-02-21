"""
Telegram bot service layer
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from src.storage.data_manager import data_manager
from src.content.blog_generator import DateBasedBlogGenerator
from src.services.blog_workflow import get_blog_workflow_service, WorkflowProgress, WorkflowStatus

from .models.session import TelegramSession, ConversationState, delete_session, update_session
from .models.responses import ResponseTemplates
from .handlers.image_handler import ImageHandler
from .utils import get_user_logger


class BlogGenerationService:
    """블로그 생성 서비스"""

    def __init__(self, image_handler: ImageHandler):
        self.data_manager = data_manager
        self.blog_generator = DateBasedBlogGenerator()
        self.workflow_service = get_blog_workflow_service()
        self.image_handler = image_handler
        self.responses = ResponseTemplates()
        self.logger = logging.getLogger(__name__)

    async def generate_blog_from_session(
        self,
        message,
        session: TelegramSession,
        auto_upload_to_naver: bool = True
    ) -> Dict[str, Any]:
        """
        세션 데이터로부터 블로그 생성 및 네이버 업로드

        Args:
            message: 텔레그램 메시지 객체 (reply_text 가능한 것)
            session: 텔레그램 세션
            auto_upload_to_naver: 네이버 자동 업로드 여부

        Returns:
            Dict with 'success', 'error', 'workflow_progress' keys
        """
        try:
            # 사용자별 로깅
            user_logger = get_user_logger(session.user_id)
            user_logger.log_generation_start()

            # 시작 알림
            await message.reply_text("🚀 블로그 자동화를 시작합니다...")

            # 세션 상태 업데이트
            session.state = ConversationState.GENERATING
            session.update_activity()

            # 이미지 파일 준비
            image_files = []
            if session.images:
                image_files = await self.image_handler.prepare_images_for_data_manager(session)

            # 사용자 경험 데이터 준비
            user_experience = session.to_user_experience_dict()

            # 진행상황 콜백 정의
            async def progress_callback(progress: WorkflowProgress):
                """진행상황을 텔레그램으로 전송하고 로깅"""
                status_emoji = {
                    WorkflowStatus.VALIDATING: "🔍",
                    WorkflowStatus.GENERATING_BLOG: "🤖",
                    WorkflowStatus.QUALITY_CHECKING: "📊",
                    WorkflowStatus.UPLOADING_TO_NAVER: "📤",
                    WorkflowStatus.COMPLETED: "✅",
                    WorkflowStatus.FAILED: "❌",
                    WorkflowStatus.CANCELLED: "⏹️"
                }.get(progress.status, "⏳")

                progress_msg = (
                    f"{status_emoji} **{progress.step_name}** ({progress.current_step}/{progress.total_steps})\n"
                    f"{progress.message}\n"
                    f"진행률: {progress.progress_percentage:.1f}%"
                )

                # 워크플로우 단계별 로깅
                status_name = {
                    WorkflowStatus.VALIDATING: "검증",
                    WorkflowStatus.GENERATING_BLOG: "생성",
                    WorkflowStatus.QUALITY_CHECKING: "품질검사",
                    WorkflowStatus.UPLOADING_TO_NAVER: "업로드",
                    WorkflowStatus.COMPLETED: "완료",
                    WorkflowStatus.FAILED: "실패",
                    WorkflowStatus.CANCELLED: "취소"
                }.get(progress.status, progress.status.value)

                user_logger.log_workflow_step(
                    step_name=progress.step_name,
                    status=status_name,
                    details=f"{progress.message} ({progress.progress_percentage:.1f}%)"
                )

                try:
                    await message.reply_text(progress_msg, parse_mode='Markdown')
                except Exception as e:
                    self.logger.warning(f"Failed to send progress update: {e}")

            # 통합 워크플로우 실행
            workflow_result = await self.workflow_service.process_complete_workflow(
                date_directory=session.visit_date,
                user_experience=user_experience,
                images=image_files,
                auto_upload=auto_upload_to_naver,
                progress_callback=progress_callback
            )

            # 결과 처리
            if workflow_result.status == WorkflowStatus.COMPLETED:
                session.date_directory = workflow_result.results.get('session', {}).get('directory')

                # 성공 로깅
                results = workflow_result.results
                generation_data = results.get('generation', {})
                length = generation_data.get('length', '알 수 없음')
                file_path = session.date_directory or "알 수 없음"
                user_logger.log_generation_success(file_path, str(length))

                # 품질 점수 로깅
                quality_data = results.get('quality', {})
                if quality_data:
                    user_logger.log_quality_check(
                        quality_data.get('overall_score', 0),
                        quality_data.get('issues', [])
                    )

                # 네이버 업로드 로깅
                upload_data = results.get('upload', {})
                if upload_data:
                    if upload_data.get('success') and upload_data.get('draft_saved', False):
                        if upload_data.get('image_included_success'):
                            user_logger.log_naver_upload_success(upload_data.get('post_url'))
                        else:
                            missing = upload_data.get('image_missing_count', 0)
                            user_logger.log_naver_upload_error(
                                f"임시저장 성공(이미지 누락 {missing}장)"
                            )
                    elif upload_data.get('success'):
                        user_logger.log_naver_upload_success(upload_data.get('post_url'))
                    else:
                        user_logger.log_naver_upload_error(upload_data.get('error', '알 수 없는 오류'))

                await self._handle_workflow_success(message, session, workflow_result)

                return {
                    'success': True,
                    'directory': session.date_directory,
                    'workflow_progress': workflow_result.to_dict()
                }
            else:
                # 실패 로깅
                user_logger.log_generation_error(f"{workflow_result.step_name}: {workflow_result.message}")

                await self._handle_workflow_error(message, session, workflow_result)
                return {
                    'success': False,
                    'error': workflow_result.message,
                    'workflow_progress': workflow_result.to_dict()
                }

        except Exception as e:
            # 예외 로깅
            user_logger.log_generation_error(f"예외 발생: {str(e)}")

            self.logger.error(f"Workflow execution failed: {e}", exc_info=True)
            await self._handle_generation_error(message, session, str(e))
            return {'success': False, 'error': str(e)}

    async def _handle_workflow_success(
        self,
        message,
        session: TelegramSession,
        workflow_result: WorkflowProgress
    ):
        """워크플로우 성공 처리"""
        # 세션 상태 업데이트
        session.blog_generated = True
        session.state = ConversationState.COMPLETED

        # 상세 결과 메시지 생성
        results = workflow_result.results
        generation_data = results.get('generation', {})
        quality_data = results.get('quality', {})
        upload_data = results.get('upload', {})

        length = generation_data.get('length', '알 수 없음')
        quality_score = quality_data.get('overall_score', 0)
        quality_grade = quality_data.get('grade', '알 수 없음')
        quality_warning = quality_data.get('quality_warning')
        quality_issues = quality_data.get('issues', [])

        success_msg = f"""
🎉 **블로그 자동화 완료!**

📝 **생성 결과:**
• 글자 수: {length}자
• 품질 점수: {quality_score:.2f} ({quality_grade})

📊 **품질 세부 점수:**
• 네이버 정책 준수: {quality_data.get('detailed_scores', {}).get('naver_compliance', 0):.2f}
• 키워드 품질: {quality_data.get('detailed_scores', {}).get('keyword_quality', 0):.2f}
• 개인 경험 진정성: {quality_data.get('detailed_scores', {}).get('personal_authenticity', 0):.2f}
• 기술적 품질: {quality_data.get('detailed_scores', {}).get('technical_quality', 0):.2f}
"""

        if upload_data and upload_data.get('success'):
            draft_saved = upload_data.get('draft_saved', True)
            image_ok = upload_data.get('image_included_success', True)
            missing_count = upload_data.get('image_missing_count', 0)
            uploaded_count = upload_data.get('image_uploaded_count', 0)
            requested_count = upload_data.get('image_requested_count', 0)

            if draft_saved and image_ok:
                success_msg += "\n✅ **네이버 임시저장:** 성공 (이미지 포함)"
            elif draft_saved:
                success_msg += (
                    f"\n⚠️ **네이버 임시저장:** 성공 (텍스트 저장, 이미지 누락 {missing_count}장)"
                    f"\n• 이미지 상태: {uploaded_count}/{requested_count}장 포함"
                )
            else:
                success_msg += "\n❌ **네이버 임시저장:** 실패"
        elif upload_data:
            error_code = upload_data.get('error_code', '')
            error_detail = upload_data.get('error', '알 수 없는 오류')

            if error_code == 'ENV_NO_XSERVER':
                success_msg += "\n❌ **네이버 임시저장:** 실패 (환경 설정: XServer 없음)"
                success_msg += "\n• 해결: HEADLESS=true 또는 xvfb-run -a 사용"
            elif error_code == 'PLAYWRIGHT_LAUNCH_FAILED':
                success_msg += "\n❌ **네이버 임시저장:** 실패 (브라우저 실행 오류)"
                success_msg += "\n• 해결: npx playwright install chromium"
            elif error_code == 'NAVER_AUTH_FAILED':
                success_msg += "\n❌ **네이버 임시저장:** 실패 (로그인/세션 만료)"
                success_msg += "\n• 해결: 네이버 로그인 세션 갱신 필요"
            elif error_code == 'NETWORK_DNS':
                success_msg += "\n❌ **네이버 임시저장:** 실패 (네트워크 오류)"
                success_msg += "\n• 해결: 인터넷 연결 확인"
            else:
                success_msg += f"\n❌ **네이버 임시저장:** 실패"
                success_msg += f"\n• 원인: {error_detail[:200]}"

            if upload_data.get('manual_instruction'):
                success_msg += f"\n💡 {upload_data['manual_instruction']}"

        if quality_warning:
            success_msg += f"\n\n⚠️ **품질 경고:** {quality_warning}"
            if quality_issues:
                success_msg += f"\n• 개선 포인트: {quality_issues[0]}"

        success_msg += f"\n📁 **저장 위치:** {Path(session.date_directory).name if session.date_directory else '알 수 없음'}"

        # 안전한 메시지 전송
        from src.telegram.utils.message_formatter import safe_reply_text_async
        await safe_reply_text_async(message, success_msg, parse_mode='Markdown')

        self.logger.info(f"Workflow successful for user {session.user_id}")

        # 세션 정리
        await self._cleanup_session(session)

    async def _handle_workflow_error(
        self,
        message,
        session: TelegramSession,
        workflow_result: WorkflowProgress
    ):
        """워크플로우 실패 처리"""
        error_msg = (
            f"❌ 블로그 자동화 실패\n\n"
            f"실패 단계: {workflow_result.step_name}\n"
            f"오류 내용: {workflow_result.message}\n\n"
            "아래 '완료하기' 버튼으로 다시 시도하세요."
        )

        await message.reply_text(
            error_msg,
            reply_markup=self.responses.create_generation_keyboard()
        )
        self.logger.error(f"Workflow failed for user {session.user_id}: {workflow_result.message}")

        # 세션은 유지하여 재시도 가능하도록 함
        session.state = ConversationState.READY_TO_GENERATE
        update_session(session)

    async def _handle_generation_error(
        self,
        message,
        session: TelegramSession,
        error_msg: str
    ):
        """생성 실패 처리"""
        await message.reply_text(
            self.responses.generation_failed(error_msg),
            reply_markup=self.responses.create_generation_keyboard()
        )
        self.logger.error(f"Blog generation failed for user {session.user_id}: {error_msg}")

        # 세션은 유지하여 재시도 가능하도록 함
        session.state = ConversationState.READY_TO_GENERATE
        update_session(session)

    async def _cleanup_session(self, session: TelegramSession):
        """세션 정리"""
        await self.image_handler.cleanup_temp_files(session.user_id)
        delete_session(session.user_id)


class SessionManagementService:
    """세션 관리 서비스"""

    def __init__(self, image_handler: ImageHandler):
        self.image_handler = image_handler
        self.responses = ResponseTemplates()
        self.logger = logging.getLogger(__name__)

    async def validate_session_for_generation(
        self,
        update,
        session: Optional[TelegramSession]
    ) -> bool:
        """생성을 위한 세션 검증"""
        if not session:
            await update.message.reply_text(self.responses.no_active_session())
            return False

        # 필수 필드 검증
        missing_fields = session.get_missing_fields()
        if missing_fields:
            await update.message.reply_text(self.responses.missing_fields(missing_fields))
            return False

        return True

    async def cleanup_user_session(self, user_id: int) -> bool:
        """사용자 세션 정리"""
        try:
            await self.image_handler.cleanup_temp_files(user_id)
            delete_session(user_id)
            return True
        except Exception as e:
            self.logger.error(f"Failed to cleanup session for user {user_id}: {e}")
            return False


class MaintenanceService:
    """유지보수 서비스"""

    def __init__(self, image_handler: ImageHandler, session_timeout: int):
        self.image_handler = image_handler
        self.session_timeout = session_timeout
        self.logger = logging.getLogger(__name__)

    async def run_periodic_cleanup(self):
        """주기적 정리 작업"""
        try:
            # 만료된 세션 정리
            from .models.session import cleanup_expired_sessions
            cleaned_count = cleanup_expired_sessions(self.session_timeout)

            if cleaned_count > 0:
                self.logger.info(f"Cleaned up {cleaned_count} expired sessions")

            # 오래된 임시 파일 정리
            from .constants import TEMP_FILE_CLEANUP_HOURS
            await self.image_handler.cleanup_old_temp_files(TEMP_FILE_CLEANUP_HOURS)

        except Exception as e:
            self.logger.error(f"Error in periodic cleanup: {e}")
            raise  # Re-raise to be handled by caller
