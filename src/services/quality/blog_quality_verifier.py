"""
Blog quality verification service
Extracted from BlogWorkflowService._verify_blog_quality method
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass

from .retry_manager import RetryManager, RetryAttempt
from .quality_threshold_manager import QualityThresholdManager

logger = logging.getLogger(__name__)


@dataclass
class QualityVerificationResult:
    """품질 검증 결과"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0


class BlogQualityVerifier:
    """블로그 품질 검증을 담당하는 서비스"""

    def __init__(self, quality_scorer, data_manager, settings):
        self.quality_scorer = quality_scorer
        self.data_manager = data_manager
        self.settings = settings

        # 구성 요소 초기화
        self.threshold_manager = QualityThresholdManager(settings)
        self.retry_manager = RetryManager(max_attempts=5)

        self.logger = logging.getLogger(__name__)

    async def verify_blog_quality(
        self,
        date_directory: str,
        user_experience: Dict[str, Any],
        blog_file_override: Optional[str] = None
    ) -> QualityVerificationResult:
        """
        생성된 블로그 품질 검증 (품질 미달 시 최대 5번까지 재생성)

        Args:
            date_directory: 날짜 디렉토리명
            user_experience: 사용자 경험 데이터
            blog_file_override: 블로그 파일 경로 오버라이드

        Returns:
            QualityVerificationResult: 품질 검증 결과
        """

        async def quality_check_operation(attempt: int) -> Dict[str, Any]:
            """품질 확인 작업 (재시도 가능한 단위)"""

            # 재생성이 필요한 경우 (첫 번째 시도가 아닐 때)
            if attempt > 0:
                regeneration_result = await self._regenerate_blog_content(date_directory)
                if not regeneration_result.success:
                    raise Exception(f"블로그 재생성 실패: {regeneration_result.error}")

            # 블로그 파일 경로 결정
            blog_file_path = self._resolve_blog_file_path(date_directory, blog_file_override)

            # 블로그 파일 존재 확인
            if not blog_file_path.exists():
                raise Exception("생성된 블로그 파일을 찾을 수 없습니다")

            # 블로그 콘텐츠 읽기
            with open(blog_file_path, 'r', encoding='utf-8') as f:
                blog_content = f.read()

            # 품질 점수 계산
            loop = asyncio.get_event_loop()
            quality_result = await loop.run_in_executor(
                None,
                self.quality_scorer.calculate_unified_score,
                blog_content,
                user_experience.get('personal_review', ''),
                [user_experience.get('store_name', ''), user_experience.get('category', '')],
                user_experience.get('category', '')
            )

            # 품질 결과 분석
            unified = quality_result.get('unified_score', {}) if isinstance(quality_result, dict) else {}
            component_scores = unified.get('component_scores', {})
            overall_score = float(unified.get('weighted_score', 0.0))
            quality_grade = str(unified.get('quality_grade', 'UNKNOWN'))

            # 피드백 정보 추출
            feedback = quality_result.get('real_time_feedback', {}) if isinstance(quality_result, dict) else {}
            issues = []
            issues.extend(feedback.get('priority_fixes', []) or [])
            issues.extend(feedback.get('improvement_suggestions', []) or [])
            # 순서 유지 중복 제거
            issues = list(dict.fromkeys([str(item).strip() for item in issues if str(item).strip()]))[:5]

            return {
                'overall_score': overall_score,
                'quality_grade': quality_grade,
                'component_scores': component_scores,
                'issues': issues,
                'attempt': attempt
            }

        def should_retry(result: Dict[str, Any]) -> bool:
            """재시도가 필요한지 판단"""
            if not isinstance(result, dict):
                return True

            overall_score = result.get('overall_score', 0.0)
            evaluation = self.threshold_manager.evaluate_quality_score(overall_score)

            # 통과하거나 soft pass면 재시도 불필요
            return not evaluation['passes_threshold']

        # 재시도 로직 실행
        try:
            retry_result = await self.retry_manager.execute_with_retry(
                quality_check_operation,
                should_retry,
                f"Quality verification for {date_directory}"
            )

            if retry_result.success and retry_result.result_data:
                result_data = retry_result.result_data
                overall_score = result_data['overall_score']

                # 임계값 평가
                evaluation = self.threshold_manager.evaluate_quality_score(overall_score)

                # 성공 결과 구성
                return QualityVerificationResult(
                    success=True,
                    message=evaluation['message'] + (f" ({retry_result.attempt_number}회 시도 후)" if retry_result.attempt_number > 1 else ""),
                    data={
                        'overall_score': overall_score,
                        'grade': result_data['quality_grade'],
                        'issues': result_data['issues'],
                        'retry_count': retry_result.attempt_number - 1,
                        'quality_warning': evaluation['message'] if evaluation['is_soft_pass'] else None,
                        'thresholds': self.threshold_manager.get_thresholds(),
                        'detailed_scores': {
                            'naver_compliance': float(result_data['component_scores'].get('naver_compliance', 0.0)),
                            'keyword_quality': float(result_data['component_scores'].get('keyword_quality', 0.0)),
                            'personal_authenticity': float(result_data['component_scores'].get('personal_authenticity', 0.0)),
                            'technical_quality': float(result_data['component_scores'].get('technical_quality', 0.0)),
                        }
                    },
                    retry_count=retry_result.attempt_number - 1
                )
            else:
                # 실패 결과
                return QualityVerificationResult(
                    success=False,
                    message="품질 검증 실패 - 최대 시도 횟수 초과",
                    error=retry_result.error,
                    retry_count=retry_result.attempt_number - 1
                )

        except Exception as e:
            self.logger.error(f"Quality verification error: {e}")
            return QualityVerificationResult(
                success=False,
                message="품질 검증 중 오류 발생",
                error=str(e)
            )

    def _resolve_blog_file_path(self, date_directory: str, blog_file_override: Optional[str]) -> Path:
        """블로그 파일 경로 해석"""
        if blog_file_override:
            return Path(blog_file_override)

        # 날짜 문자열(yyyyMMdd) 또는 실제 디렉토리명(yyyyMMdd(상호명)) 모두 허용
        target_dir = self.data_manager.date_manager.get_directory_path(date_directory)
        if not target_dir:
            target_dir = Path(self.settings.DATA_DIR) / date_directory

        return target_dir / "blog_result.md"

    async def _regenerate_blog_content(self, date_directory: str) -> QualityVerificationResult:
        """품질 기준 미달로 인한 AI 블로그 콘텐츠 재생성"""
        try:
            # 블로그 생성기 임포트 (순환 import 방지)
            from src.content.blog_generator import DateBasedBlogGenerator

            blog_generator = DateBasedBlogGenerator()

            # 비동기 실행을 위해 executor 사용
            loop = asyncio.get_event_loop()

            # force_regenerate=True로 기존 블로그를 덮어쓰도록 함
            result = await loop.run_in_executor(
                None,
                blog_generator.generate_from_session_data,
                date_directory,
                True  # force_regenerate=True
            )

            if result["success"]:
                self.logger.info(f"Blog regeneration successful for {date_directory}")

                return QualityVerificationResult(
                    success=True,
                    message="블로그 재생성 완료",
                    data={
                        "blog_file": result.get('blog_file_path') or str(self._resolve_blog_file_path(date_directory, None)),
                        "metadata": result.get('metadata'),
                        "length": result.get('metadata', {}).get('actual_length', 0),
                        "regenerated": True
                    }
                )
            else:
                error_msg = result.get('error', '알 수 없는 오류')
                self.logger.error(f"Blog regeneration failed: {error_msg}")

                return QualityVerificationResult(
                    success=False,
                    message="블로그 재생성 실패",
                    error=error_msg
                )

        except Exception as e:
            self.logger.error(f"Blog regeneration error: {e}")
            return QualityVerificationResult(
                success=False,
                message="블로그 재생성 중 오류 발생",
                error=str(e)
            )