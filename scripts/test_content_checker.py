#!/usr/bin/env python3
"""
개인 경험 비율 자동 검증 시스템 테스트 스크립트
콘텐츠의 개인 경험 비율을 분석하여 자연스러운 개인 후기의 특성을 평가합니다.

사용법:
    python3 scripts/test_content_checker.py [project_id]

예시:
    python3 scripts/test_content_checker.py 20260207
    python3 scripts/test_content_checker.py  # 기본값: 20260207 사용
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
    from src.quality.content_checker import ContentQualityChecker
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some modules not available: {e}")
    MODULES_AVAILABLE = False


class ContentCheckerTester:
    """개인 경험 비율 분석 테스트 클래스"""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.project_dir = Path(f"data/{project_id}")
        self.meta_path = self.project_dir / "meta.json"
        self.generated_blog_path = self.project_dir / "generated_blog.txt"
        self.content_analysis_report_path = self.project_dir / "content_analysis_report.json"
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
        log_file = self.logs_dir / "content_checker_log.json"

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

    def load_data(self) -> tuple[Optional[Dict], Optional[str]]:
        """메타 데이터와 블로그 콘텐츠 로드"""
        self.log_event("data_loading", "info", "데이터 로드 시작")

        try:
            # 메타 데이터 로드
            with open(self.meta_path, 'r', encoding='utf-8') as f:
                meta_data = json.load(f)

            # 블로그 콘텐츠 로드
            with open(self.generated_blog_path, 'r', encoding='utf-8') as f:
                blog_content = f.read().strip()

            self.log_event("data_loading", "completed", "데이터 로드 성공",
                          meta_data_keys=list(meta_data.keys()),
                          blog_content_length=len(blog_content))

            return meta_data, blog_content

        except Exception as e:
            self.log_event("data_loading", "failed", f"데이터 로드 실패: {str(e)}")
            return None, None

    def run_content_analysis(self, original_experience: str, generated_content: str) -> Optional[Dict[str, Any]]:
        """개인 경험 비율 분석 실행"""
        self.log_event("content_analysis", "info", "개인 경험 비율 분석 시작")

        try:
            # ContentQualityChecker 초기화
            checker = ContentQualityChecker()

            # 개인 경험 비율 분석
            analysis_result = checker.analyze_personal_experience_ratio(
                original_experience,
                generated_content
            )

            overall_evaluation = analysis_result["overall_evaluation"]

            self.log_event("content_analysis", "completed", "개인 경험 비율 분석 완료",
                          weighted_score=overall_evaluation["weighted_score"],
                          quality_grade=overall_evaluation["quality_grade"],
                          passed=overall_evaluation["passed"])

            return analysis_result

        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": datetime.now().isoformat()
            }
            self.log_event("content_analysis", "failed", f"개인 경험 비율 분석 실패: {str(e)}")
            return error_result

    def save_analysis_report(self, analysis_result: Dict[str, Any], meta_data: Dict, blog_content: str):
        """분석 결과 저장"""
        self.log_event("report_saving", "info", f"분석 보고서 저장 중: {self.content_analysis_report_path}")

        try:
            # 저장용 데이터 구성
            report_data = {
                "project_id": self.project_id,
                "analysis_timestamp": datetime.now().isoformat(),
                "meta_data": meta_data,
                "generated_content": blog_content,
                "analysis_result": analysis_result,
                "file_info": {
                    "meta_file": str(self.meta_path),
                    "blog_file": str(self.generated_blog_path),
                    "report_file": str(self.content_analysis_report_path),
                    "log_file": str(self.logs_dir / "content_checker_log.json")
                }
            }

            with open(self.content_analysis_report_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)

            self.log_event("report_saving", "completed", "분석 보고서 저장 성공")

        except Exception as e:
            self.log_event("report_saving", "failed", f"보고서 저장 실패: {str(e)}")

    def display_results(self, analysis_result: Dict[str, Any]):
        """결과 화면 출력"""
        print("\n" + "=" * 80)
        print("🔍 개인 경험 비율 자동 검증 완료!")
        print("=" * 80)

        if "error" not in analysis_result:
            overall_eval = analysis_result['overall_evaluation']
            similarity = analysis_result['similarity_analysis']
            personal_exp = analysis_result['personal_expression_analysis']
            experience_ref = analysis_result['experience_reflection_analysis']
            emotion = analysis_result['emotion_analysis']
            specificity = analysis_result['specificity_analysis']

            # 종합 결과
            print(f"\n📊 종합 평가:")
            print(f"   🎯 종합 점수: {overall_eval['weighted_score']:.3f}")
            print(f"   📈 품질 등급: {overall_eval['quality_grade']}")
            print(f"   ✅ 통과 여부: {'통과' if overall_eval['passed'] else '미통과'}")
            print(f"   🏛️  네이버 준수: {'준수' if overall_eval['naver_compliance'] else '미준수'}")

            # 세부 점수
            scores = overall_eval["individual_scores"]
            weights = overall_eval["weights"]
            print(f"\n📈 세부 점수:")
            print(f"   📝 유사도 점수: {scores['similarity']:.3f} ({weights['similarity']:.0%})")
            print(f"   👤 개인표현 점수: {scores['personal_expression']:.3f} ({weights['personal_expression']:.0%})")
            print(f"   💭 경험반영 점수: {scores['experience_reflection']:.3f} ({weights['experience_reflection']:.0%})")
            print(f"   ❤️  감정진정성 점수: {scores['emotion_authenticity']:.3f} ({weights['emotion_authenticity']:.0%})")
            print(f"   🔍 구체성 점수: {scores['specificity']:.3f} ({weights['specificity']:.0%})")

            # 세부 분석
            print(f"\n🔍 세부 분석:")
            print(f"   📊 전체 텍스트 유사도: {similarity['overall_similarity']:.1%}")
            print(f"   🔗 단어 중복 비율: {similarity['word_overlap_ratio']:.1%}")
            print(f"   📝 공통 단어: {similarity['common_word_count']}개")
            print(f"   👤 개인 표현 비율: {personal_exp['personal_ratio']:.1%}")
            print(f"   📖 객관 표현 비율: {personal_exp['objective_ratio']:.1%}")
            print(f"   💭 경험 반영 비율: {experience_ref['overall_reflection_ratio']:.1%}")
            print(f"   ❤️  감정 진정성: {emotion['emotional_authenticity_score']:.3f}")
            print(f"   🔍 구체성 유지: {specificity['specificity_maintenance']:.3f}")

            # 개선 권장사항
            recommendations = analysis_result.get("recommendations", [])
            if recommendations:
                print(f"\n💡 개선 권장사항:")
                for i, rec in enumerate(recommendations, 1):
                    print(f"   {i}. {rec}")

        else:
            print(f"\n❌ 분석 실패:")
            print(f"   오류 유형: {analysis_result.get('error_type', 'Unknown')}")
            print(f"   오류 메시지: {analysis_result.get('error', 'No message')}")

        print(f"\n📁 생성된 파일:")
        print(f"   - {self.content_analysis_report_path}")
        print(f"   - {self.logs_dir / 'content_checker_log.json'}")

    def run_full_analysis(self):
        """전체 개인 경험 비율 분석 프로세스 실행"""
        try:
            print(f"\n🔍 개인 경험 비율 자동 검증 테스트 시작")
            print(f"   프로젝트 ID: {self.project_id}")
            print(f"   프로젝트 경로: {self.project_dir}")
            print("=" * 80)

            # 1. 사전 요구사항 확인
            if not self.check_prerequisites():
                print("\n❌ 사전 요구사항을 충족하지 않아 테스트를 중단합니다.")
                return

            # 2. 데이터 로드
            meta_data, blog_content = self.load_data()
            if not meta_data or not blog_content:
                print("\n❌ 데이터 로드에 실패하여 테스트를 중단합니다.")
                return

            # 3. 원본 경험 추출
            original_experience = meta_data.get("user_input", {}).get("personal_review", "")
            if not original_experience:
                print("\n❌ 원본 사용자 경험 정보가 없습니다.")
                return

            # 4. 개인 경험 비율 분석 실행
            analysis_result = self.run_content_analysis(original_experience, blog_content)
            if not analysis_result:
                print("\n❌ 개인 경험 비율 분석에 실패했습니다.")
                return

            # 5. 결과 저장
            self.save_analysis_report(analysis_result, meta_data, blog_content)

            # 6. 결과 출력
            self.display_results(analysis_result)

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

    print(f"Phase 3 개인 경험 비율 자동 검증 테스트 - 프로젝트 ID: {project_id}")

    # 테스트 실행
    tester = ContentCheckerTester(project_id)
    tester.run_full_analysis()


if __name__ == "__main__":
    main()