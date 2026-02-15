"""
Quality threshold management for blog content verification
"""

from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class QualityThresholdManager:
    """Manages quality thresholds and scoring criteria for blog content"""

    def __init__(self, settings):
        self.settings = settings

        # Quality thresholds
        self.MIN_QUALITY_SCORE = self._normalize_score_threshold(
            getattr(settings, "MIN_QUALITY_SCORE", 0.7)
        )
        self.QUALITY_SOFT_FAIL_MARGIN = self._normalize_margin(
            getattr(settings, "QUALITY_SOFT_FAIL_MARGIN", 0.1)
        )
        self.SOFT_MIN_QUALITY_SCORE = max(0.0, self.MIN_QUALITY_SCORE - self.QUALITY_SOFT_FAIL_MARGIN)

        logger.info(f"Quality thresholds initialized - Min: {self.MIN_QUALITY_SCORE}, Soft Min: {self.SOFT_MIN_QUALITY_SCORE}")

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

    def evaluate_quality_score(self, overall_score: float) -> Dict[str, Any]:
        """
        품질 점수를 평가하고 결과를 반환

        Returns:
            Dict containing:
            - passes_threshold: bool
            - is_soft_pass: bool
            - action: str ('pass', 'soft_pass', 'fail')
            - message: str
        """
        if overall_score >= self.MIN_QUALITY_SCORE:
            return {
                'passes_threshold': True,
                'is_soft_pass': False,
                'action': 'pass',
                'message': f'품질 기준 통과 (점수: {overall_score:.2f})'
            }
        elif overall_score >= self.SOFT_MIN_QUALITY_SCORE:
            warning = (
                f"품질 점수 {overall_score:.2f}가 권장 기준 {self.MIN_QUALITY_SCORE:.2f}에 "
                f"조금 못 미쳐 경고 상태로 진행합니다."
            )
            return {
                'passes_threshold': True,
                'is_soft_pass': True,
                'action': 'soft_pass',
                'message': warning
            }
        else:
            return {
                'passes_threshold': False,
                'is_soft_pass': False,
                'action': 'fail',
                'message': f'품질 점수 {overall_score:.2f}가 최소 기준 {self.MIN_QUALITY_SCORE:.2f}보다 낮습니다'
            }

    def get_thresholds(self) -> Dict[str, float]:
        """현재 설정된 임계값들을 반환"""
        return {
            'recommended_min': self.MIN_QUALITY_SCORE,
            'soft_min': self.SOFT_MIN_QUALITY_SCORE,
            'margin': self.QUALITY_SOFT_FAIL_MARGIN
        }