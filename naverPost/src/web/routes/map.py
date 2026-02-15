"""
네이버 지도 API 웹 라우터

네이버 지도 API 기능을 웹 인터페이스로 제공합니다.
"""

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import io
import asyncio
import logging

from src.services.naver_map_service import (
    naver_map_service,
    get_location_from_address,
    get_address_from_coordinates,
    generate_map_image,
    search_nearby_places,
    Location,
    MapOptions
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/map", tags=["map"])


# Pydantic 모델 정의
class LocationResponse(BaseModel):
    """위치 정보 응답 모델"""
    lat: float
    lng: float
    address: str
    name: str


class MapImageRequest(BaseModel):
    """지도 이미지 생성 요청 모델"""
    address: str
    width: int = 400
    height: int = 300
    zoom: int = 13
    map_type: str = "basic"
    markers: Optional[List[Dict[str, Any]]] = None


class PlaceSearchRequest(BaseModel):
    """장소 검색 요청 모델"""
    query: str
    center_address: Optional[str] = None
    radius: int = 5000


@router.get("/health")
async def health_check():
    """네이버 지도 API 상태 확인"""
    try:
        is_valid = await naver_map_service.validate_api_keys()
        return {
            "status": "healthy" if is_valid else "unhealthy",
            "message": "네이버 지도 API 연결 성공" if is_valid else "네이버 지도 API 연결 실패",
            "api_valid": is_valid
        }
    except Exception as e:
        logger.error(f"네이버 지도 API 상태 확인 중 오류: {e}")
        return {
            "status": "unhealthy",
            "message": f"상태 확인 중 오류 발생: {str(e)}",
            "api_valid": False
        }


@router.get("/geocode", response_model=LocationResponse)
async def geocode_address(address: str = Query(..., description="변환할 주소")):
    """
    주소를 좌표로 변환 (Geocoding)

    Args:
        address: 변환할 주소

    Returns:
        LocationResponse: 위치 정보
    """
    try:
        location = await get_location_from_address(address)
        if location:
            return LocationResponse(
                lat=location.lat,
                lng=location.lng,
                address=location.address,
                name=location.name
            )
        else:
            raise HTTPException(status_code=404, detail=f"주소 '{address}'를 찾을 수 없습니다.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Geocoding 중 오류: {e}")
        raise HTTPException(status_code=500, detail=f"주소 변환 중 오류가 발생했습니다: {str(e)}")


@router.get("/reverse-geocode")
async def reverse_geocode_coordinates(
    lat: float = Query(..., description="위도"),
    lng: float = Query(..., description="경도")
):
    """
    좌표를 주소로 변환 (Reverse Geocoding)

    Args:
        lat: 위도
        lng: 경도

    Returns:
        Dict: 주소 정보
    """
    try:
        address = await get_address_from_coordinates(lat, lng)
        if address:
            return {"address": address, "lat": lat, "lng": lng}
        else:
            raise HTTPException(status_code=404, detail=f"좌표 ({lat}, {lng})에 해당하는 주소를 찾을 수 없습니다.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reverse Geocoding 중 오류: {e}")
        raise HTTPException(status_code=500, detail=f"좌표 변환 중 오류가 발생했습니다: {str(e)}")


@router.post("/static-image")
async def generate_static_map_image(request: MapImageRequest):
    """
    정적 지도 이미지 생성

    Args:
        request: 지도 이미지 생성 요청

    Returns:
        StreamingResponse: PNG 이미지
    """
    try:
        # 주소로부터 위치 정보 가져오기
        location = await get_location_from_address(request.address)
        if not location:
            raise HTTPException(status_code=404, detail=f"주소 '{request.address}'를 찾을 수 없습니다.")

        # 지도 옵션 설정
        options = MapOptions(
            width=request.width,
            height=request.height,
            zoom=request.zoom,
            map_type=request.map_type,
            markers=request.markers
        )

        # 지도 이미지 생성
        image_data = await naver_map_service.get_static_map(location, options)
        if not image_data:
            raise HTTPException(status_code=500, detail="지도 이미지 생성에 실패했습니다.")

        # 이미지 응답 생성
        return StreamingResponse(
            io.BytesIO(image_data),
            media_type="image/png",
            headers={
                "Content-Disposition": f"inline; filename=map_{location.name or 'location'}.png"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"지도 이미지 생성 중 오류: {e}")
        raise HTTPException(status_code=500, detail=f"지도 이미지 생성 중 오류가 발생했습니다: {str(e)}")


@router.get("/static-image")
async def generate_static_map_image_get(
    address: str = Query(..., description="주소"),
    width: int = Query(400, description="이미지 너비"),
    height: int = Query(300, description="이미지 높이"),
    zoom: int = Query(13, description="줌 레벨")
):
    """
    정적 지도 이미지 생성 (GET 방식)

    Args:
        address: 주소
        width: 이미지 너비
        height: 이미지 높이
        zoom: 줌 레벨

    Returns:
        StreamingResponse: PNG 이미지
    """
    request = MapImageRequest(
        address=address,
        width=width,
        height=height,
        zoom=zoom
    )
    return await generate_static_map_image(request)


@router.post("/search-places", response_model=List[LocationResponse])
async def search_places(request: PlaceSearchRequest):
    """
    장소 검색

    Args:
        request: 장소 검색 요청

    Returns:
        List[LocationResponse]: 검색된 장소 목록
    """
    try:
        if request.center_address:
            # 특정 주소 주변 검색
            places = await search_nearby_places(
                request.query,
                request.center_address,
                request.radius
            )
        else:
            # 전체 검색
            places = await naver_map_service.search_places(request.query)

        return [
            LocationResponse(
                lat=place.lat,
                lng=place.lng,
                address=place.address,
                name=place.name
            )
            for place in places
        ]

    except Exception as e:
        logger.error(f"장소 검색 중 오류: {e}")
        raise HTTPException(status_code=500, detail=f"장소 검색 중 오류가 발생했습니다: {str(e)}")


@router.get("/search-places", response_model=List[LocationResponse])
async def search_places_get(
    query: str = Query(..., description="검색어"),
    center_address: Optional[str] = Query(None, description="중심 주소"),
    radius: int = Query(5000, description="검색 반경(미터)")
):
    """
    장소 검색 (GET 방식)

    Args:
        query: 검색어
        center_address: 중심 주소 (옵션)
        radius: 검색 반경

    Returns:
        List[LocationResponse]: 검색된 장소 목록
    """
    request = PlaceSearchRequest(
        query=query,
        center_address=center_address,
        radius=radius
    )
    return await search_places(request)


@router.get("/url")
async def generate_map_url(
    address: str = Query(..., description="주소"),
    zoom: int = Query(13, description="줌 레벨")
):
    """
    네이버 지도 웹 URL 생성

    Args:
        address: 주소
        zoom: 줌 레벨

    Returns:
        Dict: 지도 URL 정보
    """
    try:
        location = await get_location_from_address(address)
        if not location:
            raise HTTPException(status_code=404, detail=f"주소 '{address}'를 찾을 수 없습니다.")

        map_url = naver_map_service.generate_map_url(location, zoom)

        return {
            "address": address,
            "location": {
                "lat": location.lat,
                "lng": location.lng,
                "name": location.name,
                "address": location.address
            },
            "map_url": map_url
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"지도 URL 생성 중 오류: {e}")
        raise HTTPException(status_code=500, detail=f"지도 URL 생성 중 오류가 발생했습니다: {str(e)}")


@router.get("/distance")
async def calculate_distance(
    from_address: str = Query(..., description="출발지 주소"),
    to_address: str = Query(..., description="도착지 주소")
):
    """
    두 주소 간의 직선거리 계산

    Args:
        from_address: 출발지 주소
        to_address: 도착지 주소

    Returns:
        Dict: 거리 정보
    """
    try:
        # 두 주소를 좌표로 변환
        from_location = await get_location_from_address(from_address)
        to_location = await get_location_from_address(to_address)

        if not from_location:
            raise HTTPException(status_code=404, detail=f"출발지 주소 '{from_address}'를 찾을 수 없습니다.")
        if not to_location:
            raise HTTPException(status_code=404, detail=f"도착지 주소 '{to_address}'를 찾을 수 없습니다.")

        # 거리 계산
        distance = naver_map_service._calculate_distance(
            from_location.lat, from_location.lng,
            to_location.lat, to_location.lng
        )

        return {
            "from": {
                "address": from_address,
                "lat": from_location.lat,
                "lng": from_location.lng
            },
            "to": {
                "address": to_address,
                "lat": to_location.lat,
                "lng": to_location.lng
            },
            "distance_meters": round(distance, 2),
            "distance_km": round(distance / 1000, 2)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"거리 계산 중 오류: {e}")
        raise HTTPException(status_code=500, detail=f"거리 계산 중 오류가 발생했습니다: {str(e)}")


# 개발/테스트용 엔드포인트
@router.get("/test/all")
async def test_all_features():
    """모든 네이버 지도 API 기능 테스트"""
    try:
        test_results = {}

        # 1. API 키 검증
        test_results["api_validation"] = await naver_map_service.validate_api_keys()

        # 2. Geocoding 테스트
        test_address = "서울특별시 중구 세종대로 110"
        location = await get_location_from_address(test_address)
        test_results["geocoding"] = {
            "success": location is not None,
            "location": LocationResponse(
                lat=location.lat,
                lng=location.lng,
                address=location.address,
                name=location.name
            ).dict() if location else None
        }

        # 3. Reverse Geocoding 테스트
        if location:
            reverse_address = await get_address_from_coordinates(location.lat, location.lng)
            test_results["reverse_geocoding"] = {
                "success": reverse_address is not None,
                "address": reverse_address
            }

        # 4. 장소 검색 테스트
        places = await naver_map_service.search_places("강남역 맛집")
        test_results["place_search"] = {
            "success": len(places) > 0,
            "count": len(places),
            "sample": LocationResponse(
                lat=places[0].lat,
                lng=places[0].lng,
                address=places[0].address,
                name=places[0].name
            ).dict() if places else None
        }

        return {
            "status": "completed",
            "timestamp": "현재 시각",  # 실제로는 datetime.now()를 사용
            "test_results": test_results
        }

    except Exception as e:
        logger.error(f"전체 테스트 중 오류: {e}")
        raise HTTPException(status_code=500, detail=f"테스트 중 오류가 발생했습니다: {str(e)}")