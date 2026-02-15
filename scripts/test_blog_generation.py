#!/usr/bin/env python3
"""
날짜 기반 블로그 글 생성 테스트 스크립트
새로운 yyyyMMdd 디렉토리 구조를 사용하여 블로그 포스트를 생성하고 품질을 검증합니다.

사용법:
    python3 scripts/test_blog_generation.py [date_directory]

예시:
    python3 scripts/test_blog_generation.py 20260212
    python3 scripts/test_blog_generation.py 20260212_2
    python3 scripts/test_blog_generation.py  # 가장 최근 세션 사용

환경 요구사항:
    - OPENAI_API_KEY 환경변수 설정 필요
    - 날짜 디렉토리에 ai_request.json 파일 존재 필요
"""

import sys
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

# 프로젝트 루트를 파이썬 경로에 추가 (scripts/ 아래로 이동했기 때문)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

try:
    from src.content.blog_generator import DateBasedBlogGenerator
    from src.storage.data_manager import data_manager
    from src.utils.logger import web_logger as logger
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some modules not available: {e}")
    MODULES_AVAILABLE = False


class DateBasedBlogTester:
    """날짜 기반 블로그 글 생성 테스트 클래스"""

    def __init__(self, date_directory: Optional[str] = None):
        self.date_directory = date_directory
        self.data_manager = data_manager if MODULES_AVAILABLE else None

        if self.date_directory:
            self.session_info = self.data_manager.get_posting_info(self.date_directory) if self.data_manager else None
        else:
            self.session_info = None

    def log_event(self, stage: str, status: str, message: str, **kwargs):
        """구조화된 로그 기록"""
        timestamp = datetime.now().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "stage": stage,
            "status": status,
            "message": message,
            "date_directory": self.date_directory,
            **kwargs
        }

        # 콘솔 출력
        print(f"[{timestamp}] {stage.upper()} - {status}: {message}")
        for key, value in kwargs.items():
            if value is not None:
                print(f"  └─ {key}: {value}")

        # 세션 로그에 기록 (data_manager를 통해)
        if self.data_manager and self.date_directory:
            self.data_manager.date_manager.append_log(
                self.date_directory,
                f"{stage.upper()} - {status}: {message}",
                "INFO" if status != "failed" else "ERROR"
            )

    def find_latest_session(self) -> Optional[str]:
        """가장 최근 포스팅 세션 찾기"""
        if not self.data_manager:
            return None

        try:
            all_sessions = self.data_manager.list_all_postings()

            # ai_request.json이 있는 세션들만 필터링
            ready_sessions = [
                s for s in all_sessions
                if s.get('status') == 'ai_ready' or
                self.data_manager.get_posting_info(s['date_directory'])['directory_info']['has_ai_request']
            ]

            if ready_sessions:
                # 가장 최근 세션 반환
                latest = max(ready_sessions, key=lambda x: x['created_at'])
                return latest['date_directory']

            return None

        except Exception as e:
            print(f"최근 세션 찾기 실패: {e}")
            return None

    def check_prerequisites(self) -> bool:
        """사전 요구사항 확인"""
        self.log_event("prerequisites", "info", "사전 요구사항 확인 시작")

        # 1. 모듈 가용성 확인
        if not MODULES_AVAILABLE:
            self.log_event("prerequisites", "failed", "필요 모듈이 설치되지 않았습니다")
            return False

        # 2. OpenAI API 키 확인
        openai_key = os.getenv('OPENAI_API_KEY')
        if not openai_key:
            self.log_event("prerequisites", "failed", "OPENAI_API_KEY 환경변수가 설정되지 않았습니다")
            return False

        self.log_event("prerequisites", "info", "OpenAI API 키 확인됨", key_length=len(openai_key))

        # 3. 날짜 디렉토리 자동 결정 (제공되지 않은 경우)
        if not self.date_directory:
            self.date_directory = self.find_latest_session()
            if not self.date_directory:
                self.log_event("prerequisites", "failed", "사용 가능한 세션이 없습니다")
                return False

            self.log_event("prerequisites", "info", f"자동 선택된 세션: {self.date_directory}")

        # 4. 세션 정보 로드
        self.session_info = self.data_manager.get_posting_info(self.date_directory)
        if not self.session_info:
            self.log_event("prerequisites", "failed", f"세션 정보를 찾을 수 없습니다: {self.date_directory}")
            return False

        # 5. AI 요청 데이터 확인
        if not self.session_info["directory_info"]["has_ai_request"]:
            self.log_event("prerequisites", "failed", f"ai_request.json 파일이 없습니다: {self.date_directory}")
            return False

        self.log_event("prerequisites", "completed", "모든 사전 요구사항이 충족되었습니다")
        return True

    def generate_blog_post(self) -> Dict[str, Any]:
        """실제 블로그 포스트 생성"""
        self.log_event("blog_generation", "info", "날짜 기반 블로그 포스트 생성 시작")

        try:
            # DateBasedBlogGenerator 초기화
            blog_generator = DateBasedBlogGenerator()

            # 블로그 포스트 생성 및 저장
            result = blog_generator.generate_and_save_blog_post(self.date_directory)

            if result["success"]:
                metadata = result["metadata"]
                quality = result["quality_metrics"]

                self.log_event("blog_generation", "completed", "블로그 포스트 생성 성공",
                              tokens_used=metadata["total_tokens"],
                              content_length=metadata["actual_length"],
                              quality_score=quality["quality_score"],
                              blog_file=result["blog_file_path"])
                return result
            else:
                self.log_event("blog_generation", "failed", f"생성 실패: {result['error']}")
                return result

        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "date_directory": self.date_directory,
                "timestamp": datetime.now().isoformat()
            }
            self.log_event("blog_generation", "failed", f"예외 발생: {str(e)}")
            return error_result

    def display_results(self, generation_result: Dict[str, Any]):
        """결과 화면 출력"""
        print("\n" + "=" * 70)
        print("🎉 날짜 기반 블로그 글 생성 완료!")
        print("=" * 70)

        print(f"\n📂 세션 정보:")
        print(f"   📅 날짜 디렉토리: {self.date_directory}")

        if self.session_info and self.session_info["metadata"]:
            metadata = self.session_info["metadata"]
            print(f"   📝 카테고리: {metadata['user_input']['category']}")
            print(f"   🗓️  방문일: {metadata['user_input']['visit_date']}")
            print(f"   👥 동행자: {metadata['user_input'].get('companion', 'N/A')}")
            print(f"   📸 이미지 수: {len(metadata.get('images', []))}")

        if generation_result.get("success"):
            content = generation_result["generated_content"]
            metadata = generation_result["metadata"]
            quality = generation_result["quality_metrics"]

            print(f"\n📝 생성된 블로그 포스트:")
            print("-" * 50)
            print(content)
            print("-" * 50)

            print(f"\n📊 생성 정보:")
            print(f"   🤖 사용 모델: {metadata['model_used']}")
            print(f"   🎯 목표 길이: {metadata['target_length']}자")
            print(f"   📏 실제 길이: {metadata['actual_length']}자")
            print(f"   💰 사용 토큰: {metadata['total_tokens']}개 (프롬프트: {metadata['prompt_tokens']}, 완료: {metadata['completion_tokens']})")

            print(f"\n🔍 품질 지표:")
            print(f"   📈 전체 품질 점수: {quality['quality_score']}점")
            print(f"   🎭 경험 재현률: {quality['experience_overlap_ratio']*100:.1f}%")
            print(f"   🏷️  해시태그 포함률: {quality['hashtag_inclusion_rate']*100:.1f}%")
            print(f"   🤖 AI 전형 표현: {quality['ai_expression_count']}개")
            print(f"   📄 문단 수: {quality['paragraph_count']}개")

        else:
            print(f"\n❌ 생성 실패:")
            print(f"   오류 유형: {generation_result.get('error_type', 'Unknown')}")
            print(f"   오류 메시지: {generation_result.get('error', 'No message')}")

        print(f"\n📁 관련 파일:")
        if self.session_info:
            dir_info = self.session_info["directory_info"]
            print(f"   📂 세션 디렉토리: {dir_info['directory_path']}")
            print(f"   📋 metadata.json: {'✅' if dir_info['has_metadata'] else '❌'}")
            print(f"   🤖 ai_request.json: {'✅' if dir_info['has_ai_request'] else '❌'}")
            print(f"   📝 blog_result.md: {'✅' if dir_info['has_blog_result'] else '❌'}")
            print(f"   📜 log.txt: {'✅' if dir_info['has_log'] else '❌'}")

        if generation_result.get("success"):
            print(f"   💾 저장 파일: {generation_result['blog_file_path']}")

    def run_full_generation(self):
        """전체 블로그 생성 프로세스 실행"""
        try:
            print(f"\n🚀 날짜 기반 블로그 글 생성 테스트 시작")
            if self.date_directory:
                print(f"   📅 대상 세션: {self.date_directory}")
            else:
                print(f"   🔍 최신 세션 자동 선택")
            print("=" * 70)

            # 1. 사전 요구사항 확인
            if not self.check_prerequisites():
                print("\n❌ 사전 요구사항을 충족하지 않아 테스트를 중단합니다.")
                return

            # 2. 블로그 포스트 생성
            generation_result = self.generate_blog_post()
            if not generation_result:
                print("\n❌ 블로그 포스트 생성에 실패했습니다.")
                return

            # 3. 결과 출력
            self.display_results(generation_result)

            self.log_event("full_process", "completed", "전체 프로세스 성공적으로 완료")

        except Exception as e:
            self.log_event("full_process", "failed", f"전체 프로세스 실행 실패: {str(e)}")
            print(f"\n❌ 전체 프로세스 실행 실패: {str(e)}")
            raise


def main():
    """메인 실행 함수"""
    # 명령행 인수 처리
    if len(sys.argv) > 1:
        date_directory = sys.argv[1]
    else:
        date_directory = None

    print(f"날짜 기반 블로그 글 생성 테스트")
    if date_directory:
        print(f"대상 세션: {date_directory}")
    else:
        print("최신 세션 자동 선택")

    # 환경변수 확인 안내
    if not os.getenv('OPENAI_API_KEY'):
        print("\n⚠️  OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        print("   다음 명령어로 설정하세요:")
        print("   export OPENAI_API_KEY='your-api-key-here'")
        print("   또는 .env 파일에 OPENAI_API_KEY=your-api-key-here 추가\n")

    # 테스트 실행
    tester = DateBasedBlogTester(date_directory)
    tester.run_full_generation()


if __name__ == "__main__":
    main()

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
        log_file = self.logs_dir / "blog_generation_log.json"

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

        # 2. OpenAI API 키 확인
        openai_key = os.getenv('OPENAI_API_KEY')
        if not openai_key:
            self.log_event("prerequisites", "failed", "OPENAI_API_KEY 환경변수가 설정되지 않았습니다")
            return False

        self.log_event("prerequisites", "info", "OpenAI API 키 확인됨", key_length=len(openai_key))

        # 3. generation_ready.json 파일 존재 확인
        if not self.generation_ready_path.exists():
            self.log_event("prerequisites", "failed", f"generation_ready.json 파일이 없습니다: {self.generation_ready_path}")
            return False

        self.log_event("prerequisites", "completed", "모든 사전 요구사항이 충족되었습니다")
        return True

    def load_generation_data(self) -> Optional[Dict[str, Any]]:
        """generation_ready.json 로드"""
        self.log_event("data_loading", "info", f"generation_ready.json 로드 중: {self.generation_ready_path}")

        try:
            with open(self.generation_ready_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.log_event("data_loading", "completed", "데이터 로드 성공",
                          project_id=data.get("project_id"),
                          target_length=data.get("generation_settings", {}).get("target_length"))

            return data

        except Exception as e:
            self.log_event("data_loading", "failed", f"데이터 로드 실패: {str(e)}")
            return None

    def generate_blog_post(self, generation_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """실제 블로그 포스트 생성"""
        self.log_event("blog_generation", "info", "OpenAI API를 사용한 블로그 포스트 생성 시작")

        try:
            # BlogContentGenerator 초기화
            generator = BlogContentGenerator()

            # 블로그 포스트 생성
            result = generator.generate_blog_post(generation_data)

            if result["success"]:
                metadata = result["metadata"]
                quality = result["quality_metrics"]

                self.log_event("blog_generation", "completed", "블로그 포스트 생성 성공",
                              tokens_used=metadata["total_tokens"],
                              content_length=metadata["actual_length"],
                              quality_score=quality["quality_score"])
                return result
            else:
                self.log_event("blog_generation", "failed", f"생성 실패: {result['error']}")
                return result

        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": datetime.now().isoformat()
            }
            self.log_event("blog_generation", "failed", f"예외 발생: {str(e)}")
            return error_result

    def save_generated_content(self, generation_result: Dict[str, Any]):
        """생성된 블로그 포스트 저장"""
        self.log_event("content_saving", "info", f"생성된 콘텐츠 저장 중: {self.output_path}")

        try:
            # 저장용 데이터 구성
            output_data = {
                "project_id": self.project_id,
                "generation_timestamp": datetime.now().isoformat(),
                "generation_result": generation_result,
                "file_info": {
                    "input_file": str(self.generation_ready_path),
                    "output_file": str(self.output_path),
                    "log_file": str(self.logs_dir / "blog_generation_log.json")
                }
            }

            with open(self.output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2, default=str)

            # 텍스트 파일로도 저장 (읽기 편의를 위해)
            if generation_result.get("success"):
                text_output_path = self.project_dir / "generated_blog.txt"
                with open(text_output_path, 'w', encoding='utf-8') as f:
                    f.write(generation_result["generated_content"])

                self.log_event("content_saving", "completed", "콘텐츠 저장 성공",
                              json_file=str(self.output_path),
                              text_file=str(text_output_path))
            else:
                self.log_event("content_saving", "completed", "실패 정보 저장 완료")

        except Exception as e:
            self.log_event("content_saving", "failed", f"저장 실패: {str(e)}")

    def display_results(self, generation_result: Dict[str, Any]):
        """결과 화면 출력"""
        print("\n" + "=" * 70)
        print("🎉 블로그 글 생성 완료!")
        print("=" * 70)

        if generation_result.get("success"):
            content = generation_result["generated_content"]
            metadata = generation_result["metadata"]
            quality = generation_result["quality_metrics"]

            print(f"\n📝 생성된 블로그 포스트:")
            print("-" * 50)
            print(content)
            print("-" * 50)

            print(f"\n📊 생성 정보:")
            print(f"   🤖 사용 모델: {metadata['model_used']}")
            print(f"   🎯 목표 길이: {metadata['target_length']}자")
            print(f"   📏 실제 길이: {metadata['actual_length']}자")
            print(f"   💰 사용 토큰: {metadata['total_tokens']}개 (프롬프트: {metadata['prompt_tokens']}, 완료: {metadata['completion_tokens']})")

            print(f"\n🔍 품질 지표:")
            print(f"   📈 전체 품질 점수: {quality['quality_score']}점")
            print(f"   🎭 경험 재현률: {quality['experience_overlap_ratio']*100:.1f}%")
            print(f"   🏷️  해시태그 포함률: {quality['hashtag_inclusion_rate']*100:.1f}%")
            print(f"   🤖 AI 전형 표현: {quality['ai_expression_count']}개")
            print(f"   📄 문단 수: {quality['paragraph_count']}개")

        else:
            print(f"\n❌ 생성 실패:")
            print(f"   오류 유형: {generation_result.get('error_type', 'Unknown')}")
            print(f"   오류 메시지: {generation_result.get('error', 'No message')}")

        print(f"\n📁 생성된 파일:")
        print(f"   - {self.output_path}")
        if generation_result.get("success"):
            print(f"   - {self.project_dir / 'generated_blog.txt'}")
        print(f"   - {self.logs_dir / 'blog_generation_log.json'}")

    def run_full_generation(self):
        """전체 블로그 생성 프로세스 실행"""
        try:
            print(f"\n🚀 블로그 글 생성 테스트 시작")
            print(f"   프로젝트 ID: {self.project_id}")
            print(f"   프로젝트 경로: {self.project_dir}")
            print("=" * 70)

            # 1. 사전 요구사항 확인
            if not self.check_prerequisites():
                print("\n❌ 사전 요구사항을 충족하지 않아 테스트를 중단합니다.")
                return

            # 2. 생성용 데이터 로드
            generation_data = self.load_generation_data()
            if not generation_data:
                print("\n❌ 데이터 로드에 실패하여 테스트를 중단합니다.")
                return

            # 3. 블로그 포스트 생성
            generation_result = self.generate_blog_post(generation_data)
            if not generation_result:
                print("\n❌ 블로그 포스트 생성에 실패했습니다.")
                return

            # 4. 결과 저장
            self.save_generated_content(generation_result)

            # 5. 결과 출력
            self.display_results(generation_result)

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

    print(f"Phase 2 블로그 글 생성 테스트 - 프로젝트 ID: {project_id}")

    # 환경변수 확인 안내
    if not os.getenv('OPENAI_API_KEY'):
        print("\n⚠️  OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        print("   다음 명령어로 설정하세요:")
        print("   export OPENAI_API_KEY='your-api-key-here'")
        print("   또는 .env 파일에 OPENAI_API_KEY=your-api-key-here 추가\n")

    # 테스트 실행
    tester = BlogGenerationTester(project_id)
    tester.run_full_generation()


if __name__ == "__main__":
    main()