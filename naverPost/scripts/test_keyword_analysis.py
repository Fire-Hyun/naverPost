#!/usr/bin/env python3
"""
키워드 밀도 및 문장 구조 분석 테스트 스크립트
블로그 콘텐츠의 키워드 밀도와 분포 패턴을 분석합니다.

사용법:
    python3 scripts/test_keyword_analysis.py [project_id]

예시:
    python3 scripts/test_keyword_analysis.py 20260207
    python3 scripts/test_keyword_analysis.py  # 기본값: 20260207 사용
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
    from src.quality.keyword_analyzer import KeywordDensityAnalyzer
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some modules not available: {e}")
    MODULES_AVAILABLE = False


class KeywordAnalysisTester:
    """키워드 분석 테스트 클래스"""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.project_dir = Path(f"data/{project_id}")
        self.generated_blog_path = self.project_dir / "generated_blog.txt"
        self.keyword_report_path = self.project_dir / "keyword_analysis_report.json"
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
        log_file = self.logs_dir / "keyword_analysis_log.json"

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

    def extract_hashtags_as_keywords(self, content: str) -> Optional[list]:
        """해시태그에서 키워드 추출"""
        import re
        hashtags = re.findall(r'#([가-힣a-zA-Z0-9_]+)', content)

        # 한글 해시태그만 추출하고 정리
        korean_keywords = []
        for tag in hashtags:
            # 한글이 포함된 태그만 선택
            if re.search(r'[가-힣]', tag):
                # '맛집', '카페', '강추' 등의 의미 있는 키워드 추출
                clean_keyword = re.sub(r'[a-zA-Z0-9_]', '', tag)  # 영문/숫자 제거
                if len(clean_keyword) >= 2:  # 2글자 이상만
                    korean_keywords.append(clean_keyword)

        return korean_keywords if korean_keywords else None

    def run_keyword_analysis(self, content: str) -> Optional[Dict[str, Any]]:
        """키워드 분석 실행"""
        self.log_event("keyword_analysis", "info", "키워드 밀도 분석 시작")

        try:
            # KeywordDensityAnalyzer 초기화
            analyzer = KeywordDensityAnalyzer()

            # 해시태그에서 키워드 추출
            target_keywords = self.extract_hashtags_as_keywords(content)

            if target_keywords:
                self.log_event("keyword_extraction", "info", f"대상 키워드 추출: {', '.join(target_keywords)}")
                # 특정 키워드 분석
                analysis_result = analyzer.analyze_keyword_density(content, target_keywords)
            else:
                self.log_event("keyword_extraction", "info", "자동 키워드 추출 모드")
                # 자동 키워드 분석
                analysis_result = analyzer.analyze_keyword_density(content)

            quality_score = analysis_result["quality_score"]

            self.log_event("keyword_analysis", "completed", "키워드 분석 완료",
                          overall_score=quality_score["overall_score"],
                          rating=quality_score["rating"],
                          passed=quality_score["passed"])

            return analysis_result

        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": datetime.now().isoformat()
            }
            self.log_event("keyword_analysis", "failed", f"키워드 분석 실패: {str(e)}")
            return error_result

    def save_keyword_report(self, analysis_result: Dict[str, Any], original_content: str):
        """키워드 분석 결과 저장"""
        self.log_event("report_saving", "info", f"키워드 분석 보고서 저장 중: {self.keyword_report_path}")

        try:
            # 저장용 데이터 구성
            report_data = {
                "project_id": self.project_id,
                "analysis_timestamp": datetime.now().isoformat(),
                "original_content": original_content,
                "analysis_result": analysis_result,
                "file_info": {
                    "blog_file": str(self.generated_blog_path),
                    "report_file": str(self.keyword_report_path),
                    "log_file": str(self.logs_dir / "keyword_analysis_log.json")
                }
            }

            with open(self.keyword_report_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)

            self.log_event("report_saving", "completed", "키워드 분석 보고서 저장 성공")

        except Exception as e:
            self.log_event("report_saving", "failed", f"보고서 저장 실패: {str(e)}")

    def display_results(self, analysis_result: Dict[str, Any]):
        """결과 화면 출력"""
        print("\n" + "=" * 80)
        print("🔍 키워드 밀도 및 문장 구조 분석 완료!")
        print("=" * 80)

        if "error" not in analysis_result:
            content_stats = analysis_result["content_stats"]
            quality_score = analysis_result["quality_score"]
            keyword_analysis = analysis_result["keyword_analysis"]
            density_evaluation = analysis_result["density_evaluation"]
            distribution_analysis = analysis_result["distribution_analysis"]

            # 종합 결과
            print(f"\n📊 종합 평가:")
            print(f"   🎯 품질 점수: {quality_score['overall_score']:.2f} ({quality_score['rating']})")
            print(f"   📈 밀도 점수: {quality_score['density_score']:.2f}")
            print(f"   📊 분포 점수: {quality_score['distribution_score']:.2f}")
            print(f"   ✅ 통과 여부: {'통과' if quality_score['passed'] else '미통과'}")

            # 콘텐츠 통계
            print(f"\n📝 콘텐츠 통계:")
            print(f"   📄 총 단어 수: {content_stats['total_words']}개")
            print(f"   🔤 고유 단어 수: {content_stats['unique_words']}개")
            print(f"   📊 어휘 다양성: {content_stats['lexical_diversity']:.1%}")
            print(f"   📏 글자 수: {content_stats['content_length']}자")

            # 키워드 분석
            keywords = keyword_analysis["keywords"]
            print(f"\n🔑 키워드 분석:")
            print(f"   📋 분석 방식: {'타겟 키워드' if keyword_analysis['method'] == 'target_keywords' else '자동 추출'}")
            print(f"   🔍 키워드 수: {len(keywords)}개")
            print(f"   📊 평균 밀도: {keyword_analysis['average_density']:.1%}")

            # 상위 키워드 밀도
            if keywords:
                print(f"   📈 키워드별 밀도:")
                sorted_keywords = sorted(keywords.items(), key=lambda x: x[1]["density"], reverse=True)
                for i, (keyword, data) in enumerate(sorted_keywords[:5], 1):  # 상위 5개
                    risk_color = "🔴" if data["density"] > 0.03 else "🟡" if data["density"] > 0.02 else "🟢"
                    print(f"      {i}. {keyword}: {data['density']:.1%} ({data['count']}회) {risk_color}")

            # 밀도 평가
            print(f"\n⚠️  밀도 평가:")
            print(f"   🔺 최고 밀도: {density_evaluation['max_density']:.1%}")
            print(f"   📊 평균 밀도: {density_evaluation['average_density']:.1%}")
            print(f"   ⚠️  위험도: {density_evaluation['overall_risk']}")

            # 분포 분석
            print(f"\n📍 분포 분석:")
            print(f"   📊 패턴: {distribution_analysis['pattern']}")
            print(f"   ⚖️  균등성: {distribution_analysis['evenness']:.2f}")
            print(f"   📈 커버리지: {distribution_analysis['coverage_ratio']:.1%}")
            print(f"   📝 키워드 포함 문장: {distribution_analysis['sentences_with_keywords']}/{distribution_analysis['total_sentences']}개")

            # 위험 키워드
            high_risk_keywords = [
                keyword for keyword, eval_data in density_evaluation["keyword_evaluations"].items()
                if eval_data["risk_level"] in ["HIGH", "CRITICAL"]
            ]

            if high_risk_keywords:
                print(f"\n🚨 주의 필요 키워드:")
                for keyword in high_risk_keywords:
                    eval_data = density_evaluation["keyword_evaluations"][keyword]
                    print(f"   • {keyword}: {eval_data['density']:.1%} ({eval_data['risk_level']}) - {eval_data['recommendation']}")

            # 개선 권장사항
            recommendations = analysis_result["recommendations"]
            if recommendations:
                print(f"\n💡 개선 권장사항:")
                for i, rec in enumerate(recommendations, 1):
                    print(f"   {i}. {rec}")

            # 단어 빈도 TOP 5
            word_frequency = analysis_result["word_frequency"]
            if word_frequency["most_frequent"]:
                print(f"\n📊 최고 빈도 단어 TOP 5:")
                for i, word_data in enumerate(word_frequency["most_frequent"][:5], 1):
                    print(f"   {i}. {word_data['word']}: {word_data['frequency']:.1%} ({word_data['count']}회)")

        else:
            print(f"\n❌ 분석 실패:")
            print(f"   오류 유형: {analysis_result.get('error_type', 'Unknown')}")
            print(f"   오류 메시지: {analysis_result.get('error', 'No message')}")

        print(f"\n📁 생성된 파일:")
        print(f"   - {self.keyword_report_path}")
        print(f"   - {self.logs_dir / 'keyword_analysis_log.json'}")

    def run_full_analysis(self):
        """전체 키워드 분석 프로세스 실행"""
        try:
            print(f"\n🔍 키워드 밀도 및 문장 구조 분석 테스트 시작")
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

            # 3. 키워드 분석 실행
            analysis_result = self.run_keyword_analysis(content)
            if not analysis_result:
                print("\n❌ 키워드 분석에 실패했습니다.")
                return

            # 4. 결과 저장
            self.save_keyword_report(analysis_result, content)

            # 5. 결과 출력
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

    print(f"Phase 3 키워드 밀도 및 문장 구조 분석 테스트 - 프로젝트 ID: {project_id}")

    # 테스트 실행
    tester = KeywordAnalysisTester(project_id)
    tester.run_full_analysis()


if __name__ == "__main__":
    main()