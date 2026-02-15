"""
장소 검색 Provider 추상화 및 구현체
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any
import logging
import requests
import urllib.parse
from enum import Enum

from src.config.settings import Settings
from ..models.session import LocationInfo


class SearchStatus(Enum):
    """검색 결과 상태"""
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    API_ERROR = "api_error"
    NETWORK_ERROR = "network_error"


@dataclass
class PlaceCandidate:
    """장소 검색 결과 후보"""
    name: str
    address: str
    lat: float
    lng: float
    distance: Optional[float] = None  # 검색 위치로부터의 거리 (미터)
    similarity_score: Optional[float] = None  # 검색어와의 유사도 (0.0-1.0)
    phone: Optional[str] = None
    category: Optional[str] = None
    road_address: Optional[str] = None


@dataclass
class SearchResult:
    """검색 결과"""
    status: SearchStatus
    candidates: List[PlaceCandidate]
    query: str
    error_message: Optional[str] = None
    api_response: Optional[Dict[str, Any]] = None  # 디버깅용


class PlaceSearchProvider(ABC):
    """장소 검색 Provider 추상 클래스"""

    @abstractmethod
    async def search_by_name(self, query: str, location: Optional[LocationInfo] = None) -> SearchResult:
        """
        상호명으로 장소 검색

        Args:
            query: 검색할 상호명
            location: 검색 중심 좌표 (선택적)

        Returns:
            SearchResult: 검색 결과
        """
        pass

    @abstractmethod
    async def search_nearest(self, keyword: str, location: LocationInfo) -> SearchResult:
        """
        위치 기반 가장 가까운 지점 검색

        Args:
            keyword: 검색 키워드 (예: "스타벅스")
            location: 검색 중심 좌표

        Returns:
            SearchResult: 검색 결과
        """
        pass

    def calculate_similarity(self, query: str, candidate_name: str) -> float:
        """
        검색어와 후보 이름의 유사도 계산

        Args:
            query: 검색어
            candidate_name: 후보 이름

        Returns:
            float: 유사도 (0.0-1.0)
        """
        from difflib import SequenceMatcher

        # 정규화: 공백 제거, 소문자 변환
        normalized_query = query.strip().lower().replace(" ", "")
        normalized_candidate = candidate_name.strip().lower().replace(" ", "")

        # 정확히 일치하는 경우
        if normalized_query == normalized_candidate:
            return 1.0

        # 후보 이름이 검색어를 포함하는 경우
        if normalized_query in normalized_candidate:
            return 0.8 + (len(normalized_query) / len(normalized_candidate)) * 0.2

        # 검색어가 후보 이름을 포함하는 경우
        if normalized_candidate in normalized_query:
            return 0.7

        # Sequence Matcher를 사용한 유사도 계산
        return SequenceMatcher(None, normalized_query, normalized_candidate).ratio()

    def calculate_distance(self, location1: LocationInfo, lat2: float, lng2: float) -> float:
        """
        두 위치 간의 거리를 계산 (미터 단위)

        Args:
            location1: 기준 위치
            lat2: 대상 위치 위도
            lng2: 대상 위치 경도

        Returns:
            float: 거리 (미터)
        """
        import math

        # Haversine 공식
        R = 6371000  # 지구 반지름 (미터)

        lat1_rad = math.radians(location1.lat)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - location1.lat)
        delta_lng = math.radians(lng2 - location1.lng)

        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

        return R * c


class NaverLocalSearchProvider(PlaceSearchProvider):
    """네이버 지역검색 API Provider"""

    def __init__(self):
        self.client_id = Settings.NAVER_CLIENT_ID
        self.client_secret = Settings.NAVER_CLIENT_SECRET
        self.logger = logging.getLogger(__name__)

        if not self.client_id or not self.client_secret:
            self.logger.warning("NAVER_CLIENT_ID or NAVER_CLIENT_SECRET not found in settings")

    async def search_by_name(self, query: str, location: Optional[LocationInfo] = None) -> SearchResult:
        """네이버 지역검색 API로 상호명 검색"""
        if not self.client_id or not self.client_secret:
            return SearchResult(
                status=SearchStatus.API_ERROR,
                candidates=[],
                query=query,
                error_message="Naver API credentials not configured"
            )

        try:
            url = "https://openapi.naver.com/v1/search/local.json"
            headers = {
                "X-Naver-Client-Id": self.client_id,
                "X-Naver-Client-Secret": self.client_secret
            }

            params = {
                "query": query,
                "display": 5,  # 최대 5개 결과
                "start": 1,
                "sort": "comment" if not location else "distance"  # 위치가 있으면 거리순, 없으면 평점순
            }

            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            candidates = []

            for item in data.get("items", []):
                try:
                    # 네이버 API 응답에서 필요한 정보 추출
                    lat = float(item.get("mapy", 0)) / 10000000  # 네이버는 10^7 배수로 제공
                    lng = float(item.get("mapx", 0)) / 10000000

                    if lat == 0 or lng == 0:
                        continue

                    candidate = PlaceCandidate(
                        name=item.get("title", "").replace("<b>", "").replace("</b>", ""),
                        address=item.get("address", ""),
                        lat=lat,
                        lng=lng,
                        road_address=item.get("roadAddress", ""),
                        phone=item.get("telephone", ""),
                        category=item.get("category", "")
                    )

                    # 유사도 계산
                    candidate.similarity_score = self.calculate_similarity(query, candidate.name)

                    # 거리 계산 (위치가 있는 경우)
                    if location:
                        candidate.distance = self.calculate_distance(location, lat, lng)

                    candidates.append(candidate)

                except (ValueError, KeyError) as e:
                    self.logger.warning(f"Failed to parse candidate: {e}")
                    continue

            # 정렬: 유사도 높은 순, 거리 가까운 순
            if location:
                candidates.sort(key=lambda x: (-x.similarity_score, x.distance))
            else:
                candidates.sort(key=lambda x: -x.similarity_score)

            status = SearchStatus.SUCCESS if candidates else SearchStatus.NOT_FOUND

            return SearchResult(
                status=status,
                candidates=candidates,
                query=query,
                api_response=data
            )

        except requests.exceptions.Timeout:
            return SearchResult(
                status=SearchStatus.NETWORK_ERROR,
                candidates=[],
                query=query,
                error_message="Request timeout"
            )
        except requests.exceptions.RequestException as e:
            return SearchResult(
                status=SearchStatus.NETWORK_ERROR,
                candidates=[],
                query=query,
                error_message=f"Network error: {str(e)}"
            )
        except Exception as e:
            self.logger.error(f"Unexpected error in search_by_name: {e}")
            return SearchResult(
                status=SearchStatus.API_ERROR,
                candidates=[],
                query=query,
                error_message=f"Unexpected error: {str(e)}"
            )

    async def search_nearest(self, keyword: str, location: LocationInfo) -> SearchResult:
        """위치 기반 가장 가까운 지점 검색"""
        if not self.client_id or not self.client_secret:
            return SearchResult(
                status=SearchStatus.API_ERROR,
                candidates=[],
                query=keyword,
                error_message="Naver API credentials not configured"
            )

        try:
            url = "https://openapi.naver.com/v1/search/local.json"
            headers = {
                "X-Naver-Client-Id": self.client_id,
                "X-Naver-Client-Secret": self.client_secret
            }

            params = {
                "query": keyword,
                "display": 10,  # 더 많은 결과 중에서 가장 가까운 것 선택
                "start": 1,
                "sort": "distance"
            }

            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            candidates = []

            for item in data.get("items", []):
                try:
                    lat = float(item.get("mapy", 0)) / 10000000
                    lng = float(item.get("mapx", 0)) / 10000000

                    if lat == 0 or lng == 0:
                        continue

                    candidate = PlaceCandidate(
                        name=item.get("title", "").replace("<b>", "").replace("</b>", ""),
                        address=item.get("address", ""),
                        lat=lat,
                        lng=lng,
                        road_address=item.get("roadAddress", ""),
                        phone=item.get("telephone", ""),
                        category=item.get("category", "")
                    )

                    # 거리 계산
                    candidate.distance = self.calculate_distance(location, lat, lng)

                    # 유사도 계산
                    candidate.similarity_score = self.calculate_similarity(keyword, candidate.name)

                    candidates.append(candidate)

                except (ValueError, KeyError) as e:
                    self.logger.warning(f"Failed to parse candidate: {e}")
                    continue

            # 거리순으로 정렬
            candidates.sort(key=lambda x: x.distance)

            status = SearchStatus.SUCCESS if candidates else SearchStatus.NOT_FOUND

            return SearchResult(
                status=status,
                candidates=candidates,
                query=keyword,
                api_response=data
            )

        except requests.exceptions.Timeout:
            return SearchResult(
                status=SearchStatus.NETWORK_ERROR,
                candidates=[],
                query=keyword,
                error_message="Request timeout"
            )
        except requests.exceptions.RequestException as e:
            return SearchResult(
                status=SearchStatus.NETWORK_ERROR,
                candidates=[],
                query=keyword,
                error_message=f"Network error: {str(e)}"
            )
        except Exception as e:
            self.logger.error(f"Unexpected error in search_nearest: {e}")
            return SearchResult(
                status=SearchStatus.API_ERROR,
                candidates=[],
                query=keyword,
                error_message=f"Unexpected error: {str(e)}"
            )


class KakaoLocalSearchProvider(PlaceSearchProvider):
    """카카오 로컬 API Provider"""

    def __init__(self):
        self.rest_api_key = Settings.KAKAO_REST_API_KEY
        self.logger = logging.getLogger(__name__)

        if not self.rest_api_key:
            self.logger.warning("KAKAO_REST_API_KEY not found in settings")

    async def search_by_name(self, query: str, location: Optional[LocationInfo] = None) -> SearchResult:
        """카카오 로컬 API로 상호명 검색"""
        if not self.rest_api_key:
            return SearchResult(
                status=SearchStatus.API_ERROR,
                candidates=[],
                query=query,
                error_message="Kakao API credentials not configured"
            )

        try:
            url = "https://dapi.kakao.com/v2/local/search/keyword.json"
            headers = {"Authorization": f"KakaoAK {self.rest_api_key}"}

            params = {
                "query": query,
                "size": 5,
                "page": 1
            }

            # 위치가 있는 경우 중심 좌표 설정
            if location:
                params["x"] = str(location.lng)
                params["y"] = str(location.lat)
                params["radius"] = 10000  # 10km 반경

            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            candidates = []

            for item in data.get("documents", []):
                try:
                    lat = float(item.get("y", 0))
                    lng = float(item.get("x", 0))

                    if lat == 0 or lng == 0:
                        continue

                    candidate = PlaceCandidate(
                        name=item.get("place_name", ""),
                        address=item.get("address_name", ""),
                        lat=lat,
                        lng=lng,
                        road_address=item.get("road_address_name", ""),
                        phone=item.get("phone", ""),
                        category=item.get("category_name", "")
                    )

                    # 유사도 계산
                    candidate.similarity_score = self.calculate_similarity(query, candidate.name)

                    # 거리 계산 (위치가 있는 경우)
                    if location:
                        candidate.distance = self.calculate_distance(location, lat, lng)

                    candidates.append(candidate)

                except (ValueError, KeyError) as e:
                    self.logger.warning(f"Failed to parse candidate: {e}")
                    continue

            # 정렬: 유사도 높은 순, 거리 가까운 순
            if location:
                candidates.sort(key=lambda x: (-x.similarity_score, x.distance))
            else:
                candidates.sort(key=lambda x: -x.similarity_score)

            status = SearchStatus.SUCCESS if candidates else SearchStatus.NOT_FOUND

            return SearchResult(
                status=status,
                candidates=candidates,
                query=query,
                api_response=data
            )

        except requests.exceptions.Timeout:
            return SearchResult(
                status=SearchStatus.NETWORK_ERROR,
                candidates=[],
                query=query,
                error_message="Request timeout"
            )
        except requests.exceptions.RequestException as e:
            return SearchResult(
                status=SearchStatus.NETWORK_ERROR,
                candidates=[],
                query=query,
                error_message=f"Network error: {str(e)}"
            )
        except Exception as e:
            self.logger.error(f"Unexpected error in search_by_name: {e}")
            return SearchResult(
                status=SearchStatus.API_ERROR,
                candidates=[],
                query=query,
                error_message=f"Unexpected error: {str(e)}"
            )

    async def search_nearest(self, keyword: str, location: LocationInfo) -> SearchResult:
        """위치 기반 가장 가까운 지점 검색"""
        if not self.rest_api_key:
            return SearchResult(
                status=SearchStatus.API_ERROR,
                candidates=[],
                query=keyword,
                error_message="Kakao API credentials not configured"
            )

        try:
            url = "https://dapi.kakao.com/v2/local/search/keyword.json"
            headers = {"Authorization": f"KakaoAK {self.rest_api_key}"}

            params = {
                "query": keyword,
                "size": 15,  # 더 많은 결과 중에서 가장 가까운 것 선택
                "page": 1,
                "x": str(location.lng),
                "y": str(location.lat),
                "radius": 5000,  # 5km 반경
                "sort": "distance"
            }

            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            candidates = []

            for item in data.get("documents", []):
                try:
                    lat = float(item.get("y", 0))
                    lng = float(item.get("x", 0))

                    if lat == 0 or lng == 0:
                        continue

                    candidate = PlaceCandidate(
                        name=item.get("place_name", ""),
                        address=item.get("address_name", ""),
                        lat=lat,
                        lng=lng,
                        road_address=item.get("road_address_name", ""),
                        phone=item.get("phone", ""),
                        category=item.get("category_name", "")
                    )

                    # 거리 계산
                    candidate.distance = self.calculate_distance(location, lat, lng)

                    # 유사도 계산
                    candidate.similarity_score = self.calculate_similarity(keyword, candidate.name)

                    candidates.append(candidate)

                except (ValueError, KeyError) as e:
                    self.logger.warning(f"Failed to parse candidate: {e}")
                    continue

            # 거리순으로 정렬
            candidates.sort(key=lambda x: x.distance)

            status = SearchStatus.SUCCESS if candidates else SearchStatus.NOT_FOUND

            return SearchResult(
                status=status,
                candidates=candidates,
                query=keyword,
                api_response=data
            )

        except requests.exceptions.Timeout:
            return SearchResult(
                status=SearchStatus.NETWORK_ERROR,
                candidates=[],
                query=keyword,
                error_message="Request timeout"
            )
        except requests.exceptions.RequestException as e:
            return SearchResult(
                status=SearchStatus.NETWORK_ERROR,
                candidates=[],
                query=keyword,
                error_message=f"Network error: {str(e)}"
            )
        except Exception as e:
            self.logger.error(f"Unexpected error in search_nearest: {e}")
            return SearchResult(
                status=SearchStatus.API_ERROR,
                candidates=[],
                query=keyword,
                error_message=f"Unexpected error: {str(e)}"
            )


def get_place_search_provider() -> PlaceSearchProvider:
    """
    환경변수 설정에 따라 적절한 Provider 반환

    Returns:
        PlaceSearchProvider: 설정된 Provider 인스턴스
    """
    provider_type = getattr(Settings, 'PLACE_SEARCH_PROVIDER', 'naver').lower()

    if provider_type == 'kakao':
        return KakaoLocalSearchProvider()
    else:
        return NaverLocalSearchProvider()  # 기본값