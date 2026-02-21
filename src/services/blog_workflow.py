"""
블로그 생성부터 네이버 임시저장까지의 통합 워크플로우 서비스
"""

import asyncio
import logging
import subprocess
import json
import inspect
import random
import os
import time
import shutil
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
from src.services.naver_map_service import NaverMapService


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
        self.NAVER_UPLOAD_TIMEOUT_SECONDS = self._normalize_timeout(
            os.getenv("NAVER_UPLOAD_TIMEOUT_SECONDS"),
            default=420,
            min_value=60,
            max_value=1800,
        )
        self.NAVER_STEP_TIMEOUT_SECONDS = self._normalize_timeout(
            os.getenv("NAVER_STEP_TIMEOUT_SECONDS"),
            default=45,
            min_value=20,
            max_value=300,
        )
        self.NAVER_SESSION_PREFLIGHT_TIMEOUT_SECONDS = self._normalize_timeout(
            os.getenv("NAVER_SESSION_PREFLIGHT_TIMEOUT_SECONDS"),
            default=90,
            min_value=30,
            max_value=300,
        )
        self.NAVER_AUTOLOGIN_TIMEOUT_SECONDS = self._normalize_timeout(
            os.getenv("NAVER_AUTOLOGIN_TIMEOUT_SECONDS"),
            default=120,
            min_value=20,
            max_value=600,
        )

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

    @staticmethod
    def _normalize_timeout(
        raw_value: Any,
        default: int,
        min_value: int,
        max_value: int
    ) -> int:
        """subprocess timeout 정규화."""
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return default
        return max(min_value, min(max_value, value))

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

        # 단계별 타이밍 계측
        step_timings: Dict[str, float] = {}
        workflow_start = time.monotonic()

        try:
            # 실제 작업에 사용할 디렉토리명 (세션 준비 단계에서 확정)
            active_directory = date_directory

            # Step 1: 데이터 검증
            step_t0 = time.monotonic()
            await self._update_progress(progress, 1, WorkflowStatus.VALIDATING,
                                     "데이터 검증", "입력 데이터를 검증하고 있습니다...",
                                     progress_callback)

            validation_result = await self._validate_input_data(date_directory, user_experience, images)
            step_timings["1_validation"] = time.monotonic() - step_t0
            if not validation_result.success:
                progress.status = WorkflowStatus.FAILED
                progress.message = f"데이터 검증 실패: {validation_result.error}"
                await self._invoke_progress_callback(progress_callback, progress)
                return progress

            progress.results['validation'] = validation_result.data

            # Step 2: 포스팅 세션 생성 및 이미지 처리
            step_t0 = time.monotonic()
            await self._update_progress(progress, 2, WorkflowStatus.GENERATING_BLOG,
                                     "데이터 준비", "포스팅 데이터를 준비하고 있습니다...",
                                     progress_callback)

            session_result = await self._prepare_posting_session(date_directory, user_experience, images)
            step_timings["2_session_prepare"] = time.monotonic() - step_t0
            if not session_result.success:
                progress.status = WorkflowStatus.FAILED
                progress.message = f"데이터 준비 실패: {session_result.error}"
                await self._invoke_progress_callback(progress_callback, progress)
                return progress

            progress.results['session'] = session_result.data
            active_directory = session_result.data.get('directory', date_directory) if session_result.data else date_directory

            # Step 2.5: 위치 정보 조회 (실패해도 계속 진행)
            step_t0 = time.monotonic()
            await self._fetch_location_info(active_directory, user_experience)
            step_timings["2.5_location_lookup"] = time.monotonic() - step_t0

            # Step 3: AI 블로그 생성
            step_t0 = time.monotonic()
            await self._update_progress(progress, 3, WorkflowStatus.GENERATING_BLOG,
                                     "블로그 생성", "AI를 사용하여 블로그를 생성하고 있습니다...",
                                     progress_callback)

            generation_result = await self._generate_blog_content(active_directory)
            step_timings["3_ai_generation"] = time.monotonic() - step_t0
            if not generation_result.success:
                progress.status = WorkflowStatus.FAILED
                progress.message = f"블로그 생성 실패: {generation_result.error}"
                await self._invoke_progress_callback(progress_callback, progress)
                return progress

            progress.results['generation'] = generation_result.data

            # Step 4: 품질 검증
            step_t0 = time.monotonic()
            await self._update_progress(progress, 4, WorkflowStatus.QUALITY_CHECKING,
                                     "품질 검증", "생성된 블로그의 품질을 검증하고 있습니다...",
                                     progress_callback)

            quality_result = await self._verify_blog_quality(
                active_directory,
                user_experience,
                generation_result.data.get("blog_file") if generation_result.data else None
            )
            step_timings["4_quality_check"] = time.monotonic() - step_t0
            if not quality_result.success:
                progress.status = WorkflowStatus.FAILED
                progress.message = f"품질 검증 실패: {quality_result.error}"
                await self._invoke_progress_callback(progress_callback, progress)
                return progress

            progress.results['quality'] = quality_result.data

            # Step 5: 네이버 업로드 (선택적)
            if auto_upload:
                step_t0 = time.monotonic()
                await self._update_progress(progress, 5, WorkflowStatus.UPLOADING_TO_NAVER,
                                         "네이버 업로드", "네이버 블로그에 임시저장하고 있습니다...",
                                         progress_callback)

                upload_result = await self._upload_to_naver(
                    active_directory,
                    store_name=user_experience.get("store_name"),
                    region_hint=user_experience.get("region_hint") or user_experience.get("location"),
                )
                step_timings["5_naver_upload"] = time.monotonic() - step_t0
                if not upload_result.success:
                    progress.status = WorkflowStatus.FAILED
                    progress.end_time = datetime.now()
                    progress.results['upload'] = {
                        'success': False,
                        'error': upload_result.error,
                    }
                    progress.message = upload_result.message or "네이버 업로드 단계에서 오류가 발생했습니다."
                    await self._invoke_progress_callback(progress_callback, progress)
                    return progress

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

        finally:
            # 타이밍 리포트 출력
            total_elapsed = time.monotonic() - workflow_start
            step_timings["total"] = total_elapsed
            timing_parts = " | ".join(
                f"{name}={elapsed:.1f}s" for name, elapsed in step_timings.items()
            )
            self.logger.info(f"[timing] {timing_parts}")

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

    async def _fetch_location_info(
        self,
        date_directory: str,
        user_experience: Dict[str, Any],
    ) -> None:
        """
        상호명으로 위치 정보를 조회하여 AI 처리 데이터에 반영한다.
        실패해도 워크플로우를 중단하지 않는다.
        """
        store_name = user_experience.get("store_name")
        if not store_name:
            self.logger.info("No store_name provided, skipping location lookup")
            return

        try:
            naver_map = NaverMapService()
            # region_hint: user_experience에 location 정보가 있으면 활용
            region_hint = user_experience.get("location") or None
            location_detail = await naver_map.fetch_place_by_store_name(store_name, region_hint)

            if location_detail:
                self.logger.info(
                    f"Location found for '{store_name}': {location_detail.get('address', '')}"
                )
            else:
                self.logger.warning(f"Location not found for '{store_name}', proceeding without location")

            # user_experience에 location_detail 추가 (이후 save_ai_processing_data에서 반영됨)
            user_experience["location_detail"] = location_detail

            await naver_map.cleanup()

        except Exception as e:
            self.logger.warning(f"Location lookup failed for '{store_name}': {e}. Proceeding without location.")
            user_experience["location_detail"] = None

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

    async def _upload_to_naver(
        self,
        date_directory: str,
        store_name: Optional[str] = None,
        region_hint: Optional[Union[str, float]] = None,
    ) -> WorkflowStepResult:
        """네이버 블로그 임시저장"""
        try:
            if not self.naver_poster_cli.exists():
                return WorkflowStepResult(
                    success=False,
                    message="네이버 업로드 실패",
                    error="naver-poster CLI를 찾을 수 없습니다"
                )

            await self._ensure_naver_poster_cli_ready()

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

            adaptive_upload_timeout = self._estimate_naver_upload_timeout_seconds(data_path)
            self.logger.info(
                "Adaptive naver upload timeout selected",
                extra={
                    "directory": str(data_path),
                    "timeout_seconds": adaptive_upload_timeout,
                },
            )

            attempts = 3
            auth_retry_done = False
            last_error = "알 수 없는 오류"
            last_payload: Optional[Dict[str, Any]] = None
            last_stdout = ""
            last_stderr = ""

            for attempt in range(1, attempts + 1):
                cmd_args = ["--dir", str(data_path)]
                if isinstance(store_name, str) and store_name.strip():
                    cmd_args.extend(["--placeName", store_name.strip()])
                if isinstance(region_hint, str) and region_hint.strip():
                    cmd_args.extend(["--regionHint", region_hint.strip()])

                cmd = self._build_naver_poster_command(*cmd_args)
                self.logger.info(
                    "Executing naver-poster",
                    extra={"attempt": attempt, "total_attempts": attempts, "dir": str(data_path)}
                )

                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=str(self.naver_poster_path),
                    env=self._build_naver_poster_env(adaptive_upload_timeout),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=adaptive_upload_timeout
                    )
                except asyncio.TimeoutError:
                    self.logger.error(
                        f"Naver upload subprocess timeout after {adaptive_upload_timeout}s "
                        f"(attempt {attempt}/{attempts})"
                    )
                    process.kill()
                    try:
                        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
                    except asyncio.TimeoutError:
                        stdout, stderr = b"", b""
                    timeout_msg = (
                        f"[TIMEOUT] naver-poster subprocess exceeded "
                        f"{adaptive_upload_timeout}s"
                    )
                    stderr = (stderr or b"") + f"\n{timeout_msg}\n".encode("utf-8")
                stdout_str = stdout.decode('utf-8', errors='replace') if stdout else ""
                stderr_str = stderr.decode('utf-8', errors='replace') if stderr else ""
                report = self._extract_naver_post_report(stdout_str, stderr_str)

                last_stdout = stdout_str
                last_stderr = stderr_str
                last_payload = report
                last_error = stderr_str or stdout_str or "알 수 없는 오류"

                draft_success = False
                image_status = "unknown"
                if report:
                    draft_success = bool(report.get("draft_summary", {}).get("success"))
                    image_status = str(report.get("image_summary", {}).get("status", "unknown"))
                elif process.returncode == 0:
                    draft_success = True
                    image_status = "unknown"

                # 임시저장 성공은 process returncode와 분리 판정
                if draft_success:
                    uploaded_count = int(report.get("image_summary", {}).get("uploaded_count", 0)) if report else 0
                    missing_count = int(report.get("image_summary", {}).get("missing_count", 0)) if report else 0
                    requested_count = int(report.get("image_summary", {}).get("requested_count", 0)) if report else 0
                    image_refs = report.get("image_summary", {}).get("sample_refs", []) if report else []

                    has_full_images = image_status in {"full", "not_requested"}
                    has_partial_images = image_status == "partial"
                    has_no_images = image_status == "none"
                    overall_status = str(report.get("overall_status", "")) if report else ""

                    message = "네이버 임시저장 완료"
                    if overall_status == "SUCCESS_WITH_IMAGE_VERIFY_WARNING":
                        message = "네이버 임시저장 완료 ⚠️ (이미지 참조 DOM 검증 경고: 업로드는 성공, 사후 DOM 확인 불가)"
                    elif has_partial_images:
                        message = "네이버 임시저장 완료 (이미지 일부 누락)"
                    elif has_no_images and requested_count > 0:
                        message = "네이버 임시저장 완료 (텍스트만 저장됨)"

                    self.logger.info(
                        "Naver draft result",
                        extra={
                            "draft_success": draft_success,
                            "image_status": image_status,
                            "requested_count": requested_count,
                            "uploaded_count": uploaded_count,
                            "missing_count": missing_count,
                            "attempt": attempt,
                        },
                    )

                    return WorkflowStepResult(
                        success=True,
                        message=message,
                        data={
                            "success": True,
                            "directory": date_directory,
                            "upload_time": datetime.now().isoformat(),
                            "draft_saved": True,
                            "image_status": image_status,
                            "image_requested_count": requested_count,
                            "image_uploaded_count": uploaded_count,
                            "image_missing_count": missing_count,
                            "image_included_success": has_full_images,
                            "image_partial": has_partial_images,
                            "image_none": has_no_images,
                            "image_refs_sample": image_refs,
                            "pipeline_report": report,
                            "output": stdout_str[-4000:],
                            "stderr": stderr_str[-2000:] if stderr_str else None,
                        }
                    )

                # CAPTCHA 차단 감지: storageState 백업 후 즉시 중단 (autoLogin 재시도 대상 아님)
                captcha_error = self._is_captcha_error(stderr_str, stdout_str, report)
                if captcha_error:
                    self.logger.error(
                        "CAPTCHA 차단 감지 - storageState 백업 후 재시도 중단 "
                        f"(attempt {attempt}/{attempts})"
                    )
                    self._backup_invalid_storage_state()
                    break

                # 인증 실패 시 1회 자동 로그인 재시도 (CAPTCHA 아닌 경우만)
                auth_error = self._is_authentication_error(stderr_str, stdout_str, report)
                if auth_error and not auth_retry_done:
                    auth_retry_done = True
                    self.logger.warning("Authentication issue detected. Trying auto-login once before retry.")
                    relogin_ok = await self._attempt_naver_relogin()
                    if relogin_ok:
                        continue

                transient_error = self._is_transient_naver_failure(stderr_str, stdout_str, report)
                client_hang = self._is_client_hang_failure(stderr_str, stdout_str, report)
                if client_hang:
                    self.logger.error(
                        "Client-side hang/step-timeout detected in naver-poster. "
                        "Skipping retries and failing fast."
                    )
                    break
                if transient_error and attempt < attempts:
                    wait_seconds = (2 ** (attempt - 1)) + random.uniform(0.2, 0.9)
                    self.logger.warning(
                        f"Transient naver upload failure (attempt {attempt}/{attempts}), "
                        f"retrying in {wait_seconds:.2f}s"
                    )
                    await asyncio.sleep(wait_seconds)
                    continue

                break

            self.logger.error(f"Naver upload failed: {last_error}")

            # 실패 시 브라우저 세션 정리
            await self._cleanup_browser_session()

            # 에러 분류
            error_code = self._classify_upload_error(last_stderr, last_stdout)
            user_message = self._get_error_user_message(error_code, last_error[:500])

            return WorkflowStepResult(
                success=False,
                message=user_message,
                error=f"[{error_code}] 업로드 프로세스 실패: {last_error[:1000]}",
                data={
                    "pipeline_report": last_payload,
                    "error_code": error_code,
                    "output": last_stdout[-4000:] if last_stdout else "",
                    "stderr": last_stderr[-2000:] if last_stderr else "",
                }
            )

        except Exception as e:
            self.logger.error(f"Naver upload error: {e}")

            # 예외 발생 시에도 브라우저 세션 정리
            await self._cleanup_browser_session()

            # 예외 에러도 분류
            error_str = str(e)
            error_code = self._classify_upload_error(error_str, "")
            user_message = self._get_error_user_message(error_code, error_str[:500])

            return WorkflowStepResult(
                success=False,
                message=user_message,
                error=f"[{error_code}] {error_str}"
            )

    def _extract_naver_post_report(self, stdout: str, stderr: str) -> Optional[Dict[str, Any]]:
        marker = "NAVER_POST_RESULT_JSON:"
        for chunk in (stdout, stderr):
            if marker not in chunk:
                continue
            for line in chunk.splitlines():
                if marker not in line:
                    continue
                raw = line.split(marker, 1)[1].strip()
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    continue
        return None

    def _is_captcha_error(
        self,
        stderr: str,
        stdout: str,
        report: Optional[Dict[str, Any]]
    ) -> bool:
        """CAPTCHA/보안문자 차단 감지 (autoLogin 재시도 대상에서 제외)"""
        haystack = f"{stderr}\n{stdout}".lower()
        captcha_patterns = [
            "captcha_detected",
            "captcha",
            "보안문자",
            "blocked_url=https://nid.naver.com",
            "로그인 차단 신호",
            "nidlogin.login",
        ]
        return any(p in haystack for p in captcha_patterns)

    def _backup_invalid_storage_state(self) -> Optional[str]:
        """CAPTCHA 차단된 storageState를 .invalid.<ts>.json으로 이름 변경/격리"""
        storage_state_path = (
            Path(self.settings.PROJECT_ROOT)
            / "naver-poster" / ".secrets" / "naver_user_data_dir"
            / "session_storage_state.json"
        )
        if not storage_state_path.exists():
            return None
        try:
            ts = datetime.now().strftime("%Y%m%dT%H%M%S")
            backup_path = Path(str(storage_state_path.with_suffix('')) + f".invalid.{ts}.json")
            storage_state_path.rename(backup_path)
            self.logger.warning(f"CAPTCHA: storageState 백업/격리 완료: {backup_path}")
            return str(backup_path)
        except Exception as exc:
            self.logger.warning(f"storageState 백업 실패: {exc}")
            return None

    def _is_authentication_error(
        self,
        stderr: str,
        stdout: str,
        report: Optional[Dict[str, Any]]
    ) -> bool:
        haystack = f"{stderr}\n{stdout}".lower()
        # 콘텐츠 삽입/에디터 조작 오류는 인증 오류로 분류하지 않음
        non_auth_patterns = [
            "블록 순차 삽입 실패",
            "텍스트 블록 입력 실패",
            "본문 입력 실패",
            "제목 입력 실패",
            "body_input_failed",
            "title_input_failed",
            "place_attach",
            "장소 첨부 실패",
        ]
        if any(pattern.lower() in haystack for pattern in non_auth_patterns):
            return False

        auth_patterns = [
            "login",
            "로그인",
            "인증",
            "세션 만료",
            "storage state",
            "unauthorized",
            "forbidden",
        ]
        if any(pattern in haystack for pattern in auth_patterns):
            return True

        if report:
            step_f = report.get("steps", {}).get("F", {})
            message = str(step_f.get("message", "")).lower()
            if any(pattern in message for pattern in auth_patterns):
                return True
        return False

    def _classify_upload_error(self, stderr: str, stdout: str) -> Optional[str]:
        """업로드 에러를 환경/인증/네트워크/업로드 문제로 분류"""
        haystack = f"{stderr}\n{stdout}".lower()

        # CAPTCHA 차단 (최우선 분류: autoLogin 재시도와 구분)
        captcha_patterns = [
            "captcha_detected",
            "captcha",
            "보안문자",
            "blocked_url=https://nid.naver.com",
            "로그인 차단 신호",
        ]
        if any(p in haystack for p in captcha_patterns):
            return "NAVER_CAPTCHA_BLOCKED"

        # 로그인 재확인 단계 타임아웃은 별도 분류 (임시저장 대기 정체와 구분)
        login_recheck_timeout_patterns = [
            "stage=ensure_logged_in_before_draft",
            "stage_timeout_ensure_logged_in_before_draft",
            "ensure_logged_in_before_draft exceeded",
        ]
        if any(p in haystack for p in login_recheck_timeout_patterns):
            return "NAVER_LOGIN_RECHECK_TIMEOUT"

        # subprocess 전체 타임아웃/무응답 워치독/단계 타임아웃 => 클라이언트 hang
        client_hang_patterns = [
            "[timeout] naver-poster subprocess exceeded",
            "silence_watchdog",
            "stage_timeout_",
            "[stage_timeout]",
            "무응답 감지",
        ]
        if any(p in haystack for p in client_hang_patterns):
            return "NAVER_CLIENT_HANG"

        # EDITOR_NOT_CLEAN: 에디터에 이전 세션 잔존 이미지 감지
        editor_not_clean_patterns = [
            "editor_not_clean",
            "에디터 잔존 이미지 감지",
        ]
        if any(p.lower() in haystack for p in editor_not_clean_patterns):
            return "EDITOR_NOT_CLEAN"

        # 콘텐츠/에디터 삽입 실패는 인증보다 우선 분류
        content_insert_patterns = [
            "블록 순차 삽입 실패",
            "텍스트 블록 입력 실패",
            "본문 입력 실패",
            "제목 입력 실패",
            "body_input_failed",
            "title_input_failed",
            "장소 첨부 실패",
            "place_attach",
        ]
        if any(p.lower() in haystack for p in content_insert_patterns):
            return "EDITOR_INSERT_FAILED"

        # ENV_NO_XSERVER: XServer 없음 + headed 실행 시도
        xserver_patterns = [
            "xserver", "xvfb", "env_no_xserver",
            "headed browser without having a xserver",
            "target page, context or browser has been closed",
            "display", "headless: true",
        ]
        if any(p in haystack for p in xserver_patterns):
            # "headless: true" 단독은 오탐 가능 → closed와 함께일 때만
            if "browser has been closed" in haystack or "xserver" in haystack or "xvfb" in haystack or "env_no_xserver" in haystack:
                return "ENV_NO_XSERVER"

        # PLAYWRIGHT_LAUNCH_FAILED: 바이너리/권한/의존성
        launch_patterns = ["browsertype.launch", "executable doesn't exist", "permission denied", "no usable sandbox"]
        if any(p in haystack for p in launch_patterns):
            return "PLAYWRIGHT_LAUNCH_FAILED"

        # NAVER_AUTH_FAILED: 인증 문제
        auth_patterns = ["login", "로그인", "인증", "세션 만료", "unauthorized", "forbidden"]
        if any(p in haystack for p in auth_patterns):
            return "NAVER_AUTH_FAILED"

        # NAVER_RATE_LIMIT: 429
        if "429" in haystack or "too many" in haystack or "rate limit" in haystack:
            return "NAVER_RATE_LIMIT"

        # NETWORK_DNS: DNS/네트워크
        dns_patterns = ["dns", "resolve", "enotfound", "getaddrinfo"]
        if any(p in haystack for p in dns_patterns):
            return "NETWORK_DNS"

        # NAVER_UPLOAD_FAILED: 일반 업로드 실패
        return "NAVER_UPLOAD_FAILED"

    def _get_error_user_message(self, error_code: str, raw_error: str) -> str:
        """에러 코드에 따른 사용자 친화적 메시지 생성"""
        messages = {
            "EDITOR_NOT_CLEAN": (
                "❌ 네이버 임시저장 실패 (에디터 잔존 이미지)\n\n"
                "에디터에 이전 세션의 이미지가 남아있습니다.\n"
                "해결:\n"
                "  1. 네이버 블로그 임시저장 목록에서 해당 글을 삭제하세요.\n"
                "  2. 다시 시도해 주세요."
            ),
            "NAVER_CAPTCHA_BLOCKED": (
                "❌ 네이버 임시저장 실패 (CAPTCHA 차단)\n\n"
                "네이버가 자동 로그인을 CAPTCHA로 차단했습니다.\n"
                "세션이 무효화되어 자동으로 백업되었습니다.\n"
                "해결:\n"
                "  1. 서버에서 직접 로그인:\n"
                "     node dist/cli/post_to_naver.js --interactiveLogin\n"
                "  2. 로그인 완료 후 Enter\n"
                "  3. 잠시 후 다시 요청"
            ),
            "ENV_NO_XSERVER": (
                "❌ 네이버 임시저장 실패 (환경 설정 문제: XServer 없음)\n\n"
                "원인: headed 모드(HEADLESS=false)로 실행했으나 XServer가 없습니다.\n"
                "해결:\n"
                "  1. HEADLESS=true로 실행 (권장)\n"
                "  2. xvfb-run -a 로 실행\n"
                "참고: docs/naver_temp_save_troubleshooting.md"
            ),
            "PLAYWRIGHT_LAUNCH_FAILED": (
                "❌ 네이버 임시저장 실패 (브라우저 실행 오류)\n\n"
                "원인: Playwright 브라우저 바이너리/권한/의존성 문제\n"
                "해결: npx playwright install chromium 실행"
            ),
            "NAVER_AUTH_FAILED": (
                "❌ 네이버 임시저장 실패 (로그인/세션 만료)\n\n"
                "해결: 네이버 로그인 세션을 갱신하세요.\n"
                "  node dist/cli/post_to_naver.js --autoLogin"
            ),
            "NAVER_RATE_LIMIT": (
                "❌ 네이버 임시저장 실패 (요청 횟수 초과)\n\n"
                "잠시 후 다시 시도해 주세요."
            ),
            "NAVER_CLIENT_HANG": (
                "❌ 네이버 임시저장 실패 (클라이언트 대기/정체)\n\n"
                "원인: naver-poster 프로세스가 내부 단계에서 제한 시간 내 종료되지 않았습니다.\n"
                "서버 5xx가 아니라 자동화 단계 정체로 분류되었습니다.\n"
                "디버그: logs/<YYYYMMDD>/navertimeoutdebug/* 를 확인하세요."
            ),
            "NAVER_LOGIN_RECHECK_TIMEOUT": (
                "❌ 네이버 임시저장 실패 (로그인 재확인 타임아웃)\n\n"
                "원인: 임시저장 직전 로그인 재확인 단계(ensure_logged_in_before_draft)가 제한 시간 내 종료되지 않았습니다.\n"
                "임시저장 클릭/검증 단계 정체와는 별도 유형입니다.\n"
                "디버그: logs/<YYYYMMDD>/navertimeoutdebug/* 의 stage_timeout_ensure_logged_in_before_draft_* 리포트를 확인하세요."
            ),
            "NETWORK_DNS": (
                "❌ 네이버 임시저장 실패 (네트워크/DNS 오류)\n\n"
                "인터넷 연결을 확인하세요."
            ),
            "EDITOR_INSERT_FAILED": (
                "❌ 네이버 임시저장 실패 (에디터 입력/삽입 오류)\n\n"
                f"상세: {raw_error[:200]}\n"
                "같은 내용으로 다시 시도해 주세요. 반복되면 텍스트 길이/마커 형식을 점검해야 합니다."
            ),
            "NAVER_UPLOAD_FAILED": (
                "❌ 네이버 임시저장 실패 (업로드 프로세스 오류)\n\n"
                f"상세: {raw_error[:200]}\n"
                "수동 업로드가 필요할 수 있습니다."
            ),
        }
        return messages.get(error_code, f"❌ 네이버 임시저장 실패\n\n상세: {raw_error[:200]}")

    def _is_client_hang_failure(
        self,
        stderr: str,
        stdout: str,
        report: Optional[Dict[str, Any]]
    ) -> bool:
        haystack = f"{stderr}\n{stdout}".lower()
        direct_patterns = [
            "[timeout] naver-poster subprocess exceeded",
            "silence_watchdog",
            "stage_timeout_",
            "[stage_timeout]",
            "무응답 감지",
        ]
        if any(pattern in haystack for pattern in direct_patterns):
            return True

        if report:
            steps = report.get("steps", {})
            for key in ("C", "E", "F", "G"):
                message = str(steps.get(key, {}).get("message", "")).lower()
                if "stage_timeout" in message or "timeout" in message:
                    return True
        return False

    def _is_transient_naver_failure(
        self,
        stderr: str,
        stdout: str,
        report: Optional[Dict[str, Any]]
    ) -> bool:
        haystack = f"{stderr}\n{stdout}".lower()
        transient_patterns = [
            "timeout",
            "timed out",
            "econnreset",
            "econnrefused",
            "network",
            "429",
            "503",
            "502",
            "500",
            "temporar",
        ]
        if any(pattern in haystack for pattern in transient_patterns):
            return True

        if report:
            step_c = report.get("steps", {}).get("C", {})
            message = str(step_c.get("message", "")).lower()
            if "simulated_timeout" in message:
                return True

            attempts = step_c.get("data", {}).get("attempts", [])
            if isinstance(attempts, list):
                for entry in attempts:
                    if isinstance(entry, dict) and bool(entry.get("transient_failure")):
                        return True

        return False

    async def _attempt_naver_relogin(self) -> bool:
        try:
            cmd = self._build_naver_poster_command("--autoLogin")
            await self._ensure_naver_poster_cli_ready()
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(self.naver_poster_path),
                env=self._build_naver_poster_env(self.NAVER_AUTOLOGIN_TIMEOUT_SECONDS),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.NAVER_AUTOLOGIN_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                self.logger.warning(
                    f"Auto-login subprocess timeout after {self.NAVER_AUTOLOGIN_TIMEOUT_SECONDS}s"
                )
                process.kill()
                try:
                    await asyncio.wait_for(process.communicate(), timeout=5)
                except asyncio.TimeoutError:
                    pass
                return False
            stdout_str = stdout.decode('utf-8', errors='replace') if stdout else ""
            stderr_str = stderr.decode('utf-8', errors='replace') if stderr else ""

            if process.returncode == 0:
                self.logger.info("Auto-login succeeded before retry.")
                return True

            self.logger.warning(
                "Auto-login failed",
                extra={
                    "returncode": process.returncode,
                    "stdout": stdout_str[-800:],
                    "stderr": stderr_str[-800:],
                },
            )
            return False
        except Exception as exc:
            self.logger.warning(f"Auto-login attempt failed with exception: {exc}")
            return False

    def _build_naver_poster_command(self, *args: str) -> List[str]:
        """
        naver-poster 실행 커맨드 구성.
        우선순위:
        1) dist/cli/post_to_naver.js (빌드된 CLI)
        2) npx --no-install tsx src/cli/post_to_naver.ts
        """
        dist_cli = self.naver_poster_path / "dist" / "cli" / "post_to_naver.js"
        if dist_cli.exists():
            return ["node", str(dist_cli), *args]

        return ["npx", "--no-install", "tsx", str(self.naver_poster_cli), *args]

    def _build_naver_poster_env(self, upload_timeout_seconds: int) -> Dict[str, str]:
        env = os.environ.copy()
        # 운영 기본값: headless=true 명시 고정 (암묵적 변경 방지)
        env["HEADLESS"] = env.get("HEADLESS", "true")
        env["NAVER_STEP_TIMEOUT_SECONDS"] = str(self.NAVER_STEP_TIMEOUT_SECONDS)
        env["NAVER_SESSION_PREFLIGHT_TIMEOUT_SECONDS"] = str(self.NAVER_SESSION_PREFLIGHT_TIMEOUT_SECONDS)
        env["NAVER_UPLOAD_TIMEOUT_SECONDS"] = str(upload_timeout_seconds)
        # naver-poster 내부 워치독이 상위 타임아웃보다 먼저 동작하도록 보정
        process_watchdog = max(180, min(upload_timeout_seconds - 30, upload_timeout_seconds))
        env["NAVER_PROCESS_WATCHDOG_SECONDS"] = str(process_watchdog)
        # 업로드 볼륨이 큰 포스트를 위해 block insert 상한을 업로드 timeout에 비례해 확장
        insert_blocks_max = max(360, min(upload_timeout_seconds - 120, 1200))
        env["NAVER_INSERT_BLOCKS_TIMEOUT_MAX_SECONDS"] = str(insert_blocks_max)
        return env

    def _estimate_naver_upload_timeout_seconds(self, data_path: Path) -> int:
        """
        이미지 수 기반으로 naver 업로드 타임아웃을 동적으로 산정한다.
        이미지가 많을수록 실제 소요가 커서 고정 420s는 조기 종료를 유발할 수 있다.
        """
        image_count = 0
        images_dir = data_path / "images"
        if images_dir.exists():
            image_count = sum(1 for p in images_dir.iterdir() if p.is_file())

        # base 240s + per-image 45s + login/session 여유 60s
        estimated = 240 + (image_count * 45) + 60
        estimated = max(self.NAVER_UPLOAD_TIMEOUT_SECONDS, estimated)
        return min(estimated, 1800)

    async def _ensure_naver_poster_cli_ready(self) -> None:
        """
        dist CLI가 없거나 src보다 오래된 경우 자동 빌드한다.
        운영에서 TS 변경 후 구버전 dist를 실행하는 문제를 방지한다.
        """
        dist_cli = self.naver_poster_path / "dist" / "cli" / "post_to_naver.js"
        if not dist_cli.exists() or self._is_naver_poster_build_stale(dist_cli):
            self.logger.info("naver-poster dist is missing/stale. running npm run build...")
            build_cmd = ["npm", "run", "build"]
            if shutil.which("npm") is None:
                raise RuntimeError("npm is not available for building naver-poster")

            proc = await asyncio.create_subprocess_exec(
                *build_cmd,
                cwd=str(self.naver_poster_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                out = stdout.decode("utf-8", errors="replace")[-2000:]
                err = stderr.decode("utf-8", errors="replace")[-2000:]
                raise RuntimeError(
                    f"naver-poster build failed (code={proc.returncode})\nstdout:\n{out}\nstderr:\n{err}"
                )

    def _is_naver_poster_build_stale(self, dist_cli: Path) -> bool:
        try:
            dist_mtime = dist_cli.stat().st_mtime
        except FileNotFoundError:
            return True

        source_roots = [
            self.naver_poster_path / "src" / "cli",
            self.naver_poster_path / "src" / "naver",
            self.naver_poster_path / "src" / "utils",
        ]

        newest_src_mtime = 0.0
        for root in source_roots:
            if not root.exists():
                continue
            for ts_file in root.rglob("*.ts"):
                try:
                    newest_src_mtime = max(newest_src_mtime, ts_file.stat().st_mtime)
                except FileNotFoundError:
                    continue
        return newest_src_mtime > dist_mtime

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
