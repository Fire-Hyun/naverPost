"""
이미지 업로드 및 사용자 경험 데이터 처리 라우터
"""

import os
import uuid
from typing import List
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from src.config.settings import Settings
from src.content.models import UserExperience, ImageUploadData
from src.utils.logger import web_logger
from src.utils.exceptions import ImageUploadError, FileProcessingError

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

async def save_uploaded_file(file: UploadFile) -> ImageUploadData:
    """업로드된 파일 저장"""
    try:
        # 파일 유효성 검증
        if not await validate_image_file(file):
            raise ImageUploadError(
                f"지원하지 않는 이미지 파일입니다: {file.filename}",
                file_path=file.filename
            )

        # 고유한 파일명 생성
        file_extension = Path(file.filename).suffix.lower()
        unique_filename = f"{uuid.uuid4()}{file_extension}"

        # 저장 경로 설정
        save_path = Settings.get_upload_path(unique_filename)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        # 파일 크기 확인
        file_content = await file.read()
        file_size = len(file_content)

        if file_size > Settings.MAX_FILE_SIZE_MB * 1024 * 1024:
            raise ImageUploadError(
                f"파일 크기가 너무 큽니다. 최대 {Settings.MAX_FILE_SIZE_MB}MB까지 허용됩니다",
                file_path=file.filename,
                file_size=file_size
            )

        # 파일 저장
        with open(save_path, "wb") as buffer:
            buffer.write(file_content)

        web_logger.info(f"File uploaded successfully: {unique_filename}")

        return ImageUploadData(
            filename=file.filename,
            saved_path=str(save_path),
            file_size=file_size,
            mime_type=file.content_type,
            uploaded_at=datetime.now()
        )

    except ImageUploadError:
        raise
    except Exception as e:
        web_logger.error(f"Failed to save uploaded file: {e}")
        raise FileProcessingError(
            f"파일 저장 중 오류가 발생했습니다: {str(e)}",
            file_path=file.filename
        )

@router.post("/upload/images")
async def upload_images(files: List[UploadFile] = File(...)):
    """이미지 업로드 엔드포인트"""
    try:
        if len(files) > Settings.MAX_IMAGES_PER_POST:
            raise HTTPException(
                status_code=400,
                detail=f"이미지는 최대 {Settings.MAX_IMAGES_PER_POST}개까지 업로드 가능합니다"
            )

        uploaded_files = []

        for file in files:
            if not file.filename:
                continue

            upload_data = await save_uploaded_file(file)
            uploaded_files.append({
                "original_filename": upload_data.filename,
                "saved_path": upload_data.saved_path,
                "file_size": upload_data.file_size,
                "url": f"/uploads/images/{Path(upload_data.saved_path).name}"
            })

        web_logger.info(f"Successfully uploaded {len(uploaded_files)} images")

        return JSONResponse(content={
            "success": True,
            "message": f"{len(uploaded_files)}개 이미지가 성공적으로 업로드되었습니다",
            "uploaded_files": uploaded_files
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

@router.post("/user-experience")
async def create_user_experience(
    images: str = Form(...),  # JSON 문자열로 받음
    category: str = Form(...),
    personal_review: str = Form(...),
    additional_notes: str = Form(None),
    location: str = Form(None),
    hashtags: str = Form("[]"),  # JSON 문자열로 받음
    rating: int = Form(None),
    visit_date: str = Form(None),
    companion: str = Form(None)
):
    """사용자 경험 데이터 생성"""
    try:
        import json

        # JSON 문자열을 파이썬 객체로 변환
        images_list = json.loads(images) if images else []
        hashtags_list = json.loads(hashtags) if hashtags else []

        # UserExperience 모델로 검증
        user_experience = UserExperience(
            images=images_list,
            category=category,
            personal_review=personal_review,
            additional_notes=additional_notes if additional_notes else None,
            location=location if location else None,
            hashtags=hashtags_list,
            rating=rating if rating else None,
            visit_date=visit_date if visit_date else None,
            companion=companion if companion else None
        )

        web_logger.info(f"User experience created: category={category}, images_count={len(images_list)}")

        return JSONResponse(content={
            "success": True,
            "message": "사용자 경험 데이터가 성공적으로 생성되었습니다",
            "user_experience": user_experience.model_dump()
        })

    except ValidationError as e:
        web_logger.error(f"User experience validation error: {e}")
        raise HTTPException(status_code=400, detail=f"데이터 검증 실패: {str(e)}")
    except json.JSONDecodeError as e:
        web_logger.error(f"JSON decode error: {e}")
        raise HTTPException(status_code=400, detail="잘못된 JSON 형식입니다")
    except Exception as e:
        web_logger.error(f"Unexpected error during user experience creation: {e}")
        raise HTTPException(status_code=500, detail="사용자 경험 데이터 생성 중 오류가 발생했습니다")

@router.get("/categories")
async def get_categories():
    """지원되는 카테고리 목록 조회"""
    return JSONResponse(content={
        "categories": Settings.SUPPORTED_CATEGORIES
    })

@router.delete("/upload/images/{filename}")
async def delete_uploaded_image(filename: str):
    """업로드된 이미지 삭제"""
    try:
        file_path = Settings.get_upload_path(filename)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

        file_path.unlink()
        web_logger.info(f"Image deleted: {filename}")

        return JSONResponse(content={
            "success": True,
            "message": "이미지가 성공적으로 삭제되었습니다"
        })

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    except Exception as e:
        web_logger.error(f"Error deleting image: {e}")
        raise HTTPException(status_code=500, detail="이미지 삭제 중 오류가 발생했습니다")

@router.get("/uploads/status")
async def get_upload_status():
    """업로드 상태 및 설정 정보"""
    return JSONResponse(content={
        "max_file_size_mb": Settings.MAX_FILE_SIZE_MB,
        "max_images_per_post": Settings.MAX_IMAGES_PER_POST,
        "allowed_extensions": Settings.ALLOWED_IMAGE_EXTENSIONS,
        "supported_categories": Settings.SUPPORTED_CATEGORIES
    })