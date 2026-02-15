"""
실시간 품질 점수 계산 및 피드백 시스템

생성된 블로그 콘텐츠를 실시간으로 분석하여 종합적인 품질 점수를 제공하고,
네이버 블로그 정책 준수 및 품질 개선을 위한 구체적인 피드백을 제공합니다.
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import json

try:
    from .naver_validator import NaverQualityValidator
    from .keyword_analyzer import KeywordDensityAnalyzer
    from .content_checker import ContentQualityChecker
except ImportError:
    # 개발/테스트 환경에서 직접 실행할 때
    from naver_validator import NaverQualityValidator
    from keyword_analyzer import KeywordDensityAnalyzer
    from content_checker import ContentQualityChecker


class UnifiedQualityScorer:
    """통합 품질 점수 계산기"""

    # 각 검증 영역의 가중치 설정
    VALIDATION_WEIGHTS = {
        "naver_compliance": 0.35,      # 네이버 정책 준수 (35%)
        "keyword_quality": 0.25,       # 키워드 품질 (25%)
        "personal_authenticity": 0.25, # 개인 경험 진정성 (25%)
        "technical_quality": 0.15      # 기술적 품질 (15%)
    }

    # 품질 등급 기준점
    QUALITY_THRESHOLDS = {
        "EXCELLENT": 0.9,
        "VERY_GOOD": 0.8,
        "GOOD": 0.7,
        "FAIR": 0.6,
        "POOR": 0.5,
        "VERY_POOR": 0.0
    }

    # 네이버 정책 통과 기준
    NAVER_PASS_THRESHOLD = 0.75

    def __init__(self):
        """통합 품질 점수 계산기 초기화"""
        self.naver_validator = NaverQualityValidator()
        self.keyword_analyzer = KeywordDensityAnalyzer()
        self.content_checker = ContentQualityChecker()

    def calculate_unified_score(self,
                              generated_content: str,
                              original_review: Optional[str] = None,
                              target_keywords: Optional[List[str]] = None,
                              category: Optional[str] = None) -> Dict[str, Any]:
        """
        통합 품질 점수 계산

        Args:
            generated_content: 생성된 블로그 글
            original_review: 원본 사용자 리뷰 (개인 경험 분석용)
            target_keywords: 대상 키워드 리스트 (밀도 분석용)
            category: 콘텐츠 카테고리 (맛집, 제품 등)

        Returns:
            통합 품질 분석 결과
        """
        analysis_start_time = datetime.now()

        # 1. 네이버 정책 준수 검증
        naver_analysis = self._run_naver_validation(generated_content)

        # 2. 키워드 품질 분석
        keyword_analysis = self._run_keyword_analysis(generated_content, target_keywords)

        # 3. 개인 경험 진정성 분석 (원본 리뷰가 있을 때만)
        personal_analysis = None
        if original_review:
            personal_analysis = self._run_personal_analysis(generated_content, original_review, category)

        # 4. 기술적 품질 지표 계산
        technical_analysis = self._calculate_technical_quality(generated_content, naver_analysis, keyword_analysis)

        # 5. 통합 점수 계산
        unified_score = self._calculate_unified_quality_score(
            naver_analysis, keyword_analysis, personal_analysis, technical_analysis
        )

        # 6. 실시간 피드백 생성
        real_time_feedback = self._generate_real_time_feedback(
            unified_score, naver_analysis, keyword_analysis, personal_analysis
        )

        analysis_duration = (datetime.now() - analysis_start_time).total_seconds()

        return {
            "timestamp": datetime.now().isoformat(),
            "analysis_duration_seconds": round(analysis_duration, 3),
            "content_length": len(generated_content),
            "content_word_count": len(generated_content.split()),

            # 통합 결과
            "unified_score": unified_score,

            # 세부 분석 결과
            "naver_compliance_analysis": naver_analysis,
            "keyword_quality_analysis": keyword_analysis,
            "personal_authenticity_analysis": personal_analysis,
            "technical_quality_analysis": technical_analysis,

            # 실시간 피드백
            "real_time_feedback": real_time_feedback,

            # 메타데이터
            "analysis_metadata": {
                "has_original_review": original_review is not None,
                "has_target_keywords": target_keywords is not None,
                "category": category,
                "validation_components_used": [
                    "naver_validator",
                    "keyword_analyzer",
                    "content_checker" if original_review else None,
                    "technical_analyzer"
                ]
            }
        }

    def _run_naver_validation(self, content: str) -> Dict[str, Any]:
        """네이버 정책 준수 검증 실행"""
        try:
            validation_result = self.naver_validator.validate_content(content)
            risk_assessment = validation_result.get("risk_assessment", {})

            return {
                "success": True,
                "quality_score": risk_assessment.get("quality_score", 0) / 100.0,  # 0-1 범위로 변환
                "risk_level": risk_assessment.get("risk_level", "UNKNOWN"),
                "risk_score": risk_assessment.get("overall_risk_score", 1.0),
                "passed": risk_assessment.get("passed", False),
                "validation_details": validation_result.get("validations", {}),
                "recommendations": risk_assessment.get("recommendations", [])
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "quality_score": 0.0,
                "risk_level": "ERROR",
                "passed": False
            }

    def _run_keyword_analysis(self, content: str, target_keywords: Optional[List[str]] = None) -> Dict[str, Any]:
        """키워드 품질 분석 실행"""
        try:
            analysis_result = self.keyword_analyzer.analyze_keyword_density(content, target_keywords)
            quality_score = analysis_result.get("quality_score", {})

            return {
                "success": True,
                "overall_score": quality_score.get("overall_score", 0.0),
                "density_score": quality_score.get("density_score", 0.0),
                "distribution_score": quality_score.get("distribution_score", 0.0),
                "rating": quality_score.get("rating", "POOR"),
                "passed": quality_score.get("passed", False),
                "keyword_details": analysis_result.get("keyword_analysis", {}),
                "density_evaluation": analysis_result.get("density_evaluation", {}),
                "recommendations": analysis_result.get("recommendations", [])
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "overall_score": 0.0,
                "rating": "ERROR",
                "passed": False
            }

    def _run_personal_analysis(self, content: str, original_review: str, category: Optional[str] = None) -> Dict[str, Any]:
        """개인 경험 진정성 분석 실행"""
        try:
            analysis_result = self.content_checker.analyze_personal_experience_ratio(original_review, content, category)
            overall_eval = analysis_result.get("overall_evaluation", {})

            return {
                "success": True,
                "weighted_score": overall_eval.get("weighted_score", 0.0),
                "quality_grade": overall_eval.get("quality_grade", "VERY_POOR"),
                "passed": overall_eval.get("passed", False),
                "naver_compliance": overall_eval.get("naver_compliance", False),
                "individual_scores": overall_eval.get("individual_scores", {}),
                "analysis_details": {
                    "similarity": analysis_result.get("similarity_analysis", {}),
                    "personal_expression": analysis_result.get("personal_expression_analysis", {}),
                    "experience_reflection": analysis_result.get("experience_reflection_analysis", {}),
                    "emotion_analysis": analysis_result.get("emotion_analysis", {}),
                    "specificity": analysis_result.get("specificity_analysis", {})
                },
                "recommendations": analysis_result.get("recommendations", [])
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "weighted_score": 0.0,
                "quality_grade": "ERROR",
                "passed": False
            }

    def _calculate_technical_quality(self, content: str, naver_analysis: Dict, keyword_analysis: Dict) -> Dict[str, Any]:
        """기술적 품질 지표 계산"""
        try:
            # 기본 콘텐츠 메트릭
            content_length = len(content)
            word_count = len(content.split())
            sentence_count = len([s for s in content.split('.') if s.strip()])

            # 길이 점수 (800-2000자 기준)
            length_score = self._calculate_length_score(content_length)

            # 가독성 점수 (평균 문장 길이 기준)
            avg_sentence_length = word_count / max(sentence_count, 1)
            readability_score = self._calculate_readability_score(avg_sentence_length)

            # 구조 점수 (해시태그, 단락 구성 등)
            structure_score = self._calculate_structure_score(content)

            # 종합 기술적 품질 점수
            technical_score = (length_score + readability_score + structure_score) / 3

            return {
                "success": True,
                "technical_score": round(technical_score, 3),
                "length_score": round(length_score, 3),
                "readability_score": round(readability_score, 3),
                "structure_score": round(structure_score, 3),
                "metrics": {
                    "content_length": content_length,
                    "word_count": word_count,
                    "sentence_count": sentence_count,
                    "avg_sentence_length": round(avg_sentence_length, 1)
                },
                "passed": technical_score >= 0.6
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "technical_score": 0.0,
                "passed": False
            }

    def _calculate_unified_quality_score(self, naver: Dict, keyword: Dict, personal: Optional[Dict], technical: Dict) -> Dict[str, Any]:
        """통합 품질 점수 계산"""
        try:
            # 각 영역별 점수 추출
            scores = {
                "naver_compliance": naver.get("quality_score", 0.0),
                "keyword_quality": keyword.get("overall_score", 0.0),
                "personal_authenticity": personal.get("weighted_score", 0.7) if personal else 0.7,  # 개인분석 없으면 기본값
                "technical_quality": technical.get("technical_score", 0.0)
            }

            # 가중 평균 계산
            weighted_score = sum(scores[key] * self.VALIDATION_WEIGHTS[key] for key in scores.keys())

            # 품질 등급 결정
            quality_grade = self._determine_quality_grade(weighted_score)

            # 네이버 정책 통과 여부
            naver_pass = weighted_score >= self.NAVER_PASS_THRESHOLD

            # 전체 통과 여부 (모든 주요 검증 통과)
            all_pass = (
                naver.get("passed", False) and
                keyword.get("passed", False) and
                technical.get("passed", False) and
                (personal.get("passed", True) if personal else True)  # 개인분석 없으면 기본 통과
            )

            return {
                "weighted_score": round(weighted_score, 3),
                "quality_grade": quality_grade,
                "naver_policy_compliance": naver_pass,
                "overall_passed": all_pass,

                "component_scores": scores,
                "component_weights": self.VALIDATION_WEIGHTS,

                "detailed_pass_status": {
                    "naver_validation": naver.get("passed", False),
                    "keyword_analysis": keyword.get("passed", False),
                    "personal_authenticity": personal.get("passed", True) if personal else True,
                    "technical_quality": technical.get("passed", False)
                },

                "confidence_level": self._calculate_confidence_level(naver, keyword, personal, technical)
            }

        except Exception as e:
            return {
                "weighted_score": 0.0,
                "quality_grade": "ERROR",
                "naver_policy_compliance": False,
                "overall_passed": False,
                "error": str(e)
            }

    def _calculate_length_score(self, length: int) -> float:
        """콘텐츠 길이 점수 계산"""
        if length < 300:
            return 0.3  # 너무 짧음
        elif length < 600:
            return 0.6  # 짧음
        elif length <= 2000:
            return 1.0  # 적절
        elif length <= 3000:
            return 0.8  # 조금 김
        else:
            return 0.5  # 너무 김

    def _calculate_readability_score(self, avg_sentence_length: float) -> float:
        """가독성 점수 계산 (평균 문장 길이 기준)"""
        if avg_sentence_length < 10:
            return 0.7  # 너무 짧은 문장들
        elif avg_sentence_length <= 20:
            return 1.0  # 적절한 길이
        elif avg_sentence_length <= 30:
            return 0.8  # 조금 긴 문장들
        else:
            return 0.5  # 너무 긴 문장들

    def _calculate_structure_score(self, content: str) -> float:
        """구조 점수 계산"""
        score = 0.0

        # 해시태그 존재 여부
        if '#' in content:
            score += 0.3

        # 단락 구분 여부 (빈 줄로 구분)
        if '\n\n' in content:
            score += 0.4

        # 적절한 문장 부호 사용
        punctuation_count = content.count('.') + content.count('!') + content.count('?')
        if punctuation_count >= 3:
            score += 0.3

        return min(score, 1.0)

    def _determine_quality_grade(self, score: float) -> str:
        """품질 등급 결정"""
        for grade, threshold in self.QUALITY_THRESHOLDS.items():
            if score >= threshold:
                return grade
        return "VERY_POOR"

    def _calculate_confidence_level(self, naver: Dict, keyword: Dict, personal: Optional[Dict], technical: Dict) -> str:
        """분석 신뢰도 계산"""
        success_count = sum([
            1 if naver.get("success", False) else 0,
            1 if keyword.get("success", False) else 0,
            1 if personal and personal.get("success", False) else 0.5,  # 개인분석은 선택사항이므로 0.5점
            1 if technical.get("success", False) else 0
        ])

        max_possible = 4 if personal else 3.5
        confidence_ratio = success_count / max_possible

        if confidence_ratio >= 0.9:
            return "HIGH"
        elif confidence_ratio >= 0.7:
            return "MEDIUM"
        else:
            return "LOW"

    def _generate_real_time_feedback(self, unified_score: Dict, naver: Dict, keyword: Dict, personal: Optional[Dict]) -> Dict[str, Any]:
        """실시간 피드백 생성"""
        feedback = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "PASS" if unified_score.get("overall_passed", False) else "FAIL",
            "quality_grade": unified_score.get("quality_grade", "UNKNOWN"),
            "immediate_actions": [],
            "improvement_suggestions": [],
            "priority_fixes": []
        }

        # 즉시 조치가 필요한 항목들
        if not naver.get("passed", False):
            feedback["immediate_actions"].append("⚠️ 네이버 정책 위반 요소 수정 필요")
            feedback["priority_fixes"].extend(naver.get("recommendations", [])[:2])

        if not keyword.get("passed", False):
            feedback["immediate_actions"].append("🔍 키워드 밀도 및 분포 조정 필요")
            feedback["priority_fixes"].extend(keyword.get("recommendations", [])[:2])

        # 개선 제안사항
        score = unified_score.get("weighted_score", 0)
        if score < 0.8:
            if personal and personal.get("weighted_score", 0) < 0.7:
                feedback["improvement_suggestions"].append("👤 개인 경험 표현을 더 자연스럽게 작성하세요")

            if keyword.get("overall_score", 0) < 0.8:
                feedback["improvement_suggestions"].append("🔑 키워드 사용을 더 자연스럽게 분산시키세요")

        # 점수별 메시지
        if score >= 0.9:
            feedback["overall_message"] = "🎉 탁월한 품질의 콘텐츠입니다!"
        elif score >= 0.8:
            feedback["overall_message"] = "✅ 매우 좋은 품질입니다. 발행 가능한 수준입니다."
        elif score >= 0.7:
            feedback["overall_message"] = "👍 양호한 품질입니다. 약간의 개선 후 발행 권장."
        elif score >= 0.6:
            feedback["overall_message"] = "⚠️ 보통 품질입니다. 개선이 필요합니다."
        else:
            feedback["overall_message"] = "❌ 품질이 낮습니다. 대폭적인 수정이 필요합니다."

        return feedback

    def get_quality_report(self, analysis_result: Dict[str, Any]) -> str:
        """사용자 친화적인 품질 보고서 생성"""
        unified = analysis_result["unified_score"]
        feedback = analysis_result["real_time_feedback"]

        report = f"""
=== 📊 블로그 콘텐츠 품질 분석 보고서 ===

🎯 종합 점수: {unified['weighted_score']:.3f} ({unified['quality_grade']})
✅ 전체 통과: {'통과' if unified['overall_passed'] else '미통과'}
🏛️ 네이버 정책: {'준수' if unified['naver_policy_compliance'] else '미준수'}

📈 세부 점수:
• 네이버 정책 준수: {unified['component_scores']['naver_compliance']:.2f} (35%)
• 키워드 품질: {unified['component_scores']['keyword_quality']:.2f} (25%)
• 개인 경험 진정성: {unified['component_scores']['personal_authenticity']:.2f} (25%)
• 기술적 품질: {unified['component_scores']['technical_quality']:.2f} (15%)

{feedback['overall_message']}

⚡ 즉시 조치 필요:
{chr(10).join(f"• {action}" for action in feedback['immediate_actions']) if feedback['immediate_actions'] else "• 없음"}

💡 개선 제안:
{chr(10).join(f"• {suggestion}" for suggestion in feedback['improvement_suggestions']) if feedback['improvement_suggestions'] else "• 현재 품질 유지"}

분석 시간: {analysis_result['analysis_duration_seconds']}초
"""
        return report.strip()