"""
네이버 블로그 품질 검증 모듈

네이버 블로그의 저품질 콘텐츠 판정을 회피하고,
고품질 블로그 포스트를 보장하는 검증 시스템을 제공합니다.

주요 기능:
- 네이버 저품질 알고리즘 회피 로직
- 키워드 밀도 및 문장 구조 분석
- AI 전형 문구 탐지 및 필터링
- 개인 경험 비율 자동 검증
- 실시간 품질 점수 계산
"""

from .naver_validator import NaverQualityValidator

__all__ = [
    'NaverQualityValidator'
]

# TODO: 추후 구현 예정
# from .content_checker import ContentQualityChecker
# from .keyword_analyzer import KeywordDensityAnalyzer
# from .quality_metrics import QualityMetricsCalculator

__version__ = "1.0.0"