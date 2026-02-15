"""
이미지 업로드 및 사용자 경험 데이터 처리 라우터 (날짜 기반)
yyyyMMdd 날짜 단위로 데이터를 관리합니다.
"""

import os
import json
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError

from src.config.settings import Settings
from src.storage.data_manager import data_manager
from src.utils.logger import web_logger
from src.utils.exceptions import ImageUploadError, FileProcessingError


class UserExperienceInput(BaseModel):
    """사용자 경험 입력 데이터"""
    category: str
    personal_review: str
    rating: Optional[int] = None
    visit_date: Optional[str] = None
    companion: Optional[str] = None
    ai_additional_script: Optional[str] = None
    hashtags: Optional[str] = None


class PostingSessionResponse(BaseModel):
    """포스팅 세션 응답 데이터"""
    success: bool
    date_directory: str
    message: str
    session_info: Optional[Dict[str, Any]] = None


router = APIRouter()


async def validate_image_file(file: UploadFile) -> bool:
    """이미지 파일 유효성 검증"""
    # 파일 확장자 검증
    if not Settings.is_valid_image_extension(file.filename):
        return False

    # MIME 타입 검증
    if not file.content_type or not file.content_type.startswith('image/'):
        return False

    return True


@router.post("/sessions/create")
async def create_posting_session(user_experience: UserExperienceInput):
    """
    새 포스팅 세션 생성

    방문일자를 기준으로 날짜 디렉토리를 생성하고 사용자 경험 데이터를 저장합니다.
    """
    try:
        # 방문일자 처리 (기본값: 오늘)
        visit_date = user_experience.visit_date or datetime.now().strftime('%Y-%m-%d')

        # 사용자 경험 데이터 준비
        experience_data = {
            "category": user_experience.category,
            "personal_review": user_experience.personal_review,
            "rating": user_experience.rating,
            "visit_date": visit_date,
            "companion": user_experience.companion,
            "ai_additional_script": user_experience.ai_additional_script,
            "hashtags": user_experience.hashtags.split(',') if user_experience.hashtags else []
        }

        # 포스팅 세션 생성
        date_directory = data_manager.create_posting_session(visit_date, experience_data)

        # 세션 정보 조회
        session_info = data_manager.get_posting_info(date_directory)

        web_logger.info(f"Posting session created: {date_directory}")

        return JSONResponse(content={
            "success": True,
            "date_directory": date_directory,
            "message": f"포스팅 세션이 생성되었습니다: {date_directory}",
            "session_info": {
                "visit_date": visit_date,
                "category": user_experience.category,
                "workflow_stage": "user_input",
                "images_uploaded": 0
            }
        })

    except Exception as e:
        web_logger.error(f"Failed to create posting session: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"포스팅 세션 생성 중 오류가 발생했습니다: {str(e)}"
        )


@router.post("/sessions/{date_directory}/images")
async def upload_images_to_session(
    date_directory: str,
    files: List[UploadFile] = File(...)
):
    """
    특정 날짜 세션에 이미지 업로드
    """
    try:
        web_logger.info(f"[Upload endpoint hit] session={date_directory} files={len(files)}")
        # 최대 업로드 수 검증
        if len(files) > Settings.MAX_IMAGES_PER_POST:
            raise HTTPException(
                status_code=400,
                detail=f"이미지는 최대 {Settings.MAX_IMAGES_PER_POST}개까지 업로드 가능합니다"
            )

        uploaded_images = []

        for file in files:
            if not file.filename:
                continue

            # 파일 유효성 검증
            if not await validate_image_file(file):
                raise ImageUploadError(
                    f"지원하지 않는 이미지 파일입니다: {file.filename}",
                    file_path=file.filename
                )

            # 파일 내용 읽기
            file_content = await file.read()

            # 파일 크기 검증
            if len(file_content) > Settings.MAX_FILE_SIZE_MB * 1024 * 1024:
                raise ImageUploadError(
                    f"파일 크기가 너무 큽니다. 최대 {Settings.MAX_FILE_SIZE_MB}MB까지 허용됩니다",
                    file_path=file.filename,
                    file_size=len(file_content)
                )

            uploaded_images.append({
                'filename': file.filename,
                'content': file_content,
                'content_type': file.content_type,
                'size': len(file_content)
            })

        # 데이터 매니저를 통해 이미지 저장
        saved_filenames = data_manager.save_uploaded_images(date_directory, uploaded_images)

        # 응답 데이터 구성
        uploaded_files_info = []
        for i, filename in enumerate(saved_filenames):
            uploaded_files_info.append({
                "original_filename": uploaded_images[i]['filename'],
                "saved_filename": filename,
                "file_size": uploaded_images[i]['size'],
                "url": f"/data/{date_directory}/images/{filename}"  # data 경로로 수정
            })

        web_logger.info(f"Successfully uploaded {len(uploaded_files_info)} images to {date_directory}")

        return JSONResponse(content={
            "success": True,
            "message": f"{len(uploaded_files_info)}개 이미지가 성공적으로 업로드되었습니다",
            "date_directory": date_directory,
            "uploaded_files": uploaded_files_info
        })

    except ImageUploadError as e:
        web_logger.error(f"Image upload error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except FileProcessingError as e:
        web_logger.error(f"File processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        web_logger.error(f"Unexpected error during image upload: {e}")
        raise HTTPException(status_code=500, detail="이미지 업로드 중 오류가 발생했습니다")


@router.put("/sessions/{date_directory}/experience")
async def update_user_experience(
    date_directory: str,
    user_experience: UserExperienceInput
):
    """
    사용자 경험 데이터 업데이트
    """
    try:
        web_logger.info(f"[Experience endpoint hit] session={date_directory}")
        # 사용자 경험 데이터 준비
        experience_data = {
            "category": user_experience.category,
            "personal_review": user_experience.personal_review,
            "rating": user_experience.rating,
            "visit_date": user_experience.visit_date,
            "companion": user_experience.companion,
            "ai_additional_script": user_experience.ai_additional_script,
            "hashtags": user_experience.hashtags.split(',') if user_experience.hashtags else []
        }

        # 데이터 업데이트
        success = data_manager.update_user_experience(date_directory, experience_data)

        if not success:
            raise HTTPException(status_code=404, detail="해당 날짜 세션을 찾을 수 없습니다")

        # 업데이트된 정보 조회
        updated_info = data_manager.get_posting_info(date_directory)

        web_logger.info(f"User experience updated for {date_directory}")

        return JSONResponse(content={
            "success": True,
            "message": "사용자 경험 데이터가 성공적으로 업데이트되었습니다",
            "date_directory": date_directory,
            "updated_info": updated_info
        })

    except Exception as e:
        web_logger.error(f"Failed to update user experience: {e}")
        raise HTTPException(status_code=500, detail="사용자 경험 데이터 업데이트 중 오류가 발생했습니다")


@router.post("/sessions/{date_directory}/generate-blog")
async def generate_blog_post(date_directory: str):
    """
    세션 데이터를 기반으로 블로그 포스트 생성

    - metadata.json + (있으면) ai_request.json을 사용
    - ai_request.json이 없으면, 사용자 입력(location/hashtags)을 기반으로 생성 후 진행
    """
    try:
        web_logger.info(f"[Generate endpoint hit] session={date_directory}")
        if not Settings.OPENAI_API_KEY:
            raise HTTPException(status_code=400, detail="OPENAI_API_KEY가 설정되어 있지 않습니다")

        session_info = data_manager.get_posting_info(date_directory)
        if not session_info or not session_info.get("metadata"):
            raise HTTPException(status_code=404, detail="해당 날짜 세션을 찾을 수 없습니다")

        metadata = session_info["metadata"]
        user_input = metadata.get("user_input", {})
        images = metadata.get("images") or []

        # 이미지 업로드 여부는 "세션 메타데이터(images 목록)" 기준으로 판단합니다.
        # (저장 위치는 uploads/<date_directory>/images 가 기본이지만, 레거시 data/<date>/images도 허용)
        if len(images) <= 0:
            raise HTTPException(status_code=400, detail="이미지가 업로드되지 않았습니다")

        # 실제 파일 존재 여부 확인(둘 중 한 곳에라도 있어야 함)
        uploads_dir = Settings.UPLOADS_DIR / date_directory / "images"
        data_dir = Settings.DATA_DIR / date_directory / "images"
        missing = []
        for name in images:
            if (uploads_dir / name).exists():
                continue
            if (data_dir / name).exists():
                continue
            missing.append(name)

        if len(missing) == len(images):
            raise HTTPException(
                status_code=400,
                detail="세션 메타데이터에는 이미지가 있지만 파일이 존재하지 않습니다. 업로드를 다시 해주세요."
            )

        # ai_request.json이 없으면 사용자 입력 기반으로 생성
        if not session_info.get("ai_request_data"):
            processing_data = {
                "final_location": user_input.get("location") or "",
                "final_hashtags": user_input.get("hashtags") or []
            }
            data_manager.save_ai_processing_data(date_directory, processing_data)

        from src.content.blog_generator import DateBasedBlogGenerator

        generator = DateBasedBlogGenerator()
        result = generator.generate_and_save_blog_post(date_directory)

        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "블로그 생성에 실패했습니다"))

        # 결과 섹션에 바로 보여줄 수 있게 content 포함
        return JSONResponse(content={
            "success": True,
            "date_directory": date_directory,
            "generated_content": result.get("generated_content", ""),
            "blog_file_path": result.get("blog_file_path"),
            "metadata": result.get("metadata", {})
        })

    except HTTPException:
        raise
    except Exception as e:
        web_logger.error(f"Failed to generate blog post for {date_directory}: {e}")
        raise HTTPException(status_code=500, detail="블로그 포스트 생성 중 오류가 발생했습니다")


@router.get("/sessions")
async def list_posting_sessions():
    """
    모든 포스팅 세션 목록 조회
    """
    try:
        all_sessions = data_manager.list_all_postings()

        return JSONResponse(content={
            "success": True,
            "total_sessions": len(all_sessions),
            "sessions": all_sessions
        })

    except Exception as e:
        web_logger.error(f"Failed to list posting sessions: {e}")
        raise HTTPException(status_code=500, detail="포스팅 세션 목록 조회 중 오류가 발생했습니다")


@router.get("/sessions/{date_directory}")
async def get_posting_session(date_directory: str):
    """
    특정 포스팅 세션 정보 조회
    """
    try:
        session_info = data_manager.get_posting_info(date_directory)

        if not session_info:
            raise HTTPException(status_code=404, detail="해당 날짜 세션을 찾을 수 없습니다")

        return JSONResponse(content={
            "success": True,
            "date_directory": date_directory,
            "session_info": session_info
        })

    except HTTPException:
        raise
    except Exception as e:
        web_logger.error(f"Failed to get posting session: {e}")
        raise HTTPException(status_code=500, detail="포스팅 세션 정보 조회 중 오류가 발생했습니다")


@router.delete("/sessions/{date_directory}")
async def delete_posting_session(date_directory: str):
    """
    포스팅 세션 삭제
    """
    try:
        success = data_manager.delete_posting(date_directory)

        if not success:
            raise HTTPException(status_code=404, detail="해당 날짜 세션을 찾을 수 없습니다")

        web_logger.info(f"Posting session deleted: {date_directory}")

        return JSONResponse(content={
            "success": True,
            "message": f"포스팅 세션이 삭제되었습니다: {date_directory}"
        })

    except HTTPException:
        raise
    except Exception as e:
        web_logger.error(f"Failed to delete posting session: {e}")
        raise HTTPException(status_code=500, detail="포스팅 세션 삭제 중 오류가 발생했습니다")


@router.get("/categories")
async def get_categories():
    """지원되는 카테고리 목록 조회"""
    return JSONResponse(content={
        "categories": Settings.SUPPORTED_CATEGORIES
    })


@router.get("/statistics")
async def get_storage_statistics():
    """저장소 통계 정보"""
    try:
        stats = data_manager.get_storage_statistics()

        return JSONResponse(content={
            "success": True,
            "statistics": stats
        })

    except Exception as e:
        web_logger.error(f"Failed to get storage statistics: {e}")
        raise HTTPException(status_code=500, detail="통계 정보 조회 중 오류가 발생했습니다")


@router.post("/cleanup")
async def cleanup_incomplete_sessions():
    """미완성 포스팅 세션 정리"""
    try:
        cleaned_sessions = data_manager.cleanup_incomplete_postings()

        web_logger.info(f"Cleaned up {len(cleaned_sessions)} incomplete sessions")

        return JSONResponse(content={
            "success": True,
            "message": f"{len(cleaned_sessions)}개의 미완성 세션이 정리되었습니다",
            "cleaned_sessions": cleaned_sessions
        })

    except Exception as e:
        web_logger.error(f"Failed to cleanup incomplete sessions: {e}")
        raise HTTPException(status_code=500, detail="미완성 세션 정리 중 오류가 발생했습니다")


@router.get("/uploads/status")
async def get_upload_status():
    """업로드 상태 및 설정 정보"""
    return JSONResponse(content={
        "max_file_size_mb": Settings.MAX_FILE_SIZE_MB,
        "max_images_per_post": Settings.MAX_IMAGES_PER_POST,
        "allowed_extensions": Settings.ALLOWED_IMAGE_EXTENSIONS,
        "supported_categories": Settings.SUPPORTED_CATEGORIES,
        "date_based_structure": True,
        "directory_format": "yyyyMMdd(상호명)"
    })


# 레거시 호환성을 위한 엔드포인트들 (필요시 제거 가능)
@router.post("/upload/images")
async def upload_images_legacy(files: List[UploadFile] = File(...)):
    """레거시 이미지 업로드 (오늘 날짜 사용)"""
    web_logger.info(f"[Upload endpoint hit] legacy /upload/images files={len(files)}")
    # 오늘 날짜로 세션 생성 후 이미지 업로드
    today = datetime.now().strftime('%Y-%m-%d')

    # 기본 사용자 경험 데이터 생성
    default_experience = {
        "category": "기타",
        "personal_review": "업로드된 이미지",
        "visit_date": today
    }

    # 세션 생성
    date_directory = data_manager.create_posting_session(today, default_experience)

    # 이미지 업로드
    return await upload_images_to_session(date_directory, files)


@router.post("/user-experience")
async def create_user_experience_legacy(
    category: str = Form(...),
    personal_review: str = Form(...),
    rating: int = Form(None),
    visit_date: str = Form(None),
    companion: str = Form(None),
    ai_additional_script: str = Form(None),
    hashtags: str = Form(None)
):
    """레거시 사용자 경험 데이터 생성"""
    user_experience = UserExperienceInput(
        category=category,
        personal_review=personal_review,
        rating=rating,
        visit_date=visit_date,
        companion=companion,
        ai_additional_script=ai_additional_script,
        hashtags=hashtags
    )

    return await create_posting_session(user_experience)
