"""
Browser session management
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SessionPaths:
    """브라우저 세션 경로 정보"""
    base_dir: Path
    user_data_dir: Path
    sessions_dir: Path
    cache_dir: Optional[Path] = None


class BrowserSessionManager:
    """브라우저 세션 관리자"""

    def __init__(self, naver_poster_path: Path, settings=None):
        self.naver_poster_path = naver_poster_path
        self.settings = settings
        self.logger = logging.getLogger(__name__)

        # 세션 경로 구성
        self.paths = self._configure_session_paths()

    def _configure_session_paths(self) -> SessionPaths:
        """세션 경로들을 구성"""
        secrets_dir = self.naver_poster_path / ".secrets"
        user_data_dir = secrets_dir / "naver_user_data_dir"
        default_dir = user_data_dir / "Default"
        sessions_dir = default_dir / "Sessions"

        return SessionPaths(
            base_dir=secrets_dir,
            user_data_dir=user_data_dir,
            sessions_dir=sessions_dir,
            cache_dir=default_dir / "Cache"
        )

    def get_session_directory(self) -> Path:
        """세션 디렉토리 경로 반환"""
        return self.paths.sessions_dir

    def get_user_data_directory(self) -> Path:
        """사용자 데이터 디렉토리 경로 반환"""
        return self.paths.user_data_dir

    def session_directory_exists(self) -> bool:
        """세션 디렉토리 존재 여부 확인"""
        return self.paths.sessions_dir.exists()

    def ensure_directories_exist(self):
        """필요한 디렉토리들이 존재하는지 확인하고 생성"""
        try:
            self.paths.user_data_dir.mkdir(parents=True, exist_ok=True)
            self.paths.sessions_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info("Browser session directories ensured")
        except Exception as e:
            self.logger.error(f"Failed to create session directories: {e}")
            raise

    def get_session_info(self) -> Dict[str, Any]:
        """현재 세션 정보 반환"""
        return {
            "sessions_dir": str(self.paths.sessions_dir),
            "exists": self.session_directory_exists(),
            "user_data_dir": str(self.paths.user_data_dir),
            "base_dir": str(self.paths.base_dir)
        }