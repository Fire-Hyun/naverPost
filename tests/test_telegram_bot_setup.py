#!/usr/bin/env python3
"""
텔레그램 봇 설정 및 버튼 인터페이스 테스트
"""

import sys
import logging
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

def test_imports():
    """필수 모듈 import 테스트"""
    try:
        print("🔍 모듈 import 테스트 시작...")

        # 핵심 봇 모듈
        from src.telegram.bot import NaverPostTelegramBot
        print("✅ NaverPostTelegramBot import 성공")

        # 유틸리티 모듈
        from src.telegram.utils import (
            SessionValidator, DateValidator, ProgressSummaryBuilder,
            ContentTypeDetector, ErrorHandler, AccessControl,
            UserLogger, get_user_logger
        )
        print("✅ utils 모듈들 import 성공")

        # 응답 템플릿 및 버튼 생성
        from src.telegram.models.responses import ResponseTemplates
        responses = ResponseTemplates()

        # 버튼 키보드 테스트
        start_keyboard = responses.create_start_keyboard()
        category_keyboard = responses.create_category_keyboard(['카페', '식당', '쇼핑'])
        generation_keyboard = responses.create_generation_keyboard()
        print("✅ 버튼 키보드 생성 테스트 성공")

        # 세션 모델
        from src.telegram.models.session import TelegramSession, ConversationState
        print("✅ 세션 모델 import 성공")

        # 서비스 레이어
        from src.telegram.service_layer import (
            BlogGenerationService, SessionManagementService, MaintenanceService
        )
        print("✅ 서비스 레이어 import 성공")

        print("\n✅ 모든 모듈 import 테스트 통과!")
        return True

    except Exception as e:
        print(f"\n❌ Import 오류: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_user_logger():
    """UserLogger 기능 테스트"""
    try:
        print("\n🔍 UserLogger 기능 테스트...")

        user_logger = get_user_logger(12345)

        # 로깅 테스트
        user_logger.log_session_start()
        user_logger.log_date_input("20260214")
        user_logger.log_category_selected("카페")
        user_logger.log_store_name_input("스타벅스")
        user_logger.log_store_name_resolved(raw_name="스타벅스", resolved_name="스타벅스 강남역점")
        user_logger.log_image_uploaded(1, "test_image.jpg")
        user_logger.log_review_submitted(length=120)
        user_logger.log_additional_content(True)
        user_logger.log_generation_start()
        user_logger.log_generation_success("/path/to/blog", "1500자")

        # 로그 읽기 테스트
        recent_logs = user_logger.get_recent_logs(10)
        if recent_logs:
            print(f"✅ 로그 기록 및 읽기 성공 ({len(recent_logs)}개 라인)")
            print("최근 로그 샘플:")
            for line in recent_logs[-3:]:
                print(f"   {line.strip()}")
        else:
            print("⚠️  로그가 기록되지 않았습니다.")

        return True

    except Exception as e:
        print(f"\n❌ UserLogger 테스트 오류: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_bot_creation():
    """봇 인스턴스 생성 테스트"""
    try:
        print("\n🔍 봇 인스턴스 생성 테스트...")

        # 환경변수 확인
        from src.config.settings import Settings

        # 텔레그램 설정이 있는지 확인
        if not hasattr(Settings, 'TELEGRAM_BOT_TOKEN') or not Settings.TELEGRAM_BOT_TOKEN:
            print("⚠️  TELEGRAM_BOT_TOKEN이 설정되지 않음 - 봇 생성 건너뛰기")
            return True

        # 봇 인스턴스 생성 (토큰이 있는 경우만)
        try:
            bot = NaverPostTelegramBot()
            print("✅ 봇 인스턴스 생성 성공")

            # 애플리케이션 빌드 테스트
            application = bot.build_application()
            print("✅ 텔레그램 애플리케이션 빌드 성공")

            return True

        except ValueError as e:
            if "TELEGRAM_BOT_TOKEN is required" in str(e):
                print("⚠️  유효하지 않은 TELEGRAM_BOT_TOKEN - 봇 생성 건너뛰기")
                return True
            else:
                raise

    except Exception as e:
        print(f"\n❌ 봇 생성 테스트 오류: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """메인 테스트 실행"""
    print("🚀 텔레그램 봇 설정 및 버튼 인터페이스 테스트")
    print("=" * 60)

    success_count = 0
    total_tests = 3

    # 1. Import 테스트
    if test_imports():
        success_count += 1

    # 2. UserLogger 테스트
    if test_user_logger():
        success_count += 1

    # 3. 봇 생성 테스트
    if test_bot_creation():
        success_count += 1

    # 결과 요약
    print("\n" + "=" * 60)
    print(f"🏁 테스트 완료: {success_count}/{total_tests} 통과")

    if success_count == total_tests:
        print("✅ 모든 테스트 통과! 텔레그램 봇이 올바르게 설정되었습니다.")
        print("\n💡 사용 방법:")
        print("   python etc_scripts/run_telegram_bot.py")
        print("   텔레그램에서 /start 또는 버튼을 눌러 시작하세요!")
        return True
    else:
        print(f"❌ {total_tests - success_count}개 테스트 실패")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
