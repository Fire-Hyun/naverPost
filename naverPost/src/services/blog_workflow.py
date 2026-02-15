"""
블로그 생성부터 네이버 임시저장까지의 통합 워크플로우 서비스
"""

import asyncio
import logging
import subprocess
import json
import inspect
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from src.storage.data_manager import data_manager
from src.content.blog_generator import DateBasedBlogGenerator
from src.quality.unified_scorer import UnifiedQualityScorer
from src.config.settings import Settings
from src.services.quality import BlogQualityVerifier
from src.services.generation import BlogContentManager
from src.services.browser import BrowserSessionManager, BrowserCleanupService


class WorkflowStatus(Enum):
    """워크플로우 진행 상태"""
    PENDING = "pending"
    VALIDATING = "validating"
    GENERATING_BLOG = "generating_blog"
    QUALITY_CHECKING = "quality_checking"
    UPLOADING_TO_NAVER = "uploading_to_naver"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ValidationResult(Enum):
    """검증 결과"""
    VALID = "valid"
    INVALID_DATA = "invalid_data"
    MISSING_REQUIRED = "missing_required"
    QUALITY_ISSUE = "quality_issue"


@dataclass
class WorkflowStepResult:
    """워크플로우 단계 결과"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class WorkflowProgress:
    """워크플로우 진행 상황"""
    status: WorkflowStatus
    current_step: int
    total_steps: int
    step_name: str
    message: str
    progress_percentage: float = 0.0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    results: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리 형태로 변환 (API 응답용)"""
        return {
            "status": self.status.value,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "step_name": self.step_name,
            "message": self.message,
            "progress_percentage": self.progress_percentage,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "results": self.results
        }


class BlogWorkflowService:
    """블로그 생성부터 네이버 임시저장까지 통합 워크플로우 서비스"""

    def __init__(self):
        self.data_manager = data_manager
        self.blog_generator = DateBasedBlogGenerator()
        self.quality_scorer = UnifiedQualityScorer()
        self.settings = Settings
        self.logger = logging.getLogger(__name__)

        # 워크플로우 설정
        self.TOTAL_STEPS = 5
        self.MIN_QUALITY_SCORE = self._normalize_score_threshold(
            getattr(self.settings, "MIN_QUALITY_SCORE", 0.7)
        )
        self.QUALITY_SOFT_FAIL_MARGIN = self._normalize_margin(
            getattr(self.settings, "QUALITY_SOFT_FAIL_MARGIN", 0.1)
        )
        self.SOFT_MIN_QUALITY_SCORE = max(0.0, self.MIN_QUALITY_SCORE - self.QUALITY_SOFT_FAIL_MARGIN)

        # 품질 검증 서비스 초기화
        self.quality_verifier = BlogQualityVerifier(
            quality_scorer=self.quality_scorer,
            data_manager=self.data_manager,
            settings=self.settings
        )

        # naver-poster 설정 (다른 컴포넌트보다 먼저 설정)
        self.naver_poster_path = Path(self.settings.PROJECT_ROOT / "naver-poster")
        self.naver_poster_cli = self.naver_poster_path / "src" / "cli" / "post_to_naver.ts"

        # 블로그 생성 관리자 초기화
        self.content_manager = BlogContentManager(
            blog_generator=self.blog_generator,
            data_manager=self.data_manager,
            settings=self.settings
        )

        # 브라우저 세션 관리자 초기화
        self.browser_session_manager = BrowserSessionManager(
            naver_poster_path=self.naver_poster_path,
            settings=self.settings
        )
        self.browser_cleanup_service = BrowserCleanupService(
            session_manager=self.browser_session_manager
        )

    @staticmethod
    def _normalize_score_threshold(raw_value: Any) -> float:
        """점수 임계값을 0~1 범위로 정규화."""
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return 0.7

        # 70 형태(0~100 스케일)도 허용
        if value > 1.0:
            value = value / 100.0

        return max(0.0, min(1.0, value))

    @staticmethod
    def _normalize_margin(raw_value: Any) -> float:
        """soft fail margin 정규화."""
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return 0.1
        return max(0.0, min(0.3, value))

    async def process_complete_workflow(
        self,
        date_directory: str,
        user_experience: Dict[str, Any],
        images: Optional[List[Any]] = None,
        auto_upload: bool = True,
        progress_callback: Optional[Callable[[WorkflowProgress], None]] = None
    ) -> WorkflowProgress:
        """
        완전한 워크플로우 실행

        Args:
            date_directory: 날짜 기반 디렉토리명 (yyyyMMdd 형식)
            user_experience: 사용자 경험 데이터
            images: 업로드할 이미지 파일들
            auto_upload: 네이버 자동 업로드 여부
            progress_callback: 진행상황 콜백 함수

        Returns:
            WorkflowProgress: 최종 워크플로우 결과
        """
        progress = WorkflowProgress(
            status=WorkflowStatus.PENDING,
            current_step=0,
            total_steps=self.TOTAL_STEPS,
            step_name="시작",
            message="워크플로우를 시작합니다..."
        )

        try:
            # 실제 작업에 사용할 디렉토리명 (세션 준비 단계에서 확정)
            active_directory = date_directory

            # Step 1: 데이터 검증
            await self._update_progress(progress, 1, WorkflowStatus.VALIDATING,
                                     "데이터 검증", "입력 데이터를 검증하고 있습니다...",
                                     progress_callback)

            validation_result = await self._validate_input_data(date_directory, user_experience, images)
            if not validation_result.success:
                progress.status = WorkflowStatus.FAILED
                progress.message = f"데이터 검증 실패: {validation_result.error}"
                await self._invoke_progress_callback(progress_callback, progress)
                return progress

            progress.results['validation'] = validation_result.data

            # Step 2: 포스팅 세션 생성 및 이미지 처리
            await self._update_progress(progress, 2, WorkflowStatus.GENERATING_BLOG,
                                     "데이터 준비", "포스팅 데이터를 준비하고 있습니다...",
                                     progress_callback)

            session_result = await self._prepare_posting_session(date_directory, user_experience, images)
            if not session_result.success:
                progress.status = WorkflowStatus.FAILED
                progress.message = f"데이터 준비 실패: {session_result.error}"
                await self._invoke_progress_callback(progress_callback, progress)
                return progress

            progress.results['session'] = session_result.data
            active_directory = session_result.data.get('directory', date_directory) if session_result.data else date_directory

            # Step 3: AI 블로그 생성
            await self._update_progress(progress, 3, WorkflowStatus.GENERATING_BLOG,
                                     "블로그 생성", "AI를 사용하여 블로그를 생성하고 있습니다...",
                                     progress_callback)

            generation_result = await self._generate_blog_content(active_directory)
            if not generation_result.success:
                progress.status = WorkflowStatus.FAILED
                progress.message = f"블로그 생성 실패: {generation_result.error}"
                await self._invoke_progress_callback(progress_callback, progress)
                return progress

            progress.results['generation'] = generation_result.data

            # Step 4: 품질 검증
            await self._update_progress(progress, 4, WorkflowStatus.QUALITY_CHECKING,
                                     "품질 검증", "생성된 블로그의 품질을 검증하고 있습니다...",
                                     progress_callback)

            quality_result = await self._verify_blog_quality(
                active_directory,
                user_experience,
                generation_result.data.get("blog_file") if generation_result.data else None
            )
            if not quality_result.success:
                progress.status = WorkflowStatus.FAILED
                progress.message = f"품질 검증 실패: {quality_result.error}"
                await self._invoke_progress_callback(progress_callback, progress)
                return progress

            progress.results['quality'] = quality_result.data

            # Step 5: 네이버 업로드 (선택적)
            if auto_upload:
                await self._update_progress(progress, 5, WorkflowStatus.UPLOADING_TO_NAVER,
                                         "네이버 업로드", "네이버 블로그에 임시저장하고 있습니다...",
                                         progress_callback)

                upload_result = await self._upload_to_naver(active_directory)
                if not upload_result.success:
                    # 업로드 실패는 치명적이지 않음 (수동 업로드 가능)
                    progress.results['upload'] = {
                        'success': False,
                        'error': upload_result.error,
                        'manual_instruction': f"수동 업로드가 필요합니다. 파일 위치: {active_directory}"
                    }
                else:
                    progress.results['upload'] = upload_result.data

            # 완료
            progress.status = WorkflowStatus.COMPLETED
            progress.end_time = datetime.now()
            progress.message = "모든 작업이 성공적으로 완료되었습니다!"

            await self._invoke_progress_callback(progress_callback, progress)

            return progress

        except Exception as e:
            self.logger.error(f"Workflow execution failed: {e}", exc_info=True)
            progress.status = WorkflowStatus.FAILED
            progress.end_time = datetime.now()
            progress.message = f"예상치 못한 오류가 발생했습니다: {str(e)}"

            await self._invoke_progress_callback(progress_callback, progress)

            return progress

    async def _validate_input_data(
        self,
        date_directory: str,
        user_experience: Dict[str, Any],
        images: Optional[List[Any]]
    ) -> WorkflowStepResult:
        """입력 데이터 검증"""
        try:
            validation_errors = []

            # 필수 필드 검증
            required_fields = ['category', 'personal_review', 'visit_date']
            for field in required_fields:
                if not user_experience.get(field):
                    validation_errors.append(f"필수 필드 '{field}'가 누락되었습니다")

            # 상호명 검증
            if not user_experience.get('store_name'):
                validation_errors.append("상호명이 누락되었습니다")

            # 날짜 형식 검증
            if date_directory:
                try:
                    datetime.strptime(date_directory, "%Y%m%d")
                except ValueError:
                    validation_errors.append("날짜 형식이 올바르지 않습니다 (YYYYMMDD)")

            # 감상평 길이 검증
            review = user_experience.get('personal_review', '')
            if len(review) < 50:
                validation_errors.append(f"감상평이 너무 짧습니다 (최소 50자, 현재 {len(review)}자)")

            # 이미지 검증
            if images is not None and len(images) == 0:
                validation_errors.append("최소 1장의 이미지가 필요합니다")

            # 카테고리 검증
            if user_experience.get('category') not in self.settings.SUPPORTED_CATEGORIES:
                validation_errors.append(f"지원하지 않는 카테고리입니다: {user_experience.get('category')}")

            if validation_errors:
                return WorkflowStepResult(
                    success=False,
                    message="데이터 검증 실패",
                    error="; ".join(validation_errors)
                )

            self.logger.info(f"Input data validation successful for {date_directory}")

            return WorkflowStepResult(
                success=True,
                message="데이터 검증 완료",
                data={
                    "validated_fields": list(user_experience.keys()),
                    "image_count": len(images) if images else 0,
                    "review_length": len(review)
                }
            )

        except Exception as e:
            self.logger.error(f"Data validation error: {e}")
            return WorkflowStepResult(
                success=False,
                message="검증 중 오류 발생",
                error=str(e)
            )

    async def _prepare_posting_session(
        self,
        date_directory: str,
        user_experience: Dict[str, Any],
        images: Optional[List[Any]]
    ) -> WorkflowStepResult:
        """포스팅 세션 준비"""
        try:
            # 포스팅 세션 생성
            actual_directory = self.data_manager.create_posting_session(
                date_directory,
                user_experience
            )

            # 이미지 저장
            saved_image_count = 0
            if images:
                self.data_manager.save_uploaded_images(actual_directory, images)
                saved_image_count = len(images)

            self.logger.info(f"Posting session created: {actual_directory}")

            return WorkflowStepResult(
                success=True,
                message="포스팅 세션 준비 완료",
                data={
                    "directory": actual_directory,
                    "saved_images": saved_image_count
                }
            )

        except Exception as e:
            self.logger.error(f"Posting session preparation failed: {e}")
            return WorkflowStepResult(
                success=False,
                message="포스팅 세션 준비 실패",
                error=str(e)
            )

    async def _generate_blog_content(self, date_directory: str) -> WorkflowStepResult:
        """AI 블로그 콘텐츠 생성 - 통합된 생성 관리자 사용"""

        # 통합된 블로그 생성 관리자 사용
        result = await self.content_manager.generate_blog_content(
            date_directory=date_directory,
            force_regenerate=False
        )

        # BlogGenerationResult를 WorkflowStepResult로 변환하여 기존 호환성 유지
        return WorkflowStepResult(
            success=result.success,
            message=result.message,
            data=result.data,
            error=result.error
        )

    async def _regenerate_blog_content(self, date_directory: str) -> WorkflowStepResult:
        """품질 기준 미달로 인한 AI 블로그 콘텐츠 재생성 - 통합된 생성 관리자 사용"""

        # 통합된 블로그 생성 관리자 사용
        result = await self.content_manager.generate_blog_content(
            date_directory=date_directory,
            force_regenerate=True
        )

        # BlogGenerationResult를 WorkflowStepResult로 변환하여 기존 호환성 유지
        return WorkflowStepResult(
            success=result.success,
            message=result.message,
            data=result.data,
            error=result.error
        )

    async def _verify_blog_quality(
        self,
        date_directory: str,
        user_experience: Dict[str, Any],
        blog_file_override: Optional[str] = None
    ) -> WorkflowStepResult:
        """생성된 블로그 품질 검증 (품질 미달 시 최대 5번까지 재생성) - 리팩토링된 서비스 사용"""

        # 새로운 품질 검증 서비스 사용
        result = await self.quality_verifier.verify_blog_quality(
            date_directory=date_directory,
            user_experience=user_experience,
            blog_file_override=blog_file_override
        )

        # QualityVerificationResult를 WorkflowStepResult로 변환하여 기존 호환성 유지
        return WorkflowStepResult(
            success=result.success,
            message=result.message,
            data=result.data,
            error=result.error
        )

    async def _cleanup_browser_session(self):
        """브라우저 세션 강제 정리 - 리팩토링된 서비스 사용"""
        try:
            # 새로운 브라우저 정리 서비스 사용
            result = await self.browser_cleanup_service.cleanup_browser_session(wait_seconds=2.0)

            if result.success:
                self.logger.info(
                    f"Browser cleanup successful: killed {len(result.processes_killed)} processes, "
                    f"cleaned {len(result.directories_cleaned)} directories"
                )
            else:
                self.logger.warning(f"Browser cleanup had issues: errors={len(result.errors)}, warnings={len(result.warnings)}")

            # 경고나 에러가 있으면 로그에 기록
            for warning in result.warnings:
                self.logger.warning(f"Browser cleanup warning: {warning}")

            for error in result.errors:
                self.logger.error(f"Browser cleanup error: {error}")

        except Exception as e:
            self.logger.error(f"Browser cleanup service error: {e}")

    async def _upload_to_naver(self, date_directory: str) -> WorkflowStepResult:
        """네이버 블로그 임시저장"""
        try:
            if not self.naver_poster_cli.exists():
                return WorkflowStepResult(
                    success=False,
                    message="네이버 업로드 실패",
                    error="naver-poster CLI를 찾을 수 없습니다"
                )

            # 날짜 문자열(yyyyMMdd) 또는 실제 디렉토리명(yyyyMMdd(상호명)) 모두 허용
            data_path = self.data_manager.date_manager.get_directory_path(date_directory)
            if not data_path:
                data_path = Path(self.settings.DATA_DIR) / date_directory

            # subprocess cwd가 naver-poster이므로, 상대경로는 프로젝트 루트 기준 절대경로로 고정
            data_path = Path(data_path)
            if not data_path.is_absolute():
                data_path = (Path(self.settings.PROJECT_ROOT) / data_path).resolve()
            else:
                data_path = data_path.resolve()

            if not data_path.exists():
                return WorkflowStepResult(
                    success=False,
                    message="네이버 업로드 실패",
                    error=f"데이터 디렉토리를 찾을 수 없습니다: {data_path}"
                )

            # naver-poster 실행
            cmd = [
                "npx", "tsx", str(self.naver_poster_cli),
                "--dir", str(data_path),
            ]

            self.logger.info(f"Executing naver-poster: {' '.join(cmd)}")

            # 비동기 subprocess 실행
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.naver_poster_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                self.logger.info(f"Naver upload successful for {date_directory}")

                return WorkflowStepResult(
                    success=True,
                    message="네이버 임시저장 완료",
                    data={
                        "directory": date_directory,
                        "output": stdout.decode('utf-8') if stdout else "",
                        "upload_time": datetime.now().isoformat()
                    }
                )
            else:
                error_output = stderr.decode('utf-8') if stderr else "알 수 없는 오류"
                self.logger.error(f"Naver upload failed: {error_output}")

                # 실패 시 브라우저 세션 정리
                await self._cleanup_browser_session()

                return WorkflowStepResult(
                    success=False,
                    message="네이버 업로드 실패",
                    error=f"업로드 프로세스 실패: {error_output}"
                )

        except Exception as e:
            self.logger.error(f"Naver upload error: {e}")

            # 예외 발생 시에도 브라우저 세션 정리
            await self._cleanup_browser_session()

            return WorkflowStepResult(
                success=False,
                message="네이버 업로드 중 오류 발생",
                error=str(e)
            )

    async def _update_progress(
        self,
        progress: WorkflowProgress,
        step: int,
        status: WorkflowStatus,
        step_name: str,
        message: str,
        callback: Optional[Callable[[WorkflowProgress], None]]
    ):
        """진행상황 업데이트"""
        progress.current_step = step
        progress.status = status
        progress.step_name = step_name
        progress.message = message
        progress.progress_percentage = (step / progress.total_steps) * 100

        self.logger.info(f"Workflow step {step}/{progress.total_steps}: {step_name} - {message}")

        await self._invoke_progress_callback(callback, progress)

    async def _invoke_progress_callback(
        self,
        callback: Optional[Callable[[WorkflowProgress], None]],
        progress: WorkflowProgress
    ) -> None:
        """콜백이 async/sync 어느 타입이든 안전하게 실행"""
        if not callback:
            return

        callback_result = callback(progress)
        if inspect.isawaitable(callback_result):
            await callback_result

    def _resolve_blog_file_path(self, date_directory: str) -> Optional[str]:
        """date_directory 기준 blog_result.md 실제 경로를 안전하게 해석"""
        try:
            target_dir = self.data_manager.date_manager.get_directory_path(date_directory)
            if not target_dir:
                target_dir = Path(self.settings.DATA_DIR) / date_directory

            blog_file = target_dir / "blog_result.md"
            if blog_file.exists():
                return str(blog_file)
            return None
        except Exception:
            return None

    def cancel_workflow(self, progress: WorkflowProgress):
        """워크플로우 취소"""
        progress.status = WorkflowStatus.CANCELLED
        progress.end_time = datetime.now()
        progress.message = "사용자에 의해 취소되었습니다"

        self.logger.info("Workflow cancelled by user")


# 전역 인스턴스
_workflow_service: Optional[BlogWorkflowService] = None


def get_blog_workflow_service() -> BlogWorkflowService:
    """전역 BlogWorkflowService 인스턴스 반환"""
    global _workflow_service
    if _workflow_service is None:
        _workflow_service = BlogWorkflowService()
    return _workflow_service
