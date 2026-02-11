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