#!/usr/bin/env python3
"""
Phase 3 품질 검증 시스템 테스트 스크립트
네이버 저품질 판정 회피를 위한 품질 검증 시스템을 테스트합니다.

사용법:
    python3 scripts/test_quality_validation.py [project_id]

예시:
    python3 scripts/test_quality_validation.py 20260207
    python3 scripts/test_quality_validation.py  # 기본값: 20260207 사용
"""

import sys
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# 프로젝트 루트를 파이썬 경로에 추가 (scripts/ 아래로 이동했기 때문)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

try:
    from src.quality.naver_validator import NaverQualityValidator
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some modules not available: {e}")
    MODULES_AVAILABLE = False


class QualityValidationTester:
    """품질 검증 테스트 클래스"""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.project_dir = Path(f"data/{project_id}")
        self.generated_blog_path = self.project_dir / "generated_blog.txt"
        self.quality_report_path = self.project_dir / "quality_report.json"
        self.logs_dir = self.project_dir / "logs"

        # 디렉토리 생성
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def log_event(self, stage: str, status: str, message: str, **kwargs):
        """구조화된 로그 기록"""
        timestamp = datetime.now().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "stage": stage,
            "status": status,
            "message": message,
            **kwargs
        }

        # 콘솔 출력
        print(f"[{timestamp}] {stage.upper()} - {status}: {message}")
        for key, value in kwargs.items():
            if value is not None:
                print(f"  └─ {key}: {value}")

        # JSON 로그 파일에 기록
        log_file = self.logs_dir / "quality_validation_log.json"

        if log_file.exists():
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        else:
            logs = []

        logs.append(log_entry)

        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2, default=str)

    def check_prerequisites(self) -> bool:
        """사전 요구사항 확인"""
        self.log_event("prerequisites", "info", "사전 요구사항 확인 시작")

        # 1. 모듈 가용성 확인
        if not MODULES_AVAILABLE:
            self.log_event("prerequisites", "failed", "필요 모듈이 설치되지 않았습니다")
            return False

        # 2. 생성된 블로그 글 파일 존재 확인
        if not self.generated_blog_path.exists():
            self.log_event("prerequisites", "failed", f"블로그 글 파일이 없습니다: {self.generated_blog_path}")
            return False

        file_size = self.generated_blog_path.stat().st_size
        self.log_event("prerequisites", "completed", "모든 사전 요구사항이 충족되었습니다",
                      blog_file_size=file_size)
        return True

    def load_blog_content(self) -> Optional[str]:
        """생성된 블로그 글 로드"""
        self.log_event("content_loading", "info", f"블로그 글 로드 중: {self.generated_blog_path}")

        try:
            with open(self.generated_blog_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            self.log_event("content_loading", "completed", "콘텐츠 로드 성공",
                          content_length=len(content),
                          word_count=len(content.split()))

            return content

        except Exception as e:
            self.log_event("content_loading", "failed", f"콘텐츠 로드 실패: {str(e)}")
            return None

    def run_quality_validation(self, content: str) -> Optional[Dict[str, Any]]:
        """품질 검증 실행"""
        self.log_event("quality_validation", "info", "네이버 품질 검증 시작")

        try:
            # NaverQualityValidator 초기화
            validator = NaverQualityValidator()

            # 품질 검증 실행
            validation_result = validator.validate_content(content)

            risk_assessment = validation_result["risk_assessment"]

            self.log_event("quality_validation", "completed", "품질 검증 완료",
                          overall_risk_score=risk_assessment["overall_risk_score"],
                          risk_level=risk_assessment["risk_level"],
                          quality_score=risk_assessment["quality_score"],
                          passed=risk_assessment["passed"])

            return validation_result

        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": datetime.now().isoformat()
            }
            self.log_event("quality_validation", "failed", f"품질 검증 실패: {str(e)}")
            return error_result

    def save_quality_report(self, validation_result: Dict[str, Any], original_content: str):
        """품질 검증 결과 저장"""
        self.log_event("report_saving", "info", f"품질 보고서 저장 중: {self.quality_report_path}")

        try:
            # 저장용 데이터 구성
            report_data = {
                "project_id": self.project_id,
                "validation_timestamp": datetime.now().isoformat(),
                "original_content": original_content,
                "validation_result": validation_result,
                "file_info": {
                    "blog_file": str(self.generated_blog_path),
                    "report_file": str(self.quality_report_path),
                    "log_file": str(self.logs_dir / "quality_validation_log.json")
                }
            }

            with open(self.quality_report_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)

            self.log_event("report_saving", "completed", "품질 보고서 저장 성공")

        except Exception as e:
            self.log_event("report_saving", "failed", f"보고서 저장 실패: {str(e)}")

    def display_results(self, validation_result: Dict[str, Any]):
        """결과 화면 출력"""
        print("\n" + "=" * 80)
        print("🛡️  네이버 블로그 품질 검증 완료!")
        print("=" * 80)

        if "error" not in validation_result:
            risk_assessment = validation_result["risk_assessment"]
            validations = validation_result["validations"]

            # 종합 결과
            print(f"\n📊 종합 평가:")
            print(f"   🎯 품질 점수: {risk_assessment['quality_score']}점")
            print(f"   ⚠️  위험도: {risk_assessment['risk_level']} (점수: {risk_assessment['overall_risk_score']})")
            print(f"   ✅ 통과 여부: {'통과' if risk_assessment['passed'] else '미통과'}")

            # 세부 검증 결과
            print(f"\n🔍 세부 검증 결과:")

            # 1. AI 패턴 검사
            ai_patterns = validations["ai_patterns"]
            status_icon = "✅" if ai_patterns["passed"] else "❌"
            print(f"   {status_icon} AI 전형 패턴: {ai_patterns['total_ai_patterns']}개 감지 ({ai_patterns['risk_level']})")

            # 2. 상업적 패턴 검사
            commercial = validations["commercial_patterns"]
            status_icon = "✅" if commercial["passed"] else "❌"
            print(f"   {status_icon} 상업적 표현: {commercial['total_commercial_patterns']}개 감지 ({commercial['risk_level']})")

            # 3. 키워드 스터핑 검사
            keyword_stuffing = validations["keyword_stuffing"]
            status_icon = "✅" if keyword_stuffing["passed"] else "❌"
            print(f"   {status_icon} 키워드 스터핑: {keyword_stuffing['total_stuffing_violations']}개 위반 ({keyword_stuffing['risk_level']})")

            # 4. 문장 다양성 검사
            sentence_div = validations["sentence_diversity"]
            status_icon = "✅" if sentence_div["passed"] else "❌"
            print(f"   {status_icon} 문장 다양성: {sentence_div['diversity_score']} 점수 ({sentence_div['risk_level']})")

            # 5. 개인 표현 비율
            personal_exp = validations["personal_expressions"]
            status_icon = "✅" if personal_exp["passed"] else "❌"
            print(f"   {status_icon} 개인 표현 비율: {personal_exp['personal_ratio']} ({personal_exp['risk_level']})")

            # 상세 분석 정보
            print(f"\n📈 상세 분석:")
            print(f"   📝 총 문장 수: {sentence_div['total_sentences']}개")
            print(f"   📊 문장 길이 다양성: {sentence_div['length_variety']}패턴")
            print(f"   🔤 어휘 다양성: {keyword_stuffing['word_frequency']['diversity_ratio']:.1%}")
            print(f"   👤 개인 표현: {personal_exp['personal_count']}개")
            print(f"   📖 객관 표현: {personal_exp['objective_count']}개")

            # 위험 요소 분석
            if risk_assessment["risk_factors"]:
                print(f"\n⚠️  위험 요소:")
                for factor, score in risk_assessment["risk_factors"]:
                    risk_name = {
                        "AI_HIGH": "AI 작성 패턴 과다",
                        "AI_MEDIUM": "AI 작성 패턴 보통",
                        "COMMERCIAL": "상업적 표현 감지",
                        "KEYWORD_STUFFING": "키워드 스터핑",
                        "LOW_DIVERSITY": "낮은 문장 다양성",
                        "LOW_PERSONAL": "낮은 개인 표현 비율"
                    }.get(factor, factor)
                    print(f"   • {risk_name}: 위험도 {score:.1f}")

            # 개선 권장사항
            recommendations = risk_assessment["recommendations"]
            if len(recommendations) > 1:  # 첫 번째는 헤더
                print(f"\n💡 개선 권장사항:")
                for i, rec in enumerate(recommendations[1:], 1):
                    print(f"   {i}. {rec}")

            # 감지된 문제 패턴들
            if ai_patterns["total_ai_patterns"] > 0:
                print(f"\n🤖 감지된 AI 패턴:")
                for category, data in ai_patterns["patterns_by_category"].items():
                    if data["count"] > 0:
                        print(f"   • {category}: {data['matches'][:3]}")  # 최대 3개만 표시

        else:
            print(f"\n❌ 검증 실패:")
            print(f"   오류 유형: {validation_result.get('error_type', 'Unknown')}")
            print(f"   오류 메시지: {validation_result.get('error', 'No message')}")

        print(f"\n📁 생성된 파일:")
        print(f"   - {self.quality_report_path}")
        print(f"   - {self.logs_dir / 'quality_validation_log.json'}")

    def run_full_validation(self):
        """전체 품질 검증 프로세스 실행"""
        try:
            print(f"\n🛡️  네이버 블로그 품질 검증 테스트 시작")
            print(f"   프로젝트 ID: {self.project_id}")
            print(f"   프로젝트 경로: {self.project_dir}")
            print("=" * 80)

            # 1. 사전 요구사항 확인
            if not self.check_prerequisites():
                print("\n❌ 사전 요구사항을 충족하지 않아 테스트를 중단합니다.")
                return

            # 2. 블로그 콘텐츠 로드
            content = self.load_blog_content()
            if not content:
                print("\n❌ 블로그 콘텐츠 로드에 실패하여 테스트를 중단합니다.")
                return

            # 3. 품질 검증 실행
            validation_result = self.run_quality_validation(content)
            if not validation_result:
                print("\n❌ 품질 검증에 실패했습니다.")
                return

            # 4. 결과 저장
            self.save_quality_report(validation_result, content)

            # 5. 결과 출력
            self.display_results(validation_result)

            self.log_event("full_process", "completed", "전체 프로세스 성공적으로 완료")

        except Exception as e:
            self.log_event("full_process", "failed", f"전체 프로세스 실행 실패: {str(e)}")
            print(f"\n❌ 전체 프로세스 실행 실패: {str(e)}")
            raise


def main():
    """메인 실행 함수"""
    # 명령행 인수 처리
    if len(sys.argv) > 1:
        project_id = sys.argv[1]
    else:
        project_id = "20260207"

    print(f"Phase 3 네이버 블로그 품질 검증 테스트 - 프로젝트 ID: {project_id}")

    # 테스트 실행
    tester = QualityValidationTester(project_id)
    tester.run_full_validation()


if __name__ == "__main__":
    main()