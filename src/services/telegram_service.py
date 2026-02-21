"""
Unified Telegram bot service
Combines functionality from run_telegram_bot.py and src/telegram/__main__.py
"""

import asyncio
import fcntl
import logging
import os
import signal
import socket
import sys
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Callable

logger = logging.getLogger(__name__)


class TelegramBotService:
    """통합된 Telegram 봇 서비스"""

    def __init__(self,
                 enable_dns_fallback: bool = True,
                 base_retry_delay: int = 10,
                 max_retry_delay: int = 300,
                 exponential_backoff: bool = True):
        self.enable_dns_fallback = enable_dns_fallback
        self.base_retry_delay = base_retry_delay
        self.max_retry_delay = max_retry_delay
        self.exponential_backoff = exponential_backoff
        self.logger = logging.getLogger(__name__)

        # 설정은 런타임에 로드
        self._settings = None
        self._bot = None

        # 프로세스 관리
        self._shutdown_requested = False
        self._current_loop: Optional[asyncio.AbstractEventLoop] = None
        self._shutdown_handlers: list[Callable[[], None]] = []
        self._instance_lock_fd = None
        self._instance_lock_path = Path("/tmp/naverpost_telegram_bot.lock")

    def _load_settings(self):
        """설정 로드 및 검증"""
        if self._settings is not None:
            return self._settings

        try:
            from src.config.settings import Settings
            self._settings = Settings

            # 필요한 디렉토리 생성
            Settings.create_directories()

            return self._settings
        except Exception as e:
            raise RuntimeError(f"Failed to load settings: {e}")

    def _install_dns_fallback(self):
        """DNS fallback 설치"""
        if not self.enable_dns_fallback:
            return

        try:
            from src.utils.dns_fallback import install_dns_fallback
            install_dns_fallback()
            self.logger.info("DNS fallback installed")
        except Exception as e:
            self.logger.warning(f"Failed to install DNS fallback: {e}")

    def _validate_configuration(self) -> Dict[str, Any]:
        """전체 설정 검증"""
        settings = self._load_settings()

        # Telegram 설정 검증
        telegram_validation = settings.validate_telegram_keys()

        # 추가 검증 로직 (미래 확장용)
        validation_result = {
            'telegram': telegram_validation,
            'directories_created': True,
            'settings_loaded': True
        }

        # 실패한 검증 항목 확인
        failed_validations = []
        if not telegram_validation.get("TELEGRAM_BOT_TOKEN"):
            failed_validations.append("TELEGRAM_BOT_TOKEN is missing")

        validation_result['failures'] = failed_validations
        validation_result['success'] = len(failed_validations) == 0

        return validation_result

    def _perform_dns_diagnostics(self):
        """DNS 진단"""
        try:
            socket.getaddrinfo("api.telegram.org", 443)
            self.logger.info("DNS check for api.telegram.org passed")
        except Exception as e:
            self.logger.warning(f"DNS check failed for api.telegram.org: {e}")
            print(f"⚠️ DNS check failed for api.telegram.org: {e}")
            print("   - WSL DNS 이슈 가능성이 큽니다.")
            print("   - 해결: bash maintenance/fix_wsl_dns_and_restart_bot.sh")

    def _create_bot_instance(self):
        """봇 인스턴스 생성"""
        if self._bot is not None:
            return self._bot

        try:
            from src.telegram.bot import NaverPostTelegramBot
            self._bot = NaverPostTelegramBot()
            return self._bot
        except Exception as e:
            raise RuntimeError(f"Failed to create bot instance: {e}")

    def _setup_signal_handlers(self):
        """시그널 핸들러 설정"""
        if threading.current_thread() is not threading.main_thread():
            self.logger.info("Skipping signal handler install outside main thread")
            return

        def signal_handler(signum, frame):
            signal_name = signal.Signals(signum).name
            self.logger.info(f"Received signal {signal_name}, requesting shutdown...")
            print(f"\n🛑 Received {signal_name}, shutting down gracefully...")
            self._shutdown_requested = True

            # 실행 중인 이벤트 루프가 있으면 종료 작업 스케줄
            if self._current_loop and self._current_loop.is_running():
                self._current_loop.call_soon_threadsafe(self._schedule_shutdown)

        # SIGINT (Ctrl+C)와 SIGTERM 처리
        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            self.logger.info("Signal handlers installed")
        except Exception as e:
            self.logger.warning(f"Failed to install signal handlers: {e}")

    def _schedule_shutdown(self):
        """이벤트 루프 내에서 안전하게 종료 스케줄"""
        async def shutdown():
            await self._perform_graceful_shutdown()
            if self._current_loop:
                self._current_loop.stop()

        if self._current_loop:
            asyncio.create_task(shutdown())

    async def _perform_graceful_shutdown(self):
        """우아한 종료 수행"""
        self.logger.info("Performing graceful shutdown...")

        # 등록된 종료 핸들러들 실행
        for handler in self._shutdown_handlers:
            try:
                handler()
            except Exception as e:
                self.logger.error(f"Error in shutdown handler: {e}")

        # 봇 정리
        if self._bot:
            try:
                # 봇에 종료 메서드가 있으면 호출
                if hasattr(self._bot, 'shutdown'):
                    await self._bot.shutdown()
                elif hasattr(self._bot, 'stop'):
                    self._bot.stop()
            except Exception as e:
                self.logger.error(f"Error stopping bot: {e}")

    def add_shutdown_handler(self, handler: Callable[[], None]):
        """종료 핸들러 추가"""
        self._shutdown_handlers.append(handler)

    def _calculate_retry_delay(self, attempt: int) -> int:
        """재시도 지연 시간 계산 (지수 백오프)"""
        if not self.exponential_backoff:
            return self.base_retry_delay

        # 지수 백오프: base_delay * (2 ^ (attempt - 1))
        delay = self.base_retry_delay * (2 ** max(0, attempt - 1))
        return min(delay, self.max_retry_delay)

    def _reuse_or_create_event_loop(self, attempt: int) -> asyncio.AbstractEventLoop:
        """이벤트 루프 재사용 또는 생성"""
        try:
            # 기존 루프가 있고 실행 중이면 재사용
            current_loop = asyncio.get_event_loop()
            if current_loop and not current_loop.is_closed():
                self.logger.debug(f"Reusing existing event loop for attempt #{attempt}")
                self._current_loop = current_loop
                return current_loop
        except RuntimeError:
            pass

        # 새 루프 생성
        self.logger.debug(f"Creating new event loop for attempt #{attempt}")
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        self._current_loop = new_loop
        return new_loop

    def _print_startup_info(self):
        """시작 정보 출력"""
        settings = self._settings
        print("🤖 Starting naverPost Telegram Bot...")
        print(f"📁 Data directory: {settings.DATA_DIR}")
        print(f"🔑 Bot token: {settings.TELEGRAM_BOT_TOKEN[:10]}...")
        print(f"🛡️ Safe messaging: {getattr(settings, 'USE_SAFE_MESSAGING', True)}")
        print(f"🔄 Exponential backoff: {self.exponential_backoff}")
        print(f"⏰ Base retry delay: {self.base_retry_delay}s")

    def _acquire_single_instance_lock(self) -> bool:
        """
        동일 머신에서 중복 polling 인스턴스 실행을 차단한다.
        중복 실행 시 Telegram getUpdates Conflict를 유발하므로 즉시 종료.
        """
        try:
            self._instance_lock_path.parent.mkdir(parents=True, exist_ok=True)
            fd = open(self._instance_lock_path, "w")
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self.logger.error(
                    "Another telegram bot instance is already running (lock busy)",
                    extra={"lock_path": str(self._instance_lock_path)},
                )
                print(
                    "❌ Another bot instance is already running on this host.\n"
                    "   Duplicate polling causes Telegram Conflict(getUpdates).\n"
                    f"   lock: {self._instance_lock_path}"
                )
                fd.close()
                return False

            fd.seek(0)
            fd.truncate(0)
            fd.write(str(os.getpid()))
            fd.flush()
            self._instance_lock_fd = fd
            return True
        except Exception as e:
            self.logger.error(f"Failed to acquire instance lock: {e}")
            print(
                "❌ Failed to acquire bot instance lock.\n"
                "   To avoid duplicate polling and session breakage, startup is aborted."
            )
            return False

    def _release_single_instance_lock(self) -> None:
        if not self._instance_lock_fd:
            return
        try:
            fcntl.flock(self._instance_lock_fd, fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            self._instance_lock_fd.close()
        except Exception:
            pass
        self._instance_lock_fd = None

    def run(self) -> int:
        """봇 실행 (메인 엔트리 포인트)"""
        try:
            if not self._acquire_single_instance_lock():
                return 1

            # 1. 시그널 핸들러 설정 (우아한 종료를 위해)
            self._setup_signal_handlers()

            # 2. DNS fallback 설치
            self._install_dns_fallback()

            # 3. 설정 로드 및 검증
            validation_result = self._validate_configuration()

            if not validation_result['success']:
                print("❌ Configuration validation failed:")
                for failure in validation_result['failures']:
                    print(f"   - {failure}")

                if "TELEGRAM_BOT_TOKEN is missing" in validation_result['failures']:
                    print("Please set your Telegram bot token in .env file:")
                    print("TELEGRAM_BOT_TOKEN=your_bot_token_here")

                return 1

            # 4. 시작 정보 출력
            self._print_startup_info()

            # 5. DNS 진단
            self._perform_dns_diagnostics()

            # 6. 재시도 루프로 봇 실행
            return self._run_with_retry()

        except KeyboardInterrupt:
            print("\n👋 Bot stopped by user")
            return 0
        except Exception as e:
            self.logger.error(f"Failed to start bot service: {e}")
            print(f"❌ Failed to start bot: {e}")
            return 1
        finally:
            self._release_single_instance_lock()

    def _run_with_retry(self) -> int:
        """재시도 로직으로 봇 실행 (개선된 버전)"""
        attempt = 0

        while not self._shutdown_requested:
            attempt += 1

            # 재시도 지연 계산 (지수 백오프)
            retry_delay = self._calculate_retry_delay(attempt)

            try:
                self.logger.info(f"Bot startup attempt #{attempt}")

                # 이벤트 루프 재사용 또는 생성
                loop = self._reuse_or_create_event_loop(attempt)

                # 봇 인스턴스 생성 및 실행
                bot = self._create_bot_instance()

                # 종료 요청 체크
                if self._shutdown_requested:
                    self.logger.info("Shutdown requested before starting bot")
                    return 0

                bot.run()

                self.logger.info("Bot stopped normally")
                return 0

            except KeyboardInterrupt:
                print("\n👋 Bot stopped by user")
                self._shutdown_requested = True
                return 0

            except Exception as e:
                if self._shutdown_requested:
                    self.logger.info("Shutdown requested during error handling")
                    return 0

                self.logger.error(f"Bot runtime error (attempt #{attempt}): {e}")

                # 특정 에러 타입에 대한 처리
                if "Timed out" in str(e):
                    print(f"⚠️ Bot runtime error: {e}")
                    print("   - Telegram API 타임아웃입니다.")
                    print("   - DNS/네트워크 연결 확인: getent hosts api.telegram.org")
                    print("   - WSL인 경우 DNS 복구: bash maintenance/fix_wsl_dns_and_restart_bot.sh")
                else:
                    print(f"⚠️ Bot runtime error: {e}")

                print(f"🔁 Retrying in {retry_delay}s... (attempt #{attempt})")

                # 인터럽트 가능한 슬립
                if self._interruptible_sleep(retry_delay):
                    return 0  # 종료 요청됨

            except BaseException as e:
                if self._shutdown_requested:
                    self.logger.info("Shutdown requested during fatal error handling")
                    return 0

                # SystemExit 등 치명적 에러
                self.logger.error(f"Bot runtime fatal error (attempt #{attempt}): {type(e).__name__}: {e}")
                print(f"⚠️ Bot runtime fatal error: {type(e).__name__}: {e}")
                print(f"🔁 Retrying in {retry_delay}s... (attempt #{attempt})")

                # 인터럽트 가능한 슬립
                if self._interruptible_sleep(retry_delay):
                    return 0  # 종료 요청됨

        self.logger.info("Bot service stopped due to shutdown request")
        return 0

    def _interruptible_sleep(self, duration: int) -> bool:
        """인터럽트 가능한 슬립 (종료 요청 시 일찍 깨어남)"""
        start_time = time.time()
        while time.time() - start_time < duration:
            if self._shutdown_requested:
                return True  # 종료 요청됨
            time.sleep(0.1)  # 짧은 간격으로 체크
        return False  # 정상 완료

    def run_once(self) -> int:
        """한 번만 실행 (재시도 없음) - 테스트용"""
        try:
            # DNS fallback과 설정 로드
            self._install_dns_fallback()
            validation_result = self._validate_configuration()

            if not validation_result['success']:
                return 1

            # 봇 생성 및 실행
            bot = self._create_bot_instance()
            bot.run()

            return 0

        except KeyboardInterrupt:
            print("\nBot stopped by user")
            return 0
        except Exception as e:
            print(f"Failed to start bot: {e}")
            return 1


# 전역 서비스 인스턴스
_telegram_service: Optional[TelegramBotService] = None


def get_telegram_service(
    enable_dns_fallback: bool = True,
    base_retry_delay: int = 10
) -> TelegramBotService:
    """전역 TelegramBotService 인스턴스 반환"""
    global _telegram_service
    if _telegram_service is None:
        _telegram_service = TelegramBotService(
            enable_dns_fallback=enable_dns_fallback,
            base_retry_delay=base_retry_delay
        )
    return _telegram_service


def main():
    """메인 함수 - run_telegram_bot.py와 호환"""
    service = get_telegram_service()
    return service.run()


if __name__ == "__main__":
    exit(main())
