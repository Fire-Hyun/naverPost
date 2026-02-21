"""
DNS 헬스체커 테스트
"""

import pytest
import asyncio
import platform
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path

from src.utils.dns_health_checker import (
    DNSHealthChecker, DNSTestResult, NetworkConnectivityResult, SystemNetworkInfo,
    check_dns_health, wait_for_network_ready, diagnose_and_log_dns_issues
)
from src.utils.exceptions import DNSResolutionError, TimeoutError


@pytest.fixture
def dns_checker():
    """DNS 헬스체커 인스턴스"""
    return DNSHealthChecker(timeout_seconds=1.0)


@pytest.fixture
def mock_dns_response():
    """모킹된 DNS 응답"""
    mock_item = MagicMock()
    mock_item.__str__ = Mock(return_value="192.0.2.1")
    mock_response = Mock()
    mock_response.__iter__ = Mock(return_value=iter([mock_item]))
    return mock_response


class TestDNSHealthChecker:
    """DNS 헬스체커 테스트"""

    def test_detect_wsl(self, dns_checker):
        """WSL 감지 테스트"""
        with patch("pathlib.Path.exists") as mock_exists, \
             patch("pathlib.Path.read_text") as mock_read:

            # WSL 환경 시뮬레이션
            mock_exists.return_value = True
            mock_read.return_value = "Linux version 5.4.0-Microsoft-standard-WSL2"

            is_wsl = dns_checker._detect_wsl()
            assert is_wsl is True

            # 일반 Linux 환경
            mock_read.return_value = "Linux version 5.4.0-generic"
            is_wsl = dns_checker._detect_wsl()
            assert is_wsl is False

    @pytest.mark.asyncio
    async def test_get_system_network_info(self, dns_checker):
        """시스템 네트워크 정보 수집 테스트"""
        with patch.object(dns_checker, '_detect_wsl', return_value=False), \
             patch.object(dns_checker, '_get_system_dns_servers', return_value=["8.8.8.8"]), \
             patch.object(dns_checker, '_get_network_interfaces', return_value={"eth0": "192.168.1.1"}), \
             patch.object(dns_checker, '_check_systemd_resolved', return_value=True):

            info = await dns_checker.get_system_network_info()

            assert isinstance(info, SystemNetworkInfo)
            assert info.platform == platform.system()
            assert info.is_wsl is False
            assert "8.8.8.8" in info.dns_servers
            assert "eth0" in info.network_interfaces

    @pytest.mark.asyncio
    async def test_dns_resolution_success(self, dns_checker, mock_dns_response):
        """DNS 해상도 성공 테스트"""
        with patch.object(dns_checker._dns_resolvers["system"], 'resolve', return_value=mock_dns_response):
            result = await dns_checker.test_dns_resolution("google.com", "system")

            assert isinstance(result, DNSTestResult)
            assert result.success is True
            assert result.hostname == "google.com"
            assert "192.0.2.1" in result.resolved_ips
            assert result.response_time_ms > 0

    @pytest.mark.asyncio
    async def test_dns_resolution_failure(self, dns_checker):
        """DNS 해상도 실패 테스트"""
        with patch.object(dns_checker._dns_resolvers["system"], 'resolve', side_effect=Exception("DNS error")):
            result = await dns_checker.test_dns_resolution("invalid.domain", "system")

            assert isinstance(result, DNSTestResult)
            assert result.success is False
            assert result.hostname == "invalid.domain"
            assert result.error_message == "DNS error"

    @pytest.mark.asyncio
    async def test_dns_resolution_timeout(self, dns_checker):
        """DNS 해상도 타임아웃 테스트"""
        import time as _time

        def slow_resolve(*args, **kwargs):
            # run_in_executor는 동기 함수를 실행하므로 time.sleep 사용
            _time.sleep(2.0)  # checker timeout is 1.0s
            return Mock()

        with patch.object(dns_checker._dns_resolvers["system"], 'resolve', side_effect=slow_resolve):
            result = await dns_checker.test_dns_resolution("slow.domain", "system")

            assert result.success is False
            assert "timeout" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_network_connectivity_success(self, dns_checker):
        """네트워크 연결성 성공 테스트"""
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()

        with patch('asyncio.open_connection', return_value=(mock_reader, mock_writer)):
            result = await dns_checker.test_network_connectivity("google.com", 443)

            assert isinstance(result, NetworkConnectivityResult)
            assert result.success is True
            assert result.target_host == "google.com"
            assert result.target_port == 443
            assert result.connection_time_ms > 0

    @pytest.mark.asyncio
    async def test_network_connectivity_failure(self, dns_checker):
        """네트워크 연결성 실패 테스트"""
        with patch('asyncio.open_connection', side_effect=ConnectionError("Connection refused")):
            result = await dns_checker.test_network_connectivity("invalid.host", 443)

            assert result.success is False
            assert "Connection refused" in result.error_message

    @pytest.mark.asyncio
    async def test_network_connectivity_timeout(self, dns_checker):
        """네트워크 연결성 타임아웃 테스트"""
        async def slow_connection(*args, **kwargs):
            await asyncio.sleep(2.0)  # checker timeout is 1.0s
            return (AsyncMock(), AsyncMock())

        with patch('asyncio.open_connection', side_effect=slow_connection):
            result = await dns_checker.test_network_connectivity("slow.host", 443)

            assert result.success is False

    @pytest.mark.asyncio
    async def test_comprehensive_dns_test(self, dns_checker):
        """포괄적 DNS 테스트"""
        test_hosts = ["google.com", "github.com"]

        with patch.object(dns_checker, 'test_dns_resolution') as mock_test:
            # 성공적인 DNS 테스트 결과 모킹
            mock_test.return_value = DNSTestResult(
                hostname="test.com",
                success=True,
                resolved_ips=["192.0.2.1"],
                response_time_ms=50.0,
                resolver_used="system"
            )

            results = await dns_checker.comprehensive_dns_test(test_hosts)

            assert len(results) == 2
            assert "google.com" in results
            assert "github.com" in results

            # 각 호스트에 대해 최소 한 번은 테스트했는지 확인
            assert mock_test.call_count >= 2

    @pytest.mark.asyncio
    async def test_comprehensive_connectivity_test(self, dns_checker):
        """포괄적 연결성 테스트"""
        with patch.object(dns_checker, 'test_network_connectivity') as mock_test:
            # 성공적인 연결성 테스트 결과 모킹
            mock_test.return_value = NetworkConnectivityResult(
                target_host="test.com",
                target_port=443,
                success=True,
                connection_time_ms=100.0
            )

            results = await dns_checker.comprehensive_connectivity_test()

            assert len(results) > 0
            assert all(":" in key for key in results.keys())  # host:port 형식

            # 여러 호스트에 대해 테스트했는지 확인
            assert mock_test.call_count >= 3

    @pytest.mark.asyncio
    async def test_diagnose_dns_issues(self, dns_checker):
        """DNS 문제 진단 테스트"""
        mock_system_info = SystemNetworkInfo(
            platform="Linux",
            is_wsl=True,
            dns_servers=["127.0.0.1"],
            systemd_resolved_active=True
        )

        mock_dns_results = {
            "api.telegram.org": [
                DNSTestResult(hostname="api.telegram.org", success=False, error_message="DNS failure")
            ]
        }

        mock_connectivity_results = {
            "google.com:443": NetworkConnectivityResult(
                target_host="google.com",
                target_port=443,
                success=True
            )
        }

        with patch.object(dns_checker, 'get_system_network_info', return_value=mock_system_info), \
             patch.object(dns_checker, 'comprehensive_dns_test', return_value=mock_dns_results), \
             patch.object(dns_checker, 'comprehensive_connectivity_test', return_value=mock_connectivity_results):

            diagnosis = await dns_checker.diagnose_dns_issues()

            assert "system_info" in diagnosis
            assert "dns_tests" in diagnosis
            assert "connectivity_tests" in diagnosis
            assert "recommendations" in diagnosis
            assert "severity" in diagnosis

            # WSL 환경에서 DNS 실패가 있으므로 권장사항이 있어야 함
            assert len(diagnosis["recommendations"]) > 0

            # 심각도가 적절히 평가되어야 함
            assert diagnosis["severity"] in ["low", "medium", "high", "critical"]

    def test_generate_recommendations_wsl(self, dns_checker):
        """WSL 환경에서의 권장사항 생성 테스트"""
        system_info = SystemNetworkInfo(
            platform="Linux",
            is_wsl=True,
            systemd_resolved_active=False
        )

        dns_results = {
            "api.telegram.org": [
                DNSTestResult(hostname="api.telegram.org", success=False)
            ]
        }

        connectivity_results = {}

        recommendations = dns_checker._generate_recommendations(
            system_info, dns_results, connectivity_results
        )

        assert len(recommendations) > 0
        assert any("WSL" in rec for rec in recommendations)
        assert any("resolv.conf" in rec for rec in recommendations)

    def test_generate_recommendations_systemd_resolved(self, dns_checker):
        """systemd-resolved 환경에서의 권장사항 생성 테스트"""
        system_info = SystemNetworkInfo(
            platform="Linux",
            is_wsl=False,
            systemd_resolved_active=True
        )

        dns_results = {
            "google.com": [
                DNSTestResult(hostname="google.com", success=False, resolver_used="system")
            ]
        }

        connectivity_results = {}

        recommendations = dns_checker._generate_recommendations(
            system_info, dns_results, connectivity_results
        )

        assert len(recommendations) > 0
        assert any("systemd-resolved" in rec for rec in recommendations)

    def test_assess_severity(self, dns_checker):
        """심각도 평가 테스트"""
        # Critical: 중요 호스트 DNS 실패 + 연결성 실패
        dns_results_critical = {
            "api.telegram.org": [DNSTestResult(hostname="api.telegram.org", success=False)]
        }
        connectivity_results_critical = {
            "google.com:443": NetworkConnectivityResult(target_host="google.com", target_port=443, success=False)
        }
        severity = dns_checker._assess_severity(dns_results_critical, connectivity_results_critical)
        assert severity == "critical"

        # Low: 모든 테스트 성공
        dns_results_low = {
            "api.telegram.org": [DNSTestResult(hostname="api.telegram.org", success=True)]
        }
        connectivity_results_low = {
            "google.com:443": NetworkConnectivityResult(target_host="google.com", target_port=443, success=True)
        }
        severity = dns_checker._assess_severity(dns_results_low, connectivity_results_low)
        assert severity == "low"


@pytest.mark.asyncio
class TestConvenienceFunctions:
    """편의 함수 테스트"""

    async def test_check_dns_health_success(self):
        """DNS 헬스체크 성공 테스트"""
        with patch('src.utils.dns_health_checker.DNSHealthChecker') as MockChecker:
            mock_instance = MockChecker.return_value
            # CRITICAL_HOSTS를 실제 리스트로 설정 (MagicMock의 __contains__는 항상 False 반환)
            MockChecker.CRITICAL_HOSTS = ["api.telegram.org"]
            mock_instance.comprehensive_dns_test = AsyncMock(return_value={
                "api.telegram.org": [DNSTestResult(hostname="api.telegram.org", success=True)]
            })

            result = await check_dns_health()
            assert result is True

    async def test_check_dns_health_failure(self):
        """DNS 헬스체크 실패 테스트"""
        with patch('src.utils.dns_health_checker.DNSHealthChecker') as MockChecker:
            mock_instance = MockChecker.return_value
            # CRITICAL_HOSTS를 실제 리스트로 설정 (MagicMock의 __contains__는 항상 False 반환)
            MockChecker.CRITICAL_HOSTS = ["api.telegram.org"]
            mock_instance.comprehensive_dns_test = AsyncMock(return_value={
                "api.telegram.org": [DNSTestResult(hostname="api.telegram.org", success=False)]
            })

            result = await check_dns_health()
            assert result is False

    async def test_wait_for_network_ready_success(self):
        """네트워크 준비 대기 성공 테스트"""
        with patch('src.utils.dns_health_checker.check_dns_health', new=AsyncMock(return_value=True)), \
             patch('src.utils.dns_health_checker.DNSHealthChecker') as MockChecker:

            mock_instance = MockChecker.return_value
            mock_instance.test_network_connectivity = AsyncMock(return_value=NetworkConnectivityResult(
                target_host="google.com",
                target_port=443,
                success=True
            ))

            result = await wait_for_network_ready(max_wait_seconds=5, check_interval=1)
            assert result is True

    async def test_wait_for_network_ready_timeout(self):
        """네트워크 준비 대기 타임아웃 테스트"""
        with patch('src.utils.dns_health_checker.check_dns_health', new=AsyncMock(return_value=False)):
            result = await wait_for_network_ready(max_wait_seconds=2, check_interval=1)
            assert result is False

    async def test_diagnose_and_log_dns_issues(self):
        """DNS 문제 진단 및 로깅 테스트"""
        mock_diagnosis = {
            "system_info": {"platform": "Linux", "is_wsl": False},
            "severity": "low",
            "recommendations": []
        }

        with patch('src.utils.dns_health_checker.DNSHealthChecker') as MockChecker:
            mock_instance = MockChecker.return_value
            mock_instance.diagnose_dns_issues = AsyncMock(return_value=mock_diagnosis)

            result = await diagnose_and_log_dns_issues()

            assert result == mock_diagnosis
            assert result["severity"] == "low"


# 통합 테스트 (실제 네트워크 필요)
@pytest.mark.integration
@pytest.mark.asyncio
class TestDNSIntegration:
    """실제 네트워크를 사용한 DNS 통합 테스트"""

    @pytest.mark.skipif(not __import__('os').environ.get('RUN_INTEGRATION_TESTS'), reason="Integration tests disabled")
    async def test_real_dns_resolution(self):
        """실제 DNS 해상도 테스트"""
        checker = DNSHealthChecker(timeout_seconds=5.0)

        # 안정적인 호스트로 테스트
        result = await checker.test_dns_resolution("google.com", "system")

        if result.success:
            assert len(result.resolved_ips) > 0
            assert all("." in ip for ip in result.resolved_ips)  # IPv4 형식 확인
        else:
            # 네트워크 문제가 있을 수 있으므로 경고만 출력
            print(f"DNS resolution failed: {result.error_message}")

    @pytest.mark.skipif(not __import__('os').environ.get('RUN_INTEGRATION_TESTS'), reason="Integration tests disabled")
    async def test_real_network_connectivity(self):
        """실제 네트워크 연결성 테스트"""
        checker = DNSHealthChecker(timeout_seconds=5.0)

        # 안정적인 호스트로 테스트
        result = await checker.test_network_connectivity("google.com", 443)

        if result.success:
            assert result.connection_time_ms > 0
        else:
            # 네트워크 문제가 있을 수 있으므로 경고만 출력
            print(f"Network connectivity failed: {result.error_message}")


# pytest 설정
def pytest_addoption(parser):
    """pytest 옵션 추가"""
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="run integration tests"
    )


def pytest_configure(config):
    """pytest 설정"""
    config.addinivalue_line("markers", "integration: mark test as integration test")


if __name__ == "__main__":
    # 단위 테스트 실행
    pytest.main([__file__, "-v"])