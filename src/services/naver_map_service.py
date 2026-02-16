"""
네이버 지도 API 연동 서비스 (안정화 버전)

안정화된 네이버 지도 API를 활용한 다양한 지도 관련 기능을 제공합니다.
- 지도 표시
- 주소/좌표 변환 (Geocoding/Reverse Geocoding)
- 정적 지도 이미지 생성
- 장소 검색 (재시도, 캐싱, 레이트 리밋 적용)
"""

import asyncio
import aiohttp
import base64
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from urllib.parse import quote, urlencode
import logging

from src.config.settings import Settings
from src.utils.naver_map_client import StabilizedNaverMapClient, create_naver_map_client, MapLocation
from src.utils.structured_logger import get_logger

logger = get_logger("naver_map_service")

@dataclass
class Location:
    """위치 정보를 담는 데이터 클래스 (호환성 유지)"""
    lat: float
    lng: float
    address: str = ""
    name: str = ""

    @classmethod
    def from_map_location(cls, map_loc: MapLocation) -> 'Location':
        """MapLocation을 Location으로 변환"""
        return cls(
            lat=map_loc.lat,
            lng=map_loc.lng,
            address=map_loc.address or map_loc.road_address,
            name=map_loc.name
        )

@dataclass
class MapOptions:
    """지도 옵션을 담는 데이터 클래스"""
    width: int = 400
    height: int = 300
    zoom: int = 13
    map_type: str = "basic"  # basic, satellite, hybrid
    markers: List[Dict[str, Any]] = None
    format: str = "png"  # png, jpg

class NaverMapService:
    """네이버 지도 API 서비스 클래스 (안정화 버전)"""

    def __init__(self):
        self.client_id = Settings.NAVER_MAP_CLIENT_ID
        self.client_secret = Settings.NAVER_MAP_CLIENT_SECRET

        if not self.client_id or not self.client_secret:
            raise ValueError("네이버 지도 API 클라이언트 ID와 시크릿이 설정되지 않았습니다.")

        # 안정화된 클라이언트 사용
        self.stabilized_client = create_naver_map_client()

        # 레거시 헤더들 (하위 호환성)
        self.base_url = "https://naveropenapi.apigw.ntruss.com"
        self.headers = {
            "X-NCP-APIGW-API-KEY-ID": self.client_id,
            "X-NCP-APIGW-API-KEY": self.client_secret
        }

        # 네이버 개발자센터 API용 헤더도 준비 (fallback)
        self.naver_dev_headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret
        }

    async def fetch_place_by_store_name(
        self, store_name: str, region_hint: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        상호명으로 장소 정보를 조회한다.

        Args:
            store_name: 상호명 (예: "하이디라오 연동점")
            region_hint: 지역 힌트 (예: "제주", "강남")

        Returns:
            장소 정보 dict 또는 None (조회 실패 시)
        """
        if not store_name or not store_name.strip():
            logger.warning("Empty store_name provided")
            return None

        try:
            # 검색 쿼리 구성
            search_query = f"{region_hint} {store_name}" if region_hint else store_name
            logger.info("Fetching place by store name", store_name=store_name, region_hint=region_hint, query=search_query)

            search_result = await self.stabilized_client.search_place(search_query, similarity_threshold=0.1)

            # 결과 0건이고 region_hint가 있었으면 store_name만으로 재시도
            if (not search_result.success or not search_result.locations) and region_hint:
                logger.info("Retrying without region hint", store_name=store_name)
                search_result = await self.stabilized_client.search_place(store_name, similarity_threshold=0.1)

            if not search_result.success or not search_result.locations:
                logger.warning("No place found for store name", store_name=store_name)
                return None

            # 최적 결과 선택: similarity_score 최대
            best = search_result.get_best_match()
            if not best:
                return None

            logger.info(
                "Place found",
                store_name=store_name,
                found_name=best.name,
                similarity=best.similarity_score,
            )

            return {
                "name": best.name,
                "address": best.road_address or best.address,
                "jibun_address": best.jibun_address,
                "lat": best.lat,
                "lng": best.lng,
                "phone": best.phone,
                "category": best.category,
            }

        except Exception as e:
            logger.error("fetch_place_by_store_name failed", error=e, store_name=store_name)
            return None

    async def geocode(self, address: str) -> Optional[Location]:
        """
        주소를 좌표로 변환 (Geocoding) - 안정화 버전

        Args:
            address: 변환할 주소

        Returns:
            Location 객체 또는 None
        """
        if not address or not address.strip():
            logger.warning("Empty address provided for geocoding")
            return None

        try:
            logger.info("Starting geocoding", address=address)

            # 안정화된 클라이언트로 검색
            search_result = await self.stabilized_client.search_place(address, similarity_threshold=0.1)

            if search_result.success and search_result.locations:
                # 가장 유사도가 높은 결과 선택
                best_match = search_result.get_best_match()

                if best_match:
                    logger.info("Geocoding successful",
                              address=address,
                              found_name=best_match.name,
                              similarity=best_match.similarity_score,
                              cache_hit=search_result.cache_hit)

                    return Location.from_map_location(best_match)
                else:
                    logger.warning("No suitable matches found for geocoding", address=address)
            else:
                logger.warning("Geocoding failed",
                             address=address,
                             error_type=search_result.error_type,
                             error_message=search_result.error_message)

                # fallback: NCP Geocoding API 시도 (기존 로직 유지)
                return await self._fallback_ncp_geocoding(address)

        except Exception as e:
            logger.error("Geocoding error", error=e, address=address)

            # fallback: NCP Geocoding API 시도
            return await self._fallback_ncp_geocoding(address)

        return None

    async def _fallback_ncp_geocoding(self, address: str) -> Optional[Location]:
        """NCP Geocoding API 폴백"""
        try:
            logger.info("Trying fallback NCP geocoding", address=address)

            url = f"{self.base_url}/map-geocode/v2/geocode"
            params = {"query": address}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        if data.get("meta", {}).get("totalCount", 0) > 0:
                            result = data["addresses"][0]
                            location = Location(
                                lat=float(result["y"]),
                                lng=float(result["x"]),
                                address=result.get("roadAddress") or result.get("jibunAddress", ""),
                                name=address
                            )
                            logger.info("NCP geocoding successful", address=address)
                            return location
                    else:
                        logger.warning("NCP Geocoding API error", status_code=response.status, address=address)

        except Exception as e:
            logger.error("NCP Geocoding error", error=e, address=address)

        return None

    async def reverse_geocode(self, lat: float, lng: float) -> Optional[str]:
        """
        좌표를 주소로 변환 (Reverse Geocoding)

        Args:
            lat: 위도
            lng: 경도

        Returns:
            주소 문자열 또는 None
        """
        try:
            url = f"{self.base_url}/map-reversegeocode/v2/gc"
            params = {
                "coords": f"{lng},{lat}",
                "output": "json"
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        if data["status"]["code"] == 0:
                            result = data["results"][0]
                            region = result["region"]
                            land = result["land"]

                            # 도로명 주소 우선
                            if land and land["addition0"]["value"]:
                                return f"{region['area1']['name']} {region['area2']['name']} {land['addition0']['value']}"
                            else:
                                return f"{region['area1']['name']} {region['area2']['name']} {region['area3']['name']}"
                    else:
                        logger.error(f"Reverse Geocoding API 오류: {response.status}")

        except Exception as e:
            logger.error(f"Reverse Geocoding 중 오류 발생: {e}")

        return None

    async def get_static_map(self, location: Location, options: MapOptions = None) -> Optional[bytes]:
        """
        정적 지도 이미지 생성

        Args:
            location: 중심 좌표
            options: 지도 옵션

        Returns:
            이미지 바이트 데이터 또는 None
        """
        if options is None:
            options = MapOptions()

        try:
            url = f"{self.base_url}/map-static/v2/raster"

            # 기본 파라미터
            params = {
                "w": options.width,
                "h": options.height,
                "center": f"{location.lng},{location.lat}",
                "level": options.zoom,
                "maptype": options.map_type,
                "format": options.format
            }

            # 마커 추가
            if options.markers:
                marker_strings = []
                for marker in options.markers:
                    marker_str = f"type:t|size:mid|pos:{marker.get('lng', location.lng)} {marker.get('lat', location.lat)}"
                    if 'color' in marker:
                        marker_str += f"|color:{marker['color']}"
                    if 'label' in marker:
                        marker_str += f"|label:{marker['label']}"
                    marker_strings.append(marker_str)
                params["markers"] = "|".join(marker_strings)
            else:
                # 기본 마커 추가
                params["markers"] = f"type:t|size:mid|pos:{location.lng} {location.lat}|color:red"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params) as response:
                    if response.status == 200:
                        return await response.read()
                    else:
                        logger.error(f"Static Map API 오류: {response.status}")

        except Exception as e:
            logger.error(f"정적 지도 생성 중 오류 발생: {e}")

        return None

    async def search_places(self, query: str, lat: float = None, lng: float = None, radius: int = 5000) -> List[Location]:
        """
        장소 검색 - 안정화 버전

        Args:
            query: 검색할 장소명
            lat: 중심 위도 (옵션)
            lng: 중심 경도 (옵션)
            radius: 검색 반경 (미터, 옵션)

        Returns:
            검색된 장소 목록
        """
        try:
            logger.info("Starting place search", query=query, lat=lat, lng=lng, radius=radius)

            # 안정화된 클라이언트로 검색
            search_result = await self.stabilized_client.search_place(query, similarity_threshold=0.0)

            if search_result.success and search_result.locations:
                places = []

                for map_location in search_result.locations:
                    location = Location.from_map_location(map_location)

                    # 거리 필터링 (중심 좌표가 제공된 경우)
                    if lat is not None and lng is not None:
                        distance = self._calculate_distance(lat, lng, location.lat, location.lng)
                        if distance <= radius:
                            places.append(location)
                    else:
                        places.append(location)

                logger.info("Place search completed",
                          query=query,
                          total_found=len(search_result.locations),
                          after_radius_filter=len(places),
                          cache_hit=search_result.cache_hit)

                return places

            else:
                logger.warning("Place search failed",
                             query=query,
                             error_type=search_result.error_type,
                             error_message=search_result.error_message)
                return []

        except Exception as e:
            logger.error("Place search error", error=e, query=query)
            return []

    def _calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """
        두 좌표 간의 거리 계산 (미터)

        Args:
            lat1, lng1: 첫 번째 좌표
            lat2, lng2: 두 번째 좌표

        Returns:
            거리 (미터)
        """
        import math

        # 지구 반지름 (미터)
        R = 6371000

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)

        a = (math.sin(delta_lat / 2) * math.sin(delta_lat / 2) +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lng / 2) * math.sin(delta_lng / 2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c

    def generate_map_url(self, location: Location, zoom: int = 13) -> str:
        """
        네이버 지도 웹 URL 생성

        Args:
            location: 위치 정보
            zoom: 줌 레벨

        Returns:
            네이버 지도 URL
        """
        base_url = "https://map.naver.com/v5/search/"
        query = quote(location.name or location.address)
        return f"{base_url}{query}"

    async def validate_api_keys(self) -> bool:
        """
        API 키 유효성 검증 - 안정화 버전

        Returns:
            API 키 유효 여부
        """
        try:
            logger.info("Validating Naver Map API keys")

            # 안정화된 클라이언트의 검증 메소드 사용
            is_valid = await self.stabilized_client.validate_api_connection()

            if is_valid:
                logger.info("API key validation successful")
            else:
                logger.warning("API key validation failed")

            return is_valid

        except Exception as e:
            logger.error("API key validation error", error=e)
            return False

    async def cleanup(self):
        """리소스 정리"""
        try:
            await self.stabilized_client.close()
            logger.info("NaverMapService cleanup completed")
        except Exception as e:
            logger.error("Error during NaverMapService cleanup", error=e)

    def get_service_metrics(self) -> Dict[str, Any]:
        """서비스 메트릭 반환"""
        try:
            return self.stabilized_client.get_search_metrics()
        except Exception as e:
            logger.error("Error getting service metrics", error=e)
            return {"error": str(e)}


# 전역 인스턴스
naver_map_service = NaverMapService()


# 편의 함수들
async def get_location_from_address(address: str) -> Optional[Location]:
    """주소를 Location 객체로 변환"""
    return await naver_map_service.geocode(address)


async def get_address_from_coordinates(lat: float, lng: float) -> Optional[str]:
    """좌표를 주소로 변환"""
    return await naver_map_service.reverse_geocode(lat, lng)


async def generate_map_image(address: str, width: int = 400, height: int = 300) -> Optional[bytes]:
    """주소로부터 지도 이미지 생성"""
    location = await get_location_from_address(address)
    if location:
        options = MapOptions(width=width, height=height)
        return await naver_map_service.get_static_map(location, options)
    return None


async def search_nearby_places(query: str, address: str, radius: int = 5000) -> List[Location]:
    """특정 주소 주변의 장소 검색"""
    center_location = await get_location_from_address(address)
    if center_location:
        return await naver_map_service.search_places(
            query, center_location.lat, center_location.lng, radius
        )
    return []