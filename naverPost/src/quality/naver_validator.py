"""
네이버 블로그 저품질 콘텐츠 판정 회피 검증기

네이버 블로그의 저품질 콘텐츠 판정 알고리즘을 분석하고,
이를 회피할 수 있는 검증 로직을 제공합니다.
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime


class NaverQualityValidator:
    """네이버 블로그 품질 검증기"""

    # AI 전형 표현 패턴 (네이버가 감지하는 AI 작성 표현들)
    AI_TYPICAL_PATTERNS = {
        "closing_phrases": [
            r"총정리하면\s*,?",
            r"정리해드리겠습니다\s*[.!?]*",
            r"도움이 되셨다면\s*,?",
            r"마무리하겠습니다\s*[.!?]*",
            r"이상으로\s+.{1,10}\s*마치겠습니다",
            r"지금까지\s+.{1,20}\s*이었습니다",
        ],
        "generic_phrases": [
            r"여러분[들]*께\s*",
            r"모든\s*분[들]*께\s*",
            r"독자분[들]*께\s*",
            r"많은\s*도움이\s*되[길시]*\s*바[라릅]*니다",
            r"참고하[시세]*기\s*바[라릅]*니다",
            r"감사합니다\s*[.!?]*\s*$",
        ],
        "ai_transitions": [
            r"먼저\s*[,.]?\s*",
            r"다음으로\s*[,.]?\s*",
            r"마지막으로\s*[,.]?\s*",
            r"결론적으로\s*[,.]?\s*",
            r"요약하면\s*[,.]?\s*",
            r"한편[으론]*\s*[,.]?\s*",
        ],
        "repetitive_structures": [
            r"(.{10,30})\s*입니다\s*[.!?]\s*\1",  # 같은 내용 반복
            r"(\w+)\s*입니다\s*[.!?]\s*\1\s*입니다",  # 단어 반복
        ]
    }

    # 상업적 표현 패턴 (네이버가 광고로 분류할 수 있는 표현들)
    COMMERCIAL_PATTERNS = {
        "promotional": [
            r"할인\s*[이가]\s*[0-9]+%",
            r"[0-9]+원\s*할인",
            r"지금\s*주문[하면시]",
            r"한정\s*특가",
            r"이벤트\s*중",
            r"무료\s*배송",
            r"구매\s*링크",
            r"쿠폰\s*받기",
        ],
        "affiliate": [
            r"파트너스\s*활동",
            r"수수료\s*[을를]\s*받[을수]",
            r"광고\s*[가를]\s*포함",
            r"협찬\s*[을를]\s*받[아았]",
            r"제공받[아았]습니다",
        ],
        "call_to_action": [
            r"지금\s*바로\s*[구매클릭확인]",
            r"자세한\s*내용[은]\s*[아래밑하단]\s*링크",
            r"더\s*많은\s*정보[는]?\s*여기",
            r"구매\s*[는은]\s*[아래여기]",
        ]
    }

    # 키워드 스터핑 패턴
    KEYWORD_STUFFING_PATTERNS = {
        "excessive_repetition": [
            r"(\w{2,})\s*([,.\s]*\1\s*){3,}",  # 같은 단어 4번 이상 반복
            r"([가-힣]{2,})\s+\1\s+\1",  # 연속 3번 반복
        ],
        "unnatural_keywords": [
            r"[가-힣]+\s*[,]\s*[가-힣]+\s*[,]\s*[가-힣]+\s*[,]",  # 부자연스러운 키워드 나열
            r"(\w+)\s*(추천|후기|리뷰)\s*\1",  # 키워드 + 속성 반복
        ]
    }

    # 문장 구조 다양성 검사 기준
    SENTENCE_DIVERSITY_CRITERIA = {
        "min_sentence_length_variety": 3,  # 최소 3가지 길이 패턴
        "max_same_length_ratio": 0.4,     # 같은 길이 문장 비율 40% 이하
        "min_structure_types": 2,         # 최소 2가지 문장 구조
    }

    def __init__(self):
        """네이버 품질 검증기 초기화"""
        self.validation_results = {}

    def validate_content(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        블로그 콘텐츠 종합 품질 검증

        Args:
            content: 검증할 블로그 콘텐츠
            metadata: 추가 메타데이터 (카테고리, 키워드 등)

        Returns:
            종합 검증 결과
        """
        validation_result = {
            "timestamp": datetime.now().isoformat(),
            "content_length": len(content),
            "word_count": len(content.split()),
            "validations": {}
        }

        # 1. AI 전형 표현 검사
        ai_check = self._check_ai_patterns(content)
        validation_result["validations"]["ai_patterns"] = ai_check

        # 2. 상업적 표현 검사
        commercial_check = self._check_commercial_patterns(content)
        validation_result["validations"]["commercial_patterns"] = commercial_check

        # 3. 키워드 스터핑 검사
        keyword_check = self._check_keyword_stuffing(content)
        validation_result["validations"]["keyword_stuffing"] = keyword_check

        # 4. 문장 구조 다양성 검사
        sentence_check = self._check_sentence_diversity(content)
        validation_result["validations"]["sentence_diversity"] = sentence_check

        # 5. 개인적 표현 비율 검사
        personal_check = self._check_personal_expression_ratio(content)
        validation_result["validations"]["personal_expressions"] = personal_check

        # 6. 종합 위험도 계산
        risk_score = self._calculate_risk_score(validation_result["validations"])
        validation_result["risk_assessment"] = risk_score

        return validation_result

    def _check_ai_patterns(self, content: str) -> Dict[str, Any]:
        """AI 전형 표현 패턴 검사"""
        detected_patterns = {}
        total_matches = 0

        for category, patterns in self.AI_TYPICAL_PATTERNS.items():
            matches = []
            for pattern in patterns:
                found = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
                if found:
                    matches.extend(found)
                    total_matches += len(found)

            detected_patterns[category] = {
                "matches": matches,
                "count": len(matches)
            }

        return {
            "total_ai_patterns": total_matches,
            "patterns_by_category": detected_patterns,
            "risk_level": self._categorize_ai_risk(total_matches),
            "passed": total_matches <= 2,  # 2개 이하는 허용
            "recommendations": self._get_ai_pattern_recommendations(detected_patterns)
        }

    def _check_commercial_patterns(self, content: str) -> Dict[str, Any]:
        """상업적 표현 패턴 검사"""
        detected_patterns = {}
        total_matches = 0

        for category, patterns in self.COMMERCIAL_PATTERNS.items():
            matches = []
            for pattern in patterns:
                found = re.findall(pattern, content, re.IGNORECASE)
                if found:
                    matches.extend(found)
                    total_matches += len(found)

            detected_patterns[category] = {
                "matches": matches,
                "count": len(matches)
            }

        return {
            "total_commercial_patterns": total_matches,
            "patterns_by_category": detected_patterns,
            "risk_level": self._categorize_commercial_risk(total_matches),
            "passed": total_matches == 0,  # 상업적 표현은 0개여야 함
            "recommendations": self._get_commercial_pattern_recommendations(detected_patterns)
        }

    def _check_keyword_stuffing(self, content: str) -> Dict[str, Any]:
        """키워드 스터핑 검사"""
        detected_stuffing = {}
        total_violations = 0

        for category, patterns in self.KEYWORD_STUFFING_PATTERNS.items():
            violations = []
            for pattern in patterns:
                found = re.findall(pattern, content, re.IGNORECASE)
                if found:
                    violations.extend(found)
                    total_violations += len(found)

            detected_stuffing[category] = {
                "violations": violations,
                "count": len(violations)
            }

        # 단어 빈도 분석
        word_frequency = self._analyze_word_frequency(content)

        return {
            "total_stuffing_violations": total_violations,
            "stuffing_by_category": detected_stuffing,
            "word_frequency": word_frequency,
            "risk_level": self._categorize_stuffing_risk(total_violations, word_frequency),
            "passed": total_violations == 0 and word_frequency["max_frequency"] <= 0.03,
            "recommendations": self._get_stuffing_recommendations(detected_stuffing, word_frequency)
        }

    def _check_sentence_diversity(self, content: str) -> Dict[str, Any]:
        """문장 구조 다양성 검사"""
        sentences = re.split(r'[.!?]+', content)
        sentences = [s.strip() for s in sentences if s.strip()]

        if len(sentences) < 3:
            return {
                "total_sentences": len(sentences),
                "passed": False,
                "risk_level": "HIGH",
                "reason": "문장 수가 너무 적음"
            }

        # 문장 길이 분석
        sentence_lengths = [len(s) for s in sentences]
        length_variety = len(set([l // 10 for l in sentence_lengths]))  # 10자 단위로 그룹화
        same_length_ratio = max([sentence_lengths.count(l) for l in set(sentence_lengths)]) / len(sentences)

        # 문장 시작 패턴 분석
        start_patterns = [s[:3] for s in sentences if len(s) >= 3]
        start_variety = len(set(start_patterns)) / len(start_patterns) if start_patterns else 0

        # 문장 구조 타입 분석
        structure_types = self._analyze_sentence_structures(sentences)

        diversity_score = (
            min(length_variety / self.SENTENCE_DIVERSITY_CRITERIA["min_sentence_length_variety"], 1.0) * 0.4 +
            max(1 - same_length_ratio / self.SENTENCE_DIVERSITY_CRITERIA["max_same_length_ratio"], 0) * 0.3 +
            start_variety * 0.3
        )

        return {
            "total_sentences": len(sentences),
            "sentence_lengths": sentence_lengths,
            "length_variety": length_variety,
            "same_length_ratio": same_length_ratio,
            "start_variety": start_variety,
            "structure_types": structure_types,
            "diversity_score": round(diversity_score, 2),
            "passed": diversity_score >= 0.7,
            "risk_level": "LOW" if diversity_score >= 0.7 else "MEDIUM" if diversity_score >= 0.5 else "HIGH",
            "recommendations": self._get_diversity_recommendations(diversity_score, same_length_ratio)
        }

    def _check_personal_expression_ratio(self, content: str) -> Dict[str, Any]:
        """개인적 표현 비율 검사"""
        # 개인적 표현 패턴
        personal_patterns = [
            r"저[는가]",
            r"제가",
            r"저희[가는]?",
            r"개인적으로",
            r"직접",
            r"실제로",
            r"경험[해본상]",
            r"느[꼈낌]",
            r"생각[이했]",
            r"추천[해드려]",
        ]

        # 객관적/일반적 표현 패턴
        objective_patterns = [
            r"일반적으로",
            r"보통",
            r"대부분",
            r"많은 사람[들이]",
            r"전문가[들의]",
            r"연구[에결과]",
            r"데이터[에서]",
            r"통계[에따르면]",
        ]

        personal_matches = []
        objective_matches = []

        for pattern in personal_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            personal_matches.extend(matches)

        for pattern in objective_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            objective_matches.extend(matches)

        total_words = len(content.split())
        personal_ratio = len(personal_matches) / max(total_words / 100, 1)  # 100단어당 개인 표현 수
        objective_ratio = len(objective_matches) / max(total_words / 100, 1)

        return {
            "personal_expressions": personal_matches,
            "objective_expressions": objective_matches,
            "personal_count": len(personal_matches),
            "objective_count": len(objective_matches),
            "personal_ratio": round(personal_ratio, 2),
            "objective_ratio": round(objective_ratio, 2),
            "balance_score": self._calculate_balance_score(personal_ratio, objective_ratio),
            "passed": personal_ratio >= 0.5,  # 100단어당 최소 0.5개 개인 표현
            "risk_level": "LOW" if personal_ratio >= 1.0 else "MEDIUM" if personal_ratio >= 0.5 else "HIGH",
            "recommendations": self._get_personal_expression_recommendations(personal_ratio)
        }

    def _analyze_word_frequency(self, content: str) -> Dict[str, Any]:
        """단어 빈도 분석"""
        words = re.findall(r'[가-힣]+', content)
        if not words:
            return {"max_frequency": 0, "frequent_words": []}

        word_counts = {}
        for word in words:
            if len(word) >= 2:  # 2글자 이상만 분석
                word_counts[word] = word_counts.get(word, 0) + 1

        total_words = len(words)
        frequencies = {word: count / total_words for word, count in word_counts.items()}

        # 상위 빈도 단어들
        sorted_words = sorted(frequencies.items(), key=lambda x: x[1], reverse=True)
        max_frequency = sorted_words[0][1] if sorted_words else 0

        return {
            "total_words": total_words,
            "unique_words": len(word_counts),
            "max_frequency": round(max_frequency, 3),
            "frequent_words": sorted_words[:10],
            "diversity_ratio": len(word_counts) / total_words if total_words > 0 else 0
        }

    def _analyze_sentence_structures(self, sentences: List[str]) -> Dict[str, int]:
        """문장 구조 타입 분석"""
        structure_types = {
            "declarative": 0,    # 평서문
            "interrogative": 0,  # 의문문
            "exclamatory": 0,    # 감탄문
            "compound": 0,       # 복문
            "simple": 0,         # 단문
        }

        for sentence in sentences:
            if '?' in sentence:
                structure_types["interrogative"] += 1
            elif '!' in sentence:
                structure_types["exclamatory"] += 1
            elif ',' in sentence or '그리고' in sentence or '하지만' in sentence:
                structure_types["compound"] += 1
            else:
                structure_types["simple"] += 1

            # 평서문은 기본
            if not any(char in sentence for char in '?!'):
                structure_types["declarative"] += 1

        return structure_types

    def _calculate_risk_score(self, validations: Dict[str, Any]) -> Dict[str, Any]:
        """종합 위험도 계산"""
        risk_factors = []

        # AI 패턴 위험도
        ai_risk = validations["ai_patterns"]["total_ai_patterns"]
        if ai_risk > 5:
            risk_factors.append(("AI_HIGH", 0.8))
        elif ai_risk > 2:
            risk_factors.append(("AI_MEDIUM", 0.4))

        # 상업적 패턴 위험도
        if validations["commercial_patterns"]["total_commercial_patterns"] > 0:
            risk_factors.append(("COMMERCIAL", 0.9))

        # 키워드 스터핑 위험도
        if validations["keyword_stuffing"]["total_stuffing_violations"] > 0:
            risk_factors.append(("KEYWORD_STUFFING", 0.7))

        # 문장 다양성 위험도
        if not validations["sentence_diversity"]["passed"]:
            risk_factors.append(("LOW_DIVERSITY", 0.5))

        # 개인 표현 비율 위험도
        if not validations["personal_expressions"]["passed"]:
            risk_factors.append(("LOW_PERSONAL", 0.6))

        # 종합 위험도 계산
        if not risk_factors:
            overall_risk = 0.0
            risk_level = "SAFE"
        else:
            overall_risk = min(sum(factor[1] for factor in risk_factors), 1.0)
            if overall_risk >= 0.8:
                risk_level = "VERY_HIGH"
            elif overall_risk >= 0.6:
                risk_level = "HIGH"
            elif overall_risk >= 0.4:
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"

        return {
            "overall_risk_score": round(overall_risk, 2),
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "quality_score": max(0, 100 - int(overall_risk * 100)),
            "passed": overall_risk < 0.4,
            "recommendations": self._get_overall_recommendations(risk_factors)
        }

    def _categorize_ai_risk(self, count: int) -> str:
        """AI 패턴 위험도 분류"""
        if count == 0:
            return "SAFE"
        elif count <= 2:
            return "LOW"
        elif count <= 5:
            return "MEDIUM"
        else:
            return "HIGH"

    def _categorize_commercial_risk(self, count: int) -> str:
        """상업적 패턴 위험도 분류"""
        return "SAFE" if count == 0 else "HIGH"

    def _categorize_stuffing_risk(self, violations: int, word_freq: Dict[str, Any]) -> str:
        """키워드 스터핑 위험도 분류"""
        if violations > 0 or word_freq["max_frequency"] > 0.05:
            return "HIGH"
        elif word_freq["max_frequency"] > 0.03:
            return "MEDIUM"
        else:
            return "SAFE"

    def _calculate_balance_score(self, personal_ratio: float, objective_ratio: float) -> float:
        """개인/객관 표현 균형 점수 계산"""
        if personal_ratio == 0:
            return 0.0

        # 이상적인 비율: 개인 60%, 객관 40%
        ideal_personal = 0.6
        ideal_objective = 0.4

        total_ratio = personal_ratio + objective_ratio
        if total_ratio == 0:
            return 0.0

        actual_personal_ratio = personal_ratio / total_ratio
        actual_objective_ratio = objective_ratio / total_ratio

        balance_score = 1.0 - (
            abs(actual_personal_ratio - ideal_personal) +
            abs(actual_objective_ratio - ideal_objective)
        ) / 2

        return max(0.0, balance_score)

    def _get_ai_pattern_recommendations(self, patterns: Dict[str, Any]) -> List[str]:
        """AI 패턴 개선 권장사항"""
        recommendations = []

        if patterns["closing_phrases"]["count"] > 0:
            recommendations.append("글 마무리에서 'AI 전형' 표현을 자연스러운 개인적 감상으로 교체하세요")

        if patterns["generic_phrases"]["count"] > 0:
            recommendations.append("'여러분께' 같은 일반적 호칭 대신 구체적이고 개인적인 표현을 사용하세요")

        if patterns["ai_transitions"]["count"] > 2:
            recommendations.append("문단 연결어를 다양화하고 자연스러운 흐름으로 개선하세요")

        return recommendations

    def _get_commercial_pattern_recommendations(self, patterns: Dict[str, Any]) -> List[str]:
        """상업적 패턴 개선 권장사항"""
        recommendations = []

        if patterns["promotional"]["count"] > 0:
            recommendations.append("할인, 이벤트 등 홍보성 표현을 제거하거나 자연스러운 정보 제공으로 변경하세요")

        if patterns["affiliate"]["count"] > 0:
            recommendations.append("파트너스, 협찬 관련 표현을 제거하고 순수한 개인 경험으로 작성하세요")

        if patterns["call_to_action"]["count"] > 0:
            recommendations.append("구매 유도 표현을 제거하고 정보 제공 중심으로 작성하세요")

        return recommendations

    def _get_stuffing_recommendations(self, stuffing: Dict[str, Any], word_freq: Dict[str, Any]) -> List[str]:
        """키워드 스터핑 개선 권장사항"""
        recommendations = []

        if stuffing["excessive_repetition"]["count"] > 0:
            recommendations.append("같은 단어의 과도한 반복을 줄이고 동의어나 다른 표현으로 다양화하세요")

        if word_freq["max_frequency"] > 0.03:
            recommendations.append(f"가장 빈번한 단어(빈도: {word_freq['max_frequency']:.1%})의 사용을 줄이세요")

        if word_freq["diversity_ratio"] < 0.3:
            recommendations.append("어휘 다양성을 높이기 위해 더 다양한 단어를 사용하세요")

        return recommendations

    def _get_diversity_recommendations(self, diversity_score: float, same_length_ratio: float) -> List[str]:
        """문장 다양성 개선 권장사항"""
        recommendations = []

        if diversity_score < 0.5:
            recommendations.append("문장 길이와 구조를 더 다양하게 구성하세요")

        if same_length_ratio > 0.4:
            recommendations.append("비슷한 길이의 문장이 너무 많습니다. 짧은 문장과 긴 문장을 적절히 섞으세요")

        if diversity_score < 0.7:
            recommendations.append("의문문, 감탄문 등을 적절히 활용하여 문장 구조를 다양화하세요")

        return recommendations

    def _get_personal_expression_recommendations(self, personal_ratio: float) -> List[str]:
        """개인 표현 비율 개선 권장사항"""
        recommendations = []

        if personal_ratio < 0.5:
            recommendations.append("'저는', '제가', '직접', '개인적으로' 등 개인적 표현을 더 많이 사용하세요")

        if personal_ratio < 0.3:
            recommendations.append("객관적 정보보다 개인적 경험과 감상을 더 많이 포함하세요")

        if personal_ratio == 0:
            recommendations.append("개인 경험이 전혀 없습니다. 실제 체험담과 개인적 느낌을 추가하세요")

        return recommendations

    def _get_overall_recommendations(self, risk_factors: List[Tuple[str, float]]) -> List[str]:
        """종합 개선 권장사항"""
        recommendations = [
            "네이버 블로그 정책에 부합하는 고품질 콘텐츠로 개선하기 위한 권장사항:",
        ]

        for factor, score in risk_factors:
            if factor == "AI_HIGH":
                recommendations.append("• AI 작성 티가 강하게 납니다. 더 자연스럽고 개인적인 표현으로 수정하세요")
            elif factor == "COMMERCIAL":
                recommendations.append("• 상업적 표현을 모두 제거하고 순수한 개인 경험 중심으로 작성하세요")
            elif factor == "KEYWORD_STUFFING":
                recommendations.append("• 키워드를 자연스럽게 배치하고 과도한 반복을 피하세요")
            elif factor == "LOW_DIVERSITY":
                recommendations.append("• 문장 구조와 길이를 더 다양하게 구성하세요")
            elif factor == "LOW_PERSONAL":
                recommendations.append("• 개인적 경험과 감정 표현을 더 많이 포함하세요")

        return recommendations