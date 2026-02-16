"""
네이버 블로그 포스팅 자동화 시스템 데이터 관리 모듈 (날짜 기반)
yyyyMMdd 날짜 단위로 블로그 포스팅 데이터를 체계적으로 관리합니다.
"""

import os
import json
import shutil
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, date

from src.config.settings import Settings
from src.utils.date_manager import DateBasedDirectoryManager, date_manager
from src.content.models import UserExperience
from src.utils.logger import storage_logger
from src.utils.exceptions import FileProcessingError, DataConsistencyError


class DateBasedDataManager:
    """날짜 기반 블로그 포스트 데이터 관리 클래스"""

    def __init__(self):
        self.settings = Settings
        self.date_manager = date_manager
        self._ensure_base_directories()

    def _ensure_base_directories(self):
        """기본 디렉토리 생성"""
        try:
            self.settings.create_directories()
            storage_logger.info("Base directories created successfully")
        except Exception as e:
            storage_logger.error(f"Failed to create base directories: {e}")
            raise FileProcessingError(f"기본 디렉토리 생성 실패: {str(e)}")

    def create_posting_session(self, visit_date: str, user_experience: Dict[str, Any]) -> str:
        """
        새 포스팅 세션 생성 (트랜잭션 방식)

        디렉토리는 생성하지 않고 메타데이터만 준비합니다.
        실제 디렉토리는 이미지 업로드나 AI 생성 성공 시에만 생성됩니다.

        Args:
            visit_date: 방문일자 (YYYY-MM-DD 또는 yyyyMMdd)
            user_experience: 사용자 경험 데이터

        Returns:
            생성될 디렉토리명 (yyyyMMdd 또는 yyyyMMdd_n)
        """
        try:
            storage_logger.info(f"[Session Create] Creating session for {visit_date}")

            # 1단계: 입력 데이터 검증
            if not user_experience.get('category'):
                raise ValueError("카테고리가 필요합니다")
            if not user_experience.get('personal_review'):
                raise ValueError("개인 리뷰가 필요합니다")

            # 2단계: 날짜 형식 정규화
            date_str = self._normalize_date_string(visit_date)

            # 3단계: 사용 가능한 디렉토리명 확인 (상호명 포함, 생성하지는 않음)
            business_name = self.date_manager._extract_business_name_from_input(user_experience)
            dir_name = self.date_manager._get_available_directory_name(date_str, business_name)

            # 4단계: 세션 메타데이터를 임시 저장소에 준비 (실제 파일 저장 안함)
            session_metadata = {
                "session_id": str(uuid.uuid4())[:8],
                "visit_date": visit_date,
                "normalized_date": date_str,
                "user_input": user_experience,
                "status": "initialized",  # created -> initialized로 변경
                "workflow_stage": "user_input",
                "images": [],
                "temp_session": True  # 임시 세션임을 표시
            }

            # 임시 세션 정보를 메모리에 저장 (클래스 속성으로)
            if not hasattr(self, '_temp_sessions'):
                self._temp_sessions = {}

            self._temp_sessions[dir_name] = session_metadata

            storage_logger.info(f"[Session Create] Temporary session prepared: {dir_name}")
            return dir_name

        except Exception as e:
            storage_logger.error(f"[Session Create] Failed to create session: {e}")
            raise FileProcessingError(f"포스팅 세션 생성 실패: {str(e)}")

    def _commit_temp_session(self, date_str: str) -> Optional[str]:
        """
        임시 세션을 실제 디렉토리와 파일로 저장 (트랜잭션 커밋)

        Args:
            date_str: 날짜 디렉토리명

        Returns:
            실제 커밋된 디렉토리명 (실패 시 None)
        """
        try:
            # 임시 세션 메타데이터 확인
            if not hasattr(self, '_temp_sessions') or date_str not in self._temp_sessions:
                storage_logger.warning(f"[Commit] No temp session found for {date_str}")
                return None

            temp_metadata = self._temp_sessions[date_str]

            # 실제 디렉토리 생성 (상호명 포함)
            user_input = temp_metadata.get("user_input", {})
            dir_path = self.date_manager.create_date_directory(temp_metadata["normalized_date"], user_input)
            dir_name = dir_path.name

            # 실제 메타데이터로 변환
            final_metadata = temp_metadata.copy()
            final_metadata["status"] = "created"
            final_metadata.pop("temp_session", None)  # 임시 표시 제거

            # 메타데이터 저장
            self.date_manager.save_metadata(dir_name, final_metadata)

            # 임시 세션 제거
            del self._temp_sessions[date_str]

            storage_logger.info(f"[Commit] Temp session committed: {date_str} -> {dir_name}")
            return dir_name

        except Exception as e:
            storage_logger.error(f"[Commit] Failed to commit temp session: {e}")
            return None

    def _cleanup_temp_session(self, date_str: str):
        """임시 세션 정리"""
        if hasattr(self, '_temp_sessions') and date_str in self._temp_sessions:
            del self._temp_sessions[date_str]
            storage_logger.info(f"[Cleanup] Temp session cleaned: {date_str}")

    def _normalize_date_string(self, date_input: str) -> str:
        """날짜 문자열을 yyyyMMdd 형식으로 정규화"""
        # 이미 yyyyMMdd 형식인 경우
        if len(date_input) == 8 and date_input.isdigit():
            return date_input

        # YYYY-MM-DD 형식인 경우
        if len(date_input) == 10 and '-' in date_input:
            return date_input.replace('-', '')

        # 다른 형식들 시도
        try:
            # 다양한 형식 파싱 시도
            for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d']:
                try:
                    parsed_date = datetime.strptime(date_input, fmt)
                    return parsed_date.strftime('%Y%m%d')
                except ValueError:
                    continue

            # 오늘 날짜 사용
            storage_logger.warning(f"Invalid date format: {date_input}, using today's date")
            return datetime.now().strftime('%Y%m%d')

        except Exception as e:
            storage_logger.error(f"Date parsing failed: {e}")
            return datetime.now().strftime('%Y%m%d')

    def save_uploaded_images(self, date_str: str, image_files: List[Dict[str, Any]]) -> List[str]:
        """
        업로드된 이미지 파일들 저장 (트랜잭션 방식)

        Args:
            date_str: 날짜 디렉토리명
            image_files: 이미지 파일 정보 리스트

        Returns:
            저장된 이미지 파일명 리스트
        """
        storage_logger.info(f"[Image Upload] Starting upload for {date_str}, files: {len(image_files)}")

        # 0단계: 임시 세션 확인 및 커밋
        temp_session_committed = False
        resolved_dir_name = date_str
        try:
            if hasattr(self, '_temp_sessions') and date_str in self._temp_sessions:
                committed_dir_name = self._commit_temp_session(date_str)
                if committed_dir_name:
                    temp_session_committed = True
                    resolved_dir_name = committed_dir_name
                    storage_logger.info(f"[Image Upload] Temp session committed for {date_str} -> {resolved_dir_name}")
                else:
                    raise FileProcessingError("임시 세션 커밋에 실패했습니다")

            # 1단계: 전체 검증 수행 (디렉토리 생성하지 않음)
            validated_files = []
            for i, img_info in enumerate(image_files):
                storage_logger.info(f"[Image Upload] Processing file {i+1}: {img_info.get('filename', 'unknown')}")

                # 파일 정보 검증
                if 'content' not in img_info:
                    raise FileProcessingError(
                        f"이미지 저장 실패: 파일 {img_info.get('filename', 'unknown')} - "
                        "업로드된 바이너리(content)가 없습니다. 이미지는 웹/API 업로드로만 허용됩니다."
                    )

                original_name = img_info.get('filename', 'image.jpg')
                if not original_name:
                    raise FileProcessingError("파일명이 없습니다")

                # 고유한 파일명 생성
                ext = Path(original_name).suffix
                unique_name = f"{uuid.uuid4().hex[:8]}{ext}"

                validated_files.append({
                    'unique_name': unique_name,
                    'content': img_info['content'],
                    'original_name': original_name
                })

                storage_logger.info(f"[Image Upload] File validated: {original_name} -> {unique_name}")

            # 2단계: 모든 검증 성공 시에만 디렉토리 생성 및 저장
            # 항상 세션 디렉토리(data/YYYYMMDD(상호명)/images) 아래로 저장
            dir_path = self.date_manager.get_directory_path(resolved_dir_name)
            if not dir_path:
                raise FileProcessingError(f"이미지 저장 대상 디렉토리를 찾을 수 없습니다: {resolved_dir_name}")
            images_dir = dir_path / "images"
            images_dir.mkdir(parents=True, exist_ok=True)

            storage_logger.info(f"[Image Upload] Directory created: {images_dir}")

            # 3단계: 파일 저장
            saved_images = []
            for file_info in validated_files:
                save_path = images_dir / file_info['unique_name']

                with open(save_path, 'wb') as f:
                    f.write(file_info['content'])

                saved_images.append(file_info['unique_name'])
                storage_logger.info(f"[Image Upload] Saved image: {save_path}")

                self.date_manager.append_log(resolved_dir_name,
                    f"Image saved: {file_info['original_name']} -> {file_info['unique_name']}")

            # 4단계: 메타데이터 업데이트
            metadata = self.date_manager.load_metadata(resolved_dir_name)
            if metadata:
                metadata['images'].extend(saved_images)
                metadata['workflow_stage'] = "images_uploaded"
                self.date_manager.save_metadata(resolved_dir_name, metadata)

            storage_logger.info(f"[Image Upload] Successfully saved {len(saved_images)} images to {images_dir}")
            return saved_images

        except Exception as e:
            storage_logger.error(f"[Image Upload] Failed to save images: {e}")

            # 실패 시 정리 작업
            if temp_session_committed:
                # 임시 세션을 커밋한 경우 - 생성된 디렉토리 삭제
                base_path = self.settings.DATA_DIR / resolved_dir_name
                if base_path.exists():
                    try:
                        shutil.rmtree(base_path)
                        storage_logger.info(f"[Image Upload] Cleaned up failed directory: {base_path}")
                    except Exception as cleanup_error:
                        storage_logger.error(f"[Image Upload] Failed to cleanup directory: {cleanup_error}")
            else:
                # 임시 세션만 있는 경우 - 임시 세션만 정리
                self._cleanup_temp_session(date_str)

            raise FileProcessingError(f"이미지 저장 실패: {str(e)}")

    def update_user_experience(self, date_str: str, user_experience: Dict[str, Any]) -> bool:
        """사용자 경험 데이터 업데이트 (임시 세션 포함)"""
        try:
            storage_logger.info(f"[Update Experience] Updating for {date_str}")

            # 1. 임시 세션 확인
            if hasattr(self, '_temp_sessions') and date_str in self._temp_sessions:
                # 임시 세션 업데이트
                self._temp_sessions[date_str]['user_input'].update(user_experience)
                self._temp_sessions[date_str]['workflow_stage'] = "experience_updated"
                self._temp_sessions[date_str]['last_updated'] = datetime.now().isoformat()

                storage_logger.info(f"[Update Experience] Temp session updated: {date_str}")
                return True

            # 2. 실제 세션 업데이트
            metadata = self.date_manager.load_metadata(date_str)
            if not metadata:
                raise DataConsistencyError(f"Metadata not found for {date_str}")

            metadata['user_input'].update(user_experience)
            metadata['workflow_stage'] = "experience_updated"
            metadata['last_updated'] = datetime.now().isoformat()

            self.date_manager.save_metadata(date_str, metadata)
            self.date_manager.append_log(date_str, "User experience updated")

            storage_logger.info(f"[Update Experience] Real session updated: {date_str}")
            return True

        except Exception as e:
            storage_logger.error(f"[Update Experience] Failed to update: {e}")
            raise FileProcessingError(f"사용자 경험 업데이트 실패: {str(e)}")

    def save_ai_processing_data(self, date_str: str, processing_data: Dict[str, Any]) -> Path:
        """
        AI 처리용 데이터 저장

        Args:
            date_str: 날짜 디렉토리명
            processing_data: AI 처리용 데이터 (location_analysis, hashtag_analysis 등)

        Returns:
            저장된 파일 경로
        """
        try:
            # 기본 메타데이터 로드
            metadata = self.date_manager.load_metadata(date_str)
            if not metadata:
                raise DataConsistencyError(f"Metadata not found for {date_str}")

            # AI 요청 데이터 구성
            ai_request_data = {
                "base_metadata": metadata,
                "processing_results": processing_data,
                "merged_data": {
                    "category": metadata["user_input"].get("category"),
                    "rating": metadata["user_input"].get("rating"),
                    "visit_date": metadata["user_input"].get("visit_date"),
                    "companion": metadata["user_input"].get("companion"),
                    "personal_review": metadata["user_input"].get("personal_review"),
                    "ai_additional_script": metadata["user_input"].get("ai_additional_script"),
                    "location": processing_data.get("final_location"),
                    "hashtags": processing_data.get("final_hashtags", []),
                    "images": metadata.get("images", []),
                    "store_name": metadata["user_input"].get("store_name"),
                    "location_detail": processing_data.get("location_detail"),
                },
                "generation_settings": {
                    "target_length": 1500,
                    "tone": "친근하고 자연스러운",
                    "include_external_info": True,
                    "external_info_ratio": 0.3
                }
            }

            # AI 요청 데이터 저장
            file_path = self.date_manager.save_ai_request(date_str, ai_request_data)

            # 메타데이터 업데이트
            metadata['workflow_stage'] = "ai_ready"
            self.date_manager.save_metadata(date_str, metadata)

            storage_logger.info(f"AI processing data saved for {date_str}")
            return file_path

        except Exception as e:
            storage_logger.error(f"Failed to save AI processing data: {e}")
            raise FileProcessingError(f"AI 처리 데이터 저장 실패: {str(e)}")

    def save_blog_result(self, date_str: str, blog_content: str, generation_metadata: Dict[str, Any]) -> Path:
        """
        AI 생성 블로그 결과 저장

        Args:
            date_str: 날짜 디렉토리명
            blog_content: 생성된 블로그 글
            generation_metadata: 생성 관련 메타데이터

        Returns:
            저장된 파일 경로
        """
        try:
            # 블로그 결과 저장 (마크다운 형식)
            blog_metadata = {
                "generation_model": generation_metadata.get("model_used", "unknown"),
                "tokens_used": generation_metadata.get("total_tokens", 0),
                "content_length": len(blog_content),
                "quality_score": generation_metadata.get("quality_score", 0),
                "generation_success": True
            }

            file_path = self.date_manager.save_blog_result(date_str, blog_content, blog_metadata)

            # 메타데이터 업데이트
            metadata = self.date_manager.load_metadata(date_str)
            if metadata:
                metadata['workflow_stage'] = "blog_generated"
                metadata['generation_metadata'] = generation_metadata
                self.date_manager.save_metadata(date_str, metadata)

            storage_logger.info(f"Blog result saved for {date_str}")
            return file_path

        except Exception as e:
            storage_logger.error(f"Failed to save blog result: {e}")
            raise FileProcessingError(f"블로그 결과 저장 실패: {str(e)}")

    def get_posting_info(self, date_str: str) -> Optional[Dict[str, Any]]:
        """포스팅 정보 조회 (임시 세션 포함)"""
        try:
            # 1. 먼저 임시 세션 확인
            if hasattr(self, '_temp_sessions') and date_str in self._temp_sessions:
                temp_metadata = self._temp_sessions[date_str]
                return {
                    "directory_info": {
                        "directory_name": date_str,
                        "directory_path": f"temp_session_{date_str}",
                        "images_count": 0,
                        "has_metadata": True,
                        "has_ai_request": False,
                        "has_blog_result": False,
                        "is_temp_session": True
                    },
                    "metadata": temp_metadata,
                    "ai_request_data": None,
                    "blog_result": None,
                    "has_complete_data": False,
                    "is_temp_session": True
                }

            # 2. 실제 디렉토리 정보 확인
            dir_info = self.date_manager.get_directory_info(date_str)
            if not dir_info:
                return None

            # 메타데이터 로드
            metadata = self.date_manager.load_metadata(date_str)

            # AI 요청 데이터 로드 (있는 경우)
            ai_request = self.date_manager.load_ai_request(date_str)

            # 블로그 결과 로드 (있는 경우)
            blog_result = self.date_manager.load_blog_result(date_str)

            return {
                "directory_info": dir_info,
                "metadata": metadata,
                "ai_request_data": ai_request,
                "blog_result": blog_result,
                "has_complete_data": all([
                    metadata,
                    dir_info["has_metadata"],
                    dir_info["images_count"] > 0
                ]),
                "is_temp_session": False
            }

        except Exception as e:
            storage_logger.error(f"Failed to get posting info: {e}")
            return None

    def list_all_postings(self) -> List[Dict[str, Any]]:
        """모든 포스팅 세션 목록 조회"""
        try:
            all_postings = []

            for dir_name in self.date_manager.list_date_directories():
                posting_info = self.get_posting_info(dir_name)
                if posting_info:
                    # 요약 정보만 포함
                    summary = {
                        "date_directory": dir_name,
                        "status": posting_info["metadata"].get("workflow_stage", "unknown") if posting_info["metadata"] else "no_metadata",
                        "images_count": posting_info["directory_info"]["images_count"],
                        "has_blog_result": posting_info["directory_info"]["has_blog_result"],
                        "created_at": posting_info["directory_info"]["created_date"]
                    }

                    if posting_info["metadata"]:
                        summary.update({
                            "category": posting_info["metadata"]["user_input"].get("category"),
                            "visit_date": posting_info["metadata"]["user_input"].get("visit_date")
                        })

                    all_postings.append(summary)

            # 최신순 정렬
            all_postings.sort(key=lambda x: x["created_at"], reverse=True)
            return all_postings

        except Exception as e:
            storage_logger.error(f"Failed to list postings: {e}")
            return []

    def delete_posting(self, date_str: str) -> bool:
        """포스팅 데이터 삭제"""
        try:
            dir_path = self.date_manager.get_directory_path(date_str)
            if not dir_path:
                return False

            # 디렉토리 전체 삭제
            shutil.rmtree(dir_path)

            storage_logger.info(f"Posting deleted: {date_str}")
            return True

        except Exception as e:
            storage_logger.error(f"Failed to delete posting: {e}")
            raise FileProcessingError(f"포스팅 삭제 실패: {str(e)}")

    def cleanup_incomplete_postings(self) -> List[str]:
        """미완성 포스팅 정리"""
        try:
            cleaned = []

            for dir_name in self.date_manager.list_date_directories():
                posting_info = self.get_posting_info(dir_name)

                if posting_info:
                    metadata = posting_info["metadata"]
                    dir_info = posting_info["directory_info"]

                    # 이미지도 없고 메타데이터도 기본 상태인 경우
                    if (dir_info["images_count"] == 0 and
                        metadata and
                        metadata.get("workflow_stage") == "created"):

                        if self.delete_posting(dir_name):
                            cleaned.append(dir_name)

            # DateManager의 빈 디렉토리 정리도 실행
            empty_cleaned = self.date_manager.cleanup_empty_directories()
            cleaned.extend(empty_cleaned)

            storage_logger.info(f"Cleaned up {len(cleaned)} incomplete postings")
            return cleaned

        except Exception as e:
            storage_logger.error(f"Failed to cleanup incomplete postings: {e}")
            return []

    def load_ai_request(self, date_str: str) -> Optional[Dict[str, Any]]:
        """AI 요청 데이터 로드 (date_manager로 위임)"""
        return self.date_manager.load_ai_request(date_str)

    def load_metadata(self, date_str: str) -> Optional[Dict[str, Any]]:
        """메타데이터 로드 (date_manager로 위임)"""
        return self.date_manager.load_metadata(date_str)

    def load_blog_result(self, date_str: str) -> Optional[str]:
        """블로그 결과 로드 (date_manager로 위임)"""
        return self.date_manager.load_blog_result(date_str)

    def get_storage_statistics(self) -> Dict[str, Any]:
        """저장소 통계 정보"""
        try:
            all_postings = self.list_all_postings()

            total_images = sum(p["images_count"] for p in all_postings)
            completed_blogs = len([p for p in all_postings if p["has_blog_result"]])

            # 카테고리별 통계
            category_stats = {}
            for posting in all_postings:
                category = posting.get("category", "unknown")
                category_stats[category] = category_stats.get(category, 0) + 1

            # 디스크 사용량 계산
            total_size = 0
            for dir_name in self.date_manager.list_date_directories():
                dir_path = self.date_manager.get_directory_path(dir_name)
                if dir_path and dir_path.exists():
                    total_size += sum(f.stat().st_size for f in dir_path.rglob('*') if f.is_file())

            return {
                "total_postings": len(all_postings),
                "total_images": total_images,
                "completed_blogs": completed_blogs,
                "completion_rate": completed_blogs / len(all_postings) if all_postings else 0,
                "category_distribution": category_stats,
                "total_disk_usage_bytes": total_size,
                "total_disk_usage_mb": round(total_size / (1024 * 1024), 2)
            }

        except Exception as e:
            storage_logger.error(f"Failed to get storage statistics: {e}")
            return {}


# 전역 인스턴스 (기존 DataManager와 호환성 유지)
data_manager = DateBasedDataManager()

# 기존 코드와의 호환성을 위한 별칭
DataManager = DateBasedDataManager
