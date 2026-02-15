"""
Unified blog content generation manager
Replaces duplicate logic between _generate_blog_content and _regenerate_blog_content
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BlogGenerationResult:
    """블로그 생성 결과"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BlogContentManager:
    """통합 블로그 콘텐츠 생성 관리자"""

    def __init__(self, blog_generator, data_manager=None, settings=None):
        self.blog_generator = blog_generator
        self.data_manager = data_manager
        self.settings = settings
        self.logger = logging.getLogger(__name__)

    async def generate_blog_content(
        self,
        date_directory: str,
        force_regenerate: bool = False
    ) -> BlogGenerationResult:
        """
        AI 블로그 콘텐츠 생성 (통합 메서드)

        Args:
            date_directory: 날짜 디렉토리명
            force_regenerate: 기존 블로그를 강제로 덮어쓸지 여부

        Returns:
            BlogGenerationResult: 생성 결과
        """
        operation_type = "regeneration" if force_regenerate else "generation"
        operation_message = "재생성" if force_regenerate else "생성"

        try:
            # 비동기 실행을 위해 executor 사용
            loop = asyncio.get_event_loop()

            # force_regenerate 매개변수에 따라 호출 방식 결정
            if force_regenerate:
                result = await loop.run_in_executor(
                    None,
                    self.blog_generator.generate_from_session_data,
                    date_directory,
                    True  # force_regenerate=True
                )
            else:
                result = await loop.run_in_executor(
                    None,
                    self.blog_generator.generate_from_session_data,
                    date_directory
                )

            if result["success"]:
                self.logger.info(f"Blog {operation_type} successful for {date_directory}")

                # 데이터 구성
                generation_data = {
                    "blog_file": result.get('blog_file_path') or self._resolve_blog_file_path(date_directory),
                    "metadata": result.get('metadata'),
                    "length": result.get('metadata', {}).get('actual_length', 0)
                }

                # 재생성인 경우 플래그 추가
                if force_regenerate:
                    generation_data["regenerated"] = True

                return BlogGenerationResult(
                    success=True,
                    message=f"블로그 {operation_message} 완료",
                    data=generation_data
                )
            else:
                error_msg = result.get('error', '알 수 없는 오류')
                self.logger.error(f"Blog {operation_type} failed: {error_msg}")

                return BlogGenerationResult(
                    success=False,
                    message=f"블로그 {operation_message} 실패",
                    error=error_msg
                )

        except Exception as e:
            self.logger.error(f"Blog {operation_type} error: {e}")
            return BlogGenerationResult(
                success=False,
                message=f"블로그 {operation_message} 중 오류 발생",
                error=str(e)
            )

    def _resolve_blog_file_path(self, date_directory: str) -> Optional[str]:
        """date_directory 기준 blog_result.md 실제 경로를 안전하게 해석"""
        try:
            if not self.data_manager or not self.settings:
                return None

            target_dir = self.data_manager.date_manager.get_directory_path(date_directory)
            if not target_dir:
                from pathlib import Path
                target_dir = Path(self.settings.DATA_DIR) / date_directory

            blog_file = target_dir / "blog_result.md"
            if blog_file.exists():
                return str(blog_file)
            return None
        except Exception:
            return None

    # Legacy methods for backward compatibility
    async def generate_initial_content(self, date_directory: str) -> BlogGenerationResult:
        """초기 블로그 생성 (하위 호환성을 위한 메서드)"""
        return await self.generate_blog_content(date_directory, force_regenerate=False)

    async def regenerate_content(self, date_directory: str) -> BlogGenerationResult:
        """블로그 재생성 (하위 호환성을 위한 메서드)"""
        return await self.generate_blog_content(date_directory, force_regenerate=True)