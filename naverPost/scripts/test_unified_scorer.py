#!/usr/bin/env python3
"""
실시간 품질 점수 계산 및 피드백 시스템 테스트 스크립트

통합 품질 점수 계산기를 테스트하여 모든 검증 컴포넌트가
올바르게 통합되어 실시간 피드백을 제공하는지 확인합니다.

사용법:
    python3 scripts/test_unified_scorer.py [project_id]

예시:
    python3 scripts/test_unified_scorer.py 20260207
    python3 scripts/test_unified_scorer.py  # 기본값: 20260207 사용
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
    from src.quality.unified_scorer import UnifiedQualityScorer
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some modules not available: {e}")
    MODULES_AVAILABLE = False


class UnifiedScorerTester:
    """통합 품질 점수 계산기 테스트 클래스"""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.project_dir = Path(f"data/{project_id}")
        self.meta_path = self.project_dir / "meta.json"
        self.generated_blog_path = self.project_dir / "generated_blog.txt"
        self.unified_report_path = self.project_dir / "unified_quality_report.json"
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
        log_file = self.logs_dir / "unified_scorer_log.json"

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

        # 2. 메타 파일 존재 확인
        if not self.meta_path.exists():
            self.log_event("prerequisites", "failed", f"메타 파일이 없습니다: {self.meta_path}")
            return False

        # 3. 생성된 블로그 글 파일 존재 확인
        if not self.generated_blog_path.exists():
            self.log_event("prerequisites", "failed", f"블로그 글 파일이 없습니다: {self.generated_blog_path}")
            return False

        file_size = self.generated_blog_path.stat().st_size
        self.log_event("prerequisites", "completed", "모든 사전 요구사항이 충족되었습니다",
                      meta_file_exists=True,
                      blog_file_size=file_size)
        return True

    def load_test_data(self) -> tuple[Optional[Dict], Optional[str], Optional[str], Optional[list]]:
        """테스트 데이터 로드"""
        self.log_event("data_loading", "info", "테스트 데이터 로드 시작")

        try:
            # 메타 데이터 로드
            with open(self.meta_path, 'r', encoding='utf-8') as f:
                meta_data = json.load(f)

            # 블로그 콘텐츠 로드
            with open(self.generated_blog_path, 'r', encoding='utf-8') as f:
                blog_content = f.read().strip()

            # 원본 리뷰 추출
            original_review = meta_data.get("user_input", {}).get("personal_review", "")

            # 키워드 추출 (해시태그에서)
            import re
            hashtags = re.findall(r'#([가-힣a-zA-Z0-9_]+)', blog_content)
            target_keywords = [tag for tag in hashtags if re.search(r'[가-힣]', tag)]

            # 카테고리 추출
            category = meta_data.get("user_input", {}).get("category", "")

            self.log_event("data_loading", "completed", "테스트 데이터 로드 성공",
                          meta_data_keys=list(meta_data.keys()),
                          blog_content_length=len(blog_content),
                          original_review_length=len(original_review),
                          target_keywords_count=len(target_keywords),
                          category=category)

            return meta_data, blog_content, original_review, target_keywords

        except Exception as e:
            self.log_event("data_loading", "failed", f"데이터 로드 실패: {str(e)}")
            return None, None, None, None

    def run_unified_analysis(self, blog_content: str, original_review: str, target_keywords: list, category: str) -> Optional[Dict[str, Any]]:
        """통합 품질 분석 실행"""
        self.log_event("unified_analysis", "info", "통합 품질 분석 시작",
                      content_length=len(blog_content),
                      has_original_review=bool(original_review),
                      target_keywords=target_keywords[:3] if target_keywords else None)

        try:
            # UnifiedQualityScorer 초기화
            scorer = UnifiedQualityScorer()

            # 통합 품질 분석 실행
            analysis_result = scorer.calculate_unified_score(
                generated_content=blog_content,
                original_review=original_review if original_review else None,
                target_keywords=target_keywords if target_keywords else None,
                category=category if category else None
            )

            unified_score = analysis_result["unified_score"]

            self.log_event("unified_analysis", "completed", "통합 품질 분석 완료",
                          weighted_score=unified_score["weighted_score"],
                          quality_grade=unified_score["quality_grade"],
                          overall_passed=unified_score["overall_passed"],
                          naver_compliance=unified_score["naver_policy_compliance"],
                          analysis_duration=analysis_result["analysis_duration_seconds"])

            return analysis_result

        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": datetime.now().isoformat()
            }
            self.log_event("unified_analysis", "failed", f"통합 품질 분석 실패: {str(e)}")
            return error_result

    def save_unified_report(self, analysis_result: Dict[str, Any], meta_data: Dict, blog_content: str):
        """통합 분석 결과 저장"""
        self.log_event("report_saving", "info", f"통합 분석 보고서 저장 중: {self.unified_report_path}")

        try:
            # 저장용 데이터 구성
            report_data = {
                "project_id": self.project_id,
                "analysis_timestamp": datetime.now().isoformat(),
                "meta_data": meta_data,
                "generated_content": blog_content,
                "unified_analysis_result": analysis_result,
                "file_info": {
                    "meta_file": str(self.meta_path),
                    "blog_file": str(self.generated_blog_path),
                    "report_file": str(self.unified_report_path),
                    "log_file": str(self.logs_dir / "unified_scorer_log.json")
                }
            }

            with open(self.unified_report_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)

            self.log_event("report_saving", "completed", "통합 분석 보고서 저장 성공")

        except Exception as e:
            self.log_event("report_saving", "failed", f"보고서 저장 실패: {str(e)}")

    def display_results(self, analysis_result: Dict[str, Any]):
        """결과 화면 출력"""
        print("\n" + "=" * 90)
        print("🚀 실시간 품질 점수 계산 및 피드백 시스템 완료!")
        print("=" * 90)

        if "error" not in analysis_result:
            unified_score = analysis_result["unified_score"]
            feedback = analysis_result["real_time_feedback"]
            metadata = analysis_result["analysis_metadata"]

            # 종합 결과
            print(f"\n🎯 통합 품질 평가:")
            print(f"   📊 종합 점수: {unified_score['weighted_score']:.3f}")
            print(f"   📈 품질 등급: {unified_score['quality_grade']}")
            print(f"   ✅ 전체 통과: {'통과' if unified_score['overall_passed'] else '미통과'}")
            print(f"   🏛️  네이버 정책: {'준수' if unified_score['naver_policy_compliance'] else '미준수'}")
            print(f"   🔍 분석 신뢰도: {unified_score['confidence_level']}")

            # 세부 점수
            scores = unified_score["component_scores"]
            weights = unified_score["component_weights"]
            print(f"\n📊 세부 점수 (가중치 적용):")
            print(f"   🛡️  네이버 정책 준수: {scores['naver_compliance']:.3f} ({weights['naver_compliance']:.0%})")
            print(f"   🔑 키워드 품질: {scores['keyword_quality']:.3f} ({weights['keyword_quality']:.0%})")
            print(f"   👤 개인 경험 진정성: {scores['personal_authenticity']:.3f} ({weights['personal_authenticity']:.0%})")
            print(f"   ⚙️  기술적 품질: {scores['technical_quality']:.3f} ({weights['technical_quality']:.0%})")

            # 세부 통과 상태
            pass_status = unified_score["detailed_pass_status"]
            print(f"\n✅ 세부 통과 상태:")
            for component, passed in pass_status.items():
                status_icon = "✅" if passed else "❌"
                component_name = {
                    "naver_validation": "네이버 정책 검증",
                    "keyword_analysis": "키워드 분석",
                    "personal_authenticity": "개인 경험 진정성",
                    "technical_quality": "기술적 품질"
                }.get(component, component)
                print(f"   {status_icon} {component_name}: {'통과' if passed else '미통과'}")

            # 실시간 피드백
            print(f"\n🔥 실시간 피드백:")
            print(f"   📋 상태: {feedback['overall_status']}")
            print(f"   💬 메시지: {feedback['overall_message']}")

            # 즉시 조치 필요
            if feedback["immediate_actions"]:
                print(f"\n⚡ 즉시 조치 필요:")
                for i, action in enumerate(feedback["immediate_actions"], 1):
                    print(f"   {i}. {action}")
            else:
                print(f"\n✅ 즉시 조치 필요 사항 없음")

            # 개선 제안
            if feedback["improvement_suggestions"]:
                print(f"\n💡 개선 제안:")
                for i, suggestion in enumerate(feedback["improvement_suggestions"], 1):
                    print(f"   {i}. {suggestion}")

            # 우선순위 수정사항
            if feedback["priority_fixes"]:
                print(f"\n🔧 우선순위 수정사항:")
                for i, fix in enumerate(feedback["priority_fixes"], 1):
                    print(f"   {i}. {fix}")

            # 분석 메타데이터
            print(f"\n📋 분석 정보:")
            print(f"   ⏱️  분석 시간: {analysis_result['analysis_duration_seconds']:.3f}초")
            print(f"   📝 콘텐츠 길이: {analysis_result['content_length']}자")
            print(f"   🔤 단어 수: {analysis_result['content_word_count']}개")
            print(f"   📚 원본 리뷰: {'사용됨' if metadata['has_original_review'] else '사용 안됨'}")
            print(f"   🏷️  대상 키워드: {'사용됨' if metadata['has_target_keywords'] else '사용 안됨'}")
            print(f"   🏷️  카테고리: {metadata['category'] or '지정 안됨'}")

        else:
            print(f"\n❌ 통합 분석 실패:")
            print(f"   오류 유형: {analysis_result.get('error_type', 'Unknown')}")
            print(f"   오류 메시지: {analysis_result.get('error', 'No message')}")

        print(f"\n📁 생성된 파일:")
        print(f"   - {self.unified_report_path}")
        print(f"   - {self.logs_dir / 'unified_scorer_log.json'}")

    def display_quality_report(self, analysis_result: Dict[str, Any]):
        """사용자 친화적인 품질 보고서 출력"""
        if "error" not in analysis_result:
            try:
                from src.quality.unified_scorer import UnifiedQualityScorer
                scorer = UnifiedQualityScorer()
                report = scorer.get_quality_report(analysis_result)

                print("\n" + "=" * 90)
                print(report)
                print("=" * 90)

            except Exception as e:
                print(f"\n⚠️ 품질 보고서 생성 실패: {str(e)}")

    def run_full_analysis(self):
        """전체 통합 품질 분석 프로세스 실행"""
        try:
            print(f"\n🚀 실시간 품질 점수 계산 및 피드백 시스템 테스트 시작")
            print(f"   프로젝트 ID: {self.project_id}")
            print(f"   프로젝트 경로: {self.project_dir}")
            print("=" * 90)

            # 1. 사전 요구사항 확인
            if not self.check_prerequisites():
                print("\n❌ 사전 요구사항을 충족하지 않아 테스트를 중단합니다.")
                return

            # 2. 테스트 데이터 로드
            meta_data, blog_content, original_review, target_keywords = self.load_test_data()
            if not meta_data or not blog_content:
                print("\n❌ 테스트 데이터 로드에 실패하여 테스트를 중단합니다.")
                return

            category = meta_data.get("user_input", {}).get("category", "")

            # 3. 통합 품질 분석 실행
            analysis_result = self.run_unified_analysis(blog_content, original_review, target_keywords, category)
            if not analysis_result:
                print("\n❌ 통합 품질 분석에 실패했습니다.")
                return

            # 4. 결과 저장
            self.save_unified_report(analysis_result, meta_data, blog_content)

            # 5. 결과 출력
            self.display_results(analysis_result)

            # 6. 품질 보고서 출력
            self.display_quality_report(analysis_result)

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

    print(f"Phase 3 실시간 품질 점수 계산 및 피드백 시스템 테스트 - 프로젝트 ID: {project_id}")

    # 테스트 실행
    tester = UnifiedScorerTester(project_id)
    tester.run_full_analysis()


if __name__ == "__main__":
    main()