#!/usr/bin/env python3
"""
통합 워크플로우 테스트 스크립트
블로그 생성부터 네이버 임시저장까지 전체 워크플로우를 테스트합니다.
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.services.blog_workflow import get_blog_workflow_service, WorkflowProgress, WorkflowStatus


def setup_logging():
    """로깅 설정"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('test_workflow.log')
        ]
    )


def progress_callback(progress: WorkflowProgress):
    """진행상황 콜백"""
    status_emoji = {
        WorkflowStatus.PENDING: "⏳",
        WorkflowStatus.VALIDATING: "🔍",
        WorkflowStatus.GENERATING_BLOG: "🤖",
        WorkflowStatus.QUALITY_CHECKING: "📊",
        WorkflowStatus.UPLOADING_TO_NAVER: "📤",
        WorkflowStatus.COMPLETED: "✅",
        WorkflowStatus.FAILED: "❌",
        WorkflowStatus.CANCELLED: "⏹️"
    }.get(progress.status, "⏳")

    print(f"{status_emoji} [{progress.current_step}/{progress.total_steps}] {progress.step_name}")
    print(f"    {progress.message} ({progress.progress_percentage:.1f}%)")
    print()


async def test_complete_workflow():
    """완전한 워크플로우 테스트"""
    print("🚀 통합 워크플로우 테스트 시작")
    print("=" * 60)

    # 테스트 데이터 준비
    test_date = datetime.now().strftime("%Y%m%d")
    test_user_experience = {
        "category": "맛집",
        "store_name": "스타벅스 강남역점",
        "personal_review": (
            "오늘 스타벅스 강남역점에 갔는데 정말 만족스러웠습니다. "
            "평소에 자주 가던 곳이라 친숙했지만 오늘은 새로운 메뉴를 시도해봤어요. "
            "아이스 아메리카노와 샌드위치를 주문했는데 맛이 훌륭했습니다. "
            "직원분들도 친절하시고 매장 분위기도 좋아서 편안하게 시간을 보낼 수 있었어요. "
            "다음에도 꼭 다시 방문할 예정입니다."
        ),
        "ai_additional_script": "분위기가 좋은 카페로 추천하고 싶습니다.",
        "visit_date": test_date,
        "rating": 5,
        "companion": "친구",
        "location": "서울시 강남구",
        "hashtags": ["#스타벅스", "#강남", "#카페"]
    }

    # 워크플로우 서비스 가져오기
    workflow_service = get_blog_workflow_service()

    print(f"📝 테스트 데이터:")
    print(f"  - 날짜: {test_date}")
    print(f"  - 카테고리: {test_user_experience['category']}")
    print(f"  - 상호명: {test_user_experience['store_name']}")
    print(f"  - 감상평 길이: {len(test_user_experience['personal_review'])}자")
    print()

    try:
        # 워크플로우 실행
        result = await workflow_service.process_complete_workflow(
            date_directory=test_date,
            user_experience=test_user_experience,
            images=None,  # 테스트에서는 이미지 제외
            auto_upload=False,  # 테스트에서는 네이버 업로드 제외
            progress_callback=progress_callback
        )

        print("📋 최종 결과:")
        print(f"  - 상태: {result.status.value}")
        print(f"  - 메시지: {result.message}")

        if result.end_time:
            duration = (result.end_time - result.start_time).total_seconds()
            print(f"  - 소요 시간: {duration:.1f}초")

        # 결과 상세 출력
        if result.results:
            print("\n📊 세부 결과:")

            # 검증 결과
            if 'validation' in result.results:
                validation = result.results['validation']
                print(f"  🔍 검증: 성공")
                print(f"    - 검증된 필드: {len(validation.get('validated_fields', []))}개")
                print(f"    - 감상평 길이: {validation.get('review_length', 0)}자")

            # 세션 결과
            if 'session' in result.results:
                session = result.results['session']
                print(f"  💾 세션: 성공")
                print(f"    - 디렉토리: {session.get('directory', 'N/A')}")
                print(f"    - 저장된 이미지: {session.get('saved_images', 0)}개")

            # 생성 결과
            if 'generation' in result.results:
                generation = result.results['generation']
                print(f"  🤖 생성: 성공")
                print(f"    - 블로그 파일: {generation.get('blog_file', 'N/A')}")
                print(f"    - 글자 수: {generation.get('length', 0)}자")

            # 품질 검증 결과
            if 'quality' in result.results:
                quality = result.results['quality']
                print(f"  📊 품질: 성공")
                print(f"    - 전체 점수: {quality.get('overall_score', 0):.2f}")
                print(f"    - 등급: {quality.get('grade', 'N/A')}")

                detailed = quality.get('detailed_scores', {})
                if detailed:
                    print("    - 세부 점수:")
                    for key, value in detailed.items():
                        print(f"      • {key}: {value:.2f}")

            # 업로드 결과
            if 'upload' in result.results:
                upload = result.results['upload']
                if upload.get('success'):
                    print(f"  📤 업로드: 성공")
                    print(f"    - 디렉토리: {upload.get('directory', 'N/A')}")
                else:
                    print(f"  📤 업로드: 실패")
                    print(f"    - 오류: {upload.get('error', 'N/A')}")

        # 생성된 파일 확인
        if result.results.get('session', {}).get('directory'):
            data_dir = Path(result.results['session']['directory'])
            if data_dir.exists():
                print(f"\n📁 생성된 파일들:")
                for file_path in data_dir.glob('*'):
                    if file_path.is_file():
                        size = file_path.stat().st_size
                        print(f"  - {file_path.name}: {size:,} bytes")

        if result.status == WorkflowStatus.COMPLETED:
            print("\n🎉 워크플로우 테스트 성공!")
            return True
        else:
            print(f"\n❌ 워크플로우 테스트 실패: {result.message}")
            return False

    except Exception as e:
        print(f"\n💥 테스트 실행 중 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_workflow_validation():
    """워크플로우 입력 검증 테스트"""
    print("\n🔍 입력 검증 테스트")
    print("-" * 40)

    workflow_service = get_blog_workflow_service()

    # 잘못된 데이터로 테스트
    invalid_data = {
        "category": "invalid_category",  # 잘못된 카테고리
        "store_name": "",  # 빈 상호명
        "personal_review": "너무 짧음",  # 짧은 감상평
        "visit_date": "invalid_date",  # 잘못된 날짜
    }

    result = await workflow_service.process_complete_workflow(
        date_directory="20260101",
        user_experience=invalid_data,
        images=None,
        auto_upload=False,
        progress_callback=lambda p: None  # 조용한 콜백
    )

    if result.status == WorkflowStatus.FAILED:
        print("✅ 입력 검증 테스트 성공 (잘못된 데이터를 올바르게 감지)")
        print(f"   오류 메시지: {result.message}")
        return True
    else:
        print("❌ 입력 검증 테스트 실패 (잘못된 데이터를 허용함)")
        return False


async def main():
    """메인 테스트 함수"""
    setup_logging()

    print("🔧 통합 워크플로우 테스트 도구")
    print("=" * 60)

    # 전체 성공 여부 추적
    all_tests_passed = True

    try:
        # 1. 완전한 워크플로우 테스트
        success = await test_complete_workflow()
        all_tests_passed = all_tests_passed and success

        # 2. 입력 검증 테스트
        success = await test_workflow_validation()
        all_tests_passed = all_tests_passed and success

        print("\n" + "=" * 60)
        if all_tests_passed:
            print("🎉 모든 테스트 성공!")
            print("\n💡 이제 다음을 시도해보세요:")
            print("  1. 텔레그램 봇에서 /done 명령어 사용")
            print("  2. 웹 인터페이스에서 /static/workflow.html 접속")
            print("  3. API 직접 호출: POST /api/workflow/start")
        else:
            print("❌ 일부 테스트 실패")
            print("\n🔧 문제 해결:")
            print("  1. .env 파일의 API 키 설정 확인")
            print("  2. naver-poster 디렉토리 및 npm 패키지 확인")
            print("  3. 로그 파일 'test_workflow.log' 확인")

    except KeyboardInterrupt:
        print("\n⏹️  테스트가 사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"\n💥 테스트 실행 중 오류: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
