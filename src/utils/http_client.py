"""
안정화된 HTTP 클라이언트
외부 API 호출에 대한 재시도, 타임아웃, Circuit Breaker 등을 제공
"""

import asyncio
import json
import time
import random
import logging
from typing import Dict, Any, Optional, Union, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
from contextlib import asynccontextmanager
import httpx

from .exceptions import (
    ExternalServiceError, RetryableError, NonRetryableError,
    RateLimitError, CircuitBreakerError, DNSResolutionError,
    ConnectionError, TimeoutError, ParseError, classify_http_error,
    is_retryable_error
)

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """회로 차단기 상태"""
    CLOSED = "closed"      # 정상 상태
    OPEN = "open"          # 차단 상태
    HALF_OPEN = "half_open"  # 부분 개방 상태


@dataclass
class RetryConfig:
    """재시도 설정"""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_status_codes: List[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])


@dataclass
class CircuitBreakerConfig:
    """회로 차단기 설정"""
    failure_threshold: int = 5  # 실패 임계값
    recovery_timeout: float = 60.0  # 복구 대기 시간
    half_open_max_calls: int = 3  # Half-open 상태에서 최대 호출 횟수


@dataclass
class TimeoutConfig:
    """타임아웃 설정"""
    connect: float = 10.0
    read: float = 30.0
    total: float = 60.0


@dataclass
class RequestMetrics:
    """요청 메트릭"""
    service_name: str
    method: str
    url: str
    start_time: float
    end_time: float = None
    status_code: int = None
    retry_count: int = 0
    error: Optional[Exception] = None
    correlation_id: str = ""

    @property
    def duration(self) -> float:
        """요청 소요 시간"""
        if self.end_time is None:
            return time.time() - self.start_time
        return self.end_time - self.start_time

    @property
    def is_success(self) -> bool:
        """성공 여부"""
        return self.status_code and 200 <= self.status_code < 400

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환 (로깅용)"""
        return {
            "service": self.service_name,
            "method": self.method,
            "url": self.url,
            "duration_ms": round(self.duration * 1000, 2),
            "status_code": self.status_code,
            "retry_count": self.retry_count,
            "success": self.is_success,
            "error": str(self.error) if self.error else None,
            "correlation_id": self.correlation_id
        }


class CircuitBreaker:
    """회로 차단기"""

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.half_open_calls = 0
        self._lock = asyncio.Lock()

    async def can_execute(self) -> bool:
        """실행 가능한지 확인"""
        async with self._lock:
            if self.state == CircuitState.CLOSED:
                return True
            elif self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time >= self.config.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                    logger.info(f"Circuit breaker transitioned to HALF_OPEN")
                    return True
                return False
            else:  # HALF_OPEN
                return self.half_open_calls < self.config.half_open_max_calls

    async def record_success(self):
        """성공 기록"""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                logger.info(f"Circuit breaker recovered to CLOSED")
            elif self.state == CircuitState.CLOSED:
                self.failure_count = max(0, self.failure_count - 1)

    async def record_failure(self):
        """실패 기록"""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                logger.warning(f"Circuit breaker opened after half-open failure")
            elif self.state == CircuitState.CLOSED and self.failure_count >= self.config.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(f"Circuit breaker opened after {self.failure_count} failures")

            if self.state == CircuitState.HALF_OPEN:
                self.half_open_calls += 1


class StabilizedHTTPClient:
    """안정화된 HTTP 클라이언트"""

    def __init__(self,
                 service_name: str,
                 base_url: str = "",
                 default_headers: Dict[str, str] = None,
                 retry_config: RetryConfig = None,
                 circuit_breaker_config: CircuitBreakerConfig = None,
                 timeout_config: TimeoutConfig = None,
                 enable_circuit_breaker: bool = True):
        self.service_name = service_name
        self.base_url = base_url.rstrip('/')
        self.default_headers = default_headers or {}
        self.retry_config = retry_config or RetryConfig()
        self.timeout_config = timeout_config or TimeoutConfig()

        # Circuit breaker 설정
        self.circuit_breaker = None
        if enable_circuit_breaker:
            cb_config = circuit_breaker_config or CircuitBreakerConfig()
            self.circuit_breaker = CircuitBreaker(cb_config)

        # HTTP 클라이언트 설정
        timeout = httpx.Timeout(
            connect=self.timeout_config.connect,
            read=self.timeout_config.read,
            write=self.timeout_config.total,
            pool=self.timeout_config.total
        )

        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers=self.default_headers,
            follow_redirects=True
        )

        self.metrics: List[RequestMetrics] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """클라이언트 종료"""
        if self.client:
            await self.client.aclose()

    def _generate_correlation_id(self) -> str:
        """상관 관계 ID 생성"""
        import uuid
        return str(uuid.uuid4())[:8]

    def _get_full_url(self, url: str) -> str:
        """전체 URL 생성"""
        if url.startswith('http'):
            return url
        return f"{self.base_url}{url}" if self.base_url else url

    async def _calculate_delay(self, attempt: int) -> float:
        """재시도 지연 시간 계산"""
        if attempt <= 1:
            return 0

        # 지수 백오프
        delay = self.retry_config.base_delay * (
            self.retry_config.exponential_base ** (attempt - 2)
        )
        delay = min(delay, self.retry_config.max_delay)

        # 지터 추가
        if self.retry_config.jitter:
            jitter = delay * 0.1 * random.random()
            delay += jitter

        return delay

    def _should_retry(self, error: Exception, attempt: int) -> bool:
        """재시도 여부 결정"""
        if attempt >= self.retry_config.max_attempts:
            return False

        return is_retryable_error(error)

    def _log_request_start(self, method: str, url: str, correlation_id: str, **kwargs):
        """요청 시작 로그"""
        log_data = {
            "event": "http_request_start",
            "service": self.service_name,
            "method": method,
            "url": url,
            "correlation_id": correlation_id
        }

        # 민감 정보 제거
        if 'headers' in kwargs:
            safe_headers = {k: v for k, v in kwargs['headers'].items()
                          if k.lower() not in ['authorization', 'x-api-key', 'cookie']}
            log_data['headers'] = safe_headers

        logger.info(json.dumps(log_data, ensure_ascii=False))

    def _log_request_end(self, metrics: RequestMetrics):
        """요청 종료 로그"""
        log_data = {
            "event": "http_request_end",
            **metrics.to_dict()
        }
        logger.info(json.dumps(log_data, ensure_ascii=False))

    async def _execute_request(self, method: str, url: str, correlation_id: str,
                             **kwargs) -> httpx.Response:
        """실제 HTTP 요청 실행"""
        full_url = self._get_full_url(url)

        try:
            # 헤더에 correlation ID 추가
            headers = kwargs.get('headers', {})
            headers['X-Correlation-ID'] = correlation_id
            kwargs['headers'] = headers

            self._log_request_start(method, full_url, correlation_id, **kwargs)

            response = await self.client.request(method, full_url, **kwargs)

            # 상태 코드 기반 예외 처리
            if not (200 <= response.status_code < 400):
                error = classify_http_error(
                    response.status_code,
                    self.service_name,
                    f"HTTP {response.status_code}",
                    response.text[:500]
                )
                raise error

            return response

        except httpx.TimeoutException as e:
            if "timed out" in str(e).lower() and "connect" in str(e).lower():
                raise TimeoutError(f"Connection timeout to {full_url}", self.service_name, "connect")
            else:
                raise TimeoutError(f"Request timeout to {full_url}", self.service_name, "read")

        except httpx.ConnectError as e:
            if "name resolution failed" in str(e).lower() or "nodename nor servname provided" in str(e).lower():
                raise DNSResolutionError(f"DNS resolution failed for {full_url}", full_url)
            else:
                raise ConnectionError(f"Connection failed to {full_url}", self.service_name, full_url)

        except httpx.RequestError as e:
            raise ExternalServiceError(f"Request error: {str(e)}", self.service_name)

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """안정화된 HTTP 요청"""
        correlation_id = self._generate_correlation_id()
        metrics = RequestMetrics(
            service_name=self.service_name,
            method=method.upper(),
            url=self._get_full_url(url),
            start_time=time.time(),
            correlation_id=correlation_id
        )

        # Circuit breaker 확인
        if self.circuit_breaker:
            if not await self.circuit_breaker.can_execute():
                error = CircuitBreakerError(
                    f"Circuit breaker is open for {self.service_name}",
                    self.service_name,
                    self.circuit_breaker.failure_count
                )
                metrics.error = error
                metrics.end_time = time.time()
                self.metrics.append(metrics)
                self._log_request_end(metrics)
                raise error

        # 재시도 루프
        last_error = None
        for attempt in range(1, self.retry_config.max_attempts + 1):
            metrics.retry_count = attempt - 1

            try:
                # 재시도 지연
                if attempt > 1:
                    delay = await self._calculate_delay(attempt)
                    if delay > 0:
                        await asyncio.sleep(delay)

                # 요청 실행
                response = await self._execute_request(method, url, correlation_id, **kwargs)

                # 성공 처리
                metrics.status_code = response.status_code
                metrics.end_time = time.time()
                self.metrics.append(metrics)

                if self.circuit_breaker:
                    await self.circuit_breaker.record_success()

                self._log_request_end(metrics)
                return response

            except Exception as error:
                last_error = error
                metrics.error = error

                # Circuit breaker에 실패 기록
                if self.circuit_breaker and is_retryable_error(error):
                    await self.circuit_breaker.record_failure()

                # 재시도 여부 확인
                if not self._should_retry(error, attempt):
                    break

                logger.warning(
                    f"Request attempt {attempt} failed for {self.service_name}: {error}. "
                    f"Retrying in {await self._calculate_delay(attempt + 1):.1f}s..."
                )

        # 모든 재시도 실패
        metrics.end_time = time.time()
        self.metrics.append(metrics)
        self._log_request_end(metrics)

        if last_error:
            raise last_error
        else:
            raise ExternalServiceError(f"All retry attempts failed for {self.service_name}", self.service_name)

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """GET 요청"""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """POST 요청"""
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> httpx.Response:
        """PUT 요청"""
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> httpx.Response:
        """DELETE 요청"""
        return await self.request("DELETE", url, **kwargs)

    async def get_json(self, url: str, **kwargs) -> Dict[str, Any]:
        """JSON 응답을 반환하는 GET 요청"""
        response = await self.get(url, **kwargs)
        try:
            return response.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise ParseError(f"Invalid JSON response from {url}", self.service_name, "json")

    async def post_json(self, url: str, json_data: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
        """JSON 데이터를 보내고 JSON 응답을 반환하는 POST 요청"""
        if json_data is not None:
            kwargs['json'] = json_data

        response = await self.post(url, **kwargs)
        try:
            return response.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise ParseError(f"Invalid JSON response from {url}", self.service_name, "json")

    def get_metrics_summary(self) -> Dict[str, Any]:
        """메트릭 요약 반환"""
        if not self.metrics:
            return {"total_requests": 0}

        total_requests = len(self.metrics)
        successful_requests = sum(1 for m in self.metrics if m.is_success)
        total_duration = sum(m.duration for m in self.metrics)
        total_retries = sum(m.retry_count for m in self.metrics)

        durations = [m.duration for m in self.metrics]
        durations.sort()

        p50 = durations[int(len(durations) * 0.5)] if durations else 0
        p95 = durations[int(len(durations) * 0.95)] if durations else 0

        return {
            "service_name": self.service_name,
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "success_rate": successful_requests / total_requests if total_requests > 0 else 0,
            "total_retries": total_retries,
            "avg_duration_ms": round((total_duration / total_requests) * 1000, 2) if total_requests > 0 else 0,
            "p50_duration_ms": round(p50 * 1000, 2),
            "p95_duration_ms": round(p95 * 1000, 2),
            "circuit_breaker_state": self.circuit_breaker.state.value if self.circuit_breaker else None
        }


# === 편의 함수들 ===

@asynccontextmanager
async def create_http_client(service_name: str, **kwargs):
    """HTTP 클라이언트 컨텍스트 매니저"""
    client = StabilizedHTTPClient(service_name, **kwargs)
    try:
        yield client
    finally:
        await client.close()


def create_naver_map_client() -> StabilizedHTTPClient:
    """네이버 지도 API용 HTTP 클라이언트 생성"""
    from src.config.settings import Settings

    headers = {
        "X-Naver-Client-Id": Settings.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": Settings.NAVER_CLIENT_SECRET
    }

    retry_config = RetryConfig(
        max_attempts=3,
        base_delay=1.0,
        max_delay=10.0
    )

    timeout_config = TimeoutConfig(
        connect=5.0,
        read=15.0,
        total=30.0
    )

    return StabilizedHTTPClient(
        service_name="NaverMap",
        base_url="https://openapi.naver.com/v1",
        default_headers=headers,
        retry_config=retry_config,
        timeout_config=timeout_config
    )


def create_telegram_client(bot_token: str) -> StabilizedHTTPClient:
    """텔레그램 API용 HTTP 클라이언트 생성"""
    retry_config = RetryConfig(
        max_attempts=3,
        base_delay=2.0,
        max_delay=30.0
    )

    timeout_config = TimeoutConfig(
        connect=10.0,
        read=30.0,
        total=60.0
    )

    return StabilizedHTTPClient(
        service_name="Telegram",
        base_url=f"https://api.telegram.org/bot{bot_token}",
        retry_config=retry_config,
        timeout_config=timeout_config
    )