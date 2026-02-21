#!/usr/bin/env python3
"""
상호명 포함 디렉토리 명명 시스템 테스트
"""

import sys
import json
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.utils.date_manager import DateBasedDirectoryManager
from src.storage.data_manager import DateBasedDataManager

def test_business_name_extraction():
    """상호명 추출 테스트"""
    print("🧪 상호명 추출 테스트")
    print("=" * 40)

    date_manager = DateBasedDirectoryManager()

    test_cases = [
        {
            "name": "AI 스크립트 - 레스토랑",
            "input": {
                "ai_additional_script": "오늘은 이탈리아 레스토랑에서 맛있는 파스타를 먹었다.",
                "category": "맛집"
            },
            "expected": "이탈리아"
        },
        {
            "name": "개인 리뷰 - 카페명",
            "input": {
                "personal_review": "스타벅스에서 커피를 마시며 공부했다.",
                "category": "카페"
            },
            "expected": "스타벅스"
        },
        {
            "name": "카테고리 기본값",
            "input": {
                "category": "호텔"
            },
            "expected": "호텔"
        }
    ]

    for test_case in test_cases:
        print(f"\n📋 테스트: {test_case['name']}")
        print(f"   입력: {test_case['input']}")

        extracted = date_manager._extract_business_name_from_input(test_case['input'])
        print(f"   추출된 상호명: {extracted}")
        print(f"   예상값: {test_case['expected']}")
        print(f"   결과: {'✅ 통과' if extracted == test_case['expected'] else '❌ 실패'}")

def test_directory_name_generation():
    """디렉토리명 생성 테스트"""
    print("\n\n🏷️  디렉토리명 생성 테스트")
    print("=" * 40)

    date_manager = DateBasedDirectoryManager()

    # 테스트 케이스
    test_cases = [
        ("20260215", "맛집", "20260215(맛집)"),
        ("20260215", "카페스타", "20260215(카페스타)"),
        ("20260215", None, "20260215")
    ]

    for date_str, business_name, expected in test_cases:
        print(f"\n📁 날짜: {date_str}, 상호명: {business_name}")

        dir_name = date_manager._get_available_directory_name(date_str, business_name)
        print(f"   생성된 디렉토리명: {dir_name}")
        print(f"   예상값: {expected}")
        print(f"   결과: {'✅ 통과' if dir_name == expected else '❌ 실패'}")

def test_full_workflow_simulation():
    """전체 워크플로우 시뮬레이션 (실제 디렉토리 생성하지 않음)"""
    print("\n\n🔄 전체 워크플로우 시뮬레이션")
    print("=" * 40)

    data_manager = DateBasedDataManager()

    # 테스트 사용자 입력
    test_input = {
        "category": "맛집",
        "rating": 5,
        "visit_date": "2026-02-15",
        "companion": "가족",
        "personal_review": "홍콩반점에서 짜장면을 먹었는데 정말 맛있었다.",
        "ai_additional_script": "홍콩반점은 유명한 중식당이다."
    }

    print("📝 테스트 입력 데이터:")
    print(f"   카테고리: {test_input['category']}")
    print(f"   개인 리뷰: {test_input['personal_review']}")
    print(f"   AI 스크립트: {test_input['ai_additional_script']}")

    # 임시 세션 생성 테스트
    try:
        session_name = data_manager.create_posting_session("20260215", test_input)
        print(f"\n✅ 임시 세션 생성 완료: {session_name}")

        # 상호명이 포함되었는지 확인
        if "홍콩반점" in session_name:
            print("   ✅ 상호명이 올바르게 추출되어 세션명에 포함됨")
        else:
            print("   ❌ 상호명 추출 실패 또는 세션명에 미포함")

        # 임시 세션 정리
        data_manager._cleanup_temp_session(session_name)
        print("   🧹 임시 세션 정리 완료")

    except Exception as e:
        print(f"   ❌ 테스트 실패: {e}")

def test_directory_pattern_recognition():
    """새로운 디렉토리 패턴 인식 테스트"""
    print("\n\n🔍 디렉토리 패턴 인식 테스트")
    print("=" * 40)

    date_manager = DateBasedDirectoryManager()

    # 가상의 디렉토리명들
    test_directories = [
        "20260215",
        "20260215_2",
        "20260215(맛집)",
        "20260215_3(카페)",
        "20260216(이탈리안레스토랑)",
        "invalid_dir"
    ]

    print("📁 테스트 디렉토리명들:")
    for dir_name in test_directories:
        # list_date_directories의 패턴 확인 로직 시뮬레이션
        import re
        patterns = [
            r'^\d{8}(_\d+)?$',                    # 기존 형식
            r'^\d{8}(_\d+)?\([^)]+\)$'            # 상호명 포함 형식
        ]

        is_valid = False
        for pattern in patterns:
            if re.match(pattern, dir_name):
                is_valid = True
                break

        print(f"   {dir_name}: {'✅ 인식됨' if is_valid else '❌ 인식 안됨'}")

def main():
    """테스트 실행"""
    print("🚀 상호명 포함 디렉토리 명명 시스템 테스트 시작")
    print("=" * 50)

    try:
        test_business_name_extraction()
        test_directory_name_generation()
        test_directory_pattern_recognition()
        test_full_workflow_simulation()

        print("\n\n🎉 모든 테스트 완료!")
        print("=" * 50)

    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
