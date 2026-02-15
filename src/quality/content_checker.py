"""
개인 경험 비율 자동 검증 시스템

생성된 블로그 글에서 사용자의 실제 개인 경험이 얼마나 반영되었는지
자동으로 측정하고 검증하는 시스템을 제공합니다.
"""

import re
import difflib
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter
from datetime import datetime


class ContentQualityChecker:
    """콘텐츠 품질 검증기 (개인 경험 비율 중심)"""

    # 개인 경험 표현 패턴
    PERSONAL_EXPERIENCE_PATTERNS = {
        "first_person": [
            r"저[는가]",
            r"제가",
            r"저희[가는도]?",
            r"내가",
            r"우리가",
        ],
        "personal_actions": [
            r"직접\s*[가본했느경]",
            r"실제로\s*[가본했느경]",
            r"개인적으로\s*[가본했느경생각]",
            r"경험[해본상했]",
            r"[가봤갔왔]었[습어다]",
        ],
        "personal_feelings": [
            r"느[꼈낌끼]",
            r"생각[이했했다]",
            r"인상[이적]",
            r"감[상동정]",
            r"기분[이좋]",
            r"만족[했스]",
        ],
        "personal_recommendations": [
            r"추천[해드려합하고]",
            r"[권하좋]아요",
            r"[강력히]?\s*추천",
        ]
    }

    # 객관적/일반적 표현 패턴
    OBJECTIVE_PATTERNS = {
        "general_statements": [
            r"일반적으로",
            r"보통",
            r"대부분",
            r"많은\s*사람[들이]",
            r"대체로",
        ],
        "factual_information": [
            r"데이터[에서]",
            r"통계[에따르면]",
            r"연구[에결과]",
            r"조사[에결과]",
            r"자료[에따르면]",
        ],
        "expert_opinions": [
            r"전문가[들의는]",
            r"업계[에서]",
            r"공식[적으로]",
            r"발표[된했]",
        ]
    }

    # 감정 표현 강도 패턴
    EMOTION_INTENSITY_PATTERNS = {
        "strong": [
            r"정말\s*[좋맛훌최]",
            r"너무\s*[좋맛훌최]",
            r"완전\s*[좋맛훌최]",
            r"진짜\s*[좋맛훌최]",
            r"엄청\s*[좋맛훌최]",
        ],
        "moderate": [
            r"꽤\s*[좋맛훌괜]",
            r"제법\s*[좋맛훌괜]",
            r"상당히\s*[좋맛훌괜]",
            r"나름\s*[좋맛훌괜]",
        ],
        "mild": [
            r"조금\s*[좋맛]",
            r"약간\s*[좋맛]",
            r"살짝\s*[좋맛]",
        ]
    }

    def __init__(self):
        """콘텐츠 품질 검증기 초기화"""
        pass

    def analyze_personal_experience_ratio(self, original_review: str, generated_content: str,
                                        category: str = None) -> Dict[str, Any]:
        """
        개인 경험 비율 종합 분석

        Args:
            original_review: 사용자 원본 리뷰
            generated_content: 생성된 블로그 글
            category: 카테고리 (맛집, 제품 등)

        Returns:
            개인 경험 비율 분석 결과
        """
        # 1. 기본 텍스트 유사도 분석
        similarity_analysis = self._analyze_text_similarity(original_review, generated_content)

        # 2. 개인 표현 비율 분석
        personal_expression_analysis = self._analyze_personal_expressions(generated_content)

        # 3. 원본 경험 요소 반영도 분석
        experience_reflection_analysis = self._analyze_experience_reflection(original_review, generated_content)

        # 4. 감정 표현 분석
        emotion_analysis = self._analyze_emotion_expressions(original_review, generated_content)

        # 5. 구체성 분석 (일반적 vs 구체적)
        specificity_analysis = self._analyze_content_specificity(original_review, generated_content)

        # 6. 종합 평가
        overall_evaluation = self._calculate_overall_personal_ratio(
            similarity_analysis,
            personal_expression_analysis,
            experience_reflection_analysis,
            emotion_analysis,
            specificity_analysis
        )

        return {
            "timestamp": datetime.now().isoformat(),
            "analysis_type": "personal_experience_ratio",
            "category": category,
            "similarity_analysis": similarity_analysis,
            "personal_expression_analysis": personal_expression_analysis,
            "experience_reflection_analysis": experience_reflection_analysis,
            "emotion_analysis": emotion_analysis,
            "specificity_analysis": specificity_analysis,
            "overall_evaluation": overall_evaluation,
            "recommendations": self._generate_improvement_recommendations(overall_evaluation)
        }

    def _analyze_text_similarity(self, original: str, generated: str) -> Dict[str, Any]:
        """텍스트 유사도 분석"""
        # 문장 단위 유사도
        original_sentences = self._extract_sentences(original)
        generated_sentences = self._extract_sentences(generated)

        # 전체 텍스트 유사도 (difflib 사용)
        overall_similarity = difflib.SequenceMatcher(None, original, generated).ratio()

        # 키워드 중복도 분석
        original_words = self._extract_meaningful_words(original)
        generated_words = self._extract_meaningful_words(generated)

        common_words = set(original_words) & set(generated_words)
        word_overlap_ratio = len(common_words) / len(set(original_words)) if original_words else 0

        # 문장별 최대 유사도 찾기
        sentence_similarities = []
        for orig_sent in original_sentences:
            max_sim = 0
            for gen_sent in generated_sentences:
                sim = difflib.SequenceMatcher(None, orig_sent, gen_sent).ratio()
                max_sim = max(max_sim, sim)
            sentence_similarities.append(max_sim)

        avg_sentence_similarity = sum(sentence_similarities) / len(sentence_similarities) if sentence_similarities else 0

        return {
            "overall_similarity": round(overall_similarity, 3),
            "word_overlap_ratio": round(word_overlap_ratio, 3),
            "average_sentence_similarity": round(avg_sentence_similarity, 3),
            "common_words": list(common_words),
            "common_word_count": len(common_words),
            "original_unique_words": len(set(original_words)),
            "generated_unique_words": len(set(generated_words))
        }

    def _analyze_personal_expressions(self, content: str) -> Dict[str, Any]:
        """개인 표현 비율 분석"""
        personal_counts = {}
        total_personal = 0

        # 개인 표현 패턴별 분석
        for category, patterns in self.PERSONAL_EXPERIENCE_PATTERNS.items():
            matches = []
            for pattern in patterns:
                found = re.findall(pattern, content, re.IGNORECASE)
                matches.extend(found)

            personal_counts[category] = {
                "matches": matches,
                "count": len(matches)
            }
            total_personal += len(matches)

        # 객관적 표현 분석
        objective_counts = {}
        total_objective = 0

        for category, patterns in self.OBJECTIVE_PATTERNS.items():
            matches = []
            for pattern in patterns:
                found = re.findall(pattern, content, re.IGNORECASE)
                matches.extend(found)

            objective_counts[category] = {
                "matches": matches,
                "count": len(matches)
            }
            total_objective += len(matches)

        # 비율 계산
        total_expressions = total_personal + total_objective
        personal_ratio = total_personal / total_expressions if total_expressions > 0 else 0
        objective_ratio = total_objective / total_expressions if total_expressions > 0 else 0

        return {
            "personal_expressions": personal_counts,
            "objective_expressions": objective_counts,
            "total_personal_count": total_personal,
            "total_objective_count": total_objective,
            "personal_ratio": round(personal_ratio, 3),
            "objective_ratio": round(objective_ratio, 3),
            "balance_assessment": self._assess_expression_balance(personal_ratio, objective_ratio)
        }

    def _analyze_experience_reflection(self, original: str, generated: str) -> Dict[str, Any]:
        """원본 경험 요소 반영도 분석"""
        # 원본에서 주요 경험 요소 추출
        original_elements = self._extract_experience_elements(original)

        # 생성된 글에서 반영된 요소 확인
        reflection_analysis = {}
        total_reflected = 0

        for category, elements in original_elements.items():
            reflected_elements = []
            for element in elements:
                if self._is_element_reflected(element, generated):
                    reflected_elements.append(element)
                    total_reflected += 1

            reflection_analysis[category] = {
                "original_count": len(elements),
                "reflected_count": len(reflected_elements),
                "reflected_elements": reflected_elements,
                "reflection_ratio": len(reflected_elements) / len(elements) if elements else 0
            }

        total_original_elements = sum(len(elements) for elements in original_elements.values())
        overall_reflection_ratio = total_reflected / total_original_elements if total_original_elements > 0 else 0

        return {
            "experience_elements": original_elements,
            "reflection_analysis": reflection_analysis,
            "total_original_elements": total_original_elements,
            "total_reflected_elements": total_reflected,
            "overall_reflection_ratio": round(overall_reflection_ratio, 3),
            "reflection_quality": self._assess_reflection_quality(overall_reflection_ratio)
        }

    def _analyze_emotion_expressions(self, original: str, generated: str) -> Dict[str, Any]:
        """감정 표현 분석"""
        # 원본과 생성글의 감정 강도 분석
        original_emotions = self._extract_emotion_intensity(original)
        generated_emotions = self._extract_emotion_intensity(generated)

        # 감정 표현 일치도 분석
        emotion_consistency = self._compare_emotion_levels(original_emotions, generated_emotions)

        return {
            "original_emotions": original_emotions,
            "generated_emotions": generated_emotions,
            "emotion_consistency": emotion_consistency,
            "emotional_authenticity_score": self._calculate_emotional_authenticity(original_emotions, generated_emotions)
        }

    def _analyze_content_specificity(self, original: str, generated: str) -> Dict[str, Any]:
        """구체성 분석 (일반적 vs 구체적)"""
        # 구체적 표현 패턴
        specific_patterns = [
            r"[0-9]+[시분일월년]",  # 시간, 날짜
            r"[0-9]+[원달러만천]",   # 가격
            r"[가-힣]+[점역센터몰]",  # 구체적 장소
            r"[가-힣]+[맛향색깔]",   # 감각적 표현
        ]

        original_specific = self._count_pattern_matches(original, specific_patterns)
        generated_specific = self._count_pattern_matches(generated, specific_patterns)

        # 일반적 표현 패턴
        generic_patterns = [
            r"보통\s*[이그]",
            r"일반적[으로인]",
            r"대체로",
            r"평균[적으로인]",
        ]

        original_generic = self._count_pattern_matches(original, generic_patterns)
        generated_generic = self._count_pattern_matches(generated, generic_patterns)

        # 구체성 점수 계산
        original_specificity = original_specific / (original_specific + original_generic + 1)
        generated_specificity = generated_specific / (generated_specific + generated_generic + 1)

        return {
            "original_specific_count": original_specific,
            "original_generic_count": original_generic,
            "generated_specific_count": generated_specific,
            "generated_generic_count": generated_generic,
            "original_specificity_score": round(original_specificity, 3),
            "generated_specificity_score": round(generated_specificity, 3),
            "specificity_maintenance": round(generated_specificity / max(original_specificity, 0.1), 3)
        }

    def _extract_sentences(self, text: str) -> List[str]:
        """문장 추출"""
        sentences = re.split(r'[.!?]+', text)
        return [s.strip() for s in sentences if s.strip()]

    def _extract_meaningful_words(self, text: str) -> List[str]:
        """의미 있는 단어 추출 (불용어 제외)"""
        stop_words = {'은', '는', '이', '가', '을', '를', '에', '의', '와', '과', '도', '만', '하다', '있다', '되다'}
        words = re.findall(r'[가-힣]{2,}', text)
        return [word for word in words if word not in stop_words]

    def _extract_experience_elements(self, original: str) -> Dict[str, List[str]]:
        """원본에서 경험 요소 추출"""
        elements = {
            "places": re.findall(r'[가-힣]+[점역센터몰타워]', original),
            "foods": re.findall(r'[가-힣]+[음식요리메뉴]|[가-힣]*[맛있죠]', original),
            "feelings": re.findall(r'[가-힣]*[좋았네요습니다]|느[꼈낌]', original),
            "actions": re.findall(r'[가갔봤했]었[다습니다어요]', original),
            "descriptions": re.findall(r'[가-힣]{3,}[하한]', original)
        }

        # 빈 리스트 제거 및 중복 제거
        return {k: list(set(v)) for k, v in elements.items() if v}

    def _is_element_reflected(self, element: str, generated: str) -> bool:
        """요소가 생성된 글에 반영되었는지 확인"""
        # 완전 일치 또는 부분 일치 확인
        if element in generated:
            return True

        # 유사한 표현 확인 (간단한 휴리스틱)
        element_words = element.split()
        if len(element_words) > 1:
            return any(word in generated for word in element_words if len(word) > 1)

        return False

    def _extract_emotion_intensity(self, text: str) -> Dict[str, int]:
        """감정 표현 강도 추출"""
        emotion_counts = {"strong": 0, "moderate": 0, "mild": 0}

        for intensity, patterns in self.EMOTION_INTENSITY_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                emotion_counts[intensity] += len(matches)

        return emotion_counts

    def _compare_emotion_levels(self, original_emotions: Dict, generated_emotions: Dict) -> Dict[str, Any]:
        """감정 수준 비교"""
        consistency_score = 0
        total_comparisons = 0

        for intensity in ["strong", "moderate", "mild"]:
            orig_count = original_emotions[intensity]
            gen_count = generated_emotions[intensity]

            if orig_count > 0 or gen_count > 0:
                # 비율 유사성 계산
                similarity = 1 - abs(orig_count - gen_count) / max(orig_count + gen_count, 1)
                consistency_score += similarity
                total_comparisons += 1

        overall_consistency = consistency_score / total_comparisons if total_comparisons > 0 else 0

        return {
            "consistency_score": round(overall_consistency, 3),
            "emotion_level_match": self._assess_emotion_match(original_emotions, generated_emotions)
        }

    def _assess_emotion_match(self, original: Dict, generated: Dict) -> str:
        """감정 매치 수준 평가"""
        orig_total = sum(original.values())
        gen_total = sum(generated.values())

        if orig_total == 0 and gen_total == 0:
            return "neutral_match"
        elif abs(orig_total - gen_total) <= 1:
            return "good_match"
        elif abs(orig_total - gen_total) <= 3:
            return "fair_match"
        else:
            return "poor_match"

    def _count_pattern_matches(self, text: str, patterns: List[str]) -> int:
        """패턴 매치 수 계산"""
        total_matches = 0
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            total_matches += len(matches)
        return total_matches

    def _assess_expression_balance(self, personal_ratio: float, objective_ratio: float) -> str:
        """표현 균형 평가"""
        if personal_ratio >= 0.7:
            return "highly_personal"
        elif personal_ratio >= 0.5:
            return "moderately_personal"
        elif personal_ratio >= 0.3:
            return "balanced"
        elif personal_ratio >= 0.1:
            return "mostly_objective"
        else:
            return "completely_objective"

    def _assess_reflection_quality(self, reflection_ratio: float) -> str:
        """반영 품질 평가"""
        if reflection_ratio >= 0.8:
            return "excellent"
        elif reflection_ratio >= 0.6:
            return "good"
        elif reflection_ratio >= 0.4:
            return "fair"
        elif reflection_ratio >= 0.2:
            return "poor"
        else:
            return "very_poor"

    def _calculate_emotional_authenticity(self, original: Dict, generated: Dict) -> float:
        """감정 진정성 점수 계산"""
        orig_total = sum(original.values())
        gen_total = sum(generated.values())

        if orig_total == 0 and gen_total == 0:
            return 1.0

        # 감정 표현의 강도 분포 비교
        orig_strong_ratio = original["strong"] / max(orig_total, 1)
        gen_strong_ratio = generated["strong"] / max(gen_total, 1)

        strong_similarity = 1 - abs(orig_strong_ratio - gen_strong_ratio)

        # 전체 감정량 비교
        quantity_similarity = 1 - abs(orig_total - gen_total) / max(orig_total + gen_total, 1)

        return round((strong_similarity + quantity_similarity) / 2, 3)

    def _calculate_overall_personal_ratio(self, similarity: Dict, personal_exp: Dict,
                                        experience_ref: Dict, emotion: Dict,
                                        specificity: Dict) -> Dict[str, Any]:
        """종합 개인 경험 비율 계산"""
        # 각 지표별 가중치
        weights = {
            "similarity": 0.25,           # 텍스트 유사도
            "personal_expression": 0.25,  # 개인 표현 비율
            "experience_reflection": 0.3, # 경험 요소 반영도
            "emotion_authenticity": 0.15, # 감정 진정성
            "specificity": 0.05          # 구체성 유지
        }

        # 각 지표를 0-1 범위로 정규화하여 점수 계산
        scores = {
            "similarity": similarity["word_overlap_ratio"],
            "personal_expression": personal_exp["personal_ratio"],
            "experience_reflection": experience_ref["overall_reflection_ratio"],
            "emotion_authenticity": emotion["emotional_authenticity_score"],
            "specificity": specificity["specificity_maintenance"]
        }

        # 가중 평균 계산
        weighted_score = sum(scores[key] * weights[key] for key in scores.keys())

        # 품질 등급 결정
        if weighted_score >= 0.8:
            quality_grade = "EXCELLENT"
        elif weighted_score >= 0.7:
            quality_grade = "GOOD"
        elif weighted_score >= 0.6:
            quality_grade = "FAIR"
        elif weighted_score >= 0.5:
            quality_grade = "POOR"
        else:
            quality_grade = "VERY_POOR"

        return {
            "individual_scores": scores,
            "weights": weights,
            "weighted_score": round(weighted_score, 3),
            "quality_grade": quality_grade,
            "passed": weighted_score >= 0.6,
            "naver_compliance": weighted_score >= 0.7,  # 네이버 정책 준수 기준
        }

    def _generate_improvement_recommendations(self, overall_eval: Dict[str, Any]) -> List[str]:
        """개선 권장사항 생성"""
        recommendations = []
        scores = overall_eval["individual_scores"]

        if scores["similarity"] < 0.3:
            recommendations.append("원본 리뷰의 핵심 내용을 더 많이 반영하세요.")

        if scores["personal_expression"] < 0.5:
            recommendations.append("'저는', '제가', '개인적으로' 등 개인적 표현을 더 많이 사용하세요.")

        if scores["experience_reflection"] < 0.6:
            recommendations.append("원본 경험의 구체적 요소들(장소, 음식, 감정 등)을 더 자세히 포함하세요.")

        if scores["emotion_authenticity"] < 0.6:
            recommendations.append("원본 리뷰의 감정 표현 강도를 더 잘 반영하세요.")

        if scores["specificity"] < 0.5:
            recommendations.append("구체적인 설명과 세부사항을 더 포함하세요.")

        if not recommendations:
            recommendations.append("개인 경험 비율이 우수합니다. 현재 품질을 유지하세요.")

        return recommendations