"""
안정화된 네이버 지도 클라이언트 테스트
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import json

from src.utils.naver_map_client import (
    StabilizedNaverMapClient, QueryProcessor, ResultMatcher, SearchCache,
    MapLocation, SearchResult, create_naver_map_client
)
from src.utils.exceptions import NaverMapAPIError, RateLimitError, ParseError


@pytest.fixture
def mock_client():
    """모킹된 클라이언트"""
    return StabilizedNaverMapClient("test_id", "test_secret")


@pytest.fixture
def sample_naver_response():
    """샘플 네이버 API 응답"""
    return {
        "lastBuildDate": "Wed, 15 Feb 2023 12:34:56 +0900",
        "total": 2,
        "start": 1,
        "display": 2,
        "items": [
            {
                "title": "<b>스타벅스</b> 강남점",
                "link": "",
                "category": "음식점>카페,디저트>커피전문점",
                "description": "",
                "telephone": "02-1234-5678",
                "address": "서울특별시 강남구 테헤란로 123",
                "roadAddress": "서울특별시 강남구 테헤란로 123",
                "mapx": "1270000000",
                "mapy": "375000000"
            },
            {
                "title": "<b>스타벅스</b> 역삼점",
                "link": "",
                "category": "음식점>카페,디저트>커피전문점",
                "description": "",
                "telephone": "02-9876-5432",
                "address": "서울특별시 강남구 역삼동 456",
                "roadAddress": "서울특별시 강남구 테헤란로 456",
                "mapx": "1270500000",
                "mapy": "375200000"
            }
        ]
    }


class TestQueryProcessor:
    """쿼리 처리기 테스트"""

    def test_normalize_query(self):
        """쿼리 정규화 테스트"""
        # 괄호 제거
        assert QueryProcessor.normalize_query("스타벅스(강남점)") == "스타벅스"

        # 특수문자 제거
        assert QueryProcessor.normalize_query("맥도날드#@$") == "맥도날드"

        # 다중 공백 제거
        assert QueryProcessor.normalize_query("KFC   강남점") == "KFC 강남점"

        # 빈 문자열
        assert QueryProcessor.normalize_query("") == ""
        assert QueryProcessor.normalize_query("   ") == ""

    def test_extract_store_variants(self):
        """상호명 변형 추출 테스트"""
        variants = QueryProcessor.extract_store_variants("스타벅스 강남점")
        assert "스타벅스 강남점" in variants
        assert "스타벅스" in variants

        variants = QueryProcessor.extract_store_variants("맥도날드(강남역점)")
        assert "맥도날드" in variants

    def test_generate_search_queries(self):
        """검색 쿼리 생성 테스트"""
        queries = QueryProcessor.generate_search_queries("스타벅스")
        assert "스타벅스" in queries
        assert "스타벅스 카페" in queries
        assert len(queries) <= 10  # 최대 10개 제한


class TestResultMatcher:
    """결과 매칭 테스트"""

    def test_calculate_similarity(self):
        """유사도 계산 테스트"""
        # 완전 일치
        similarity = ResultMatcher.calculate_similarity("스타벅스", "스타벅스")
        assert similarity == 1.0

        # HTML 태그 제거
        similarity = ResultMatcher.calculate_similarity("스타벅스", "<b>스타벅스</b>")
        assert similarity == 1.0

        # 부분 일치
        similarity = ResultMatcher.calculate_similarity("스타벅스", "스타벅스 강남점")
        assert similarity >= 0.8

        # 유사도 낮음
        similarity = ResultMatcher.calculate_similarity("스타벅스", "맥도날드")
        assert similarity < 0.3

    def test_rank_results(self):
        """결과 랭킹 테스트"""
        locations = [
            MapLocation(lat=37.5, lng=127.0, name="맥도날드"),
            MapLocation(lat=37.5, lng=127.0, name="스타벅스 강남점"),
            MapLocation(lat=37.5, lng=127.0, name="스타벅스")
        ]

        ranked = ResultMatcher.rank_results("스타벅스", locations)

        # 첫 번째가 가장 유사도 높아야 함
        assert ranked[0].name == "스타벅스"
        assert ranked[0].similarity_score >= ranked[1].similarity_score


class TestSearchCache:
    """검색 캐시 테스트"""

    def test_cache_basic_operations(self):
        """캐시 기본 동작 테스트"""
        cache = SearchCache(ttl_seconds=3600, max_size=100)

        # 캐시 미스
        result = cache.get("test_query")
        assert result is None

        # 캐시 설정
        search_result = SearchResult(success=True, locations=[], query_processed="test_query")
        cache.set("test_query", search_result)

        # 캐시 히트
        result = cache.get("test_query")
        assert result is not None
        assert result.cache_hit is True

    def test_cache_normalization(self):
        """캐시 키 정규화 테스트"""
        cache = SearchCache()

        search_result = SearchResult(success=True, locations=[], query_processed="test")

        # 다양한 형태로 저장/조회
        cache.set("Test Query", search_result)

        result = cache.get("test query")
        assert result is not None

        result = cache.get("TEST   QUERY")
        assert result is not None


@pytest.mark.asyncio
class TestStabilizedNaverMapClient:
    """안정화된 네이버 지도 클라이언트 테스트"""

    async def test_search_place_success(self, mock_client, sample_naver_response):
        """검색 성공 테스트"""
        with patch.object(mock_client, '_search_places_api', new_callable=AsyncMock) as mock_api:
            mock_api.return_value = sample_naver_response

            result = await mock_client.search_place("스타벅스")

            assert result.success is True
            assert len(result.locations) > 0
            assert result.locations[0].name == "스타벅스 강남점"
            assert result.cache_hit is False

    async def test_search_place_empty_query(self, mock_client):
        """빈 쿼리 테스트"""
        result = await mock_client.search_place("")

        assert result.success is False
        assert result.error_type == "invalid_input"

    async def test_search_place_cache_hit(self, mock_client, sample_naver_response):
        """캐시 히트 테스트"""
        with patch.object(mock_client, '_search_places_api', new_callable=AsyncMock) as mock_api:
            mock_api.return_value = sample_naver_response

            # 첫 번째 검색
            result1 = await mock_client.search_place("스타벅스")
            assert result1.cache_hit is False

            # 두 번째 검색 (캐시 히트)
            result2 = await mock_client.search_place("스타벅스")
            assert result2.cache_hit is True

            # API는 한 번만 호출되어야 함
            assert mock_api.call_count == 1

    async def test_search_place_no_results(self, mock_client):
        """검색 결과 없음 테스트"""
        empty_response = {
            "total": 0,
            "items": []
        }

        with patch.object(mock_client, '_search_places_api', new_callable=AsyncMock) as mock_api:
            mock_api.return_value = empty_response

            result = await mock_client.search_place("존재하지않는상호명12345")

            assert result.success is False
            assert result.error_type == "no_results"

    async def test_search_place_rate_limit(self, mock_client):
        """레이트 리밋 테스트"""
        with patch.object(mock_client, '_search_places_api', new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = RateLimitError("Rate limit exceeded", "NaverMap")

            result = await mock_client.search_place("스타벅스")

            assert result.success is False
            assert result.error_type == "rate_limit"

    async def test_search_place_api_error(self, mock_client):
        """API 오류 테스트"""
        with patch.object(mock_client, '_search_places_api', new_callable=AsyncMock) as mock_api:
            mock_api.side_effect = NaverMapAPIError("API Error", "test query", 500)

            result = await mock_client.search_place("스타벅스")

            assert result.success is False
            assert result.error_type in ["api_error", "network_error"]

    async def test_search_place_similarity_filtering(self, mock_client):
        """유사도 필터링 테스트"""
        response = {
            "total": 2,
            "items": [
                {
                    "title": "완전히 다른 가게",
                    "address": "서울특별시 강남구 테헤란로 123",
                    "roadAddress": "서울특별시 강남구 테헤란로 123",
                    "mapx": "1270000000",
                    "mapy": "375000000"
                },
                {
                    "title": "스타벅스 강남점",
                    "address": "서울특별시 강남구 테헤란로 456",
                    "roadAddress": "서울특별시 강남구 테헤란로 456",
                    "mapx": "1270500000",
                    "mapy": "375200000"
                }
            ]
        }

        with patch.object(mock_client, '_search_places_api', new_callable=AsyncMock) as mock_api:
            mock_api.return_value = response

            # 높은 유사도 임계값으로 검색
            result = await mock_client.search_place("스타벅스", similarity_threshold=0.5)

            assert result.success is True
            # 유사도 낮은 결과는 필터링됨
            assert len(result.locations) == 1
            assert "스타벅스" in result.locations[0].name

    async def test_parse_search_response_invalid_coordinates(self, mock_client):
        """잘못된 좌표 파싱 테스트"""
        invalid_response = {
            "total": 1,
            "items": [
                {
                    "title": "테스트 가게",
                    "address": "서울특별시 강남구",
                    "mapx": "",  # 빈 좌표
                    "mapy": "invalid"  # 잘못된 좌표
                }
            ]
        }

        locations = mock_client._parse_search_response(invalid_response, "테스트")
        assert len(locations) == 0  # 잘못된 좌표는 무시됨

    async def test_get_search_metrics(self, mock_client):
        """메트릭 조회 테스트"""
        metrics = mock_client.get_search_metrics()

        assert "http_client" in metrics
        assert "cache" in metrics
        assert isinstance(metrics["cache"]["cache_size"], int)


@pytest.mark.integration
@pytest.mark.asyncio
class TestNaverMapIntegration:
    """실제 API와의 통합 테스트 (실제 API 키가 필요)"""

    @pytest.mark.skipif(not __import__('os').environ.get('RUN_INTEGRATION_TESTS'), reason="Integration tests disabled")
    async def test_real_api_search(self):
        """실제 API 검색 테스트"""
        client = create_naver_map_client()

        try:
            # 실제 API 호출
            result = await client.search_place("스타벅스")

            if result.success:
                assert len(result.locations) > 0
                assert result.locations[0].lat != 0
                assert result.locations[0].lng != 0
            else:
                # API 키가 없거나 잘못된 경우
                assert result.error_type in ["api_error", "rate_limit", "no_results"]

        finally:
            await client.close()


# pytest 설정
def pytest_addoption(parser):
    """pytest 옵션 추가"""
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="run integration tests"
    )


def pytest_configure(config):
    """pytest 설정"""
    config.addinivalue_line("markers", "integration: mark test as integration test")


if __name__ == "__main__":
    # 단위 테스트 실행
    pytest.main([__file__, "-v"])