"""
DNS 헬스체크 및 연결 검증 시스템
봇 시작시 DNS 및 네트워크 연결을 검증하여 안정적인 기동 보장
"""

import asyncio
import socket
import time
import platform
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import dns.resolver
import dns.exception

from .exceptions import DNSResolutionError, ConnectionError, TimeoutError
from .structured_logger import get_logger

logger = get_logger("dns_health_checker")


@dataclass
class DNSTestResult:
    """DNS 테스트 결과"""
    hostname: str
    success: bool
    resolved_ips: List[str] = field(default_factory=list)
    response_time_ms: float = 0.0
    error_message: str = ""
    resolver_used: str = "system"
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hostname": self.hostname,
            "success": self.success,
            "resolved_ips": self.resolved_ips,
            "response_time_ms": self.response_time_ms,
            "error_message": self.error_message,
            "resolver_used": self.resolver_used,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class NetworkConnectivityResult:
    """네트워크 연결성 테스트 결과"""
    target_host: str
    target_port: int
    success: bool
    connection_time_ms: float = 0.0
    error_message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_host": self.target_host,
            "target_port": self.target_port,
            "success": self.success,
            "connection_time_ms": self.connection_time_ms,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class SystemNetworkInfo:
    """시스템 네트워크 정보"""
    platform: str
    is_wsl: bool
    dns_servers: List[str] = field(default_factory=list)
    network_interfaces: Dict[str, str] = field(default_factory=dict)
    resolv_conf_exists: bool = False
    systemd_resolved_active: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "is_wsl": self.is_wsl,
            "dns_servers": self.dns_servers,
            "network_interfaces": self.network_interfaces,
            "resolv_conf_exists": self.resolv_conf_exists,
            "systemd_resolved_active": self.systemd_resolved_active
        }


class DNSHealthChecker:
    """DNS 헬스체크 클래스"""

    # 중요 호스트들
    CRITICAL_HOSTS = [
        "api.telegram.org",
        "openapi.naver.com",
        "naveropenapi.apigw.ntruss.com"
    ]

    # 테스트용 안정적 호스트들
    RELIABLE_TEST_HOSTS = [
        "google.com",
        "cloudflare.com",
        "github.com"
    ]

    # 공용 DNS 서버들
    PUBLIC_DNS_SERVERS = [
        "1.1.1.1",      # Cloudflare
        "8.8.8.8",      # Google
        "9.9.9.9",      # Quad9
        "208.67.222.222" # OpenDNS
    ]

    def __init__(self, timeout_seconds: float = 5.0):
        self.timeout_seconds = timeout_seconds
        self.system_info: Optional[SystemNetworkInfo] = None
        self._dns_resolvers: Dict[str, dns.resolver.Resolver] = {}
        self._setup_resolvers()

    def _setup_resolvers(self):
        """DNS 리졸버들 설정"""
        # 시스템 기본 리졸버
        self._dns_resolvers["system"] = dns.resolver.get_default_resolver()

        # 공용 DNS 리졸버들
        for i, dns_server in enumerate(self.PUBLIC_DNS_SERVERS):
            resolver = dns.resolver.Resolver()
            resolver.nameservers = [dns_server]
            resolver.timeout = self.timeout_seconds
            resolver.lifetime = self.timeout_seconds * 2
            self._dns_resolvers[f"public_{i+1}"] = resolver

    async def get_system_network_info(self) -> SystemNetworkInfo:
        """시스템 네트워크 정보 수집"""
        if self.system_info is not None:
            return self.system_info

        logger.info("Collecting system network information")

        try:
            info = SystemNetworkInfo(
                platform=platform.system(),
                is_wsl=self._detect_wsl()
            )

            # DNS 서버 정보 수집
            info.dns_servers = await self._get_system_dns_servers()

            # 네트워크 인터페이스 정보
            info.network_interfaces = await self._get_network_interfaces()

            # resolv.conf 존재 여부
            info.resolv_conf_exists = Path("/etc/resolv.conf").exists()

            # systemd-resolved 상태
            info.systemd_resolved_active = await self._check_systemd_resolved()

            self.system_info = info
            logger.info("System network info collected", **info.to_dict())

            return info

        except Exception as e:
            logger.error("Failed to collect system network info", error=e)
            # 기본값 반환
            return SystemNetworkInfo(
                platform=platform.system(),
                is_wsl=self._detect_wsl()
            )

    def _detect_wsl(self) -> bool:
        """WSL 환경 감지"""
        try:
            # /proc/version에 Microsoft가 있으면 WSL
            version_file = Path("/proc/version")
            if version_file.exists():
                content = version_file.read_text()
                return "microsoft" in content.lower() or "wsl" in content.lower()

            # Windows 환경변수 체크
            import os
            wsl_distro = os.environ.get("WSL_DISTRO_NAME")
            return wsl_distro is not None

        except Exception:
            return False

    async def _get_system_dns_servers(self) -> List[str]:
        """시스템 DNS 서버 목록 조회"""
        dns_servers = []

        try:
            # /etc/resolv.conf에서 읽기
            resolv_conf = Path("/etc/resolv.conf")
            if resolv_conf.exists():
                content = resolv_conf.read_text()
                for line in content.split('\n'):
                    line = line.strip()
                    if line.startswith('nameserver'):
                        parts = line.split()
                        if len(parts) > 1:
                            dns_servers.append(parts[1])

            # systemd-resolved 사용시 추가 확인
            if await self._check_systemd_resolved():
                try:
                    result = subprocess.run(
                        ["systemd-resolve", "--status"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        # DNS 서버 정보 파싱 (간단한 버전)
                        for line in result.stdout.split('\n'):
                            if 'DNS Servers:' in line:
                                # 추가 파싱 로직 필요시 구현
                                pass
                except subprocess.TimeoutExpired:
                    pass
                except FileNotFoundError:
                    pass

        except Exception as e:
            logger.warning("Failed to get system DNS servers", error=e)

        return dns_servers

    async def _get_network_interfaces(self) -> Dict[str, str]:
        """네트워크 인터페이스 정보"""
        interfaces = {}

        try:
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True,
                text=True,
                timeout=3
            )

            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'default via' in line:
                        parts = line.split()
                        if 'dev' in parts:
                            dev_index = parts.index('dev')
                            if dev_index + 1 < len(parts):
                                interface = parts[dev_index + 1]
                                gateway = parts[2] if len(parts) > 2 else "unknown"
                                interfaces[interface] = gateway

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.warning("Failed to get network interfaces", error=e)

        return interfaces

    async def _check_systemd_resolved(self) -> bool:
        """systemd-resolved 활성 상태 확인"""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "systemd-resolved"],
                capture_output=True,
                text=True,
                timeout=3
            )
            return result.returncode == 0 and "active" in result.stdout

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return False

    async def test_dns_resolution(self, hostname: str, resolver_name: str = "system") -> DNSTestResult:
        """단일 호스트 DNS 해상도 테스트"""
        start_time = time.time()

        try:
            resolver = self._dns_resolvers.get(resolver_name)
            if not resolver:
                raise ValueError(f"Unknown resolver: {resolver_name}")

            # DNS 쿼리 수행
            try:
                answer = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, resolver.resolve, hostname, 'A'
                    ),
                    timeout=self.timeout_seconds
                )

                resolved_ips = [str(rdata) for rdata in answer]
                response_time = (time.time() - start_time) * 1000

                result = DNSTestResult(
                    hostname=hostname,
                    success=True,
                    resolved_ips=resolved_ips,
                    response_time_ms=round(response_time, 2),
                    resolver_used=resolver_name
                )

                logger.debug("DNS resolution successful",
                           hostname=hostname,
                           resolver=resolver_name,
                           ips=resolved_ips,
                           response_time_ms=result.response_time_ms)

                return result

            except asyncio.TimeoutError:
                raise TimeoutError(f"DNS resolution timeout for {hostname}", "dns", "resolve", self.timeout_seconds)

            except dns.exception.DNSException as e:
                raise DNSResolutionError(f"DNS query failed for {hostname}: {str(e)}", hostname)

        except Exception as e:
            response_time = (time.time() - start_time) * 1000

            result = DNSTestResult(
                hostname=hostname,
                success=False,
                response_time_ms=round(response_time, 2),
                error_message=str(e),
                resolver_used=resolver_name
            )

            logger.warning("DNS resolution failed",
                         hostname=hostname,
                         resolver=resolver_name,
                         error=str(e),
                         response_time_ms=result.response_time_ms)

            return result

    async def test_network_connectivity(self, host: str, port: int) -> NetworkConnectivityResult:
        """네트워크 연결성 테스트"""
        start_time = time.time()

        try:
            # TCP 연결 테스트
            future = asyncio.open_connection(host, port)
            reader, writer = await asyncio.wait_for(future, timeout=self.timeout_seconds)

            connection_time = (time.time() - start_time) * 1000

            # 연결 정리
            writer.close()
            await writer.wait_closed()

            result = NetworkConnectivityResult(
                target_host=host,
                target_port=port,
                success=True,
                connection_time_ms=round(connection_time, 2)
            )

            logger.debug("Network connectivity test successful",
                       host=host,
                       port=port,
                       connection_time_ms=result.connection_time_ms)

            return result

        except Exception as e:
            connection_time = (time.time() - start_time) * 1000

            result = NetworkConnectivityResult(
                target_host=host,
                target_port=port,
                success=False,
                connection_time_ms=round(connection_time, 2),
                error_message=str(e)
            )

            logger.warning("Network connectivity test failed",
                         host=host,
                         port=port,
                         error=str(e),
                         connection_time_ms=result.connection_time_ms)

            return result

    async def comprehensive_dns_test(self, hostnames: List[str] = None) -> Dict[str, List[DNSTestResult]]:
        """포괄적 DNS 테스트"""
        if hostnames is None:
            hostnames = self.CRITICAL_HOSTS + self.RELIABLE_TEST_HOSTS

        results = {}

        logger.info("Starting comprehensive DNS test", hostnames=hostnames)

        for hostname in hostnames:
            hostname_results = []

            # 여러 리졸버로 테스트
            for resolver_name in self._dns_resolvers.keys():
                result = await self.test_dns_resolution(hostname, resolver_name)
                hostname_results.append(result)

                # 시스템 리졸버가 성공하면 다른 리졸버는 스킵
                if resolver_name == "system" and result.success:
                    break

            results[hostname] = hostname_results

        # 결과 요약 로깅
        self._log_dns_test_summary(results)

        return results

    def _log_dns_test_summary(self, results: Dict[str, List[DNSTestResult]]):
        """DNS 테스트 결과 요약 로깅"""
        total_tests = sum(len(hostname_results) for hostname_results in results.values())
        successful_tests = sum(
            len([r for r in hostname_results if r.success])
            for hostname_results in results.values()
        )

        critical_host_issues = []
        for hostname in self.CRITICAL_HOSTS:
            if hostname in results:
                hostname_results = results[hostname]
                if not any(r.success for r in hostname_results):
                    critical_host_issues.append(hostname)

        logger.info("DNS test summary completed",
                   total_tests=total_tests,
                   successful_tests=successful_tests,
                   success_rate=f"{(successful_tests/total_tests*100):.1f}%" if total_tests > 0 else "0%",
                   critical_host_issues=critical_host_issues)

        if critical_host_issues:
            logger.error("Critical hosts have DNS resolution issues",
                       failed_hosts=critical_host_issues)

    async def comprehensive_connectivity_test(self) -> Dict[str, NetworkConnectivityResult]:
        """포괄적 네트워크 연결성 테스트"""
        test_targets = [
            ("api.telegram.org", 443),
            ("google.com", 443),
            ("cloudflare.com", 443),
            ("openapi.naver.com", 443)
        ]

        results = {}

        logger.info("Starting comprehensive connectivity test")

        for host, port in test_targets:
            result = await self.test_network_connectivity(host, port)
            results[f"{host}:{port}"] = result

        # 결과 요약
        successful_connections = sum(1 for r in results.values() if r.success)
        total_connections = len(results)

        logger.info("Connectivity test summary completed",
                   successful_connections=successful_connections,
                   total_connections=total_connections,
                   success_rate=f"{(successful_connections/total_connections*100):.1f}%")

        return results

    async def diagnose_dns_issues(self) -> Dict[str, Any]:
        """DNS 문제 진단"""
        logger.info("Starting DNS issue diagnosis")

        diagnosis = {
            "system_info": {},
            "dns_tests": {},
            "connectivity_tests": {},
            "recommendations": [],
            "severity": "unknown"
        }

        try:
            # 시스템 정보 수집
            system_info = await self.get_system_network_info()
            diagnosis["system_info"] = system_info.to_dict()

            # DNS 테스트
            dns_results = await self.comprehensive_dns_test()
            diagnosis["dns_tests"] = {
                hostname: [r.to_dict() for r in results]
                for hostname, results in dns_results.items()
            }

            # 연결성 테스트
            connectivity_results = await self.comprehensive_connectivity_test()
            diagnosis["connectivity_tests"] = {
                target: result.to_dict()
                for target, result in connectivity_results.items()
            }

            # 문제 분석 및 권장사항 생성
            diagnosis["recommendations"] = self._generate_recommendations(
                system_info, dns_results, connectivity_results
            )

            # 심각도 평가
            diagnosis["severity"] = self._assess_severity(dns_results, connectivity_results)

            logger.info("DNS diagnosis completed",
                       severity=diagnosis["severity"],
                       recommendations_count=len(diagnosis["recommendations"]))

            return diagnosis

        except Exception as e:
            logger.error("DNS diagnosis failed", error=e)
            diagnosis["error"] = str(e)
            diagnosis["severity"] = "critical"
            return diagnosis

    def _generate_recommendations(self, system_info: SystemNetworkInfo,
                                dns_results: Dict[str, List[DNSTestResult]],
                                connectivity_results: Dict[str, NetworkConnectivityResult]) -> List[str]:
        """문제 기반 권장사항 생성"""
        recommendations = []

        # WSL DNS 문제
        if system_info.is_wsl:
            has_dns_issues = any(
                not any(r.success for r in results)
                for results in dns_results.values()
            )

            if has_dns_issues:
                recommendations.extend([
                    "WSL DNS 문제 감지됨: wsl --shutdown 후 재시작 시도",
                    "/etc/resolv.conf에서 nameserver를 8.8.8.8로 변경",
                    "Windows에서 'netsh winsock reset' 실행 후 재부팅"
                ])

        # systemd-resolved 문제
        if system_info.systemd_resolved_active:
            system_dns_failures = any(
                results[0].resolver_used == "system" and not results[0].success
                for results in dns_results.values()
                if results
            )

            if system_dns_failures:
                recommendations.extend([
                    "systemd-resolved 재시작: sudo systemctl restart systemd-resolved",
                    "DNS 캐시 플러시: sudo systemd-resolve --flush-caches"
                ])

        # 네트워크 연결 문제
        failed_connections = [
            target for target, result in connectivity_results.items()
            if not result.success
        ]

        if failed_connections:
            recommendations.extend([
                f"네트워크 연결 실패 감지: {', '.join(failed_connections)}",
                "방화벽 설정 확인",
                "프록시 설정 확인"
            ])

        # DNS 서버 문제
        if not system_info.dns_servers:
            recommendations.append("DNS 서버가 설정되지 않음: /etc/resolv.conf 확인")

        return recommendations

    def _assess_severity(self, dns_results: Dict[str, List[DNSTestResult]],
                        connectivity_results: Dict[str, NetworkConnectivityResult]) -> str:
        """문제 심각도 평가"""
        # 중요 호스트 DNS 실패 확인
        critical_dns_failures = []
        for hostname in self.CRITICAL_HOSTS:
            if hostname in dns_results:
                if not any(r.success for r in dns_results[hostname]):
                    critical_dns_failures.append(hostname)

        # 연결성 실패 확인
        connectivity_failures = [
            target for target, result in connectivity_results.items()
            if not result.success
        ]

        if critical_dns_failures and connectivity_failures:
            return "critical"
        elif critical_dns_failures:
            return "high"
        elif connectivity_failures:
            return "medium"
        else:
            return "low"


# === 편의 함수들 ===

async def check_dns_health() -> bool:
    """DNS 상태 간단 확인"""
    checker = DNSHealthChecker(timeout_seconds=3.0)

    try:
        # 핵심 호스트들만 빠르게 테스트
        results = await checker.comprehensive_dns_test(DNSHealthChecker.CRITICAL_HOSTS)

        # 모든 중요 호스트가 해상도 가능한지 확인
        all_critical_resolved = all(
            any(r.success for r in hostname_results)
            for hostname, hostname_results in results.items()
            if hostname in DNSHealthChecker.CRITICAL_HOSTS
        )

        return all_critical_resolved

    except Exception as e:
        logger.error("DNS health check failed", error=e)
        return False


async def wait_for_network_ready(max_wait_seconds: int = 30, check_interval: int = 2) -> bool:
    """네트워크가 준비될 때까지 대기"""
    logger.info("Waiting for network to be ready", max_wait_seconds=max_wait_seconds)

    checker = DNSHealthChecker(timeout_seconds=2.0)
    start_time = time.time()

    while time.time() - start_time < max_wait_seconds:
        try:
            # DNS 상태 확인
            if await check_dns_health():
                # 연결성도 확인
                connectivity_result = await checker.test_network_connectivity("google.com", 443)
                if connectivity_result.success:
                    logger.info("Network is ready",
                              wait_time=f"{time.time() - start_time:.1f}s")
                    return True

            logger.debug("Network not ready yet, waiting...",
                       elapsed_time=f"{time.time() - start_time:.1f}s")

            await asyncio.sleep(check_interval)

        except Exception as e:
            logger.warning("Network readiness check error", error=e)
            await asyncio.sleep(check_interval)

    logger.warning("Network readiness timeout",
                  max_wait_seconds=max_wait_seconds)
    return False


async def diagnose_and_log_dns_issues():
    """DNS 문제 진단 및 로깅"""
    checker = DNSHealthChecker()

    try:
        diagnosis = await checker.diagnose_dns_issues()

        logger.info("DNS diagnosis completed",
                   severity=diagnosis["severity"],
                   system_platform=diagnosis["system_info"].get("platform", "unknown"),
                   is_wsl=diagnosis["system_info"].get("is_wsl", False))

        if diagnosis["recommendations"]:
            logger.info("DNS troubleshooting recommendations",
                       recommendations=diagnosis["recommendations"])

        return diagnosis

    except Exception as e:
        logger.error("DNS diagnosis failed", error=e)
        return {"error": str(e), "severity": "critical"}