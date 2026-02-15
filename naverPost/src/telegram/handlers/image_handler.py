"""
Telegram bot image handling
"""

from pathlib import Path
from typing import Optional
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from telegram import Update
from telegram.ext import ContextTypes
import logging

from src.config.settings import Settings
from ..models.session import TelegramSession, ConversationState, LocationInfo
from ..models.responses import ResponseTemplates
from ..constants import MIN_IMAGE_SIZE_BYTES, TEMP_FILE_CLEANUP_HOURS
from ..utils.helpers import ContentTypeDetector
from ..utils import get_user_logger
from ..utils.safe_message_mixin import SafeMessageMixin


class ImageHandler(SafeMessageMixin):
    """텔레그램 이미지 처리 핸들러"""

    def __init__(self, bot):
        super().__init__()  # Initialize SafeMessageMixin
        self.bot = bot
        self.settings = Settings
        self.temp_dir = Path(self.settings.DATA_DIR) / "telegram_temp"
        self.temp_dir.mkdir(exist_ok=True, parents=True)
        self.responses = ResponseTemplates()
        self.logger = logging.getLogger(__name__)

    async def handle_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE, session: TelegramSession):
        """텔레그램 이미지 업로드 처리"""
        # 상태 확인
        if session.state not in [ConversationState.WAITING_IMAGES, ConversationState.WAITING_REVIEW]:
            await update.message.reply_text(self.responses.wrong_step_for_images())
            return

        # 이미지 수 제한 확인
        if len(session.images) >= self.settings.MAX_IMAGES_PER_POST:
            await update.message.reply_text(
                self.responses.image_limit_reached(self.settings.MAX_IMAGES_PER_POST)
            )
            return

        try:
            # 가장 큰 사이즈의 사진 가져오기
            photo = update.message.photo[-1]  # 가장 큰 사이즈

            # 이미지 다운로드
            file = await context.bot.get_file(photo.file_id)
            file_extension = '.jpg'  # 텔레그램 사진은 보통 JPEG
            temp_filename = f"tg_{session.user_id}_{photo.file_id}{file_extension}"
            temp_path = self.temp_dir / temp_filename

            await file.download_to_drive(temp_path)

            # 이미지 검증
            if not await self._validate_image(temp_path):
                temp_path.unlink()  # 유효하지 않은 파일 삭제
                await update.message.reply_text(self.responses.image_invalid())
                return

            # EXIF GPS 정보 추출 및 상호명 보정 시도
            await self._process_image_location(session, temp_path, update)

            # 세션에 추가
            session.images.append(str(temp_path))
            session.update_activity()

            # 첫 번째 이미지인 경우 상태 업데이트
            if session.state == ConversationState.WAITING_IMAGES:
                session.state = ConversationState.WAITING_REVIEW

            # 이미지 업로드 로깅
            user_logger = get_user_logger(session.user_id)
            user_logger.log_image_uploaded(len(session.images), temp_filename)

            # 성공 메시지
            await update.message.reply_text(
                self.responses.image_uploaded(
                    len(session.images),
                    self.settings.MAX_IMAGES_PER_POST
                )
            )

        except Exception as e:
            await update.message.reply_text(
                self.responses.image_upload_error(str(e))
            )

    async def _process_image_location(self, session: TelegramSession, image_path: Path, update: Update):
        """이미지에서 GPS 정보를 추출하고 상호명 보정 시도"""
        from ..services.store_name_resolver import get_store_name_resolver, ResolutionStatus

        # GPS 정보 추출
        gps_location = self._extract_gps_from_image(image_path)
        if not gps_location:
            return

        # 위치 정보 업데이트 (기존 위치가 없거나 EXIF GPS가 더 정확한 경우)
        if not session.location or session.location.source != "telegram_location":
            session.location = gps_location
            self.logger.info(f"GPS location extracted from image: lat={gps_location.lat}, lng={gps_location.lng}")

        # 상호명이 입력되었지만 아직 해결되지 않은 경우 재시도
        if (session.raw_store_name and
            not session.resolved_store_name and
            session.state == ConversationState.WAITING_IMAGES):

            await update.message.reply_text("📍 사진에서 위치 정보를 발견했습니다. 상호명을 다시 확인해보겠습니다...")

            resolver = get_store_name_resolver()
            result = await resolver.resolve_store_name(session)

            if result.status == ResolutionStatus.SUCCESS:
                session.resolved_store_name = result.resolved_name
                confirmation_msg = resolver.get_user_confirmation_message(result)
                await update.message.reply_text(f"✅ {confirmation_msg}")
            elif result.error_message:
                await update.message.reply_text(f"⚠️ {result.error_message}")

    async def _validate_image(self, image_path: Path) -> bool:
        """업로드된 이미지 검증"""
        try:
            # 파일 크기 확인
            file_size = image_path.stat().st_size
            max_size = self.settings.MAX_FILE_SIZE_MB * 1024 * 1024

            if file_size > max_size or file_size < MIN_IMAGE_SIZE_BYTES:
                return False

            # Pillow를 사용한 이미지 형식 검증
            with Image.open(image_path) as img:
                img.verify()  # 이미지 무결성 검증

            return True

        except Exception:
            return False

    def _extract_gps_from_image(self, image_path: Path) -> Optional[LocationInfo]:
        """이미지의 EXIF 데이터에서 GPS 정보 추출"""
        try:
            with Image.open(image_path) as img:
                exif = img.getexif()

                if not exif:
                    return None

                # GPS 정보 태그 찾기
                gps_info = {}
                for tag, value in exif.items():
                    tag_name = TAGS.get(tag, tag)
                    if tag_name == "GPSInfo":
                        for gps_tag in value:
                            gps_tag_name = GPSTAGS.get(gps_tag, gps_tag)
                            gps_info[gps_tag_name] = value[gps_tag]

                if not gps_info:
                    return None

                # 위도 추출
                lat = self._convert_gps_coordinate(
                    gps_info.get('GPSLatitude'),
                    gps_info.get('GPSLatitudeRef')
                )

                # 경도 추출
                lng = self._convert_gps_coordinate(
                    gps_info.get('GPSLongitude'),
                    gps_info.get('GPSLongitudeRef')
                )

                if lat is not None and lng is not None:
                    return LocationInfo(
                        lat=lat,
                        lng=lng,
                        source="exif_gps"
                    )

                return None

        except Exception as e:
            self.logger.debug(f"Failed to extract GPS from image {image_path}: {e}")
            return None

    def _convert_gps_coordinate(self, coordinate, reference):
        """GPS 좌표를 십진수 형태로 변환"""
        if coordinate is None or reference is None:
            return None

        try:
            # 도, 분, 초를 십진수로 변환
            degrees = float(coordinate[0])
            minutes = float(coordinate[1])
            seconds = float(coordinate[2])

            decimal = degrees + minutes/60 + seconds/3600

            # 남위나 서경인 경우 음수로 변환
            if reference in ['S', 'W']:
                decimal = -decimal

            return decimal

        except (TypeError, IndexError, ZeroDivisionError):
            return None

    def cleanup_temp_files(self, user_id: int):
        """특정 사용자의 임시 파일 정리"""
        pattern = f"tg_{user_id}_*"
        for temp_file in self.temp_dir.glob(pattern):
            try:
                temp_file.unlink()
            except Exception:
                pass  # 삭제 실패는 무시

    def cleanup_old_temp_files(self, max_age_hours: int = TEMP_FILE_CLEANUP_HOURS):
        """오래된 임시 파일 정리"""
        from datetime import datetime, timedelta

        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        for temp_file in self.temp_dir.glob("tg_*"):
            try:
                if datetime.fromtimestamp(temp_file.stat().st_mtime) < cutoff_time:
                    temp_file.unlink()
            except Exception:
                pass  # 삭제 실패는 무시

    async def prepare_images_for_data_manager(self, session: TelegramSession) -> list:
        """DataManager에서 사용할 수 있는 형식으로 이미지 준비"""
        image_files = []

        for img_path_str in session.images:
            img_path = Path(img_path_str)
            if not img_path.exists():
                continue

            try:
                with open(img_path, 'rb') as f:
                    content = f.read()

                # MIME 타입 결정
                content_type = ContentTypeDetector.get_mime_type(img_path.suffix)

                image_files.append({
                    'filename': img_path.name,
                    'content': content,
                    'content_type': content_type,
                    'size': len(content)
                })

            except Exception:
                continue  # 읽기 실패한 파일은 스킵

        return image_files

