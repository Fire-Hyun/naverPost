"""
날짜 파싱 함수 테스트 - yyyymmdd 입력 오류 재현 및 검증
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.telegram.utils.validators import parse_visit_date


def test_parse_visit_date():
    """parse_visit_date 함수 종합 테스트"""
    results = []

    test_cases = [
        # (입력, 예상_성공여부, 설명)
        ("20260216", True, "기본 yyyymmdd 형식"),
        ("20260216", True, "동일 입력 반복 (2회차)"),
        ("20260216", True, "동일 입력 반복 (3회차)"),
        ("20260212", True, "일반 날짜"),
        ("20240229", True, "윤년 2월 29일"),
        ("2026-02-16", True, "하이픈 형식 YYYY-MM-DD"),
        ("오늘", True, "키워드: 오늘"),
        ("어제", True, "키워드: 어제"),
        ("today", True, "키워드: today"),
        ("yesterday", True, "키워드: yesterday"),
        (" 20260216 ", True, "앞뒤 공백 포함"),
        (" 20260216", True, "앞 공백 포함"),
        ("20260216 ", True, "뒤 공백 포함"),
        ("\n20260216\n", True, "줄바꿈 포함"),
        # 실패 케이스
        ("20260230", False, "존재하지 않는 날짜 (2월 30일)"),
        ("20230229", False, "비윤년 2월 29일"),
        ("20261301", False, "존재하지 않는 월 (13월)"),
        ("2026021", False, "7자리 숫자"),
        ("202602160", False, "9자리 숫자"),
        ("abcdefgh", False, "문자열 8자리"),
        ("", False, "빈 문자열"),
        ("   ", False, "공백만"),
        ("2026/02/16", False, "슬래시 구분자"),
    ]

    print("=" * 70)
    print("날짜 파싱 함수 테스트")
    print("=" * 70)

    pass_count = 0
    fail_count = 0

    for input_text, expect_success, description in test_cases:
        try:
            date_str, error_msg = parse_visit_date(input_text)
            actual_success = date_str is not None

            if actual_success == expect_success:
                status = "✅ PASS"
                pass_count += 1
            else:
                status = "❌ FAIL"
                fail_count += 1

            if actual_success:
                print(f"  {status} | {description:30s} | input={input_text!r:20s} | result={date_str}")
            else:
                print(f"  {status} | {description:30s} | input={input_text!r:20s} | error={error_msg[:40]}")

        except Exception as e:
            print(f"  💥 CRASH | {description:30s} | input={input_text!r:20s} | exception={type(e).__name__}: {e}")
            fail_count += 1

    print("=" * 70)
    print(f"결과: {pass_count} passed, {fail_count} failed (총 {len(test_cases)}개)")
    print("=" * 70)

    return fail_count == 0


def test_repeated_parsing():
    """동일 입력 3회 반복 테스트 (재현 테스트)"""
    print("\n" + "=" * 70)
    print("yyyymmdd 반복 입력 테스트 (3회)")
    print("=" * 70)

    test_input = "20260216"
    for i in range(3):
        date_str, error_msg = parse_visit_date(test_input)
        if date_str:
            print(f"  ✅ {i+1}회차: input={test_input!r} → parsed={date_str}")
        else:
            print(f"  ❌ {i+1}회차: input={test_input!r} → error={error_msg}")
            return False

    print("  → 3회 반복 입력 성공")
    return True


if __name__ == "__main__":
    ok1 = test_parse_visit_date()
    ok2 = test_repeated_parsing()

    if ok1 and ok2:
        print("\n🎉 모든 테스트 통과!")
        sys.exit(0)
    else:
        print("\n❌ 일부 테스트 실패!")
        sys.exit(1)
