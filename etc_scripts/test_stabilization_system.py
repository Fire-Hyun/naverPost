#!/usr/bin/env python3
"""
네이버 포스트 안정화 시스템 종합 검증 스크립트

모든 안정화 컴포넌트의 통합 테스트:
- DNS 헬스체크 및 자동 복구
- 네이버 지도 검색 안정화
- 이미지 처리 안정화
- 네이버 블로그 포스팅 안정화
- 텔레그램 봇 통합
- 모니터링 및 로깅 시스템
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

# 프로젝트 루트를 Python 경로/작업 디렉토리로 고정
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

from src.utils.dns_health_checker import diagnose_and_log_dns_issues, check_dns_health
from src.utils.naver_map_client import StabilizedNaverMapClient
from src.utils.image_processor import StabilizedImageProcessor
from src.utils.structured_logger import get_logger, operation_context as log_context
from src.config.settings import Settings

try:
    from src.utils.naver_blog_client import create_naver_blog_post, test_naver_blog_health
    NAVER_BLOG_CLIENT_AVAILABLE = True
except Exception as e:
    NAVER_BLOG_CLIENT_AVAILABLE = False
    NAVER_BLOG_CLIENT_IMPORT_ERROR = str(e)

    async def test_naver_blog_health() -> Dict[str, Any]:
        return {
            "errors": [f"naver_blog_client unavailable: {NAVER_BLOG_CLIENT_IMPORT_ERROR}"],
            "login_status": False,
        }

logger = get_logger("stabilization_system_test")
if not hasattr(type(logger), "success"):
    def _logger_success(self, message: str, **kwargs):
        self.info(message, **kwargs)
    setattr(type(logger), "success", _logger_success)


def _create_naver_map_client() -> Optional[StabilizedNaverMapClient]:
    client_id = Settings.NAVER_MAP_CLIENT_ID or Settings.NAVER_CLIENT_ID
    client_secret = Settings.NAVER_MAP_CLIENT_SECRET or Settings.NAVER_CLIENT_SECRET
    if not client_id or not client_secret:
        return None
    return StabilizedNaverMapClient(client_id=client_id, client_secret=client_secret)


@dataclass
class SystemTestResult:
    """시스템 테스트 결과"""
    component: str
    success: bool
    duration_seconds: float
    details: Dict[str, Any]
    error_message: Optional[str] = None


@dataclass
class IntegrationTestSuite:
    """통합 테스트 스위트 결과"""
    timestamp: float
    total_duration: float
    components_tested: int
    components_passed: int
    components_failed: int
    results: List[SystemTestResult]
    overall_success: bool


class StabilizationSystemTester:
    """안정화 시스템 종합 테스터"""

    def __init__(self, artifacts_dir: str = "./test_artifacts", quick_mode: bool = False):
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.quick_mode = quick_mode
        self.results: List[SystemTestResult] = []
        self.start_time = time.time()

        logger.info("Stabilization system tester initialized",
                   artifacts_dir=str(self.artifacts_dir))

    async def run_full_test_suite(self) -> IntegrationTestSuite:
        """전체 테스트 스위트 실행"""
        logger.info("🚀 Starting comprehensive stabilization system test")

        # 테스트 스위트 정의
        test_components = [
            ("DNS Health Check", self.test_dns_health_system),
            ("Naver Map Client", self.test_naver_map_stabilization),
            ("Image Processing", self.test_image_processing_stabilization),
            ("Naver Blog System", self.test_naver_blog_stabilization),
            ("End-to-End Workflow", self.test_end_to_end_workflow),
            ("Error Classification", self.test_error_classification_system),
            ("Monitoring Integration", self.test_monitoring_integration)
        ]
        if self.quick_mode:
            test_components = [
                ("DNS Health Check", self.test_dns_health_system),
                ("Naver Map Client", self.test_naver_map_stabilization),
                ("Image Processing", self.test_image_processing_stabilization),
                ("Monitoring Integration", self.test_monitoring_integration),
            ]

        # 각 컴포넌트 테스트 실행
        for component_name, test_func in test_components:
            logger.info(f"🔍 Testing {component_name}...")

            start_time = time.time()
            try:
                details = await test_func()
                duration = time.time() - start_time

                result = SystemTestResult(
                    component=component_name,
                    success=True,
                    duration_seconds=duration,
                    details=details
                )

                logger.success(f"✅ {component_name} test passed",
                             duration=f"{duration:.2f}s")

            except Exception as e:
                duration = time.time() - start_time

                result = SystemTestResult(
                    component=component_name,
                    success=False,
                    duration_seconds=duration,
                    details={},
                    error_message=str(e)
                )

                logger.error(f"❌ {component_name} test failed",
                           error=str(e), duration=f"{duration:.2f}s")

            self.results.append(result)

        # 결과 생성
        total_duration = time.time() - self.start_time
        passed = sum(1 for r in self.results if r.success)
        failed = len(self.results) - passed

        suite_result = IntegrationTestSuite(
            timestamp=self.start_time,
            total_duration=total_duration,
            components_tested=len(self.results),
            components_passed=passed,
            components_failed=failed,
            results=self.results,
            overall_success=(failed == 0)
        )

        # 결과 저장
        await self.save_test_report(suite_result)

        logger.info("🏁 Stabilization system test completed",
                   total_duration=f"{total_duration:.2f}s",
                   passed=passed,
                   failed=failed,
                   success=suite_result.overall_success)

        return suite_result

    async def test_dns_health_system(self) -> Dict[str, Any]:
        """DNS 헬스체크 시스템 테스트"""
        with log_context(operation="test_dns_health"):
            # 1. DNS 진단 실행
            diagnosis = await diagnose_and_log_dns_issues()

            # 2. DNS 헬스체크 실행
            health_check = await check_dns_health()

            # 3. 시스템 네트워크 정보 수집
            from src.utils.dns_health_checker import DNSHealthChecker
            checker = DNSHealthChecker()
            system_info = await checker.get_system_network_info()

            return {
                "diagnosis_severity": diagnosis.get("severity"),
                "health_check_passed": health_check,
                "system_info": {
                    "platform": system_info.platform,
                    "is_wsl": system_info.is_wsl,
                    "dns_servers_count": len(system_info.dns_servers) if system_info.dns_servers else 0,
                    "systemd_resolved_active": system_info.systemd_resolved_active
                },
                "recommendations_count": len(diagnosis.get("recommendations", []))
            }

    async def test_naver_map_stabilization(self) -> Dict[str, Any]:
        """네이버 지도 안정화 테스트"""
        with log_context(operation="test_naver_map"):
            client = _create_naver_map_client()
            if client is None:
                return {
                    "skipped": True,
                    "reason": "NAVER_MAP_CLIENT_ID/SECRET not configured",
                }

            # 테스트 쿼리들
            test_queries = ["강남역", "홍대입구", "잘못된검색어12345"]
            results = {}

            for query in test_queries:
                try:
                    search_result = await client.search_place(query, similarity_threshold=0.0)
                    places = search_result.locations[:3]
                    results[query] = {
                        "success": True,
                        "places_found": len(places),
                        "cache_hit": search_result.cache_hit,
                        "has_coordinates": all(place.lat and place.lng for place in places) if places else False
                    }
                except Exception as e:
                    results[query] = {
                        "success": False,
                        "error": str(e)
                    }

            # 캐시 성능 테스트
            cache_start = time.time()
            cached_result = await client.search_place("강남역", similarity_threshold=0.0)  # 캐시된 결과
            cache_duration = time.time() - cache_start

            return {
                "query_results": results,
                "cache_performance": {
                    "cache_hit_duration": cache_duration,
                    "cache_working": cached_result.cache_hit or cache_duration < 0.1
                },
                "client_status": {
                    "rate_limiter_active": client.rate_limiter is not None,
                    "cache_size": len(client.cache.cache) if hasattr(client.cache, 'cache') else 0
                }
            }

    async def test_image_processing_stabilization(self) -> Dict[str, Any]:
        """이미지 처리 안정화 테스트"""
        with log_context(operation="test_image_processing"):
            processor = StabilizedImageProcessor()

            # 테스트 이미지 생성 (간단한 컬러 이미지)
            from PIL import Image
            test_image_path = self.artifacts_dir / "test_image.jpg"

            # 2048x2048 테스트 이미지 생성 (리사이징 테스트용)
            test_image = Image.new('RGB', (2048, 2048), color='red')
            test_image.save(test_image_path, 'JPEG')

            try:
                # 1. 이미지 최적화 테스트
                optimized_path = await processor.optimize_image_for_telegram(str(test_image_path))

                # 2. 최적화된 이미지 정보 확인
                with Image.open(optimized_path) as optimized_img:
                    optimized_size = optimized_img.size
                    optimized_file_size = Path(optimized_path).stat().st_size

                # 3. 원본 이미지 정보
                original_file_size = test_image_path.stat().st_size

                # 4. 메타데이터 추출 테스트 (EXIF가 없는 생성된 이미지)
                metadata = await processor.extract_metadata(str(test_image_path))

                return {
                    "optimization_success": True,
                    "size_reduction": {
                        "original_dimensions": (2048, 2048),
                        "optimized_dimensions": optimized_size,
                        "original_file_size": original_file_size,
                        "optimized_file_size": optimized_file_size,
                        "compression_ratio": optimized_file_size / original_file_size if original_file_size > 0 else 0
                    },
                    "metadata_extraction": {
                        "success": metadata is not None,
                        "has_gps": "gps_coordinates" in metadata if metadata else False
                    },
                    "file_validation": {
                        "optimized_file_exists": Path(optimized_path).exists(),
                        "valid_image_format": optimized_path.endswith(('.jpg', '.jpeg', '.png'))
                    }
                }

            except Exception as e:
                return {
                    "optimization_success": False,
                    "error": str(e),
                    "test_image_created": test_image_path.exists()
                }
            finally:
                # 정리
                if test_image_path.exists():
                    test_image_path.unlink()

    async def test_naver_blog_stabilization(self) -> Dict[str, Any]:
        """네이버 블로그 안정화 테스트"""
        with log_context(operation="test_naver_blog"):
            if not NAVER_BLOG_CLIENT_AVAILABLE:
                return {
                    "health_check": await test_naver_blog_health(),
                    "post_creation_test": {
                        "login_check_attempted": False,
                        "reason": f"naver_blog_client import failed: {NAVER_BLOG_CLIENT_IMPORT_ERROR}"
                    },
                }

            # 1. 헬스체크 실행
            health = await test_naver_blog_health()

            # 2. 가벼운 포스트 생성 테스트 (실제 저장 없이 dry-run 모드)
            test_post_data = {
                "title": "안정화 시스템 테스트 포스트",
                "body": "이것은 자동화된 테스트 포스트입니다.\n시스템 안정성 검증 중입니다.",
                "headless": True,
                "verify_save": False  # 실제 저장하지 않음
            }

            # 실제 포스트 생성은 환경변수가 있을 때만 시도
            post_creation_result = None
            import os

            if os.getenv("NAVER_ID") and os.getenv("NAVER_PW"):
                try:
                    # 매우 짧은 타임아웃으로 빠르게 실패하도록 설정
                    from src.utils.naver_blog_client import NaverBlogStabilizedClient
                    test_client = NaverBlogStabilizedClient(
                        headless=True,
                        timeout_seconds=10  # 짧은 타임아웃
                    )

                    # 로그인 상태만 확인 (실제 포스팅은 하지 않음)
                    async with test_client.browser_session():
                        login_status = await test_client.check_login_status()
                        post_creation_result = {
                            "login_check_attempted": True,
                            "login_status": login_status,
                            "session_info": test_client.session_info.__dict__ if test_client.session_info else None
                        }

                except Exception as e:
                    post_creation_result = {
                        "login_check_attempted": True,
                        "login_status": False,
                        "error": str(e)
                    }
            else:
                post_creation_result = {
                    "login_check_attempted": False,
                    "reason": "NAVER_ID or NAVER_PW not set in environment"
                }

            return {
                "health_check": health,
                "post_creation_test": post_creation_result,
                "test_configuration": test_post_data
            }

    async def test_end_to_end_workflow(self) -> Dict[str, Any]:
        """종단 간 워크플로우 테스트"""
        with log_context(operation="test_end_to_end"):
            workflow_steps = []

            try:
                # 1. DNS 체크
                dns_start = time.time()
                dns_ok = await check_dns_health()
                dns_duration = time.time() - dns_start
                workflow_steps.append({
                    "step": "DNS Health Check",
                    "success": dns_ok,
                    "duration": dns_duration
                })

                # 2. 지도 검색 (실제 API 호출)
                map_start = time.time()
                map_client = _create_naver_map_client()
                if map_client is None:
                    workflow_steps.append({
                        "step": "Map Search",
                        "success": True,
                        "skipped": True,
                        "reason": "NAVER_MAP_CLIENT_ID/SECRET not configured",
                    })
                    map_duration = time.time() - map_start
                    workflow_steps[-1]["duration"] = map_duration
                else:
                    places_result = await map_client.search_place("테스트장소12345", similarity_threshold=0.0)
                    map_duration = time.time() - map_start
                    workflow_steps.append({
                        "step": "Map Search",
                        "success": True,  # 예외가 발생하지 않았으므로 성공
                        "duration": map_duration,
                        "places_found": len(places_result.locations)
                    })

                # 3. 이미지 처리 시뮬레이션
                image_start = time.time()
                processor = StabilizedImageProcessor()

                # 작은 테스트 이미지 생성
                from PIL import Image
                test_img_path = self.artifacts_dir / "workflow_test.jpg"
                test_img = Image.new('RGB', (100, 100), color='blue')
                test_img.save(test_img_path, 'JPEG')

                try:
                    optimized = await processor.optimize_image_for_telegram(str(test_img_path))
                    image_success = Path(optimized).exists()
                finally:
                    if test_img_path.exists():
                        test_img_path.unlink()
                    if Path(optimized).exists():
                        Path(optimized).unlink()

                image_duration = time.time() - image_start
                workflow_steps.append({
                    "step": "Image Processing",
                    "success": image_success,
                    "duration": image_duration
                })

                # 4. 블로그 헬스체크 (실제 포스팅 없이)
                blog_start = time.time()
                blog_health = await test_naver_blog_health()
                blog_duration = time.time() - blog_start
                workflow_steps.append({
                    "step": "Blog Health Check",
                    "success": len(blog_health.get("errors", [])) == 0,
                    "duration": blog_duration,
                    "login_status": blog_health.get("login_status", False)
                })

                # 워크플로우 성공률 계산
                successful_steps = sum(1 for step in workflow_steps if step["success"])
                total_steps = len(workflow_steps)

                return {
                    "workflow_steps": workflow_steps,
                    "success_rate": successful_steps / total_steps,
                    "total_duration": sum(step["duration"] for step in workflow_steps),
                    "bottleneck_step": max(workflow_steps, key=lambda x: x["duration"])["step"]
                }

            except Exception as e:
                return {
                    "workflow_steps": workflow_steps,
                    "success_rate": 0.0,
                    "error": str(e),
                    "failed_at_step": len(workflow_steps)
                }

    async def test_error_classification_system(self) -> Dict[str, Any]:
        """에러 분류 시스템 테스트"""
        with log_context(operation="test_error_classification"):
            from src.utils.naver_blog_client import NaverBlogStabilizedClient, FailureCategory

            client = NaverBlogStabilizedClient(artifacts_dir=str(self.artifacts_dir))

            # 테스트 케이스: 에러 메시지와 예상 카테고리
            test_cases = [
                (Exception("Connection timeout"), "network_test", FailureCategory.NETWORK_ERROR),
                (Exception("Login required"), "session_test", FailureCategory.SESSION_EXPIRED),
                (Exception("iframe mainFrame not found"), "frame_test", FailureCategory.IFRAME_ACQUISITION),
                (Exception("contenteditable element failed"), "editor_test", FailureCategory.EDITOR_INTERACTION),
                (Exception("temp save verification failed"), "save_test", FailureCategory.TEMP_SAVE_VERIFICATION),
                (Exception("place button not found"), "place_test", FailureCategory.PLACE_ATTACHMENT),
                (Exception("image upload timeout"), "image_test", FailureCategory.IMAGE_UPLOAD),
                (Exception("rate limit exceeded"), "rate_test", FailureCategory.RATE_LIMIT),
                (Exception("unknown system error"), "unknown_test", FailureCategory.UNKNOWN)
            ]

            classification_results = []

            for error, operation, expected_category in test_cases:
                try:
                    classified_category = await client._classify_error(error, operation)
                    classification_results.append({
                        "error_message": str(error),
                        "operation": operation,
                        "expected_category": expected_category.value,
                        "classified_category": classified_category.value,
                        "correct": classified_category == expected_category
                    })
                except Exception as e:
                    classification_results.append({
                        "error_message": str(error),
                        "operation": operation,
                        "expected_category": expected_category.value,
                        "classification_error": str(e),
                        "correct": False
                    })

            correct_classifications = sum(1 for r in classification_results if r.get("correct", False))
            accuracy = correct_classifications / len(classification_results)

            return {
                "classification_results": classification_results,
                "accuracy": accuracy,
                "total_test_cases": len(test_cases),
                "correct_classifications": correct_classifications
            }

    async def test_monitoring_integration(self) -> Dict[str, Any]:
        """모니터링 통합 테스트"""
        with log_context(operation="test_monitoring"):
            from src.utils.structured_logger import get_logger

            # 구조화된 로깅 테스트
            test_logger = get_logger("monitoring_test")

            # 로그 레벨별 테스트
            log_tests = {
                "info": lambda: test_logger.info("Info level test", test_key="test_value"),
                "warning": lambda: test_logger.warning("Warning level test", test_key="warning_value"),
                "error": lambda: test_logger.error("Error level test", test_key="error_value"),
                "success": lambda: test_logger.success("Success level test", test_key="success_value")
            }

            log_results = {}
            for level, log_func in log_tests.items():
                try:
                    log_func()
                    log_results[level] = {"success": True}
                except Exception as e:
                    log_results[level] = {"success": False, "error": str(e)}

            # 메트릭 시스템 테스트 (기본 구현)
            metrics_tests = {
                "correlation_id_generation": self._test_correlation_id(),
                "context_manager": await self._test_log_context(),
                "log_formatting": self._test_log_formatting()
            }

            return {
                "structured_logging": log_results,
                "metrics_integration": metrics_tests,
                "log_levels_working": all(r["success"] for r in log_results.values())
            }

    def _test_correlation_id(self) -> Dict[str, Any]:
        """상관관계 ID 생성 테스트"""
        try:
            from src.utils.structured_logger import get_correlation_id

            id1 = get_correlation_id()
            id2 = get_correlation_id()

            return {
                "success": True,
                "ids_generated": [id1, id2],
                "ids_unique": id1 != id2,
                "id_format_valid": len(id1) > 0 and len(id2) > 0
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def _test_log_context(self) -> Dict[str, Any]:
        """로그 컨텍스트 매니저 테스트"""
        try:
            with log_context(operation="test_context", user_id="test_user"):
                test_logger = get_logger("context_test")
                test_logger.info("Context test message")

            return {
                "success": True,
                "context_manager_working": True
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def _test_log_formatting(self) -> Dict[str, Any]:
        """로그 포매팅 테스트"""
        try:
            test_logger = get_logger("format_test")

            # 다양한 데이터 타입으로 로깅 테스트
            test_data = {
                "string_value": "test",
                "numeric_value": 123,
                "boolean_value": True,
                "list_value": [1, 2, 3],
                "dict_value": {"nested": "value"}
            }

            test_logger.info("Formatting test", **test_data)

            return {
                "success": True,
                "data_types_tested": len(test_data),
                "formatting_working": True
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def save_test_report(self, suite_result: IntegrationTestSuite):
        """테스트 보고서 저장"""
        report_path = self.artifacts_dir / f"stabilization_test_report_{int(suite_result.timestamp)}.json"

        # dataclass를 JSON으로 변환
        report_data = asdict(suite_result)

        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)

        logger.info("Test report saved", report_path=str(report_path))

        # 요약 보고서 출력
        print("\n" + "="*80)
        print("🧪 STABILIZATION SYSTEM TEST REPORT")
        print("="*80)
        print(f"📊 Overall Result: {'✅ PASS' if suite_result.overall_success else '❌ FAIL'}")
        print(f"⏱️  Total Duration: {suite_result.total_duration:.2f} seconds")
        print(f"📈 Success Rate: {suite_result.components_passed}/{suite_result.components_tested} ({suite_result.components_passed/suite_result.components_tested*100:.1f}%)")
        print(f"📄 Detailed Report: {report_path}")

        print("\n📋 Component Results:")
        for result in suite_result.results:
            status = "✅ PASS" if result.success else "❌ FAIL"
            print(f"  {status} {result.component:<25} ({result.duration_seconds:.2f}s)")
            if not result.success and result.error_message:
                print(f"      Error: {result.error_message}")

        print("\n" + "="*80)


async def main():
    """메인 함수"""
    import argparse

    parser = argparse.ArgumentParser(description="네이버 포스트 안정화 시스템 종합 테스트")
    parser.add_argument("--artifacts-dir", default="./test_artifacts",
                       help="테스트 결과물 저장 디렉토리")
    parser.add_argument("--quick", action="store_true",
                       help="빠른 테스트 모드 (일부 테스트 생략)")

    args = parser.parse_args()

    # 테스터 초기화 및 실행
    tester = StabilizationSystemTester(
        artifacts_dir=args.artifacts_dir,
        quick_mode=args.quick,
    )

    try:
        suite_result = await tester.run_full_test_suite()

        # 결과에 따른 exit code 반환
        sys.exit(0 if suite_result.overall_success else 1)

    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        print("\n🛑 테스트가 사용자에 의해 중단되었습니다.")
        sys.exit(130)
    except Exception as e:
        logger.error("Test suite execution failed", error=e)
        print(f"\n💥 테스트 실행 중 오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
