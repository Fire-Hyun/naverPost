"""
구조화된 로깅 시스템
안정성 모니터링을 위한 JSON 기반 로깅, 메트릭 수집, correlation ID 추적
"""

import json
import time
import logging
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field, asdict
from contextlib import contextmanager
from pathlib import Path
import uuid

from src.config.settings import Settings


@dataclass
class LogContext:
    """로그 컨텍스트"""
    correlation_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    operation: Optional[str] = None
    service: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        data = asdict(self)
        # start_time을 ISO 형식으로 변환
        data['start_time'] = datetime.fromtimestamp(self.start_time).isoformat()
        return data


@dataclass
class MetricEvent:
    """메트릭 이벤트"""
    name: str
    value: Union[int, float]
    unit: str = "count"
    tags: Dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "metric": self.name,
            "value": self.value,
            "unit": self.unit,
            "tags": self.tags,
            "timestamp": self.timestamp,
            "timestamp_iso": datetime.fromtimestamp(self.timestamp).isoformat()
        }


class StructuredLogger:
    """구조화된 로거 클래스"""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"structured.{name}")
        self._context_stack = threading.local()
        self._setup_logger()

    def _setup_logger(self):
        """로거 설정"""
        if self.logger.handlers:
            return  # 이미 설정됨

        self.logger.setLevel(logging.INFO)

        # JSON 파일 핸들러
        json_log_file = Path(Settings.LOG_DIR) / f"{self.name}_structured.jsonl"
        json_log_file.parent.mkdir(exist_ok=True)

        json_handler = logging.FileHandler(json_log_file, encoding='utf-8')
        json_handler.setLevel(logging.INFO)
        json_formatter = logging.Formatter('%(message)s')  # JSON 메시지만
        json_handler.setFormatter(json_formatter)

        self.logger.addHandler(json_handler)
        self.logger.propagate = False

    def _get_context_stack(self) -> List[LogContext]:
        """현재 스레드의 컨텍스트 스택 반환"""
        if not hasattr(self._context_stack, 'stack'):
            self._context_stack.stack = []
        return self._context_stack.stack

    def _get_current_context(self) -> Optional[LogContext]:
        """현재 활성 컨텍스트 반환"""
        stack = self._get_context_stack()
        return stack[-1] if stack else None

    def _create_log_entry(self, level: str, message: str, extra: Dict[str, Any] = None) -> Dict[str, Any]:
        """로그 엔트리 생성"""
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level.upper(),
            "logger": self.name,
            "message": message,
        }

        # 현재 컨텍스트 추가
        context = self._get_current_context()
        if context:
            entry["context"] = context.to_dict()

        # 추가 데이터
        if extra:
            entry["extra"] = extra

        return entry

    def _emit(self, level: str, message: str, extra: Dict[str, Any] = None):
        """로그 출력"""
        entry = self._create_log_entry(level, message, extra)
        json_message = json.dumps(entry, ensure_ascii=False, default=str)

        # JSON 로그 파일에 출력
        if level.upper() == "DEBUG":
            self.logger.debug(json_message)
        elif level.upper() == "INFO":
            self.logger.info(json_message)
        elif level.upper() == "WARNING":
            self.logger.warning(json_message)
        elif level.upper() == "ERROR":
            self.logger.error(json_message)
        elif level.upper() == "CRITICAL":
            self.logger.critical(json_message)

    def debug(self, message: str, **kwargs):
        """디버그 로그"""
        self._emit("debug", message, kwargs if kwargs else None)

    def info(self, message: str, **kwargs):
        """정보 로그"""
        self._emit("info", message, kwargs if kwargs else None)

    def success(self, message: str, **kwargs):
        """성공 로그 (info 레벨)"""
        self._emit("info", message, kwargs if kwargs else None)

    def warning(self, message: str, **kwargs):
        """경고 로그"""
        self._emit("warning", message, kwargs if kwargs else None)

    def error(self, message: str, error: Exception = None, **kwargs):
        """에러 로그"""
        extra = kwargs.copy() if kwargs else {}
        if error:
            extra.update({
                "error_type": type(error).__name__,
                "error_message": str(error),
                "error_details": getattr(error, 'details', None)
            })
        self._emit("error", message, extra if extra else None)

    def critical(self, message: str, error: Exception = None, **kwargs):
        """치명적 에러 로그"""
        extra = kwargs.copy() if kwargs else {}
        if error:
            extra.update({
                "error_type": type(error).__name__,
                "error_message": str(error),
                "error_details": getattr(error, 'details', None)
            })
        self._emit("critical", message, extra if extra else None)

    def metric(self, name: str, value: Union[int, float], unit: str = "count", **tags):
        """메트릭 로그"""
        metric = MetricEvent(name=name, value=value, unit=unit, tags=tags)
        self._emit("info", f"METRIC: {name}", {"metric": metric.to_dict()})

    def duration(self, name: str, duration_seconds: float, **tags):
        """지속 시간 메트릭"""
        self.metric(f"{name}.duration", round(duration_seconds * 1000, 2), "milliseconds", **tags)

    def counter(self, name: str, value: int = 1, **tags):
        """카운터 메트릭"""
        self.metric(f"{name}.count", value, "count", **tags)

    def gauge(self, name: str, value: Union[int, float], **tags):
        """게이지 메트릭"""
        self.metric(f"{name}.gauge", value, "gauge", **tags)

    @contextmanager
    def context(self, operation: str, correlation_id: str = None, **kwargs):
        """로그 컨텍스트 매니저"""
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())[:8]

        context = LogContext(
            correlation_id=correlation_id,
            operation=operation,
            service=self.name,
            **kwargs
        )

        stack = self._get_context_stack()
        stack.append(context)

        try:
            self.info(f"Operation started: {operation}", correlation_id=correlation_id)
            yield context
            duration = time.time() - context.start_time
            self.info(f"Operation completed: {operation}",
                     correlation_id=correlation_id,
                     duration_ms=round(duration * 1000, 2))
            self.duration(f"operation.{operation}", duration, status="success")
        except Exception as e:
            duration = time.time() - context.start_time
            self.error(f"Operation failed: {operation}",
                      error=e,
                      correlation_id=correlation_id,
                      duration_ms=round(duration * 1000, 2))
            self.duration(f"operation.{operation}", duration, status="error")
            self.counter(f"operation.{operation}.errors")
            raise
        finally:
            stack.pop()

    @contextmanager
    def external_call_context(self, service: str, operation: str, url: str = None):
        """외부 API 호출 컨텍스트"""
        correlation_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        self.info(f"External call started",
                 service=service,
                 operation=operation,
                 url=url,
                 correlation_id=correlation_id)

        try:
            yield correlation_id
            duration = time.time() - start_time
            self.info(f"External call completed",
                     service=service,
                     operation=operation,
                     correlation_id=correlation_id,
                     duration_ms=round(duration * 1000, 2))
            self.duration(f"external.{service}.{operation}", duration, status="success")
        except Exception as e:
            duration = time.time() - start_time
            self.error(f"External call failed",
                      service=service,
                      operation=operation,
                      error=e,
                      correlation_id=correlation_id,
                      duration_ms=round(duration * 1000, 2))
            self.duration(f"external.{service}.{operation}", duration, status="error")
            self.counter(f"external.{service}.{operation}.errors")
            raise

    def log_http_request(self, method: str, url: str, status_code: int = None,
                        duration_ms: float = None, error: Exception = None, **kwargs):
        """HTTP 요청 로그"""
        extra = {
            "http_method": method,
            "http_url": url,
            "http_status_code": status_code,
            "duration_ms": duration_ms,
            **kwargs
        }

        if error:
            self.error(f"HTTP {method} {url} failed", error=error, **extra)
            self.counter("http.requests.errors", method=method, status_code=status_code or 0)
        else:
            self.info(f"HTTP {method} {url} completed", **extra)
            self.counter("http.requests.success", method=method, status_code=status_code or 0)

        if duration_ms:
            self.duration("http.request", duration_ms / 1000, method=method, url=url)

    def log_database_query(self, query_type: str, table: str = None, duration_ms: float = None,
                          rows_affected: int = None, error: Exception = None):
        """데이터베이스 쿼리 로그"""
        extra = {
            "db_query_type": query_type,
            "db_table": table,
            "duration_ms": duration_ms,
            "rows_affected": rows_affected
        }

        if error:
            self.error(f"Database {query_type} failed", error=error, **extra)
            self.counter("database.queries.errors", query_type=query_type, table=table or "unknown")
        else:
            self.info(f"Database {query_type} completed", **extra)
            self.counter("database.queries.success", query_type=query_type, table=table or "unknown")

        if duration_ms:
            self.duration("database.query", duration_ms / 1000, query_type=query_type, table=table or "unknown")

    def log_user_action(self, user_id: str, action: str, **kwargs):
        """사용자 액션 로그"""
        with self.context("user_action", user_id=user_id, **kwargs):
            self.info(f"User action: {action}", user_id=user_id, action=action, **kwargs)
            self.counter("user.actions", action=action)

    def log_system_health(self, component: str, status: str, **metrics):
        """시스템 헬스 로그"""
        self.info(f"System health check: {component}",
                 component=component,
                 health_status=status,
                 **metrics)

        # 헬스 상태를 메트릭으로 기록
        health_value = 1 if status == "healthy" else 0
        self.gauge(f"health.{component}", health_value, status=status)

        # 개별 메트릭들도 기록
        for metric_name, value in metrics.items():
            if isinstance(value, (int, float)):
                self.gauge(f"health.{component}.{metric_name}", value)


# === 전역 로거 인스턴스들 ===

# 서비스별 구조화된 로거
telegram_logger = StructuredLogger("telegram")
naver_map_logger = StructuredLogger("naver_map")
naver_blog_logger = StructuredLogger("naver_blog")
blog_generator_logger = StructuredLogger("blog_generator")
image_processor_logger = StructuredLogger("image_processor")
quality_checker_logger = StructuredLogger("quality_checker")
http_client_logger = StructuredLogger("http_client")
system_logger = StructuredLogger("system")


def get_logger(name: str) -> StructuredLogger:
    """구조화된 로거 인스턴스 반환"""
    return StructuredLogger(name)


# === 편의 함수들 ===

def log_startup_info():
    """시스템 시작 정보 로깅"""
    system_logger.info("System starting up",
                      version=getattr(Settings, 'VERSION', 'unknown'),
                      environment=getattr(Settings, 'ENVIRONMENT', 'unknown'),
                      log_level=Settings.LOG_LEVEL)


def log_shutdown_info():
    """시스템 종료 정보 로깅"""
    system_logger.info("System shutting down")


@contextmanager
def operation_context(operation: str, logger_name: str = "system", **kwargs):
    """전역 오퍼레이션 컨텍스트"""
    logger_instance = get_logger(logger_name)
    with logger_instance.context(operation, **kwargs) as ctx:
        yield ctx


@contextmanager
def log_context(operation: str = "", operation_id: str = "", logger_name: str = "system", **kwargs):
    """log_context: operation_context의 별칭 (operation_id 지원)"""
    logger_instance = get_logger(logger_name)
    with logger_instance.context(operation, correlation_id=operation_id or None, **kwargs) as ctx:
        yield ctx


def mask_sensitive_data(data: Dict[str, Any], sensitive_keys: List[str] = None) -> Dict[str, Any]:
    """민감한 데이터 마스킹"""
    if sensitive_keys is None:
        sensitive_keys = [
            'password', 'token', 'secret', 'key', 'authorization',
            'x-api-key', 'cookie', 'session', 'credential'
        ]

    masked_data = data.copy()
    for key, value in masked_data.items():
        if any(sensitive_key in key.lower() for sensitive_key in sensitive_keys):
            if isinstance(value, str) and len(value) > 8:
                masked_data[key] = value[:4] + "*" * 4 + value[-4:]
            else:
                masked_data[key] = "***MASKED***"
        elif isinstance(value, dict):
            masked_data[key] = mask_sensitive_data(value, sensitive_keys)

    return masked_data


# === 로그 분석 도구 ===

class LogAnalyzer:
    """로그 분석 도구"""

    @staticmethod
    def parse_jsonl_log(log_file: Path) -> List[Dict[str, Any]]:
        """JSONL 로그 파일 파싱"""
        entries = []
        if not log_file.exists():
            return entries

        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue
        return entries

    @staticmethod
    def get_error_summary(log_entries: List[Dict[str, Any]]) -> Dict[str, int]:
        """에러 요약 생성"""
        error_counts = {}
        for entry in log_entries:
            if entry.get('level') in ['ERROR', 'CRITICAL']:
                error_type = entry.get('extra', {}).get('error_type', 'Unknown')
                error_counts[error_type] = error_counts.get(error_type, 0) + 1
        return error_counts

    @staticmethod
    def get_performance_summary(log_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """성능 요약 생성"""
        durations = []
        for entry in log_entries:
            if 'duration_ms' in entry.get('extra', {}):
                durations.append(entry['extra']['duration_ms'])

        if not durations:
            return {"count": 0}

        durations.sort()
        return {
            "count": len(durations),
            "avg_ms": round(sum(durations) / len(durations), 2),
            "min_ms": min(durations),
            "max_ms": max(durations),
            "p50_ms": durations[int(len(durations) * 0.5)],
            "p95_ms": durations[int(len(durations) * 0.95)]
        }