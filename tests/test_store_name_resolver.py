"""
상호명 보정 서비스 테스트
"""

import pytest
from unittest.mock import Mock, AsyncMock
from src.telegram.models.session import TelegramSession, ConversationState, LocationInfo
from src.telegram.services.store_name_resolver import StoreNameResolver, ResolutionStatus, ResolutionResult
from src.telegram.services.place_search import SearchResult, SearchStatus, PlaceCandidate


class TestStoreNameResolver:
    """StoreNameResolver 테스트 클래스"""

    def setup_method(self):
        """각 테스트 전 실행되는 설정"""
        self.mock_provider = Mock()
        self.resolver = StoreNameResolver(provider=self.mock_provider)

    def test_parse_store_name_with_branch(self):
        """지점명이 있는 상호명 파싱 테스트"""
        # 다양한 지점명 패턴 테스트
        test_cases = [
            ("스타벅스 강남점", True, "스타벅스", "강남점"),
            ("맥도날드 홍대입구점", True, "맥도날드", "홍대입구점"),
            ("이마트24 서초대로점", True, "이마트24", "서초대로점"),
            ("롯데시네마 건대입구점", True, "롯데시네마", "건대입구점"),
            ("CU 역삼역점", True, "CU", "역삼역점"),
            ("파리바게뜨 논현동점", True, "파리바게뜨", "논현동점"),
        ]

        for input_text, expected_has_branch, expected_brand, expected_branch in test_cases:
            has_branch, brand, branch = self.resolver.parse_store_name(input_text)
            assert has_branch == expected_has_branch, f"Failed for: {input_text}"
            assert brand == expected_brand, f"Failed brand for: {input_text}"
            assert branch == expected_branch, f"Failed branch for: {input_text}"

    def test_parse_store_name_without_branch(self):
        """지점명이 없는 상호명 파싱 테스트"""
        test_cases = [
            ("스타벅스", False, "스타벅스", ""),
            ("맥도날드", False, "맥도날드", ""),
            ("교촌치킨", False, "교촌치킨", ""),
            ("올리브영", False, "올리브영", ""),
        ]

        for input_text, expected_has_branch, expected_brand, expected_branch in test_cases:
            has_branch, brand, branch = self.resolver.parse_store_name(input_text)
            assert has_branch == expected_has_branch, f"Failed for: {input_text}"
            assert brand == expected_brand, f"Failed brand for: {input_text}"
            assert branch == expected_branch, f"Failed branch for: {input_text}"

    def test_validate_input_format_valid(self):
        """유효한 입력 형식 검증 테스트"""
        valid_inputs = [
            "스타벅스",
            "스타벅스 강남점",
            "맥도날드 홍대입구점",
            "가나다라마바사아자차카타파하",  # 긴 상호명
        ]

        for input_text in valid_inputs:
            is_valid, error_msg = self.resolver.validate_input_format(input_text)
            assert is_valid, f"Should be valid: {input_text}, Error: {error_msg}"
            assert error_msg == "", f"Should have no error: {input_text}"

    def test_validate_input_format_invalid(self):
        """잘못된 입력 형식 검증 테스트"""
        invalid_inputs = [
            ("", "상호명을 입력해주세요."),
            ("   ", "상호명을 입력해주세요."),
            ("a", "상호명은 2글자 이상 입력해주세요."),
            ("1234567", "상호명은 '브랜드명' 또는 '브랜드명 지점명' 형태로 입력해주세요."),
            ("!@#$%^&*()", "상호명은 '브랜드명' 또는 '브랜드명 지점명' 형태로 입력해주세요."),
            ("a" * 101, "상호명이 너무 깁니다. 100글자 이하로 입력해주세요."),
        ]

        for input_text, expected_error in invalid_inputs:
            is_valid, error_msg = self.resolver.validate_input_format(input_text)
            assert not is_valid, f"Should be invalid: {input_text}"
            assert expected_error in error_msg, f"Unexpected error for {input_text}: {error_msg}"

    @pytest.mark.asyncio
    async def test_resolve_with_branch_success(self):
        """지점명이 있는 상호명 보정 성공 테스트"""
        # Mock 설정
        candidate = PlaceCandidate(
            name="스타벅스 강남역점",
            address="서울시 강남구 강남대로 123",
            lat=37.5,
            lng=127.0,
            similarity_score=0.9,
            distance=50.0
        )

        self.mock_provider.search_by_name = AsyncMock(return_value=SearchResult(
            status=SearchStatus.SUCCESS,
            candidates=[candidate],
            query="스타벅스 강남점"
        ))

        # 세션 생성
        session = TelegramSession(
            user_id=12345,
            raw_store_name="스타벅스 강남점",
            location=LocationInfo(lat=37.5, lng=127.0, source="telegram_location")
        )

        # 테스트 실행
        result = await self.resolver.resolve_store_name(session)

        # 검증
        assert result.status == ResolutionStatus.SUCCESS
        assert result.resolved_name == "스타벅스 강남역점"
        assert result.confidence >= 0.8
        assert not result.fallback_used
        assert result.candidate == candidate

    @pytest.mark.asyncio
    async def test_resolve_with_branch_not_found_fallback(self):
        """지점명이 있지만 검색 실패 시 nearest fallback 테스트"""
        # Mock 설정: 정확한 검색 실패
        self.mock_provider.search_by_name = AsyncMock(return_value=SearchResult(
            status=SearchStatus.NOT_FOUND,
            candidates=[],
            query="스타벅스 잘못된점"
        ))

        # Mock 설정: nearest 검색 성공
        nearest_candidate = PlaceCandidate(
            name="스타벅스 강남역점",
            address="서울시 강남구 강남대로 123",
            lat=37.5,
            lng=127.0,
            distance=100.0
        )

        self.mock_provider.search_nearest = AsyncMock(return_value=SearchResult(
            status=SearchStatus.SUCCESS,
            candidates=[nearest_candidate],
            query="스타벅스"
        ))

        # 세션 생성
        session = TelegramSession(
            user_id=12345,
            raw_store_name="스타벅스 잘못된점",
            location=LocationInfo(lat=37.5, lng=127.0, source="telegram_location")
        )

        # 테스트 실행
        result = await self.resolver.resolve_store_name(session)

        # 검증
        assert result.status == ResolutionStatus.SUCCESS
        assert result.resolved_name == "스타벅스 강남역점"
        assert result.fallback_used
        assert result.candidate == nearest_candidate

    @pytest.mark.asyncio
    async def test_resolve_without_branch_success(self):
        """지점명이 없는 상호명 보정 성공 테스트"""
        # Mock 설정
        candidate = PlaceCandidate(
            name="스타벅스 강남역점",
            address="서울시 강남구 강남대로 123",
            lat=37.5,
            lng=127.0,
            distance=50.0
        )

        self.mock_provider.search_nearest = AsyncMock(return_value=SearchResult(
            status=SearchStatus.SUCCESS,
            candidates=[candidate],
            query="스타벅스"
        ))

        # 세션 생성
        session = TelegramSession(
            user_id=12345,
            raw_store_name="스타벅스",
            location=LocationInfo(lat=37.5, lng=127.0, source="telegram_location")
        )

        # 테스트 실행
        result = await self.resolver.resolve_store_name(session)

        # 검증
        assert result.status == ResolutionStatus.SUCCESS
        assert result.resolved_name == "스타벅스 강남역점"
        assert result.fallback_used
        assert result.candidate == candidate

    @pytest.mark.asyncio
    async def test_resolve_without_location(self):
        """위치 정보 없는 경우 테스트"""
        # 세션 생성 (위치 정보 없음)
        session = TelegramSession(
            user_id=12345,
            raw_store_name="스타벅스",
            location=None
        )

        # 테스트 실행
        result = await self.resolver.resolve_store_name(session)

        # 검증
        assert result.status == ResolutionStatus.NEEDS_LOCATION
        assert "위치" in result.error_message

    @pytest.mark.asyncio
    async def test_resolve_invalid_format(self):
        """잘못된 형식 입력 테스트"""
        # 세션 생성
        session = TelegramSession(
            user_id=12345,
            raw_store_name="a",  # 너무 짧은 입력
            location=LocationInfo(lat=37.5, lng=127.0, source="telegram_location")
        )

        # 테스트 실행
        result = await self.resolver.resolve_store_name(session)

        # 검증
        assert result.status == ResolutionStatus.INVALID_FORMAT
        assert "2글자 이상" in result.error_message

    @pytest.mark.asyncio
    async def test_resolve_too_far_distance(self):
        """거리 너무 먼 결과 테스트"""
        # Mock 설정: 거리 너무 먼 결과
        far_candidate = PlaceCandidate(
            name="스타벅스 멀리있는점",
            address="서울시 멀리구 멀리로 123",
            lat=37.6,
            lng=127.1,
            distance=5000.0  # 5km (임계값 2km 초과)
        )

        self.mock_provider.search_nearest = AsyncMock(return_value=SearchResult(
            status=SearchStatus.SUCCESS,
            candidates=[far_candidate],
            query="스타벅스"
        ))

        # 세션 생성
        session = TelegramSession(
            user_id=12345,
            raw_store_name="스타벅스",
            location=LocationInfo(lat=37.5, lng=127.0, source="telegram_location")
        )

        # 테스트 실행
        result = await self.resolver.resolve_store_name(session)

        # 검증
        assert result.status == ResolutionStatus.NOT_FOUND
        assert "가까운" in result.error_message and "찾을 수 없습니다" in result.error_message

    def test_get_user_confirmation_message(self):
        """사용자 확인 메시지 생성 테스트"""
        candidate = PlaceCandidate(
            name="스타벅스 강남역점",
            address="서울시 강남구 강남대로 123",
            lat=37.5,
            lng=127.0,
            distance=100.0
        )

        # 높은 신뢰도 테스트
        result = ResolutionResult(
            status=ResolutionStatus.SUCCESS,
            resolved_name="스타벅스 강남역점",
            confidence=0.9,
            fallback_used=False,
            candidate=candidate
        )

        message = self.resolver.get_user_confirmation_message(result)
        assert "🏪 상호명: 스타벅스 강남역점 (확실)" in message
        assert "📍 주소: 서울시 강남구 강남대로 123" in message
        assert "📏 거리: 100m" in message

        # Fallback 사용 테스트
        result.fallback_used = True
        result.confidence = 0.7

        message = self.resolver.get_user_confirmation_message(result)
        assert "(추정)" in message
        assert "💡 위치를 기반으로" in message


class TestPlaceSearchProvider:
    """PlaceSearchProvider 테스트 클래스 (기본 기능)"""

    def setup_method(self):
        """테스트 설정"""
        from src.telegram.services.place_search import PlaceSearchProvider
        from src.telegram.models.session import LocationInfo

        # abstract 메서드를 구현한 테스트용 구체 클래스
        class ConcreteProvider(PlaceSearchProvider):
            async def search_by_name(self, query, location=None):
                return None
            async def search_nearest(self, keyword, location):
                return None

        self.provider = ConcreteProvider()

    def test_calculate_similarity(self):
        """유사도 계산 테스트"""
        test_cases = [
            ("스타벅스", "스타벅스", 1.0),  # 정확히 일치
            ("스타벅스", "스타벅스 강남점", 0.8),  # 포함
            ("스타벅스 강남점", "스타벅스", 0.7),  # 검색어가 더 긴 경우
            ("스타벅스", "맥도날드", 0.0),  # 완전히 다름
        ]

        for query, candidate, expected_min in test_cases:
            similarity = self.provider.calculate_similarity(query, candidate)
            if expected_min == 1.0:
                assert similarity == expected_min, f"Expected exact match: {query} vs {candidate}"
            elif expected_min > 0.5:
                assert similarity >= expected_min, f"Expected high similarity: {query} vs {candidate}, got {similarity}"
            else:
                assert similarity <= 0.3, f"Expected low similarity: {query} vs {candidate}, got {similarity}"

    def test_calculate_distance(self):
        """거리 계산 테스트"""
        from src.telegram.models.session import LocationInfo

        # 서울시청과 강남역 대략적인 좌표
        seoul_city_hall = LocationInfo(lat=37.566536, lng=126.977966, source="test")
        gangnam_station = (37.498095, 127.027636)

        distance = self.provider.calculate_distance(seoul_city_hall, gangnam_station[0], gangnam_station[1])

        # 대략 7-8km 정도 될 것으로 예상
        assert 6000 <= distance <= 9000, f"Expected distance ~7-8km, got {distance/1000:.1f}km"

        # 같은 위치
        distance_same = self.provider.calculate_distance(seoul_city_hall, 37.566536, 126.977966)
        assert distance_same < 1, f"Expected near 0 distance, got {distance_same}m"