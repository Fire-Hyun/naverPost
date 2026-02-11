"""
네이버 블로그 포스팅 자동화 시스템 데이터 관리 모듈
파일 및 메타데이터 저장을 관리합니다.
"""

import os
import json
import shutil
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from src.config.settings import Settings
from src.content.models import ProjectMetadata, UserExperience, BlogPost, QualityValidationResult, NaverPostingResult
from src.utils.logger import storage_logger
from src.utils.exceptions import FileProcessingError, DataConsistencyError

class DataManager:
    """블로그 포스트 데이터 및 파일 관리 클래스"""

    def __init__(self):
        self.settings = Settings
        self._ensure_directories()

    def _ensure_directories(self):
        """필요한 디렉토리 생성"""
        try:
            self.settings.create_directories()
            storage_logger.info("All required directories created successfully")
        except Exception as e:
            storage_logger.error(f"Failed to create directories: {e}")
            raise FileProcessingError(f"디렉토리 생성 실패: {str(e)}")

    def create_project(self, user_experience: UserExperience, name: str = None) -> ProjectMetadata:
        """새 프로젝트 생성"""
        try:
            project_id = str(uuid.uuid4())
            project_name = name or f"프로젝트_{project_id[:8]}"

            project_metadata = ProjectMetadata(
                project_id=project_id,
                name=project_name,
                user_experience=user_experience,
                status="draft"
            )

            # 프로젝트 메타데이터 저장
            self._save_project_metadata(project_metadata)

            storage_logger.info(f"Project created: {project_id}")
            return project_metadata

        except Exception as e:
            storage_logger.error(f"Failed to create project: {e}")
            raise FileProcessingError(f"프로젝트 생성 실패: {str(e)}")

    def save_blog_post(self, project_id: str, blog_post: BlogPost) -> bool:
        """블로그 포스트 저장"""
        try:
            # 프로젝트 메타데이터 로드
            metadata = self.get_project_metadata(project_id)
            if not metadata:
                raise FileProcessingError(f"프로젝트를 찾을 수 없습니다: {project_id}")

            # 블로그 포스트 업데이트
            metadata.blog_post = blog_post
            metadata.last_modified = datetime.now()
            metadata.status = "generated"

            # 블로그 포스트 데이터 별도 저장
            post_data_path = self.settings.get_post_data_path(project_id)
            with open(post_data_path, 'w', encoding='utf-8') as f:
                json.dump(blog_post.model_dump(), f, ensure_ascii=False, indent=2, default=str)

            # 메타데이터 업데이트
            self._save_project_metadata(metadata)

            storage_logger.info(f"Blog post saved for project: {project_id}")
            return True

        except Exception as e:
            storage_logger.error(f"Failed to save blog post for project {project_id}: {e}")
            raise FileProcessingError(f"블로그 포스트 저장 실패: {str(e)}", file_path=str(post_data_path))

    def save_validation_result(self, project_id: str, validation_result: QualityValidationResult) -> bool:
        """품질 검증 결과 저장"""
        try:
            metadata = self.get_project_metadata(project_id)
            if not metadata:
                raise FileProcessingError(f"프로젝트를 찾을 수 없습니다: {project_id}")

            metadata.validation_result = validation_result
            metadata.last_modified = datetime.now()
            metadata.status = "validated" if validation_result.is_valid else "validation_failed"

            self._save_project_metadata(metadata)

            storage_logger.info(f"Validation result saved for project: {project_id}")
            return True

        except Exception as e:
            storage_logger.error(f"Failed to save validation result for project {project_id}: {e}")
            raise FileProcessingError(f"검증 결과 저장 실패: {str(e)}")

    def save_posting_result(self, project_id: str, posting_result: NaverPostingResult) -> bool:
        """네이버 포스팅 결과 저장"""
        try:
            metadata = self.get_project_metadata(project_id)
            if not metadata:
                raise FileProcessingError(f"프로젝트를 찾을 수 없습니다: {project_id}")

            metadata.posting_result = posting_result
            metadata.last_modified = datetime.now()
            metadata.status = "posted" if posting_result.success else "posting_failed"

            self._save_project_metadata(metadata)

            storage_logger.info(f"Posting result saved for project: {project_id}")
            return True

        except Exception as e:
            storage_logger.error(f"Failed to save posting result for project {project_id}: {e}")
            raise FileProcessingError(f"포스팅 결과 저장 실패: {str(e)}")

    def get_project_metadata(self, project_id: str) -> Optional[ProjectMetadata]:
        """프로젝트 메타데이터 조회"""
        try:
            metadata_path = self.settings.get_metadata_path(project_id)

            if not metadata_path.exists():
                return None

            with open(metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return ProjectMetadata(**data)

        except Exception as e:
            storage_logger.error(f"Failed to load project metadata {project_id}: {e}")
            return None

    def get_blog_post(self, project_id: str) -> Optional[BlogPost]:
        """블로그 포스트 조회"""
        try:
            post_data_path = self.settings.get_post_data_path(project_id)

            if not post_data_path.exists():
                return None

            with open(post_data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return BlogPost(**data)

        except Exception as e:
            storage_logger.error(f"Failed to load blog post {project_id}: {e}")
            return None

    def list_projects(self, status: str = None) -> List[ProjectMetadata]:
        """프로젝트 목록 조회"""
        try:
            projects = []
            metadata_dir = self.settings.DATA_DIR / "metadata"

            if not metadata_dir.exists():
                return projects

            for metadata_file in metadata_dir.glob("*_meta.json"):
                try:
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    project = ProjectMetadata(**data)

                    # 상태 필터링
                    if status and project.status != status:
                        continue

                    projects.append(project)

                except Exception as e:
                    storage_logger.warning(f"Failed to load project from {metadata_file}: {e}")
                    continue

            # 생성 시간 순으로 정렬 (최신순)
            projects.sort(key=lambda x: x.created_at, reverse=True)

            storage_logger.info(f"Loaded {len(projects)} projects")
            return projects

        except Exception as e:
            storage_logger.error(f"Failed to list projects: {e}")
            return []

    def delete_project(self, project_id: str) -> bool:
        """프로젝트 삭제"""
        try:
            # 메타데이터 파일 삭제
            metadata_path = self.settings.get_metadata_path(project_id)
            if metadata_path.exists():
                metadata_path.unlink()

            # 블로그 포스트 데이터 삭제
            post_data_path = self.settings.get_post_data_path(project_id)
            if post_data_path.exists():
                post_data_path.unlink()

            # 관련된 이미지 파일들 정리 (필요시)
            # TODO: 이미지 파일들도 삭제할지 고려

            storage_logger.info(f"Project deleted: {project_id}")
            return True

        except Exception as e:
            storage_logger.error(f"Failed to delete project {project_id}: {e}")
            return False

    def cleanup_old_files(self, days: int = 30):
        """오래된 파일 정리"""
        try:
            cutoff_time = datetime.now().timestamp() - (days * 24 * 3600)
            cleaned_files = 0

            # 메타데이터 파일 정리
            metadata_dir = self.settings.DATA_DIR / "metadata"
            if metadata_dir.exists():
                for file in metadata_dir.glob("*_meta.json"):
                    if file.stat().st_mtime < cutoff_time:
                        project_id = file.stem.replace("_meta", "")
                        self.delete_project(project_id)
                        cleaned_files += 1

            # 임시 파일 정리
            self._cleanup_temp_files()

            storage_logger.info(f"Cleaned up {cleaned_files} old projects")

        except Exception as e:
            storage_logger.error(f"Error during cleanup: {e}")

    def get_storage_stats(self) -> Dict[str, Any]:
        """저장소 통계 정보"""
        try:
            stats = {
                'total_projects': 0,
                'by_status': {},
                'total_images': 0,
                'total_size_mb': 0,
                'last_updated': datetime.now().isoformat()
            }

            # 프로젝트 통계
            projects = self.list_projects()
            stats['total_projects'] = len(projects)

            # 상태별 프로젝트 개수
            for project in projects:
                status = project.status
                stats['by_status'][status] = stats['by_status'].get(status, 0) + 1

            # 이미지 파일 통계
            uploads_dir = self.settings.UPLOADS_DIR / "images"
            if uploads_dir.exists():
                image_files = list(uploads_dir.glob("*"))
                stats['total_images'] = len(image_files)
                stats['total_size_mb'] = sum(f.stat().st_size for f in image_files if f.is_file()) / (1024 * 1024)

            return stats

        except Exception as e:
            storage_logger.error(f"Error calculating storage stats: {e}")
            return {}

    def _save_project_metadata(self, metadata: ProjectMetadata):
        """프로젝트 메타데이터 저장 (내부 함수)"""
        metadata_path = self.settings.get_metadata_path(metadata.project_id)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)

        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata.model_dump(), f, ensure_ascii=False, indent=2, default=str)

    def _cleanup_temp_files(self):
        """임시 파일 정리 (내부 함수)"""
        try:
            temp_patterns = ["*.tmp", "*.temp", "*.part"]

            for directory in [self.settings.UPLOADS_DIR, self.settings.DATA_DIR]:
                if not directory.exists():
                    continue

                for pattern in temp_patterns:
                    for temp_file in directory.rglob(pattern):
                        try:
                            if temp_file.is_file():
                                temp_file.unlink()
                                storage_logger.debug(f"Cleaned up temp file: {temp_file}")
                        except Exception as e:
                            storage_logger.warning(f"Failed to clean up {temp_file}: {e}")

        except Exception as e:
            storage_logger.error(f"Error during temp file cleanup: {e}")

    def export_project_data(self, project_id: str) -> Optional[Dict[str, Any]]:
        """프로젝트 데이터 내보내기"""
        try:
            metadata = self.get_project_metadata(project_id)
            blog_post = self.get_blog_post(project_id)

            if not metadata:
                return None

            export_data = {
                'metadata': metadata.model_dump(),
                'blog_post': blog_post.model_dump() if blog_post else None,
                'exported_at': datetime.now().isoformat()
            }

            return export_data

        except Exception as e:
            storage_logger.error(f"Failed to export project data {project_id}: {e}")
            return None

    def is_duplicate_project(self, user_experience_hash: str) -> bool:
        """중복 프로젝트 확인 (사용자 경험 해시 기반)"""
        try:
            projects = self.list_projects()

            for project in projects:
                # 간단한 중복 체크: 카테고리와 개인 리뷰의 일부가 같은 경우
                if (project.user_experience.category == user_experience_hash and
                    len(project.user_experience.personal_review) > 50):
                    # 더 정교한 중복 체크 로직을 구현할 수 있음
                    return True

            return False

        except Exception as e:
            storage_logger.error(f"Error checking duplicate project: {e}")
            return False