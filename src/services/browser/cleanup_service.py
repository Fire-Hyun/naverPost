"""
Browser cleanup service
"""

import asyncio
import logging
import subprocess
import shutil
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

from .session_manager import BrowserSessionManager

logger = logging.getLogger(__name__)


@dataclass
class CleanupResult:
    """정리 작업 결과"""
    success: bool
    processes_killed: List[str]
    directories_cleaned: List[str]
    warnings: List[str]
    errors: List[str]


class BrowserCleanupService:
    """브라우저 정리 서비스"""

    def __init__(self, session_manager: BrowserSessionManager):
        self.session_manager = session_manager
        self.logger = logging.getLogger(__name__)

        # 정리할 프로세스 패턴
        self.process_patterns = ['chrome', 'chromium', 'google-chrome']

        # 정리할 디렉토리들 (세션 매니저 기준)
        self.cleanup_directories = [
            'Sessions',
            'Cache',
            'Code Cache'
        ]

    async def cleanup_browser_session(self, wait_seconds: float = 2.0) -> CleanupResult:
        """브라우저 세션 전체 정리"""
        result = CleanupResult(
            success=True,
            processes_killed=[],
            directories_cleaned=[],
            warnings=[],
            errors=[]
        )

        try:
            # 1. 프로세스 정리
            await self._cleanup_processes(result)

            # 2. 세션 파일 정리
            await self._cleanup_session_files(result)

            # 3. 비동기 대기 (블로킹 time.sleep 대신)
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)

            self.logger.info(f"Browser cleanup completed: killed {len(result.processes_killed)} processes, cleaned {len(result.directories_cleaned)} directories")

            return result

        except Exception as e:
            self.logger.error(f"Browser cleanup error: {e}")
            result.success = False
            result.errors.append(str(e))
            return result

    async def _cleanup_processes(self, result: CleanupResult):
        """브라우저 프로세스 정리"""
        for pattern in self.process_patterns:
            try:
                # pkill을 비동기로 실행
                process = await asyncio.create_subprocess_exec(
                    'pkill', '-f', pattern,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10.0)

                if process.returncode == 0:
                    result.processes_killed.append(pattern)
                    self.logger.debug(f"Killed {pattern} processes")
                elif process.returncode == 1:
                    # pkill returns 1 when no processes found, which is normal
                    self.logger.debug(f"No {pattern} processes found")
                else:
                    error_msg = stderr.decode() if stderr else f"pkill returned {process.returncode}"
                    result.warnings.append(f"Failed to kill {pattern} processes: {error_msg}")

            except asyncio.TimeoutError:
                result.warnings.append(f"Timeout while killing {pattern} processes")
                self.logger.warning(f"Timeout while killing {pattern} processes")
            except Exception as e:
                result.warnings.append(f"Error killing {pattern} processes: {str(e)}")
                self.logger.warning(f"Error killing {pattern} processes: {e}")

    async def _cleanup_session_files(self, result: CleanupResult):
        """세션 파일 정리"""
        try:
            user_data_dir = self.session_manager.get_user_data_directory()
            default_dir = user_data_dir / "Default"

            for dir_name in self.cleanup_directories:
                dir_path = default_dir / dir_name

                if dir_path.exists():
                    try:
                        # 비동기적으로 디렉토리 정리 실행
                        await asyncio.get_event_loop().run_in_executor(
                            None, self._remove_directory_sync, dir_path
                        )

                        # 디렉토리 재생성
                        dir_path.mkdir(parents=True, exist_ok=True)

                        result.directories_cleaned.append(str(dir_path))
                        self.logger.debug(f"Cleaned directory: {dir_path}")

                    except Exception as e:
                        result.warnings.append(f"Failed to clean {dir_path}: {str(e)}")
                        self.logger.warning(f"Failed to clean directory {dir_path}: {e}")
                else:
                    self.logger.debug(f"Directory not found, skipping: {dir_path}")

        except Exception as e:
            result.errors.append(f"Session file cleanup error: {str(e)}")
            self.logger.error(f"Session file cleanup error: {e}")

    def _remove_directory_sync(self, dir_path: Path):
        """동기적으로 디렉토리 제거 (executor에서 실행용)"""
        if dir_path.exists():
            shutil.rmtree(dir_path)

    async def cleanup_specific_directory(self, directory_name: str) -> bool:
        """특정 디렉토리만 정리"""
        try:
            user_data_dir = self.session_manager.get_user_data_directory()
            target_dir = user_data_dir / "Default" / directory_name

            if target_dir.exists():
                await asyncio.get_event_loop().run_in_executor(
                    None, self._remove_directory_sync, target_dir
                )
                target_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Cleaned specific directory: {target_dir}")
                return True
            else:
                self.logger.debug(f"Directory not found: {target_dir}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to clean specific directory {directory_name}: {e}")
            return False

    async def force_kill_all_browser_processes(self) -> List[str]:
        """모든 브라우저 프로세스 강제 종료"""
        killed_processes = []

        for pattern in self.process_patterns:
            try:
                # SIGKILL로 강제 종료
                process = await asyncio.create_subprocess_exec(
                    'pkill', '-9', '-f', pattern,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)

                if process.returncode == 0:
                    killed_processes.append(pattern)
                    self.logger.info(f"Force killed {pattern} processes")

            except Exception as e:
                self.logger.warning(f"Failed to force kill {pattern} processes: {e}")

        return killed_processes