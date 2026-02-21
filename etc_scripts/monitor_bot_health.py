#!/usr/bin/env python3
"""
텔레그램 봇 24시간 헬스 모니터링 시스템

기능:
- 봇 프로세스 상태 모니터링
- 네트워크 연결성 확인
- DNS 상태 체크
- 메모리 사용량 모니터링
- 자동 재시작 및 복구
- 슬랙/이메일 알림 (선택사항)
"""

import asyncio
import json
import os
import psutil
import time
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta

# 프로젝트 루트를 Python 경로/작업 디렉토리로 고정
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

try:
    from src.utils.structured_logger import get_logger, operation_context as log_context
    from src.utils.dns_health_checker import check_dns_health, diagnose_and_log_dns_issues
except ImportError as e:
    print(f"⚠️ Import warning: {e}")
    print("Using basic logging instead of structured logging")

    # 기본 로거 폴백
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    class BasicLogger:
        def info(self, msg, **kwargs): logging.info(f"{msg} {kwargs}")
        def error(self, msg, **kwargs): logging.error(f"{msg} {kwargs}")
        def warning(self, msg, **kwargs): logging.warning(f"{msg} {kwargs}")
        def success(self, msg, **kwargs): logging.info(f"SUCCESS: {msg} {kwargs}")

    def get_logger(name): return BasicLogger()
    def log_context(**kwargs): return type('obj', (object,), {'__enter__': lambda self: None, '__exit__': lambda self, *args: None})()

    async def check_dns_health() -> bool:
        try:
            import socket
            socket.gethostbyname("api.telegram.org")
            return True
        except Exception:
            return False

    async def diagnose_and_log_dns_issues() -> Dict[str, Any]:
        return {"severity": "unknown", "details": "fallback-mode"}

logger = get_logger("bot_health_monitor")


@dataclass
class HealthStatus:
    """봇 헬스 상태"""
    timestamp: float
    process_running: bool
    process_pid: Optional[int] = None
    memory_mb: float = 0.0
    cpu_percent: float = 0.0
    network_ok: bool = False
    dns_ok: bool = False
    uptime_seconds: float = 0.0
    restart_count: int = 0
    last_restart: Optional[float] = None


@dataclass
class HealthCheckResult:
    """헬스체크 결과"""
    status: HealthStatus
    issues: List[str]
    actions_taken: List[str]
    needs_restart: bool = False


class TelegramBotHealthMonitor:
    """텔레그램 봇 헬스 모니터"""

    def __init__(
        self,
        check_interval: int = 60,  # 1분마다 체크
        max_memory_mb: int = 500,
        max_restart_attempts: int = 5,
        restart_cooldown: int = 300  # 5분 쿨다운
    ):
        self.check_interval = check_interval
        self.max_memory_mb = max_memory_mb
        self.max_restart_attempts = max_restart_attempts
        self.restart_cooldown = restart_cooldown
        self.restart_count = 0
        self.last_restart = None
        self.health_history: List[HealthStatus] = []
        self.running = False

    def find_bot_process(self) -> Optional[psutil.Process]:
        """봇 프로세스 찾기"""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info['cmdline']
                    if cmdline and any('telegram' in cmd.lower() for cmd in cmdline):
                        if any('naverpost' in cmd.lower() or 'run_telegram_bot' in cmd for cmd in cmdline):
                            return psutil.Process(proc.info['pid'])
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.error("Error finding bot process", error=e)
        return None

    async def check_bot_health(self) -> HealthCheckResult:
        """봇 헬스 상태 확인"""
        with log_context(operation="health_check"):
            issues = []
            actions_taken = []
            needs_restart = False

            # 1. 프로세스 상태 확인
            bot_process = self.find_bot_process()

            if bot_process:
                try:
                    memory_info = bot_process.memory_info()
                    memory_mb = memory_info.rss / 1024 / 1024
                    cpu_percent = bot_process.cpu_percent(interval=0.1)
                    uptime = time.time() - bot_process.create_time()

                    process_status = HealthStatus(
                        timestamp=time.time(),
                        process_running=True,
                        process_pid=bot_process.pid,
                        memory_mb=memory_mb,
                        cpu_percent=cpu_percent,
                        uptime_seconds=uptime,
                        restart_count=self.restart_count,
                        last_restart=self.last_restart
                    )

                    # 메모리 사용량 체크
                    if memory_mb > self.max_memory_mb:
                        issues.append(f"High memory usage: {memory_mb:.1f}MB > {self.max_memory_mb}MB")
                        needs_restart = True

                    logger.info("Bot process found",
                               pid=bot_process.pid,
                               memory_mb=f"{memory_mb:.1f}",
                               cpu_percent=f"{cpu_percent:.1f}",
                               uptime_hours=f"{uptime/3600:.1f}")

                except Exception as e:
                    issues.append(f"Error reading process info: {str(e)}")
                    process_status = HealthStatus(
                        timestamp=time.time(),
                        process_running=False
                    )
                    needs_restart = True
            else:
                issues.append("Bot process not found")
                process_status = HealthStatus(
                    timestamp=time.time(),
                    process_running=False,
                    restart_count=self.restart_count,
                    last_restart=self.last_restart
                )
                needs_restart = True

            # 2. 네트워크 상태 확인
            try:
                network_ok = await self.check_network_connectivity()
                process_status.network_ok = network_ok
                if not network_ok:
                    issues.append("Network connectivity issues")
            except Exception as e:
                issues.append(f"Network check failed: {str(e)}")
                process_status.network_ok = False

            # 3. DNS 상태 확인
            try:
                dns_ok = await check_dns_health()
                process_status.dns_ok = dns_ok
                if not dns_ok:
                    issues.append("DNS resolution issues")
                    # DNS 문제 시 자동 복구 시도
                    await self.fix_dns_issues()
                    actions_taken.append("DNS auto-repair attempted")
            except Exception as e:
                issues.append(f"DNS check failed: {str(e)}")
                process_status.dns_ok = False

            # 히스토리에 추가 (최근 24시간만 유지)
            self.health_history.append(process_status)
            cutoff_time = time.time() - 86400  # 24시간
            self.health_history = [h for h in self.health_history if h.timestamp > cutoff_time]

            return HealthCheckResult(
                status=process_status,
                issues=issues,
                actions_taken=actions_taken,
                needs_restart=needs_restart
            )

    async def check_network_connectivity(self) -> bool:
        """네트워크 연결성 확인"""
        try:
            # 텔레그램 API 연결 테스트
            proc = await asyncio.create_subprocess_exec(
                'curl', '-s', '--connect-timeout', '5', 'https://api.telegram.org',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            return proc.returncode == 0
        except Exception:
            return False

    async def fix_dns_issues(self):
        """DNS 문제 자동 복구 시도"""
        try:
            proc = await asyncio.create_subprocess_exec(
                'python3', str(project_root / 'etc_scripts' / 'fix_dns_issues.py'),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
        except Exception as e:
            logger.error("DNS auto-fix failed", error=e)

    async def restart_bot_service(self) -> bool:
        """봇 서비스 재시작"""
        if self.last_restart and (time.time() - self.last_restart) < self.restart_cooldown:
            logger.warning("Restart cooldown active, skipping restart")
            return False

        if self.restart_count >= self.max_restart_attempts:
            logger.error("Maximum restart attempts exceeded",
                        count=self.restart_count,
                        max_attempts=self.max_restart_attempts)
            return False

        try:
            logger.info("Attempting to restart bot service")

            # systemctl을 통한 재시작
            proc = await asyncio.create_subprocess_exec(
                'sudo', 'systemctl', 'restart', 'naverpost-bot.service',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                self.restart_count += 1
                self.last_restart = time.time()
                logger.success("Bot service restarted successfully",
                             restart_count=self.restart_count)

                # 재시작 후 잠시 대기
                await asyncio.sleep(10)
                return True
            else:
                logger.error("Service restart failed",
                           returncode=proc.returncode,
                           stderr=stderr.decode())
                return False

        except Exception as e:
            logger.error("Exception during service restart", error=e)
            return False

    async def save_health_report(self):
        """헬스 리포트 저장"""
        try:
            report_data = {
                "timestamp": time.time(),
                "monitoring_period_hours": 24,
                "total_checks": len(self.health_history),
                "restart_count": self.restart_count,
                "last_restart": self.last_restart,
                "recent_status": [asdict(status) for status in self.health_history[-10:]],
                "statistics": self.calculate_statistics()
            }

            report_path = project_root / "logs" / f"bot_health_report_{int(time.time())}.json"
            report_path.parent.mkdir(exist_ok=True)

            with open(report_path, 'w') as f:
                json.dump(report_data, f, indent=2)

            logger.info("Health report saved", report_path=str(report_path))

        except Exception as e:
            logger.error("Failed to save health report", error=e)

    def calculate_statistics(self) -> Dict[str, Any]:
        """통계 계산"""
        if not self.health_history:
            return {}

        recent_24h = [h for h in self.health_history if time.time() - h.timestamp <= 86400]

        uptime_ratio = len([h for h in recent_24h if h.process_running]) / len(recent_24h) if recent_24h else 0
        avg_memory = sum(h.memory_mb for h in recent_24h if h.memory_mb > 0) / len(recent_24h) if recent_24h else 0
        avg_cpu = sum(h.cpu_percent for h in recent_24h if h.cpu_percent > 0) / len(recent_24h) if recent_24h else 0

        return {
            "uptime_ratio_24h": uptime_ratio,
            "average_memory_mb": avg_memory,
            "average_cpu_percent": avg_cpu,
            "checks_in_24h": len(recent_24h),
            "network_success_ratio": len([h for h in recent_24h if h.network_ok]) / len(recent_24h) if recent_24h else 0,
            "dns_success_ratio": len([h for h in recent_24h if h.dns_ok]) / len(recent_24h) if recent_24h else 0
        }

    async def run_monitoring_loop(self):
        """모니터링 메인 루프"""
        self.running = True
        logger.info("Bot health monitoring started",
                   check_interval=self.check_interval,
                   max_memory_mb=self.max_memory_mb)

        consecutive_failures = 0

        while self.running:
            try:
                # 헬스체크 수행
                result = await self.check_bot_health()

                if result.issues:
                    logger.warning("Health issues detected",
                                 issues=result.issues,
                                 actions_taken=result.actions_taken)
                    consecutive_failures += 1

                    # 재시작이 필요한 경우
                    if result.needs_restart:
                        restart_success = await self.restart_bot_service()
                        if restart_success:
                            consecutive_failures = 0
                        else:
                            logger.error("Failed to restart bot service")

                else:
                    consecutive_failures = 0
                    logger.info("Bot health check passed",
                               uptime_hours=f"{result.status.uptime_seconds/3600:.1f}",
                               memory_mb=f"{result.status.memory_mb:.1f}")

                # 연속 실패가 많으면 긴급 알림
                if consecutive_failures >= 5:
                    logger.error("CRITICAL: Multiple consecutive health check failures",
                               consecutive_failures=consecutive_failures)

                # 매시간 리포트 저장
                if int(time.time()) % 3600 < self.check_interval:
                    await self.save_health_report()

                # 다음 체크까지 대기
                await asyncio.sleep(self.check_interval)

            except Exception as e:
                logger.error("Health monitoring loop error", error=e)
                await asyncio.sleep(self.check_interval)

    def stop_monitoring(self):
        """모니터링 중지"""
        self.running = False
        logger.info("Bot health monitoring stopped")


async def main():
    """메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(description="텔레그램 봇 24시간 헬스 모니터링")
    parser.add_argument("--interval", type=int, default=60,
                       help="헬스체크 간격 (초, 기본값: 60)")
    parser.add_argument("--max-memory", type=int, default=500,
                       help="최대 메모리 사용량 (MB, 기본값: 500)")
    parser.add_argument("--max-restarts", type=int, default=5,
                       help="최대 재시작 시도 횟수 (기본값: 5)")
    parser.add_argument("--one-shot", action="store_true",
                       help="한 번만 체크하고 종료")

    args = parser.parse_args()

    monitor = TelegramBotHealthMonitor(
        check_interval=args.interval,
        max_memory_mb=args.max_memory,
        max_restart_attempts=args.max_restarts
    )

    if args.one_shot:
        # 한 번만 체크
        result = await monitor.check_bot_health()

        print(f"🤖 Bot Health Check Results")
        print(f"{'='*50}")
        print(f"Process Running: {'✅' if result.status.process_running else '❌'}")

        if result.status.process_running:
            print(f"PID: {result.status.process_pid}")
            print(f"Memory: {result.status.memory_mb:.1f} MB")
            print(f"CPU: {result.status.cpu_percent:.1f}%")
            print(f"Uptime: {result.status.uptime_seconds/3600:.1f} hours")

        print(f"Network OK: {'✅' if result.status.network_ok else '❌'}")
        print(f"DNS OK: {'✅' if result.status.dns_ok else '❌'}")

        if result.issues:
            print(f"\n⚠️ Issues Found:")
            for issue in result.issues:
                print(f"  - {issue}")

        if result.actions_taken:
            print(f"\n🔧 Actions Taken:")
            for action in result.actions_taken:
                print(f"  - {action}")

        return 0 if not result.issues else 1

    else:
        # 지속적인 모니터링
        try:
            await monitor.run_monitoring_loop()
        except KeyboardInterrupt:
            monitor.stop_monitoring()
            logger.info("Monitoring stopped by user")
        except Exception as e:
            logger.error("Monitoring failed", error=e)
            return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
