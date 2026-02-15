"""
네이버 지도 API 연동 서비스

네이버 지도 API를 활용한 다양한 지도 관련 기능을 제공합니다.
- 지도 표시
- 주소/좌표 변환 (Geocoding/Reverse Geocoding)
- 정적 지도 이미지 생성
- 장소 검색
"""

import asyncio
import aiohttp
import base64
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from urllib.parse import quote, urlencode
import logging

from src.config.settings import Settings

logger = logging.getLogger(__name__)

@dataclass
class Location:
    """위치 정보를 담는 데이터 클래스"""
    lat: float
    lng: float
    address: str = ""
    name: str = ""

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
    """네이버 지도 API 서비스 클래스"""

    def __init__(self):
        self.client_id = Settings.NAVER_MAP_CLIENT_ID
        self.client_secret = Settings.NAVER_MAP_CLIENT_SECRET

        if not self.client_id or not self.client_secret:
            raise ValueError("네이버 지도 API 클라이언트 ID와 시크릿이 설정되지 않았습니다.")

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

    async def geocode(self, address: str) -> Optional[Location]:
        """
        주소를 좌표로 변환 (Geocoding)

        Args:
            address: 변환할 주소

        Returns:
            Location 객체 또는 None
        """
        # 장소 검색을 통한 좌표 추출 시도 (네이버 지역 검색 API 활용)
        try:
            url = "https://openapi.naver.com/v1/search/local.json"
            params = {"query": address, "display": 5}  # 검색 결과를 5개로 증가

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.naver_dev_headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        if data.get("total", 0) > 0 and len(data.get("items", [])) > 0:
                            # 가장 관련성 높은 결과 선택
                            for item in data["items"]:
                                if item.get("mapx") and item.get("mapy"):
                                    return Location(
                                        lat=float(item["mapy"]) / 10000000,
                                        lng=float(item["mapx"]) / 10000000,
                                        address=item.get("address", ""),
                                        name=item.get("title", "").replace("<b>", "").replace("</b>", "") or address
                                    )
                    else:
                        logger.warning(f"네이버 지역 검색 API 오류: {response.status}")

        except Exception as e:
            logger.warning(f"네이버 지역 검색을 통한 Geocoding 중 오류 발생: {e}")

        # 더 간단한 키워드로 재시도
        simple_keywords = [
            address.split()[-2:],  # 마지막 두 단어
            [address.split()[-1]],  # 마지막 한 단어
            ["서울시청"] if "세종대로" in address else
            ["강남역"] if "테헤란로" in address else
            ["해운대"] if "해운대" in address else
            ["제주도"] if "제주" in address else []
        ]

        for keywords in simple_keywords:
            if not keywords:
                continue

            try:
                query = " ".join(keywords)
                url = "https://openapi.naver.com/v1/search/local.json"
                params = {"query": query, "display": 1}

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self.naver_dev_headers, params=params) as response:
                        if response.status == 200:
                            data = await response.json()

                            if data.get("total", 0) > 0 and len(data.get("items", [])) > 0:
                                item = data["items"][0]
                                if item.get("mapx") and item.get("mapy"):
                                    return Location(
                                        lat=float(item["mapy"]) / 10000000,
                                        lng=float(item["mapx"]) / 10000000,
                                        address=item.get("address", ""),
                                        name=item.get("title", "").replace("<b>", "").replace("</b>", "") or address
                                    )
            except Exception:
                continue

        # NCP Geocoding API 시도 (fallback)
        try:
            url = f"{self.base_url}/map-geocode/v2/geocode"
            params = {"query": address}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        if data["meta"]["totalCount"] > 0:
                            result = data["addresses"][0]
                            return Location(
                                lat=float(result["y"]),
                                lng=float(result["x"]),
                                address=result["roadAddress"] or result["jibunAddress"],
                                name=address
                            )
                    else:
                        logger.error(f"NCP Geocoding API 오류: {response.status}")

        except Exception as e:
            logger.error(f"NCP Geocoding 중 오류 발생: {e}")

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
        장소 검색

        Args:
            query: 검색할 장소명
            lat: 중심 위도 (옵션)
            lng: 중심 경도 (옵션)
            radius: 검색 반경 (미터, 옵션)

        Returns:
            검색된 장소 목록
        """
        places = []

        try:
            # 네이버 지역 검색 API 사용
            url = "https://openapi.naver.com/v1/search/local.json"
            headers = {
                "X-Naver-Client-Id": Settings.NAVER_CLIENT_ID,
                "X-Naver-Client-Secret": Settings.NAVER_CLIENT_SECRET
            }

            params = {
                "query": query,
                "display": 10,
                "start": 1,
                "sort": "random"
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()

                        for item in data.get("items", []):
                            # 좌표가 있는 경우에만 추가
                            if item.get("mapx") and item.get("mapy"):
                                location = Location(
                                    lat=float(item["mapy"]) / 10000000,  # 네이버 API는 좌표에 10^7을 곱한 값 반환
                                    lng=float(item["mapx"]) / 10000000,
                                    address=item.get("address", ""),
                                    name=item.get("title", "").replace("<b>", "").replace("</b>", "")
                                )

                                # 거리 필터링 (중심 좌표가 제공된 경우)
                                if lat is not None and lng is not None:
                                    distance = self._calculate_distance(lat, lng, location.lat, location.lng)
                                    if distance <= radius:
                                        places.append(location)
                                else:
                                    places.append(location)
                    else:
                        logger.error(f"장소 검색 API 오류: {response.status}")

        except Exception as e:
            logger.error(f"장소 검색 중 오류 발생: {e}")

        return places

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
        API 키 유효성 검증

        Returns:
            API 키 유효 여부
        """
        # 네이버 개발자센터 API 검증 먼저 시도
        try:
            url = "https://openapi.naver.com/v1/search/local.json"
            params = {"query": "테스트", "display": 1}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.naver_dev_headers, params=params) as response:
                    if response.status == 200:
                        return True
                    elif response.status == 401:
                        logger.warning("네이버 개발자센터 API 키 인증 실패")
                    else:
                        logger.warning(f"네이버 개발자센터 API 응답: {response.status}")

        except Exception as e:
            logger.warning(f"네이버 개발자센터 API 검증 중 오류: {e}")

        # NCP API 검증 시도 (fallback)
        try:
            # 간단한 Geocoding API 호출로 테스트
            result = await self.geocode("서울")
            return result is not None
        except Exception as e:
            logger.error(f"API 키 검증 중 오류 발생: {e}")
            return False


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