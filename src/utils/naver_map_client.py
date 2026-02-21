"""
안정화된 네이버 지도 API 클라이언트
검색 실패, 파싱 오류, 레이트 리밋 등을 안정적으로 처리
"""

import re
import hashlib
import asyncio
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from difflib import SequenceMatcher
import json

from .http_client import StabilizedHTTPClient, RetryConfig, TimeoutConfig
from .exceptions import (
    NaverMapAPIError, RateLimitError, ParseError, NonRetryableError,
    RetryableError, classify_http_error
)
from .structured_logger import get_logger

logger = get_logger("naver_map")


@dataclass
class MapLocation:
    """지도 위치 정보"""
    lat: float
    lng: float
    address: str = ""
    name: str = ""
    phone: str = ""
    category: str = ""
    road_address: str = ""
    jibun_address: str = ""
    similarity_score: float = 0.0
    search_query: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lat": self.lat,
            "lng": self.lng,
            "address": self.address,
            "name": self.name,
            "phone": self.phone,
            "category": self.category,
            "road_address": self.road_address,
            "jibun_address": self.jibun_address,
            "similarity_score": self.similarity_score,
            "search_query": self.search_query
        }


@dataclass
class SearchResult:
    """검색 결과"""
    success: bool
    locations: List[MapLocation]
    error_type: str = ""
    error_message: str = ""
    cache_hit: bool = False
    query_processed: str = ""
    retry_count: int = 0

    def get_best_match(self) -> Optional[MapLocation]:
        """가장 일치도가 높은 결과 반환"""
        if not self.locations:
            return None
        return max(self.locations, key=lambda x: x.similarity_score)


class QueryProcessor:
    """검색 쿼리 전처리 클래스"""

    # 정규화 패턴들
    NORMALIZATION_PATTERNS = [
        (r'\s*\([^)]*\)\s*', ' '),  # 괄호 내용 제거
        (r'[^\w\s가-힣]', ' '),      # 특수문자 제거 (한글, 영문, 숫자만 유지)
        (r'\s+', ' '),               # 다중 공백을 단일 공백으로
    ]

    # 지점명 패턴들
    BRANCH_PATTERNS = [
        r'(.+?)(?:점|지점|매장|점포)$',
        r'(.+?)\s*(?:본점|분점)$',
        r'(.+?)\s*(?:\d+호점?)$'
    ]

    # 지역명 추출 패턴
    LOCATION_PATTERNS = [
        r'(.+?)\s*(?:구|동|로|길)\s*(\d+(?:-\d+)*번지?)?',
        r'(.+?)\s*(?:시|군|구)\s*(.+)',
        r'(.+?)\s*(?:역|대학교|병원|공원)\s*(?:근처|앞|옆)',
    ]

    @classmethod
    def normalize_query(cls, query: str) -> str:
        """쿼리 정규화"""
        if not query:
            return ""

        normalized = query.strip()

        # 정규화 패턴 적용
        for pattern, replacement in cls.NORMALIZATION_PATTERNS:
            normalized = re.sub(pattern, replacement, normalized)

        return normalized.strip()

    @classmethod
    def extract_store_variants(cls, query: str) -> List[str]:
        """상호명 변형 생성"""
        variants = [query]
        normalized = cls.normalize_query(query)

        if normalized and normalized != query:
            variants.append(normalized)

        # 지점명 제거 버전 + 순수 브랜드명(공백 앞 첫 토큰)도 추출
        for pattern in cls.BRANCH_PATTERNS:
            match = re.match(pattern, normalized)
            if match:
                base_name = match.group(1).strip()
                if base_name and base_name not in variants:
                    variants.append(base_name)
                # "스타벅스 강남" → "스타벅스" 같은 순수 브랜드명도 포함
                if base_name and ' ' in base_name:
                    brand_only = base_name.split()[0].strip()
                    if brand_only and brand_only not in variants:
                        variants.append(brand_only)

        # 지역명과 함께 검색할 변형들
        location_variants = []
        for variant in variants:
            for pattern in cls.LOCATION_PATTERNS:
                match = re.search(pattern, variant)
                if match:
                    location_part = match.group(1).strip()
                    if location_part and location_part not in variants:
                        location_variants.append(location_part)

        variants.extend(location_variants)

        return list(set(variants))  # 중복 제거

    @classmethod
    def generate_search_queries(cls, store_name: str) -> List[str]:
        """검색용 쿼리들 생성"""
        variants = cls.extract_store_variants(store_name)

        # 기본 변형들
        queries = variants[:]

        # 추가 검색 패턴
        for variant in variants:
            # "음식점", "카페", "맛집" 등의 키워드 추가
            if len(variant) > 2:
                queries.extend([
                    f"{variant} 음식점",
                    f"{variant} 카페",
                    f"{variant} 맛집"
                ])

        return queries[:10]  # 최대 10개로 제한


class ResultMatcher:
    """검색 결과 매칭 클래스"""

    @staticmethod
    def calculate_similarity(query: str, result_name: str) -> float:
        """문자열 유사도 계산"""
        if not query or not result_name:
            return 0.0

        # HTML 태그 제거
        clean_result = re.sub(r'<[^>]+>', '', result_name)

        # 정규화
        query_normalized = QueryProcessor.normalize_query(query.lower())
        result_normalized = QueryProcessor.normalize_query(clean_result.lower())

        # 완전 일치
        if query_normalized == result_normalized:
            return 1.0

        # 부분 일치 (쿼리가 결과에 포함)
        if query_normalized in result_normalized:
            return 0.9

        # 시퀀스 매처를 사용한 유사도
        similarity = SequenceMatcher(None, query_normalized, result_normalized).ratio()

        # 공통 단어 수 기반 보정
        query_words = set(query_normalized.split())
        result_words = set(result_normalized.split())
        common_words = query_words.intersection(result_words)

        if common_words:
            word_similarity = len(common_words) / max(len(query_words), len(result_words))
            similarity = max(similarity, word_similarity * 0.8)

        return round(similarity, 3)

    @staticmethod
    def rank_results(query: str, results: List[MapLocation]) -> List[MapLocation]:
        """결과들을 유사도 기준으로 정렬"""
        for result in results:
            result.similarity_score = ResultMatcher.calculate_similarity(query, result.name)
            result.search_query = query

        # 유사도 기준 내림차순 정렬
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        return results


class SearchCache:
    """검색 결과 캐싱"""

    def __init__(self, ttl_seconds: int = 3600, max_size: int = 1000):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self.cache: Dict[str, Tuple[SearchResult, float]] = {}
        self._access_times: Dict[str, float] = {}

    def _generate_cache_key(self, query: str) -> str:
        """캐시 키 생성"""
        normalized = QueryProcessor.normalize_query(query.lower())
        return hashlib.md5(normalized.encode()).hexdigest()

    def _cleanup_expired(self):
        """만료된 캐시 정리"""
        current_time = time.time()
        expired_keys = [
            key for key, (_, timestamp) in self.cache.items()
            if current_time - timestamp > self.ttl_seconds
        ]

        for key in expired_keys:
            del self.cache[key]
            del self._access_times[key]

    def _cleanup_lru(self):
        """LRU 방식으로 캐시 정리"""
        if len(self.cache) <= self.max_size:
            return

        # 가장 오래 사용되지 않은 항목들 제거
        items_to_remove = len(self.cache) - self.max_size + 1
        sorted_keys = sorted(self._access_times.keys(), key=lambda k: self._access_times[k])

        for key in sorted_keys[:items_to_remove]:
            del self.cache[key]
            del self._access_times[key]

    def get(self, query: str) -> Optional[SearchResult]:
        """캐시에서 결과 조회"""
        self._cleanup_expired()

        cache_key = self._generate_cache_key(query)
        if cache_key in self.cache:
            result, _ = self.cache[cache_key]
            self._access_times[cache_key] = time.time()

            # 캐시 히트 표시
            cached_result = SearchResult(
                success=result.success,
                locations=result.locations[:],  # 복사본
                error_type=result.error_type,
                error_message=result.error_message,
                cache_hit=True,
                query_processed=result.query_processed,
                retry_count=result.retry_count
            )
            return cached_result

        return None

    def set(self, query: str, result: SearchResult):
        """캐시에 결과 저장"""
        cache_key = self._generate_cache_key(query)

        # 캐시 히트 플래그 제거
        cached_result = SearchResult(
            success=result.success,
            locations=result.locations[:],  # 복사본
            error_type=result.error_type,
            error_message=result.error_message,
            cache_hit=False,
            query_processed=result.query_processed,
            retry_count=result.retry_count
        )

        self.cache[cache_key] = (cached_result, time.time())
        self._access_times[cache_key] = time.time()

        self._cleanup_lru()

    def clear(self):
        """캐시 전체 삭제"""
        self.cache.clear()
        self._access_times.clear()


class RateLimiter:
    """네이버 API 레이트 리미터"""

    def __init__(self, calls_per_second: float = 5.0):
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self.last_call_time = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self):
        """호출 허가 대기"""
        async with self._lock:
            current_time = time.time()
            elapsed = current_time - self.last_call_time

            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed
                await asyncio.sleep(wait_time)

            self.last_call_time = time.time()


class StabilizedNaverMapClient:
    """안정화된 네이버 지도 API 클라이언트"""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret

        # HTTP 클라이언트 설정
        headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret
        }

        retry_config = RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            max_delay=10.0,
            retryable_status_codes=[429, 500, 502, 503, 504]
        )

        timeout_config = TimeoutConfig(
            connect=5.0,
            read=15.0,
            total=30.0
        )

        self.http_client = StabilizedHTTPClient(
            service_name="NaverMap",
            base_url="https://openapi.naver.com/v1",
            default_headers=headers,
            retry_config=retry_config,
            timeout_config=timeout_config
        )

        # 유틸리티 인스턴스들
        self.query_processor = QueryProcessor()
        self.result_matcher = ResultMatcher()
        self.cache = SearchCache(ttl_seconds=1800, max_size=500)  # 30분 캐시
        self.rate_limiter = RateLimiter(calls_per_second=3.0)  # 초당 3회

    async def close(self):
        """클라이언트 정리"""
        await self.http_client.close()

    async def _search_places_api(self, query: str, display: int = 5) -> Dict[str, Any]:
        """네이버 지역 검색 API 호출"""
        await self.rate_limiter.acquire()

        params = {
            "query": query,
            "display": display,
            "start": 1,
            "sort": "random"
        }

        try:
            with logger.external_call_context("naver_map", "search_places", f"/search/local.json?query={query}"):
                response = await self.http_client.get("/search/local.json", params=params)
                data = response.json()

                logger.info("Naver map search completed",
                          query=query,
                          total_results=data.get('total', 0),
                          displayed_results=len(data.get('items', [])))

                return data

        except Exception as e:
            logger.error("Naver map search failed", error=e, query=query)
            raise

    def _parse_search_response(self, data: Dict[str, Any], original_query: str) -> List[MapLocation]:
        """검색 응답 파싱"""
        locations = []

        try:
            items = data.get('items', [])

            for item in items:
                # 좌표 검증
                mapx = item.get('mapx')
                mapy = item.get('mapy')

                if not mapx or not mapy:
                    logger.warning("Missing coordinates in search result", item_title=item.get('title', ''))
                    continue

                try:
                    lng = float(mapx) / 10000000
                    lat = float(mapy) / 10000000
                except (ValueError, TypeError):
                    logger.warning("Invalid coordinates in search result", mapx=mapx, mapy=mapy)
                    continue

                # HTML 태그 제거
                name = re.sub(r'<[^>]+>', '', item.get('title', ''))
                address = item.get('address', '')
                road_address = item.get('roadAddress', '')
                category = item.get('category', '')
                phone = item.get('telephone', '')

                location = MapLocation(
                    lat=lat,
                    lng=lng,
                    name=name,
                    address=address,
                    road_address=road_address,
                    jibun_address=address,
                    category=category,
                    phone=phone
                )

                locations.append(location)

            return locations

        except Exception as e:
            logger.error("Failed to parse search response", error=e, response_sample=str(data)[:200])
            raise ParseError(f"Failed to parse Naver search response: {str(e)}", "NaverMap", "json")

    async def search_place(self, store_name: str, similarity_threshold: float = 0.3) -> SearchResult:
        """상호명으로 장소 검색 (안정화된 버전)"""
        if not store_name or not store_name.strip():
            return SearchResult(
                success=False,
                locations=[],
                error_type="invalid_input",
                error_message="Store name is empty"
            )

        store_name = store_name.strip()

        # 캐시 확인
        cached_result = self.cache.get(store_name)
        if cached_result:
            logger.info("Cache hit for store search", store_name=store_name)
            return cached_result

        # 검색 쿼리 생성
        search_queries = self.query_processor.generate_search_queries(store_name)
        all_locations = []
        last_error = None
        retry_count = 0

        logger.info("Starting place search",
                   store_name=store_name,
                   search_queries=search_queries[:3])  # 처음 3개만 로그

        # 각 쿼리로 검색 시도
        for query in search_queries:
            try:
                retry_count += 1
                logger.debug("Searching with query", query=query, attempt=retry_count)

                # API 호출
                response_data = await self._search_places_api(query, display=5)

                # 결과 파싱
                locations = self._parse_search_response(response_data, query)

                if locations:
                    # 유사도 계산 및 정렬
                    ranked_locations = self.result_matcher.rank_results(store_name, locations)
                    all_locations.extend(ranked_locations)

                    logger.info("Found locations for query",
                              query=query,
                              location_count=len(locations),
                              best_similarity=ranked_locations[0].similarity_score if ranked_locations else 0)

                    # 높은 유사도를 가진 결과가 있으면 조기 종료
                    if ranked_locations and ranked_locations[0].similarity_score >= 0.8:
                        logger.info("High similarity match found, stopping search")
                        break

            except RateLimitError as e:
                logger.warning("Rate limit hit, waiting before retry", error=str(e))
                await asyncio.sleep(2.0)
                last_error = e
                continue

            except RetryableError as e:
                logger.warning("Retryable error occurred", error=str(e))
                last_error = e
                continue

            except NonRetryableError as e:
                logger.error("Non-retryable error occurred", error=str(e))
                last_error = e
                break

            except Exception as e:
                logger.error("Unexpected error during search", error=e)
                last_error = e
                continue

        # 결과 처리
        if all_locations:
            # 중복 제거 (이름과 좌표 기준)
            unique_locations = []
            seen = set()

            for location in all_locations:
                location_key = (location.name.lower(), round(location.lat, 6), round(location.lng, 6))
                if location_key not in seen:
                    seen.add(location_key)
                    unique_locations.append(location)

            # 유사도 기준으로 다시 정렬
            unique_locations.sort(key=lambda x: x.similarity_score, reverse=True)

            # 임계값 이상인 결과만 필터링
            filtered_locations = [
                loc for loc in unique_locations
                if loc.similarity_score >= similarity_threshold
            ]

            result = SearchResult(
                success=True,
                locations=filtered_locations,
                cache_hit=False,
                query_processed=store_name,
                retry_count=retry_count
            )

            logger.info("Place search completed successfully",
                       store_name=store_name,
                       total_found=len(all_locations),
                       unique_count=len(unique_locations),
                       filtered_count=len(filtered_locations),
                       best_similarity=filtered_locations[0].similarity_score if filtered_locations else 0)

        else:
            # 검색 실패
            error_type = "no_results"
            error_message = "No matching places found"

            if last_error:
                if isinstance(last_error, RateLimitError):
                    error_type = "rate_limit"
                    error_message = "Rate limit exceeded"
                elif isinstance(last_error, NonRetryableError):
                    error_type = "api_error"
                    error_message = str(last_error)
                else:
                    error_type = "network_error"
                    error_message = str(last_error)

            result = SearchResult(
                success=False,
                locations=[],
                error_type=error_type,
                error_message=error_message,
                query_processed=store_name,
                retry_count=retry_count
            )

            logger.warning("Place search failed",
                         store_name=store_name,
                         error_type=error_type,
                         error_message=error_message)

        # 캐시에 저장 (성공/실패 관계없이)
        self.cache.set(store_name, result)

        return result

    def get_search_metrics(self) -> Dict[str, Any]:
        """검색 메트릭 반환"""
        http_metrics = self.http_client.get_metrics_summary()
        cache_stats = {
            "cache_size": len(self.cache.cache),
            "cache_max_size": self.cache.max_size,
            "cache_ttl_seconds": self.cache.ttl_seconds
        }

        return {
            "http_client": http_metrics,
            "cache": cache_stats
        }

    async def validate_api_connection(self) -> bool:
        """API 연결 상태 검증"""
        try:
            await self.search_place("테스트")
            return True
        except Exception as e:
            logger.error("API validation failed", error=e)
            return False


# === 전역 인스턴스 생성 함수 ===

def create_naver_map_client() -> StabilizedNaverMapClient:
    """안정화된 네이버 지도 클라이언트 생성"""
    from src.config.settings import Settings

    return StabilizedNaverMapClient(
        client_id=Settings.NAVER_CLIENT_ID,
        client_secret=Settings.NAVER_CLIENT_SECRET
    )


# === 편의 함수들 ===

async def search_store_location(store_name: str) -> Optional[MapLocation]:
    """상호명으로 위치 검색 (편의 함수)"""
    client = create_naver_map_client()
    try:
        result = await client.search_place(store_name)
        return result.get_best_match()
    finally:
        await client.close()


async def validate_naver_map_api() -> bool:
    """네이버 지도 API 연결 검증"""
    client = create_naver_map_client()
    try:
        return await client.validate_api_connection()
    finally:
        await client.close()