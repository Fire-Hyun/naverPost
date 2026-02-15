"""
블로그 워크플로우 API 엔드포인트
"""

import asyncio
import logging
import subprocess
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from src.services.blog_workflow import get_blog_workflow_service, WorkflowProgress, WorkflowStatus
from src.quality.unified_scorer import UnifiedQualityScorer
from src.config.settings import Settings


# Pydantic 모델 정의
class WorkflowStartRequest(BaseModel):
    """워크플로우 시작 요청"""
    visit_date: str = Field(..., description="방문 날짜 (YYYYMMDD)", pattern=r'^\d{8}$')
    category: str = Field(..., description="카테고리")
    store_name: str = Field(..., description="상호명")
    personal_review: str = Field(..., min_length=50, description="개인 감상평 (최소 50자)")
    rating: Optional[int] = Field(default=None, ge=1, le=5, description="별점 (1-5)")
    companion: Optional[str] = Field(default=None, description="동행자")
    location: Optional[str] = Field(default=None, description="위치")
    hashtags: Optional[List[str]] = Field(default=[], description="해시태그")
    additional_script: Optional[str] = Field(default="", description="추가 스크립트")
    auto_upload_to_naver: bool = Field(default=True, description="네이버 자동 업로드 여부")


class WorkflowStatusResponse(BaseModel):
    """워크플로우 상태 응답"""
    workflow_id: str
    status: str
    current_step: int
    total_steps: int
    step_name: str
    message: str
    progress_percentage: float
    start_time: str
    end_time: Optional[str] = None
    results: Dict[str, Any] = {}


class WorkflowStartResponse(BaseModel):
    """워크플로우 시작 응답"""
    success: bool
    workflow_id: str
    message: str


# 라우터 생성
router = APIRouter(prefix="/api/workflow", tags=["workflow"])


# 전역 워크플로우 상태 저장소 (실제 환경에서는 Redis 등 사용)
active_workflows: Dict[str, WorkflowProgress] = {}


def generate_workflow_id() -> str:
    """워크플로우 ID 생성"""
    from uuid import uuid4
    return str(uuid4())


@router.post("/start", response_model=WorkflowStartResponse)
async def start_workflow(
    request: WorkflowStartRequest,
    background_tasks: BackgroundTasks
):
    """
    블로그 생성 워크플로우 시작
    """
    try:
        # 워크플로우 ID 생성
        workflow_id = generate_workflow_id()

        # 사용자 경험 데이터 변환
        user_experience = {
            "category": request.category,
            "store_name": request.store_name,
            "personal_review": request.personal_review,
            "ai_additional_script": request.additional_script,
            "visit_date": request.visit_date,
            "rating": request.rating,
            "companion": request.companion,
            "location": request.location,
            "hashtags": request.hashtags or []
        }

        # 백그라운드에서 워크플로우 실행
        background_tasks.add_task(
            execute_workflow_background,
            workflow_id,
            request.visit_date,
            user_experience,
            None,  # 웹에서는 이미지를 별도로 처리
            request.auto_upload_to_naver
        )

        return WorkflowStartResponse(
            success=True,
            workflow_id=workflow_id,
            message="워크플로우가 시작되었습니다"
        )

    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to start workflow: {e}")
        raise HTTPException(status_code=500, detail=f"워크플로우 시작 실패: {str(e)}")


@router.get("/status/{workflow_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(workflow_id: str):
    """
    워크플로우 상태 조회
    """
    if workflow_id not in active_workflows:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다")

    progress = active_workflows[workflow_id]

    return WorkflowStatusResponse(
        workflow_id=workflow_id,
        status=progress.status.value,
        current_step=progress.current_step,
        total_steps=progress.total_steps,
        step_name=progress.step_name,
        message=progress.message,
        progress_percentage=progress.progress_percentage,
        start_time=progress.start_time.isoformat(),
        end_time=progress.end_time.isoformat() if progress.end_time else None,
        results=progress.results
    )


@router.get("/stream/{workflow_id}")
async def stream_workflow_progress(workflow_id: str):
    """
    워크플로우 진행상황을 Server-Sent Events로 스트리밍
    """
    if workflow_id not in active_workflows:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다")

    async def event_stream():
        """SSE 이벤트 스트림 생성"""
        try:
            while workflow_id in active_workflows:
                progress = active_workflows[workflow_id]

                # JSON 데이터 생성
                data = {
                    "workflow_id": workflow_id,
                    "status": progress.status.value,
                    "current_step": progress.current_step,
                    "total_steps": progress.total_steps,
                    "step_name": progress.step_name,
                    "message": progress.message,
                    "progress_percentage": progress.progress_percentage,
                    "timestamp": datetime.now().isoformat()
                }

                # SSE 형식으로 전송
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

                # 완료되었으면 종료
                if progress.status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED]:
                    break

                # 1초 대기
                await asyncio.sleep(1)

        except Exception as e:
            logging.getLogger(__name__).error(f"Error in event stream: {e}")
            yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*"
        }
    )


@router.post("/cancel/{workflow_id}")
async def cancel_workflow(workflow_id: str):
    """
    워크플로우 취소
    """
    if workflow_id not in active_workflows:
        raise HTTPException(status_code=404, detail="워크플로우를 찾을 수 없습니다")

    progress = active_workflows[workflow_id]

    # 워크플로우 서비스를 통해 취소
    workflow_service = get_blog_workflow_service()
    workflow_service.cancel_workflow(progress)

    return {"success": True, "message": "워크플로우가 취소되었습니다"}


@router.get("/list")
async def list_active_workflows():
    """
    활성 워크플로우 목록 조회
    """
    workflows = []

    for workflow_id, progress in active_workflows.items():
        workflows.append({
            "workflow_id": workflow_id,
            "status": progress.status.value,
            "step_name": progress.step_name,
            "progress_percentage": progress.progress_percentage,
            "start_time": progress.start_time.isoformat()
        })

    return {"workflows": workflows}


@router.delete("/cleanup")
async def cleanup_completed_workflows():
    """
    완료된 워크플로우 정리
    """
    completed_statuses = [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED]

    workflows_to_remove = [
        workflow_id for workflow_id, progress in active_workflows.items()
        if progress.status in completed_statuses
    ]

    for workflow_id in workflows_to_remove:
        del active_workflows[workflow_id]

    return {
        "success": True,
        "message": f"{len(workflows_to_remove)}개의 완료된 워크플로우를 정리했습니다"
    }


async def execute_workflow_background(
    workflow_id: str,
    date_directory: str,
    user_experience: Dict[str, Any],
    images: Optional[List[Any]],
    auto_upload: bool
):
    """
    백그라운드에서 워크플로우 실행
    """
    try:
        workflow_service = get_blog_workflow_service()

        # 진행상황 콜백
        def progress_callback(progress: WorkflowProgress):
            active_workflows[workflow_id] = progress

        # 워크플로우 실행
        result = await workflow_service.process_complete_workflow(
            date_directory=date_directory,
            user_experience=user_experience,
            images=images,
            auto_upload=auto_upload,
            progress_callback=progress_callback
        )

        # 최종 결과 저장
        active_workflows[workflow_id] = result

        # 30분 후 자동 삭제
        await asyncio.sleep(1800)
        if workflow_id in active_workflows:
            del active_workflows[workflow_id]

    except Exception as e:
        logging.getLogger(__name__).error(f"Background workflow {workflow_id} failed: {e}")

        # 실패 상태 저장
        if workflow_id in active_workflows:
            progress = active_workflows[workflow_id]
            progress.status = WorkflowStatus.FAILED
            progress.message = f"예상치 못한 오류: {str(e)}"
            progress.end_time = datetime.now()


# 기존 데이터 처리 엔드포인트
class ExistingDataRequest(BaseModel):
    """기존 데이터 처리 요청"""
    date_directory: str = Field(..., description="처리할 날짜 디렉토리")
    auto_upload_to_naver: bool = Field(default=True, description="네이버 자동 업로드 여부")


@router.post("/process-existing", response_model=WorkflowStartResponse)
async def process_existing_data(
    request: ExistingDataRequest,
    background_tasks: BackgroundTasks
):
    """
    기존 생성된 데이터를 사용해 네이버 블로그 포스팅 진행
    """
    try:
        # 데이터 디렉토리 존재 확인
        data_path = Settings.DATA_DIR / request.date_directory
        if not data_path.exists():
            raise HTTPException(status_code=404, detail=f"데이터 디렉토리를 찾을 수 없습니다: {request.date_directory}")

        # 메타데이터 파일 존재 확인
        metadata_path = data_path / "metadata.json"
        if not metadata_path.exists():
            raise HTTPException(status_code=404, detail="메타데이터 파일을 찾을 수 없습니다")

        # 블로그 콘텐츠 파일 존재 확인
        blog_result_path = data_path / "blog_result.md"
        if not blog_result_path.exists():
            raise HTTPException(status_code=404, detail="생성된 블로그 콘텐츠를 찾을 수 없습니다")

        # 워크플로우 ID 생성
        workflow_id = generate_workflow_id()

        # 백그라운드에서 기존 데이터 처리
        background_tasks.add_task(
            process_existing_data_background,
            workflow_id,
            request.date_directory,
            request.auto_upload_to_naver
        )

        return WorkflowStartResponse(
            success=True,
            workflow_id=workflow_id,
            message=f"기존 데이터({request.date_directory}) 처리가 시작되었습니다"
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to process existing data: {e}")
        raise HTTPException(status_code=500, detail=f"기존 데이터 처리 시작 실패: {str(e)}")


async def process_existing_data_background(
    workflow_id: str,
    date_directory: str,
    auto_upload: bool
):
    """
    백그라운드에서 기존 데이터 처리
    """
    from src.services.blog_workflow import WorkflowProgress, WorkflowStatus

    try:
        # 초기 진행상황 설정
        progress = WorkflowProgress(
            status=WorkflowStatus.PENDING,
            current_step=0,
            total_steps=3,
            step_name="기존 데이터 로드 중",
            message="기존 데이터를 불러오고 있습니다...",
            start_time=datetime.now()
        )
        active_workflows[workflow_id] = progress

        # 1단계: 데이터 로드 및 검증
        progress.current_step = 1
        progress.step_name = "데이터 검증"
        progress.message = "기존 데이터를 검증하고 있습니다..."
        progress.status = WorkflowStatus.VALIDATING

        data_path = Settings.DATA_DIR / date_directory

        # 메타데이터 로드
        with open(data_path / "metadata.json", "r", encoding="utf-8") as f:
            metadata = json.load(f)

        # 블로그 콘텐츠 로드
        with open(data_path / "blog_result.md", "r", encoding="utf-8") as f:
            blog_content = f.read()

        progress.results["metadata"] = metadata
        progress.results["blog_content_length"] = len(blog_content)

        await asyncio.sleep(1)  # 진행상황 표시

        # 2단계: 품질 검증 (옵션)
        progress.current_step = 2
        progress.step_name = "품질 검증"
        progress.message = "생성된 콘텐츠의 품질을 검증하고 있습니다..."
        progress.status = WorkflowStatus.QUALITY_CHECKING

        try:
            scorer = UnifiedQualityScorer()
            quality_result = await scorer.score_content(blog_content, metadata.get("user_input", {}))
            progress.results["quality_score"] = quality_result.overall_score
            progress.results["quality_details"] = quality_result.detailed_scores
        except Exception as e:
            logging.getLogger(__name__).warning(f"품질 검증 실패 (계속 진행): {e}")
            progress.results["quality_score"] = 0
            progress.results["quality_warning"] = str(e)

        await asyncio.sleep(1)

        # 3단계: 네이버 블로그 업로드
        if auto_upload:
            progress.current_step = 3
            progress.step_name = "네이버 블로그 업로드"
            progress.message = "네이버 블로그에 임시저장 중입니다..."
            progress.status = WorkflowStatus.UPLOADING_TO_NAVER

            try:
                # naver-poster CLI를 사용하여 업로드 (Node.js 프로젝트)
                naver_poster_path = Settings.PROJECT_ROOT / "naver-poster"
                naver_poster_cli = naver_poster_path / "dist" / "cli" / "post_to_naver.js"

                if not naver_poster_cli.exists():
                    # 빌드가 안되어 있으면 빌드 시도
                    if not (naver_poster_path / "dist").exists():
                        build_result = subprocess.run(
                            ["npm", "run", "build"],
                            capture_output=True,
                            text=True,
                            cwd=naver_poster_path,
                            timeout=120
                        )
                        if build_result.returncode != 0:
                            raise FileNotFoundError(f"naver-poster 빌드 실패: {build_result.stderr}")

                if not naver_poster_cli.exists():
                    raise FileNotFoundError("naver-poster CLI를 찾을 수 없습니다")

                # 업로드 명령 실행
                cmd = [
                    "node", str(naver_poster_cli),
                    "--dataDir", str(data_path),
                    "--draftSave"
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=Settings.PROJECT_ROOT,
                    timeout=300  # 5분 타임아웃
                )

                if result.returncode == 0:
                    progress.results["naver_upload"] = {
                        "success": True,
                        "message": "네이버 블로그 임시저장 완료",
                        "output": result.stdout
                    }
                    progress.message = "네이버 블로그 임시저장이 완료되었습니다!"
                else:
                    progress.results["naver_upload"] = {
                        "success": False,
                        "message": "네이버 블로그 업로드 실패",
                        "error": result.stderr,
                        "output": result.stdout
                    }
                    progress.message = f"네이버 블로그 업로드 실패: {result.stderr}"

            except subprocess.TimeoutExpired:
                progress.results["naver_upload"] = {
                    "success": False,
                    "message": "네이버 블로그 업로드 타임아웃",
                    "error": "업로드가 5분을 초과했습니다"
                }
                progress.message = "네이버 블로그 업로드가 타임아웃되었습니다"

            except Exception as e:
                progress.results["naver_upload"] = {
                    "success": False,
                    "message": "네이버 블로그 업로드 중 오류 발생",
                    "error": str(e)
                }
                progress.message = f"네이버 블로그 업로드 중 오류: {str(e)}"

        else:
            progress.results["naver_upload"] = {
                "success": True,
                "message": "자동 업로드가 비활성화되어 있습니다",
                "skipped": True
            }
            progress.message = "네이버 블로그 업로드를 건너뛰었습니다"

        # 완료
        progress.status = WorkflowStatus.COMPLETED
        progress.current_step = progress.total_steps
        progress.step_name = "완료"
        progress.message = "모든 처리가 완료되었습니다!"
        progress.end_time = datetime.now()
        progress.progress_percentage = 100.0

        # 30분 후 자동 삭제
        await asyncio.sleep(1800)
        if workflow_id in active_workflows:
            del active_workflows[workflow_id]

    except Exception as e:
        logging.getLogger(__name__).error(f"Background processing {workflow_id} failed: {e}")

        # 실패 상태 저장
        if workflow_id in active_workflows:
            progress = active_workflows[workflow_id]
            progress.status = WorkflowStatus.FAILED
            progress.message = f"처리 중 오류 발생: {str(e)}"
            progress.end_time = datetime.now()
            progress.results["error"] = str(e)


# 헬스체크 엔드포인트
@router.get("/health")
async def workflow_health():
    """
    워크플로우 시스템 헬스체크
    """
    workflow_service = get_blog_workflow_service()

    # naver-poster 경로 확인
    naver_poster_exists = workflow_service.naver_poster_cli.exists()

    return {
        "status": "healthy",
        "active_workflows": len(active_workflows),
        "naver_poster_available": naver_poster_exists,
        "naver_poster_path": str(workflow_service.naver_poster_cli) if naver_poster_exists else None
    }
