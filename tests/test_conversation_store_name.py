"""
텔레그램 대화 핸들러의 상호명 입력 처리 테스트
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from src.telegram.handlers.conversation import ConversationHandler
from src.telegram.models.session import TelegramSession, ConversationState, LocationInfo
from src.telegram.services.store_name_resolver import ResolutionStatus, ResolutionResult


class TestConversationStoreNameHandling:
    """대화 핸들러 상호명 처리 테스트"""

    def setup_method(self):
        """테스트 설정"""
        mock_bot = Mock()
        self.handler = ConversationHandler(mock_bot)

    @pytest.mark.asyncio
    @patch('src.telegram.handlers.conversation.get_store_name_resolver')
    async def test_handle_store_name_input_success(self, mock_resolver_factory):
        """상호명 입력 성공 처리 테스트"""
        # Mock resolver 설정
        mock_resolver = Mock()
        mock_resolver.resolve_store_name = AsyncMock(return_value=ResolutionResult(
            status=ResolutionStatus.SUCCESS,
            resolved_name="스타벅스 강남역점",
            confidence=0.9
        ))
        mock_resolver.get_user_confirmation_message = Mock(return_value="✅ 상호명: 스타벅스 강남역점 (확실)")
        mock_resolver_factory.return_value = mock_resolver

        # Mock update와 session
        mock_update = Mock()
        mock_update.message.text = "스타벅스 강남점"
        mock_update.message.location = None
        mock_update.message.reply_text = AsyncMock()

        session = TelegramSession(
            user_id=12345,
            state=ConversationState.WAITING_STORE_NAME,
            location=LocationInfo(lat=37.5, lng=127.0, source="telegram_location")
        )

        # 테스트 실행
        await self.handler._handle_store_name_input(mock_update, session, "스타벅스 강남점")

        # 검증
        assert session.raw_store_name == "스타벅스 강남점"
        assert session.resolved_store_name == "스타벅스 강남역점"
        assert session.state == ConversationState.WAITING_IMAGES

        # 메시지가 전송되었는지 확인
        assert mock_update.message.reply_text.call_count >= 3  # 확인 중, 확인, 다음 단계

    @pytest.mark.asyncio
    @patch('src.telegram.handlers.conversation.get_store_name_resolver')
    async def test_handle_store_name_input_needs_location(self, mock_resolver_factory):
        """위치 정보 필요한 경우 처리 테스트"""
        # Mock resolver 설정
        mock_resolver = Mock()
        mock_resolver.resolve_store_name = AsyncMock(return_value=ResolutionResult(
            status=ResolutionStatus.NEEDS_LOCATION,
            error_message="위치 정보를 공유해주세요"
        ))
        mock_resolver_factory.return_value = mock_resolver

        # Mock update와 session
        mock_update = Mock()
        mock_update.message.text = "스타벅스"
        mock_update.message.location = None
        mock_update.message.reply_text = AsyncMock()

        session = TelegramSession(
            user_id=12345,
            state=ConversationState.WAITING_STORE_NAME,
            location=None  # 위치 정보 없음
        )

        # _request_location 메서드 Mock
        with patch.object(self.handler, '_request_location') as mock_request_location:
            mock_request_location = AsyncMock()

            # 테스트 실행
            await self.handler._handle_store_name_input(mock_update, session, "스타벅스")

            # 검증
            assert session.raw_store_name == "스타벅스"
            assert session.resolved_store_name is None
            assert session.state == ConversationState.WAITING_STORE_NAME  # 상태 유지

    @pytest.mark.asyncio
    async def test_handle_store_name_input_cancel(self):
        """상호명 입력 취소 처리 테스트"""
        mock_update = Mock()
        mock_update.message.reply_text = AsyncMock()

        session = TelegramSession(
            user_id=12345,
            state=ConversationState.WAITING_STORE_NAME
        )

        # 취소 명령 테스트
        cancel_commands = ['/cancel', '취소', '중단']
        for cancel_cmd in cancel_commands:
            # 테스트 실행
            await self.handler._handle_store_name_input(mock_update, session, cancel_cmd)

            # 검증
            mock_update.message.reply_text.assert_called_with(
                "상호명 입력을 취소했습니다. 아래 '시작하기' 버튼으로 다시 시작해주세요.",
                reply_markup=mock_update.message.reply_text.call_args[1]['reply_markup']
            )

    @pytest.mark.asyncio
    async def test_handle_store_name_input_direct_input_response(self):
        """'직접 입력하겠습니다' 응답 처리 테스트"""
        mock_update = Mock()
        mock_update.message.reply_text = AsyncMock()

        session = TelegramSession(
            user_id=12345,
            state=ConversationState.WAITING_STORE_NAME
        )

        direct_inputs = ["직접 입력하겠습니다", "수동 입력", "직접 입력"]
        for direct_input in direct_inputs:
            # 테스트 실행
            await self.handler._handle_store_name_input(mock_update, session, direct_input)

            # 검증
            assert "📝 상호명을 직접 입력해주세요" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    @patch('src.telegram.handlers.conversation.get_store_name_resolver')
    async def test_handle_location_with_store_name_retry(self, mock_resolver_factory):
        """위치 메시지로 상호명 보정 재시도 테스트"""
        # Mock resolver 설정
        mock_resolver = Mock()
        mock_resolver.resolve_store_name = AsyncMock(return_value=ResolutionResult(
            status=ResolutionStatus.SUCCESS,
            resolved_name="스타벅스 강남역점",
            confidence=0.8
        ))
        mock_resolver.get_user_confirmation_message = Mock(return_value="✅ 상호명: 스타벅스 강남역점 (추정)")
        mock_resolver_factory.return_value = mock_resolver

        # Mock update와 session
        mock_update = Mock()
        mock_update.message.location.latitude = 37.5
        mock_update.message.location.longitude = 127.0
        mock_update.message.reply_text = AsyncMock()

        session = TelegramSession(
            user_id=12345,
            state=ConversationState.WAITING_STORE_NAME,
            raw_store_name="스타벅스",  # 이미 입력됨
            resolved_store_name=None,  # 아직 해결되지 않음
            location=None
        )

        # 테스트 실행
        await self.handler.handle_location(mock_update, None, session)

        # 검증
        assert session.location is not None
        assert session.location.lat == 37.5
        assert session.location.lng == 127.0
        assert session.location.source == "telegram_location"
        assert session.resolved_store_name == "스타벅스 강남역점"
        assert session.state == ConversationState.WAITING_IMAGES

    @pytest.mark.asyncio
    async def test_handle_location_without_store_name(self):
        """상호명 없이 위치만 받은 경우 테스트"""
        mock_update = Mock()
        mock_update.message.location.latitude = 37.5
        mock_update.message.location.longitude = 127.0
        mock_update.message.reply_text = AsyncMock()

        session = TelegramSession(
            user_id=12345,
            state=ConversationState.WAITING_STORE_NAME,
            raw_store_name=None,  # 상호명 아직 입력 안함
            location=None
        )

        # 테스트 실행
        await self.handler.handle_location(mock_update, None, session)

        # 검증
        assert session.location is not None
        assert session.location.lat == 37.5
        assert session.location.lng == 127.0
        assert session.state == ConversationState.WAITING_STORE_NAME  # 상태 유지

        # 위치 받았다는 메시지와 상호명 입력 요청
        mock_update.message.reply_text.assert_called_with(
            "📍 위치 정보를 받았습니다. 이제 상호명을 입력해주세요.",
            reply_markup=mock_update.message.reply_text.call_args[1]['reply_markup']
        )

    @pytest.mark.asyncio
    async def test_handle_location_wrong_state(self):
        """다른 상태에서 위치 메시지 받은 경우 테스트"""
        mock_update = Mock()
        mock_update.message.location.latitude = 37.5
        mock_update.message.location.longitude = 127.0
        mock_update.message.reply_text = AsyncMock()

        session = TelegramSession(
            user_id=12345,
            state=ConversationState.WAITING_REVIEW,  # 다른 상태
            location=None
        )

        # 테스트 실행
        await self.handler.handle_location(mock_update, None, session)

        # 검증
        assert session.location is not None  # 위치는 저장됨
        assert "지금은 위치가 필요한 단계가 아닙니다" in mock_update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_request_location(self):
        """위치 요청 메시지 생성 테스트"""
        from telegram import KeyboardButton, ReplyKeyboardMarkup

        mock_update = Mock()
        mock_update.message.reply_text = AsyncMock()

        session = TelegramSession(user_id=12345)

        # 테스트 실행
        await self.handler._request_location(mock_update, session, "테스트 메시지")

        # 검증
        call_args = mock_update.message.reply_text.call_args
        assert "📍 테스트 메시지" in call_args[0][0]

        # 키보드가 설정되었는지 확인
        reply_markup = call_args[1]['reply_markup']
        assert reply_markup is not None


class TestConversationFlow:
    """대화 플로우 통합 테스트"""

    def setup_method(self):
        """테스트 설정"""
        mock_bot = Mock()
        self.handler = ConversationHandler(mock_bot)

    @pytest.mark.asyncio
    async def test_category_to_store_name_transition(self):
        """카테고리 입력 후 상호명 입력으로 전환 테스트"""
        mock_update = Mock()
        mock_update.message.reply_text = AsyncMock()

        session = TelegramSession(
            user_id=12345,
            state=ConversationState.WAITING_CATEGORY
        )

        # 카테고리 입력
        await self.handler._handle_category_input(mock_update, session, "맛집")

        # 검증
        assert session.category == "맛집"
        assert session.state == ConversationState.WAITING_STORE_NAME

        # 상호명 입력 요청 메시지 확인
        call_args = mock_update.message.reply_text.call_args[0][0]
        assert "🏪 방문한 상호명을 입력해주세요" in call_args

    @pytest.mark.asyncio
    @patch('src.telegram.handlers.conversation.get_store_name_resolver')
    async def test_full_store_name_flow(self, mock_resolver_factory):
        """전체 상호명 입력 플로우 테스트"""
        # Mock resolver 설정
        mock_resolver = Mock()
        mock_resolver.resolve_store_name = AsyncMock(return_value=ResolutionResult(
            status=ResolutionStatus.SUCCESS,
            resolved_name="스타벅스 강남역점",
            confidence=0.9
        ))
        mock_resolver.get_user_confirmation_message = Mock(return_value="✅ 확인 메시지")
        mock_resolver_factory.return_value = mock_resolver

        mock_update = Mock()
        mock_update.message.reply_text = AsyncMock()
        mock_update.message.location = None

        # 1. 카테고리 입력
        session = TelegramSession(
            user_id=12345,
            state=ConversationState.WAITING_CATEGORY
        )

        await self.handler._handle_category_input(mock_update, session, "맛집")
        assert session.state == ConversationState.WAITING_STORE_NAME

        # 2. 상호명 입력 (위치 정보 있음)
        session.location = LocationInfo(lat=37.5, lng=127.0, source="telegram_location")
        await self.handler._handle_store_name_input(mock_update, session, "스타벅스 강남점")

        # 3. 검증
        assert session.raw_store_name == "스타벅스 강남점"
        assert session.resolved_store_name == "스타벅스 강남역점"
        assert session.state == ConversationState.WAITING_IMAGES
