"""
이미지 GPS 추출 기능 테스트
"""

import pytest
from unittest.mock import Mock, patch, mock_open
from pathlib import Path
from PIL import Image
import io

from src.telegram.handlers.image_handler import ImageHandler
from src.telegram.models.session import LocationInfo


class TestImageGPSExtraction:
    """이미지 GPS 추출 테스트 클래스"""

    def setup_method(self):
        """테스트 설정"""
        mock_bot = Mock()
        self.handler = ImageHandler(mock_bot)

    def test_convert_gps_coordinate_positive(self):
        """GPS 좌표 변환 테스트 (북위/동경)"""
        # 북위 37도 30분 0초
        coordinate = [37, 30, 0]
        reference = 'N'

        result = self.handler._convert_gps_coordinate(coordinate, reference)
        expected = 37.5  # 37 + 30/60 + 0/3600

        assert abs(result - expected) < 0.001, f"Expected {expected}, got {result}"

    def test_convert_gps_coordinate_negative(self):
        """GPS 좌표 변환 테스트 (남위/서경)"""
        # 남위 37도 30분 0초
        coordinate = [37, 30, 0]
        reference = 'S'

        result = self.handler._convert_gps_coordinate(coordinate, reference)
        expected = -37.5

        assert abs(result - expected) < 0.001, f"Expected {expected}, got {result}"

        # 서경 테스트
        reference = 'W'
        result = self.handler._convert_gps_coordinate(coordinate, reference)
        assert abs(result - expected) < 0.001, f"Expected {expected}, got {result}"

    def test_convert_gps_coordinate_complex(self):
        """복잡한 GPS 좌표 변환 테스트"""
        # 37도 33분 15초
        coordinate = [37, 33, 15]
        reference = 'N'

        result = self.handler._convert_gps_coordinate(coordinate, reference)
        expected = 37 + 33/60 + 15/3600  # 37.55416...

        assert abs(result - expected) < 0.001, f"Expected {expected}, got {result}"

    def test_convert_gps_coordinate_invalid(self):
        """잘못된 GPS 좌표 처리 테스트"""
        # None 입력
        result = self.handler._convert_gps_coordinate(None, 'N')
        assert result is None

        result = self.handler._convert_gps_coordinate([37, 30, 0], None)
        assert result is None

        # 잘못된 형식
        result = self.handler._convert_gps_coordinate([37], 'N')
        assert result is None

        # 잘못된 타입
        result = self.handler._convert_gps_coordinate("invalid", 'N')
        assert result is None

    @patch('src.telegram.handlers.image_handler.Image.open')
    def test_extract_gps_from_image_success(self, mock_image_open):
        """이미지에서 GPS 정보 추출 성공 테스트"""
        # Mock EXIF 데이터 설정
        mock_img = Mock()
        mock_exif = {
            34853: {  # GPSInfo 태그
                1: 'N',  # GPSLatitudeRef
                2: [37, 33, 15.0],  # GPSLatitude
                3: 'E',  # GPSLongitudeRef
                4: [127, 1, 30.0],  # GPSLongitude
            }
        }

        mock_img.getexif.return_value = mock_exif
        mock_image_open.return_value.__enter__.return_value = mock_img

        # 테스트 실행
        test_path = Path("/fake/path/test.jpg")
        result = self.handler._extract_gps_from_image(test_path)

        # 검증
        assert result is not None
        assert isinstance(result, LocationInfo)
        assert abs(result.lat - 37.554167) < 0.001  # 37도 33분 15초
        assert abs(result.lng - 127.025) < 0.001    # 127도 1분 30초
        assert result.source == "exif_gps"

    @patch('src.telegram.handlers.image_handler.Image.open')
    def test_extract_gps_from_image_no_exif(self, mock_image_open):
        """EXIF 정보가 없는 이미지 테스트"""
        mock_img = Mock()
        mock_img.getexif.return_value = {}  # 빈 EXIF

        mock_image_open.return_value.__enter__.return_value = mock_img

        # 테스트 실행
        test_path = Path("/fake/path/test.jpg")
        result = self.handler._extract_gps_from_image(test_path)

        # 검증
        assert result is None

    @patch('src.telegram.handlers.image_handler.Image.open')
    def test_extract_gps_from_image_no_gps_info(self, mock_image_open):
        """GPS 정보가 없는 EXIF 테스트"""
        mock_img = Mock()
        mock_exif = {
            271: "Samsung",  # Make
            272: "Galaxy S21",  # Model
            # GPSInfo (34853) 없음
        }

        mock_img.getexif.return_value = mock_exif
        mock_image_open.return_value.__enter__.return_value = mock_img

        # 테스트 실행
        test_path = Path("/fake/path/test.jpg")
        result = self.handler._extract_gps_from_image(test_path)

        # 검증
        assert result is None

    @patch('src.telegram.handlers.image_handler.Image.open')
    def test_extract_gps_from_image_incomplete_gps(self, mock_image_open):
        """불완전한 GPS 정보 테스트"""
        mock_img = Mock()
        mock_exif = {
            34853: {  # GPSInfo 태그
                1: 'N',  # GPSLatitudeRef
                2: [37, 33, 15.0],  # GPSLatitude
                # GPSLongitude 정보 없음
            }
        }

        mock_img.getexif.return_value = mock_exif
        mock_image_open.return_value.__enter__.return_value = mock_img

        # 테스트 실행
        test_path = Path("/fake/path/test.jpg")
        result = self.handler._extract_gps_from_image(test_path)

        # 검증
        assert result is None

    @patch('src.telegram.handlers.image_handler.Image.open')
    def test_extract_gps_from_image_exception(self, mock_image_open):
        """이미지 열기 예외 처리 테스트"""
        mock_image_open.side_effect = Exception("File not found")

        # 테스트 실행
        test_path = Path("/fake/path/nonexistent.jpg")
        result = self.handler._extract_gps_from_image(test_path)

        # 검증 (예외가 발생해도 None 반환해야 함)
        assert result is None

    def test_extract_gps_real_coordinates(self):
        """실제 좌표값으로 변환 테스트"""
        # 서울시청 좌표 (대략)
        seoul_city_hall_lat = [37, 33, 59.53]  # 37.566536
        seoul_city_hall_lng = [126, 58, 40.68]  # 126.977966

        lat_result = self.handler._convert_gps_coordinate(seoul_city_hall_lat, 'N')
        lng_result = self.handler._convert_gps_coordinate(seoul_city_hall_lng, 'E')

        assert abs(lat_result - 37.566536) < 0.001
        assert abs(lng_result - 126.977966) < 0.001

        # 강남역 좌표 (대략)
        gangnam_station_lat = [37, 29, 53.14]  # 37.498095
        gangnam_station_lng = [127, 1, 39.49]  # 127.027636

        lat_result = self.handler._convert_gps_coordinate(gangnam_station_lat, 'N')
        lng_result = self.handler._convert_gps_coordinate(gangnam_station_lng, 'E')

        assert abs(lat_result - 37.498095) < 0.001
        assert abs(lng_result - 127.027636) < 0.001


class TestImageLocationProcessing:
    """이미지 위치 정보 처리 통합 테스트"""

    def setup_method(self):
        """테스트 설정"""
        mock_bot = Mock()
        self.handler = ImageHandler(mock_bot)

    @pytest.mark.asyncio
    @patch('src.telegram.services.store_name_resolver.get_store_name_resolver')
    async def test_process_image_location_with_store_name_resolution(self, mock_resolver_factory):
        """이미지 위치로 상호명 보정 테스트 (_process_gps_location)"""
        from unittest.mock import AsyncMock
        from src.telegram.models.session import TelegramSession, ConversationState
        from src.telegram.services.store_name_resolver import ResolutionStatus, ResolutionResult

        # Mock resolver 설정
        mock_resolver = Mock()
        mock_resolver.resolve_store_name = AsyncMock(return_value=ResolutionResult(
            status=ResolutionStatus.SUCCESS,
            resolved_name="스타벅스 강남역점",
            confidence=0.9
        ))
        mock_resolver.get_user_confirmation_message = Mock(return_value="확인 메시지")
        mock_resolver_factory.return_value = mock_resolver

        # Mock update
        mock_update = Mock()
        mock_update.message.reply_text = AsyncMock()

        # 세션 설정
        session = TelegramSession(
            user_id=12345,
            state=ConversationState.WAITING_IMAGES,
            raw_store_name="스타벅스",
            resolved_store_name=None
        )

        # _process_gps_location 직접 호출 (GPS 좌표 tuple 전달)
        await self.handler._process_gps_location(session, (37.5, 127.0), mock_update)

        # 검증
        assert session.location is not None
        assert session.location.lat == 37.5
        assert session.location.lng == 127.0
        assert session.location.source == "exif_gps"

        # Resolver가 호출되었는지 확인
        mock_resolver.resolve_store_name.assert_called_once_with(session)

        # 성공 메시지가 전송되었는지 확인
        assert mock_update.message.reply_text.call_count >= 2

    @pytest.mark.asyncio
    async def test_process_image_location_no_gps(self):
        """GPS 정보가 없는 이미지 처리 테스트 (_process_gps_location)"""
        from src.telegram.models.session import TelegramSession

        session = TelegramSession(user_id=12345)
        mock_update = Mock()

        # GPS 없음(None)을 전달하면 처리 없이 바로 리턴
        await self.handler._process_gps_location(session, None, mock_update)

        # 검증: 세션 위치가 변경되지 않았는지 확인
        assert session.location is None