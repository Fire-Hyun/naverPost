"""
키워드 밀도 및 문장 구조 분석기

블로그 콘텐츠의 키워드 분포와 문장 구조를 분석하여
자연스러운 글쓰기 패턴을 평가합니다.
"""

import re
import math
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter, defaultdict
from datetime import datetime


class KeywordDensityAnalyzer:
    """키워드 밀도 분석기"""

    # 키워드 밀도 기준
    DENSITY_THRESHOLDS = {
        "ideal_min": 0.005,    # 0.5% - 최소 권장 밀도
        "ideal_max": 0.025,    # 2.5% - 최대 권장 밀도
        "warning_threshold": 0.035,  # 3.5% - 경고 수준
        "danger_threshold": 0.05,    # 5.0% - 위험 수준
    }

    # 불용어 (분석에서 제외할 단어들)
    STOP_WORDS = {
        "이", "그", "저", "것", "의", "가", "를", "에", "은", "는", "으로", "로", "와", "과",
        "도", "만", "까지", "부터", "에서", "에게", "한", "하나", "두", "세", "네", "다섯",
        "있다", "없다", "이다", "아니다", "하다", "되다", "같다", "다르다", "크다", "작다"
    }

    def __init__(self):
        """키워드 밀도 분석기 초기화"""
        pass

    def analyze_keyword_density(self, content: str, target_keywords: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        키워드 밀도 종합 분석

        Args:
            content: 분석할 콘텐츠
            target_keywords: 특정 키워드들 (없으면 자동 추출)

        Returns:
            키워드 밀도 분석 결과
        """
        # 전처리
        clean_content = self._preprocess_content(content)
        words = self._extract_words(clean_content)

        if not words:
            return self._empty_analysis_result()

        # 기본 통계
        total_words = len(words)
        unique_words = len(set(words))

        # 키워드 추출 및 밀도 계산
        if target_keywords:
            keyword_analysis = self._analyze_target_keywords(words, target_keywords)
        else:
            keyword_analysis = self._analyze_natural_keywords(words)

        # 전체 단어 빈도 분석
        word_frequency = self._calculate_word_frequency(words)

        # 키워드 분포 패턴 분석
        distribution_analysis = self._analyze_keyword_distribution(content, keyword_analysis["keywords"])

        # 키워드 밀도 평가
        density_evaluation = self._evaluate_keyword_density(keyword_analysis, total_words)

        return {
            "timestamp": datetime.now().isoformat(),
            "content_stats": {
                "total_words": total_words,
                "unique_words": unique_words,
                "lexical_diversity": unique_words / total_words,
                "content_length": len(content)
            },
            "keyword_analysis": keyword_analysis,
            "word_frequency": word_frequency,
            "distribution_analysis": distribution_analysis,
            "density_evaluation": density_evaluation,
            "quality_score": self._calculate_quality_score(density_evaluation, distribution_analysis),
            "recommendations": self._generate_recommendations(density_evaluation, distribution_analysis)
        }

    def _preprocess_content(self, content: str) -> str:
        """콘텐츠 전처리"""
        # 특수 문자 및 불필요한 요소 제거
        content = re.sub(r'#[가-힣a-zA-Z0-9_]+', '', content)  # 해시태그 제거
        content = re.sub(r'[^\w\s가-힣]', ' ', content)  # 특수문자를 공백으로
        content = re.sub(r'\s+', ' ', content).strip()  # 연속 공백 정리

        return content

    def _extract_words(self, content: str) -> List[str]:
        """단어 추출"""
        words = re.findall(r'[가-힣]{2,}', content)  # 2글자 이상 한글 단어만
        words = [word for word in words if word not in self.STOP_WORDS]
        return words

    def _analyze_target_keywords(self, words: List[str], target_keywords: List[str]) -> Dict[str, Any]:
        """특정 키워드 분석"""
        keyword_counts = {}
        total_words = len(words)

        for keyword in target_keywords:
            count = words.count(keyword)
            density = count / total_words if total_words > 0 else 0
            keyword_counts[keyword] = {
                "count": count,
                "density": density,
                "positions": [i for i, word in enumerate(words) if word == keyword]
            }

        return {
            "method": "target_keywords",
            "keywords": keyword_counts,
            "total_target_words": sum(data["count"] for data in keyword_counts.values()),
            "average_density": sum(data["density"] for data in keyword_counts.values()) / len(target_keywords) if target_keywords else 0
        }

    def _analyze_natural_keywords(self, words: List[str]) -> Dict[str, Any]:
        """자연 키워드 분석 (빈도 기반)"""
        word_counts = Counter(words)
        total_words = len(words)

        # 상위 빈도 단어들을 키워드로 선정 (최소 2번 이상 등장)
        keywords = {word: count for word, count in word_counts.items() if count >= 2}

        keyword_analysis = {}
        for word, count in keywords.items():
            density = count / total_words
            keyword_analysis[word] = {
                "count": count,
                "density": density,
                "positions": [i for i, w in enumerate(words) if w == word]
            }

        return {
            "method": "natural_extraction",
            "keywords": keyword_analysis,
            "total_keyword_words": sum(data["count"] for data in keyword_analysis.values()),
            "average_density": sum(data["density"] for data in keyword_analysis.values()) / len(keyword_analysis) if keyword_analysis else 0
        }

    def _calculate_word_frequency(self, words: List[str]) -> Dict[str, Any]:
        """전체 단어 빈도 분석"""
        word_counts = Counter(words)
        total_words = len(words)

        frequency_data = []
        for word, count in word_counts.most_common(20):  # 상위 20개
            frequency = count / total_words
            frequency_data.append({
                "word": word,
                "count": count,
                "frequency": frequency
            })

        return {
            "most_frequent": frequency_data,
            "max_frequency": frequency_data[0]["frequency"] if frequency_data else 0,
            "frequency_distribution": self._analyze_frequency_distribution(word_counts)
        }

    def _analyze_frequency_distribution(self, word_counts: Counter) -> Dict[str, Any]:
        """빈도 분포 분석"""
        frequencies = list(word_counts.values())
        if not frequencies:
            return {"balance": "empty", "concentration": 0}

        # 빈도 분포의 균형성 측정
        freq_counts = Counter(frequencies)
        total_unique_words = len(frequencies)

        # 상위 10% 단어가 차지하는 비율
        top_10_percent = max(1, int(total_unique_words * 0.1))
        top_words_freq = sum(sorted(frequencies, reverse=True)[:top_10_percent])
        total_freq = sum(frequencies)

        concentration_ratio = top_words_freq / total_freq if total_freq > 0 else 0

        return {
            "balance": "concentrated" if concentration_ratio > 0.5 else "balanced",
            "concentration": concentration_ratio,
            "unique_frequencies": len(freq_counts),
            "most_common_frequency": max(frequencies) if frequencies else 0
        }

    def _analyze_keyword_distribution(self, content: str, keywords: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """키워드 분포 패턴 분석"""
        sentences = re.split(r'[.!?]+', content)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences or not keywords:
            return {"pattern": "empty", "evenness": 0}

        # 문장별 키워드 분포
        sentence_keyword_counts = []
        for sentence in sentences:
            keyword_count = 0
            for keyword in keywords.keys():
                keyword_count += sentence.count(keyword)
            sentence_keyword_counts.append(keyword_count)

        # 분포 균등성 계산
        if sentence_keyword_counts:
            mean_count = sum(sentence_keyword_counts) / len(sentence_keyword_counts)
            variance = sum((x - mean_count) ** 2 for x in sentence_keyword_counts) / len(sentence_keyword_counts)
            std_dev = math.sqrt(variance)
            evenness = 1 - (std_dev / max(mean_count, 1))  # 0~1 범위로 정규화
        else:
            evenness = 0

        # 분포 패턴 분류
        non_zero_sentences = sum(1 for count in sentence_keyword_counts if count > 0)
        coverage_ratio = non_zero_sentences / len(sentences) if sentences else 0

        if coverage_ratio > 0.7 and evenness > 0.6:
            pattern = "well_distributed"
        elif coverage_ratio > 0.5:
            pattern = "moderately_distributed"
        elif coverage_ratio > 0.3:
            pattern = "clustered"
        else:
            pattern = "concentrated"

        return {
            "pattern": pattern,
            "evenness": evenness,
            "coverage_ratio": coverage_ratio,
            "sentence_distribution": sentence_keyword_counts,
            "sentences_with_keywords": non_zero_sentences,
            "total_sentences": len(sentences)
        }

    def _evaluate_keyword_density(self, keyword_analysis: Dict[str, Any], total_words: int) -> Dict[str, Any]:
        """키워드 밀도 평가"""
        keywords = keyword_analysis["keywords"]
        evaluations = {}

        for keyword, data in keywords.items():
            density = data["density"]
            evaluation = self._classify_density(density)
            evaluations[keyword] = {
                "density": density,
                "classification": evaluation["classification"],
                "risk_level": evaluation["risk_level"],
                "recommendation": evaluation["recommendation"]
            }

        # 전체 평가
        max_density = max([data["density"] for data in keywords.values()]) if keywords else 0
        avg_density = keyword_analysis["average_density"]

        overall_evaluation = {
            "max_density": max_density,
            "average_density": avg_density,
            "overall_risk": self._classify_overall_risk(max_density, avg_density),
            "keyword_evaluations": evaluations,
            "passed": max_density <= self.DENSITY_THRESHOLDS["warning_threshold"]
        }

        return overall_evaluation

    def _classify_density(self, density: float) -> Dict[str, str]:
        """개별 키워드 밀도 분류"""
        thresholds = self.DENSITY_THRESHOLDS

        if density <= thresholds["ideal_max"]:
            if density >= thresholds["ideal_min"]:
                return {
                    "classification": "optimal",
                    "risk_level": "SAFE",
                    "recommendation": "적절한 키워드 밀도입니다."
                }
            else:
                return {
                    "classification": "low",
                    "risk_level": "LOW",
                    "recommendation": "키워드 사용을 조금 더 늘려보세요."
                }
        elif density <= thresholds["warning_threshold"]:
            return {
                "classification": "moderate",
                "risk_level": "MEDIUM",
                "recommendation": "키워드 밀도가 약간 높습니다. 자연스럽게 줄여보세요."
            }
        elif density <= thresholds["danger_threshold"]:
            return {
                "classification": "high",
                "risk_level": "HIGH",
                "recommendation": "키워드 밀도가 너무 높습니다. 키워드 스터핑으로 판정될 위험이 있습니다."
            }
        else:
            return {
                "classification": "excessive",
                "risk_level": "CRITICAL",
                "recommendation": "키워드 밀도가 매우 위험합니다. 즉시 키워드 사용을 줄이세요."
            }

    def _classify_overall_risk(self, max_density: float, avg_density: float) -> str:
        """전체 위험도 분류"""
        if max_density >= self.DENSITY_THRESHOLDS["danger_threshold"]:
            return "CRITICAL"
        elif max_density >= self.DENSITY_THRESHOLDS["warning_threshold"]:
            return "HIGH"
        elif avg_density >= self.DENSITY_THRESHOLDS["ideal_max"]:
            return "MEDIUM"
        else:
            return "LOW"

    def _calculate_quality_score(self, density_eval: Dict[str, Any], distribution_eval: Dict[str, Any]) -> Dict[str, Any]:
        """품질 점수 계산"""
        # 밀도 점수 (60%)
        max_density = density_eval["max_density"]
        if max_density <= self.DENSITY_THRESHOLDS["ideal_max"]:
            density_score = 1.0
        elif max_density <= self.DENSITY_THRESHOLDS["warning_threshold"]:
            density_score = 0.7
        elif max_density <= self.DENSITY_THRESHOLDS["danger_threshold"]:
            density_score = 0.4
        else:
            density_score = 0.1

        # 분포 점수 (40%)
        evenness = distribution_eval["evenness"]
        coverage = distribution_eval["coverage_ratio"]
        distribution_score = (evenness * 0.6 + coverage * 0.4)

        # 종합 점수
        overall_score = density_score * 0.6 + distribution_score * 0.4
        quality_rating = self._get_quality_rating(overall_score)

        return {
            "density_score": round(density_score, 2),
            "distribution_score": round(distribution_score, 2),
            "overall_score": round(overall_score, 2),
            "rating": quality_rating,
            "passed": overall_score >= 0.6
        }

    def _get_quality_rating(self, score: float) -> str:
        """품질 등급 분류"""
        if score >= 0.9:
            return "EXCELLENT"
        elif score >= 0.7:
            return "GOOD"
        elif score >= 0.5:
            return "FAIR"
        else:
            return "POOR"

    def _generate_recommendations(self, density_eval: Dict[str, Any], distribution_eval: Dict[str, Any]) -> List[str]:
        """개선 권장사항 생성"""
        recommendations = []

        # 밀도 관련 권장사항
        high_density_keywords = [
            keyword for keyword, eval_data in density_eval["keyword_evaluations"].items()
            if eval_data["risk_level"] in ["HIGH", "CRITICAL"]
        ]

        if high_density_keywords:
            recommendations.append(f"다음 키워드의 밀도를 줄이세요: {', '.join(high_density_keywords)}")

        # 분포 관련 권장사항
        pattern = distribution_eval["pattern"]
        if pattern == "concentrated":
            recommendations.append("키워드가 특정 부분에 집중되어 있습니다. 전체적으로 고르게 분산시키세요.")
        elif pattern == "clustered":
            recommendations.append("키워드 분포가 고르지 않습니다. 자연스럽게 분산시켜 보세요.")

        # 일반적인 권장사항
        if density_eval["overall_risk"] == "CRITICAL":
            recommendations.append("키워드 스터핑 위험이 매우 높습니다. 키워드를 대폭 줄이고 동의어를 활용하세요.")
        elif density_eval["overall_risk"] == "HIGH":
            recommendations.append("키워드 밀도를 조금 더 자연스럽게 조정하세요.")

        if not recommendations:
            recommendations.append("키워드 밀도와 분포가 적절합니다.")

        return recommendations

    def _empty_analysis_result(self) -> Dict[str, Any]:
        """빈 분석 결과 반환"""
        return {
            "timestamp": datetime.now().isoformat(),
            "content_stats": {"total_words": 0, "unique_words": 0, "lexical_diversity": 0},
            "keyword_analysis": {"keywords": {}, "total_keyword_words": 0, "average_density": 0},
            "word_frequency": {"most_frequent": [], "max_frequency": 0},
            "distribution_analysis": {"pattern": "empty", "evenness": 0},
            "density_evaluation": {"passed": False, "overall_risk": "UNKNOWN"},
            "quality_score": {"overall_score": 0, "rating": "POOR", "passed": False},
            "recommendations": ["분석할 콘텐츠가 없습니다."]
        }