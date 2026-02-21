#!/usr/bin/env python3
"""
네이버 포스트 텔레그램 봇 시작 스크립트 (DNS 헬스체크 포함)
DNS 및 네트워크 상태를 확인 후 봇을 안전하게 시작
"""

import sys
import os
import asyncio
import signal
import time
from pathlib import Path

# 프로젝트 루트를 Python 경로/작업 디렉토리로 고정
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from src.utils.dns_health_checker import (
    DNSHealthChecker, check_dns_health, wait_for_network_ready,
    diagnose_and_log_dns_issues
)
from src.utils.structured_logger import get_logger

logger = get_logger("bot_startup")


class BotStartupManager:
    """봇 시작 관리자"""

    def __init__(self):
        self.startup_timeout = int(os.environ.get("NETWORK_WAIT_TIMEOUT", "30"))
        self.dns_check_enabled = os.environ.get("DNS_CHECK_ENABLED", "true").lower() == "true"
        self.max_startup_attempts = 3
        self.shutdown_requested = False

    async def perform_startup_checks(self) -> bool:
        """시작 전 검사 수행"""
        logger.info("Starting bot startup checks",
                   dns_check_enabled=self.dns_check_enabled,
                   network_timeout=self.startup_timeout)

        if not self.dns_check_enabled:
            logger.info("DNS checks disabled, skipping health checks")
            return True

        try:
            # Step 1: 네트워크 대기
            logger.info("Step 1: Waiting for network readiness")
            network_ready = await wait_for_network_ready(
                max_wait_seconds=self.startup_timeout,
                check_interval=2
            )

            if not network_ready:
                logger.error("Network not ready within timeout")
                await self._log_network_diagnosis()
                return False

            # Step 2: DNS 헬스체크
            logger.info("Step 2: Performing DNS health check")
            dns_healthy = await check_dns_health()

            if not dns_healthy:
                logger.error("DNS health check failed")
                await self._log_network_diagnosis()
                return False

            # Step 3: 핵심 서비스 연결성 테스트
            logger.info("Step 3: Testing critical service connectivity")
            connectivity_ok = await self._test_critical_connectivity()

            if not connectivity_ok:
                logger.error("Critical service connectivity failed")
                await self._log_network_diagnosis()
                return False

            logger.info("All startup checks passed successfully")
            return True

        except Exception as e:
            logger.error("Startup checks failed with exception", error=e)
            await self._log_network_diagnosis()
            return False

    async def _test_critical_connectivity(self) -> bool:
        """핵심 서비스 연결성 테스트"""
        checker = DNSHealthChecker(timeout_seconds=5.0)

        # 텔레그램 API 연결 테스트
        telegram_result = await checker.test_network_connectivity("api.telegram.org", 443)
        if not telegram_result.success:
            logger.error("Telegram API connectivity failed", error=telegram_result.error_message)
            return False

        # 네이버 API 연결 테스트
        naver_result = await checker.test_network_connectivity("openapi.naver.com", 443)
        if not naver_result.success:
            logger.warning("Naver API connectivity failed", error=naver_result.error_message)
            # 네이버 API 실패는 치명적이지 않음 (계속 진행)

        return True

    async def _log_network_diagnosis(self):
        """네트워크 진단 로깅"""
        try:
            logger.info("Performing network diagnosis for troubleshooting")
            diagnosis = await diagnose_and_log_dns_issues()

            if diagnosis.get("recommendations"):
                logger.error("Network troubleshooting recommendations",
                           recommendations=diagnosis["recommendations"])

        except Exception as e:
            logger.error("Network diagnosis failed", error=e)

    def setup_signal_handlers(self):
        """시그널 핸들러 설정"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, requesting shutdown")
            self.shutdown_requested = True

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def start_bot_with_checks(self):
        """검사와 함께 봇 시작"""
        logger.info("NaverPost Telegram Bot startup initiated")

        startup_attempt = 0

        while startup_attempt < self.max_startup_attempts and not self.shutdown_requested:
            startup_attempt += 1

            logger.info("Bot startup attempt", attempt=startup_attempt, max_attempts=self.max_startup_attempts)

            try:
                # 시작 전 검사
                checks_passed = await self.perform_startup_checks()

                if not checks_passed:
                    if startup_attempt < self.max_startup_attempts:
                        wait_time = min(10 * startup_attempt, 60)  # Progressive backoff
                        logger.warning("Startup checks failed, retrying",
                                     attempt=startup_attempt,
                                     retry_in_seconds=wait_time)
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.critical("All startup attempts exhausted, failing")
                        return 1

                # DNS fallback 설치
                logger.info("Installing DNS fallback")
                from src.utils.dns_fallback import install_dns_fallback
                install_dns_fallback()

                # 봇 시작
                logger.info("Starting telegram bot service")
                from src.services.telegram_service import get_telegram_service

                service = get_telegram_service(
                    enable_dns_fallback=True,
                    base_retry_delay=10
                )

                # Run blocking bot loop in a worker thread to avoid nested event loop conflicts.
                return await asyncio.to_thread(service.run)

            except KeyboardInterrupt:
                logger.info("Bot startup interrupted by user")
                return 0

            except Exception as e:
                logger.error("Bot startup failed", error=e, attempt=startup_attempt)

                if startup_attempt < self.max_startup_attempts:
                    wait_time = min(15 * startup_attempt, 90)  # Progressive backoff
                    logger.warning("Startup failed, retrying",
                                 attempt=startup_attempt,
                                 retry_in_seconds=wait_time)
                    await asyncio.sleep(wait_time)
                else:
                    logger.critical("All startup attempts failed")
                    return 1

        logger.info("Bot startup cancelled due to shutdown request")
        return 0

    def run(self):
        """메인 실행"""
        self.setup_signal_handlers()

        try:
            return asyncio.run(self.start_bot_with_checks())
        except KeyboardInterrupt:
            logger.info("Bot startup interrupted")
            return 0
        except Exception as e:
            logger.critical("Fatal error during bot startup", error=e)
            return 1


def main():
    """메인 함수"""
    startup_manager = BotStartupManager()
    return startup_manager.run()


if __name__ == "__main__":
    exit(main())
