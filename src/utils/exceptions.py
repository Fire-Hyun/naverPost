"""
네이버 블로그 포스팅 자동화 시스템 예외 클래스 정의
각 단계별로 발생할 수 있는 예외를 명확히 분류합니다.
"""

class BlogSystemError(Exception):
    """블로그 시스템 기본 예외 클래스"""

    def __init__(self, message: str, step: str = "", details: str = ""):
        self.message = message
        self.step = step
        self.details = details
        super().__init__(f"[{step}] {message}")


class APIError(BlogSystemError):
    """API 호출 실패 예외"""

    def __init__(self, message: str, api_name: str = "", status_code: int = None):
        self.api_name = api_name
        self.status_code = status_code
        super().__init__(
            message,
            step=f"API_{api_name}",
            details=f"Status: {status_code}" if status_code else ""
        )


class FileProcessingError(BlogSystemError):
    """파일 처리 실패 예외"""

    def __init__(self, message: str, file_path: str = ""):
        self.file_path = file_path
        super().__init__(
            message,
            step="FILE_PROCESSING",
            details=f"File: {file_path}"
        )


class ContentGenerationError(BlogSystemError):
    """콘텐츠 생성 실패 예외"""

    def __init__(self, message: str, content_type: str = ""):
        self.content_type = content_type
        super().__init__(
            message,
            step="CONTENT_GENERATION",
            details=f"Type: {content_type}"
        )


class QualityValidationError(BlogSystemError):
    """품질 검증 실패 예외"""

    def __init__(self, message: str, validation_type: str = "", score: float = None):
        self.validation_type = validation_type
        self.score = score
        super().__init__(
            message,
            step="QUALITY_VALIDATION",
            details=f"Type: {validation_type}, Score: {score}" if score else f"Type: {validation_type}"
        )


class NaverBlogError(BlogSystemError):
    """네이버 블로그 관련 예외"""

    def __init__(self, message: str, operation: str = ""):
        self.operation = operation
        super().__init__(
            message,
            step="NAVER_BLOG",
            details=f"Operation: {operation}"
        )


# 구체적인 예외 클래스들

class ImageUploadError(FileProcessingError):
    """이미지 업로드 실패 예외"""

    def __init__(self, message: str, file_path: str = "", file_size: int = None):
        self.file_size = file_size
        super().__init__(message, file_path)
        if file_size:
            self.details += f", Size: {file_size:,} bytes"


class OpenAIError(APIError):
    """OpenAI API 호출 실패 예외"""

    def __init__(self, message: str, model: str = "", tokens_used: int = None):
        self.model = model
        self.tokens_used = tokens_used
        super().__init__(message, "OpenAI")
        if model:
            self.details += f", Model: {model}"
        if tokens_used:
            self.details += f", Tokens: {tokens_used}"


class SeleniumError(NaverBlogError):
    """Selenium 자동화 실패 예외"""

    def __init__(self, message: str, operation: str = "", element: str = ""):
        self.element = element
        super().__init__(message, operation)
        if element:
            self.details += f", Element: {element}"


class LoginError(NaverBlogError):
    """네이버 로그인 실패 예외"""

    def __init__(self, message: str, attempt_count: int = 1):
        self.attempt_count = attempt_count
        super().__init__(message, "LOGIN")
        self.details = f"Attempt: {attempt_count}"


class PostUploadError(NaverBlogError):
    """포스트 업로드 실패 예외"""

    def __init__(self, message: str, post_title: str = "", step: str = ""):
        self.post_title = post_title
        self.upload_step = step
        super().__init__(message, "POST_UPLOAD")
        details_parts = []
        if post_title:
            details_parts.append(f"Title: {post_title}")
        if step:
            details_parts.append(f"Step: {step}")
        self.details = ", ".join(details_parts)


class SessionError(NaverBlogError):
    """네이버 블로그 세션/페이지 오류 예외"""

    def __init__(self, message: str, operation: str = "SESSION"):
        super().__init__(message, operation)


class EditorError(NaverBlogError):
    """네이버 블로그 에디터 조작 오류 예외"""

    def __init__(self, message: str, operation: str = "EDITOR"):
        super().__init__(message, operation)


class VerificationError(NaverBlogError):
    """네이버 블로그 저장/업로드 검증 실패 예외"""

    def __init__(self, message: str, operation: str = "VERIFY"):
        super().__init__(message, operation)


class ValidationRuleError(QualityValidationError):
    """품질 규칙 검증 실패 예외"""

    def __init__(self, message: str, rule_name: str = "", expected: float = None, actual: float = None):
        self.rule_name = rule_name
        self.expected = expected
        self.actual = actual
        super().__init__(message, rule_name)
        if expected is not None and actual is not None:
            self.details += f", Expected: {expected}, Actual: {actual}"


class LowQualityContentError(QualityValidationError):
    """저품질 콘텐츠 탐지 예외"""

    def __init__(self, message: str, quality_score: float, min_score: float):
        self.quality_score = quality_score
        self.min_score = min_score
        super().__init__(message, "low_quality", quality_score)
        self.details = f"Score: {quality_score}/{min_score}"


class NaverComplianceError(QualityValidationError):
    """네이버 정책 위반 탐지 예외"""

    def __init__(self, message: str, compliance_score: float, min_score: float, violations: list = None):
        self.compliance_score = compliance_score
        self.min_score = min_score
        self.violations = violations or []
        super().__init__(message, "naver_compliance", compliance_score)
        violations_text = ", ".join(self.violations) if self.violations else "None specified"
        self.details = f"Score: {compliance_score}/{min_score}, Violations: {violations_text}"


class ConfigurationError(BlogSystemError):
    """설정 오류 예외"""

    def __init__(self, message: str, missing_keys: list = None):
        self.missing_keys = missing_keys or []
        super().__init__(message, "CONFIGURATION")
        if self.missing_keys:
            self.details = f"Missing keys: {', '.join(self.missing_keys)}"


class EnvironmentConfigError(ConfigurationError):
    """실행 환경 설정 오류 (XServer 없음, 브라우저 바이너리 등)"""

    # 에러 코드 상수
    ENV_NO_XSERVER = "ENV_NO_XSERVER"
    PLAYWRIGHT_LAUNCH_FAILED = "PLAYWRIGHT_LAUNCH_FAILED"

    def __init__(self, message: str, error_code: str = "", resolution: str = ""):
        self.error_code = error_code
        self.resolution = resolution
        super().__init__(message)
        self.step = "ENVIRONMENT"
        details_parts = []
        if error_code:
            details_parts.append(f"Code: {error_code}")
        if resolution:
            details_parts.append(f"Resolution: {resolution}")
        if details_parts:
            self.details = ", ".join(details_parts)


class NetworkTimeoutError(APIError):
    """네트워크 타임아웃 예외"""

    def __init__(self, message: str, api_name: str = "", timeout_duration: float = None):
        self.timeout_duration = timeout_duration
        super().__init__(message, api_name)
        if timeout_duration:
            self.details = f"Timeout: {timeout_duration}s"


class AuthenticationError(APIError):
    """API 인증 실패 예외"""

    def __init__(self, message: str, api_name: str = ""):
        super().__init__(message, api_name, 401)
        self.details = "Invalid API key or credentials"


class DataConsistencyError(BlogSystemError):
    """데이터 일관성 오류 예외"""

    def __init__(self, message: str, data_type: str = "", expected: str = "", actual: str = ""):
        self.data_type = data_type
        self.expected = expected
        self.actual = actual
        super().__init__(message, "DATA_CONSISTENCY")
        details_parts = []
        if data_type:
            details_parts.append(f"Type: {data_type}")
        if expected:
            details_parts.append(f"Expected: {expected}")
        if actual:
            details_parts.append(f"Actual: {actual}")
        if details_parts:
            self.details = ", ".join(details_parts)


# === 안정화 관련 추가 예외 클래스 ===

class ExternalServiceError(APIError):
    """외부 서비스 호출 실패 기본 예외"""

    def __init__(self, message: str, service_name: str = "", status_code: int = None,
                 response_body: str = "", retry_count: int = 0):
        self.service_name = service_name
        self.response_body = response_body
        self.retry_count = retry_count
        super().__init__(message, service_name, status_code)
        if response_body:
            # 응답 본문이 너무 길면 잘라냄 (로깅용)
            truncated_body = response_body[:200] + "..." if len(response_body) > 200 else response_body
            self.details += f", Response: {truncated_body}"
        if retry_count > 0:
            self.details += f", Retries: {retry_count}"


class RetryableError(ExternalServiceError):
    """재시도 가능한 오류"""
    pass


class NonRetryableError(ExternalServiceError):
    """재시도 불가능한 오류"""
    pass


class RateLimitError(RetryableError):
    """레이트 리밋 예외"""

    def __init__(self, message: str, service_name: str = "", retry_after: int = None):
        self.retry_after = retry_after
        super().__init__(message, service_name, 429)
        if retry_after:
            self.details += f", Retry-After: {retry_after}s"


class CircuitBreakerError(ExternalServiceError):
    """회로 차단기 작동 예외"""

    def __init__(self, message: str, service_name: str = "", failure_count: int = 0):
        self.failure_count = failure_count
        super().__init__(message, service_name)
        self.details += f", Failures: {failure_count}"


class DNSResolutionError(NetworkTimeoutError):
    """DNS 해결 실패 예외"""

    def __init__(self, message: str, hostname: str = ""):
        self.hostname = hostname
        super().__init__(message, "DNS")
        if hostname:
            self.details = f"Hostname: {hostname}"


class ConnectionError(RetryableError):
    """연결 오류 예외"""

    def __init__(self, message: str, service_name: str = "", endpoint: str = ""):
        self.endpoint = endpoint
        super().__init__(message, service_name)
        if endpoint:
            self.details += f", Endpoint: {endpoint}"


class TimeoutError(RetryableError):
    """타임아웃 예외"""

    def __init__(self, message: str, service_name: str = "", timeout_type: str = "read",
                 timeout_duration: float = None):
        self.timeout_type = timeout_type  # connect, read, total
        super().__init__(message, service_name)
        details_parts = [f"Type: {timeout_type}"]
        if timeout_duration:
            details_parts.append(f"Duration: {timeout_duration}s")
        self.details += f", {', '.join(details_parts)}"


class ParseError(NonRetryableError):
    """응답 파싱 오류"""

    def __init__(self, message: str, service_name: str = "", response_format: str = ""):
        self.response_format = response_format
        super().__init__(message, service_name)
        if response_format:
            self.details += f", Format: {response_format}"


class AuthExpiredError(NonRetryableError):
    """인증 만료 예외 (재로그인 필요)"""

    def __init__(self, message: str, service_name: str = ""):
        super().__init__(message, service_name, 401)
        self.details += ", Action: Re-authentication required"


class ServiceUnavailableError(RetryableError):
    """서비스 이용 불가 예외"""

    def __init__(self, message: str, service_name: str = "", estimated_recovery: int = None):
        self.estimated_recovery = estimated_recovery
        super().__init__(message, service_name, 503)
        if estimated_recovery:
            self.details += f", Recovery: ~{estimated_recovery}s"


class BadGatewayError(RetryableError):
    """Bad Gateway 예외"""

    def __init__(self, message: str, service_name: str = ""):
        super().__init__(message, service_name, 502)


class TooManyRequestsError(RateLimitError):
    """요청 횟수 초과 예외"""

    def __init__(self, message: str, service_name: str = "", window_seconds: int = None):
        self.window_seconds = window_seconds
        super().__init__(message, service_name)
        if window_seconds:
            self.details += f", Window: {window_seconds}s"


# === 네이버 서비스별 특화 예외 ===

class NaverMapAPIError(ExternalServiceError):
    """네이버 지도 API 오류"""

    def __init__(self, message: str, query: str = "", status_code: int = None,
                 response_body: str = ""):
        self.query = query
        super().__init__(message, "NaverMap", status_code, response_body)
        if query:
            self.details += f", Query: {query}"


class NaverBlogUploadError(ExternalServiceError):
    """네이버 블로그 업로드 오류"""

    def __init__(self, message: str, operation: str = "", blog_title: str = ""):
        self.operation = operation
        self.blog_title = blog_title
        super().__init__(message, "NaverBlog")
        details_parts = []
        if operation:
            details_parts.append(f"Operation: {operation}")
        if blog_title:
            details_parts.append(f"Title: {blog_title}")
        if details_parts:
            self.details += f", {', '.join(details_parts)}"


class TelegramAPIError(ExternalServiceError):
    """텔레그램 API 오류"""

    def __init__(self, message: str, method: str = "", chat_id: str = ""):
        self.method = method
        self.chat_id = chat_id
        super().__init__(message, "Telegram")
        details_parts = []
        if method:
            details_parts.append(f"Method: {method}")
        if chat_id:
            details_parts.append(f"Chat: {chat_id}")
        if details_parts:
            self.details += f", {', '.join(details_parts)}"


class ImageProcessingError(FileProcessingError):
    """이미지 처리 오류"""

    def __init__(self, message: str, file_path: str = "", operation: str = "",
                 dimensions: tuple = None, file_size: int = None):
        self.operation = operation
        self.dimensions = dimensions
        self.file_size = file_size
        super().__init__(message, file_path)
        details_parts = []
        if operation:
            details_parts.append(f"Operation: {operation}")
        if dimensions:
            details_parts.append(f"Size: {dimensions[0]}x{dimensions[1]}")
        if file_size:
            details_parts.append(f"FileSize: {file_size:,}B")
        if details_parts:
            self.details += f", {', '.join(details_parts)}"


# === 예외 분류 헬퍼 함수 ===

def classify_http_error(status_code: int, service_name: str = "", message: str = "",
                       response_body: str = ""):
    """HTTP 상태 코드를 기반으로 적절한 예외 클래스 반환"""

    if status_code == 400:
        return NonRetryableError(message or "Bad Request", service_name, status_code, response_body)
    elif status_code == 401:
        return AuthExpiredError(message or "Unauthorized", service_name)
    elif status_code == 403:
        return NonRetryableError(message or "Forbidden", service_name, status_code, response_body)
    elif status_code == 404:
        return NonRetryableError(message or "Not Found", service_name, status_code, response_body)
    elif status_code == 429:
        return RateLimitError(message or "Too Many Requests", service_name)
    elif status_code == 500:
        return RetryableError(message or "Internal Server Error", service_name, status_code, response_body)
    elif status_code == 502:
        return BadGatewayError(message or "Bad Gateway", service_name)
    elif status_code == 503:
        return ServiceUnavailableError(message or "Service Unavailable", service_name)
    elif status_code == 504:
        return TimeoutError(message or "Gateway Timeout", service_name, "gateway")
    elif 400 <= status_code < 500:
        return NonRetryableError(message or f"Client Error {status_code}", service_name, status_code, response_body)
    elif 500 <= status_code < 600:
        return RetryableError(message or f"Server Error {status_code}", service_name, status_code, response_body)
    else:
        return ExternalServiceError(message or f"HTTP Error {status_code}", service_name, status_code, response_body)


def is_retryable_error(error: Exception) -> bool:
    """예외가 재시도 가능한지 확인"""
    return isinstance(error, (
        RetryableError,
        ConnectionError,
        TimeoutError,
        DNSResolutionError,
        RateLimitError,
        ServiceUnavailableError,
        BadGatewayError
    ))