"""
Retry management for blog content quality verification
"""

import logging
from typing import Optional, Callable, Any, Dict
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class RetryResult(Enum):
    """재시도 결과 상태"""
    SUCCESS = "success"
    RETRY_NEEDED = "retry_needed"
    MAX_ATTEMPTS_EXCEEDED = "max_attempts_exceeded"
    FATAL_ERROR = "fatal_error"


@dataclass
class RetryAttempt:
    """재시도 시도 정보"""
    attempt_number: int
    total_attempts: int
    success: bool
    error: Optional[str] = None
    result_data: Optional[Dict[str, Any]] = None


class RetryManager:
    """재시도 로직을 관리하는 클래스"""

    def __init__(self, max_attempts: int = 5):
        self.max_attempts = max_attempts
        self.current_attempt = 0
        self.logger = logging.getLogger(__name__)

    async def execute_with_retry(
        self,
        operation: Callable,
        should_retry_func: Callable[[Any], bool],
        context: str = "operation"
    ) -> RetryAttempt:
        """
        재시도 로직을 사용하여 작업을 실행

        Args:
            operation: 실행할 비동기 함수
            should_retry_func: 재시도가 필요한지 판단하는 함수
            context: 로그 및 에러 메시지용 컨텍스트

        Returns:
            RetryAttempt: 최종 시도 결과
        """
        for attempt in range(self.max_attempts):
            self.current_attempt = attempt + 1

            try:
                if attempt > 0:
                    logger.info(f"{context} retry attempt {self.current_attempt}/{self.max_attempts}")

                # 작업 실행
                result = await operation(attempt)

                # 성공 여부 확인
                if should_retry_func(result):
                    # 재시도 필요
                    if attempt == self.max_attempts - 1:
                        # 마지막 시도였음
                        logger.error(f"{context} failed after {self.max_attempts} attempts")
                        return RetryAttempt(
                            attempt_number=self.current_attempt,
                            total_attempts=self.max_attempts,
                            success=False,
                            error=f"최대 {self.max_attempts}회 시도 후에도 실패했습니다",
                            result_data=result if isinstance(result, dict) else None
                        )
                    else:
                        # 다음 시도 진행
                        logger.info(f"{context} needs retry, attempting {attempt + 2}/{self.max_attempts}")
                        continue
                else:
                    # 성공
                    success_message = context
                    if attempt > 0:
                        success_message += f" ({attempt + 1}회 시도 후)"

                    logger.info(f"{context} successful: attempts={attempt + 1}")

                    return RetryAttempt(
                        attempt_number=self.current_attempt,
                        total_attempts=self.max_attempts,
                        success=True,
                        result_data=result if isinstance(result, dict) else None
                    )

            except Exception as e:
                logger.error(f"{context} error on attempt {attempt + 1}: {e}")

                if attempt == self.max_attempts - 1:
                    # 마지막 시도에서도 실패
                    return RetryAttempt(
                        attempt_number=self.current_attempt,
                        total_attempts=self.max_attempts,
                        success=False,
                        error=f"최대 {self.max_attempts}회 시도 후에도 오류가 지속됩니다: {str(e)}"
                    )
                # 다음 시도 계속
                continue

        # 이 라인에 도달하면 안되지만, 안전을 위해 추가
        return RetryAttempt(
            attempt_number=self.max_attempts,
            total_attempts=self.max_attempts,
            success=False,
            error=f"예상치 못한 오류로 {self.max_attempts}회 시도가 완료되지 못했습니다"
        )

    def reset(self):
        """재시도 카운터 리셋"""
        self.current_attempt = 0