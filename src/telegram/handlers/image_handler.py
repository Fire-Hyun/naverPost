"""
Telegram bot image handling (안정화 버전)
"""

from pathlib import Path
from typing import Optional, List
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from telegram import Update
from telegram.ext import ContextTypes
import logging
import asyncio

from src.config.settings import Settings
from ..models.session import TelegramSession, ConversationState, LocationInfo, update_session
from ..models.responses import ResponseTemplates
from ..constants import MIN_IMAGE_SIZE_BYTES, TEMP_FILE_CLEANUP_HOURS
from ..utils.helpers import ContentTypeDetector
from ..utils import get_user_logger
from ..utils.safe_message_mixin import SafeMessageMixin
from src.utils.image_processor import (
    StabilizedTelegramImageClient, ImageProcessingConfig, ImageMetadata
)
from src.utils.exceptions import (
    ImageProcessingError, TelegramAPIError, NonRetryableError,
    RetryableError, TimeoutError
)
from src.utils.structured_logger import get_logger


class ImageHandler(SafeMessageMixin):
    """텔레그램 이미지 처리 핸들러 (안정화 버전)"""

    def __init__(self, bot):
        super().__init__()  # Initialize SafeMessageMixin
        self.bot = bot
        self.settings = Settings
        self.responses = ResponseTemplates()
        self.logger = get_logger("telegram_image_handler")

        # 안정화된 이미지 클라이언트 설정
        self.image_config = ImageProcessingConfig(
            max_file_size_mb=getattr(Settings, 'MAX_FILE_SIZE_MB', 20.0),
            max_dimensions=(2048, 2048),  # 블로그용으로 적절한 크기
            enable_auto_resize=True,
            enable_auto_compress=True,
            compression_quality=85,
            temp_file_retention_hours=TEMP_FILE_CLEANUP_HOURS
        )

        # 텔레그램 이미지 클라이언트
        self.image_client = StabilizedTelegramImageClient(
            Settings.TELEGRAM_BOT_TOKEN,
            self.image_config
        )

        # 레거시 임시 디렉토리 (하위 호환성)
        self.temp_dir = Path(self.settings.DATA_DIR) / "telegram_temp"
        self.temp_dir.mkdir(exist_ok=True, parents=True)

        # 동시 처리 제한 (세마포어)
        self._processing_semaphore = asyncio.Semaphore(3)  # 최대 3개 동시 처리

    async def handle_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE, session: TelegramSession):
        """텔레그램 이미지 업로드 처리 (안정화 버전)"""
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

        # 동시 처리 제한
        async with self._processing_semaphore:
            await self._process_single_image(update, context, session)

    async def _process_single_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE, session: TelegramSession):
        """단일 이미지 처리"""
        photo = update.message.photo[-1]  # 가장 큰 사이즈
        file_id = photo.file_id

        # 사용자별 로깅
        user_logger = get_user_logger(session.user_id)

        try:
            self.logger.info("Starting image processing",
                           user_id=session.user_id,
                           file_id=file_id,
                           current_image_count=len(session.images))

            # 진행 중 메시지 표시
            progress_msg = await update.message.reply_text("🔄 이미지를 처리하고 있습니다...")

            # 안정화된 클라이언트로 다운로드 및 처리
            image_path, metadata = await self.image_client.download_telegram_image(file_id)

            try:
                # GPS 정보 처리
                if metadata.gps_location:
                    await self._process_gps_location(session, metadata.gps_location, update)

                # 세션에 추가 (처리된 이미지 경로)
                session.images.append(str(image_path))
                session.update_activity()

                # 첫 번째 이미지인 경우 상태 업데이트
                if session.state == ConversationState.WAITING_IMAGES:
                    session.state = ConversationState.WAITING_REVIEW
                update_session(session)

                # 성공 로깅
                user_logger.log_image_uploaded(len(session.images), metadata.filename)

                self.logger.info("Image processing completed successfully",
                               user_id=session.user_id,
                               file_id=file_id,
                               filename=metadata.filename,
                               size_bytes=metadata.size_bytes,
                               dimensions=metadata.dimensions,
                               has_gps=metadata.gps_location is not None)

                # 진행 메시지 업데이트
                await progress_msg.edit_text(
                    self.responses.image_uploaded(
                        len(session.images),
                        self.settings.MAX_IMAGES_PER_POST
                    )
                )

            except Exception as e:
                # 처리된 이미지 파일 정리
                if image_path.exists():
                    image_path.unlink()
                raise e

        except NonRetryableError as e:
            # 재시도 불가능한 오류 (파일 크기, 포맷 등)
            error_msg = self._get_user_friendly_error_message(e)
            await update.message.reply_text(f"❌ {error_msg}")

            self.logger.warning("Non-retryable image processing error",
                              user_id=session.user_id,
                              file_id=file_id,
                              error=str(e))

        except RetryableError as e:
            # 재시도 가능한 오류 (네트워크 등)
            await update.message.reply_text("⚠️ 네트워크 문제로 이미지 처리에 실패했습니다. 잠시 후 다시 시도해주세요.")

            self.logger.error("Retryable image processing error",
                            user_id=session.user_id,
                            file_id=file_id,
                            error=str(e))

        except TelegramAPIError as e:
            # 텔레그램 API 오류
            await update.message.reply_text("❌ 텔레그램 서버 문제로 이미지를 가져올 수 없습니다. 다시 시도해주세요.")

            self.logger.error("Telegram API error during image processing",
                            user_id=session.user_id,
                            file_id=file_id,
                            error=str(e))

        except Exception as e:
            # 예상치 못한 오류
            await update.message.reply_text("❌ 이미지 처리 중 예상치 못한 오류가 발생했습니다.")

            self.logger.error("Unexpected image processing error",
                            user_id=session.user_id,
                            file_id=file_id,
                            error=e)

            user_logger.log_generation_error(f"Image processing error: {str(e)}")

    def _get_user_friendly_error_message(self, error: Exception) -> str:
        """사용자 친화적 오류 메시지 생성"""
        error_str = str(error).lower()

        if "size" in error_str and "exceed" in error_str:
            return f"이미지 파일 크기가 너무 큽니다 (최대 {self.image_config.max_file_size_mb}MB)"
        elif "format" in error_str or "invalid" in error_str:
            return "지원하지 않는 이미지 형식입니다. JPG, PNG, WEBP 파일만 업로드 가능합니다."
        elif "dimensions" in error_str:
            max_w, max_h = self.image_config.max_dimensions
            return f"이미지 크기가 너무 큽니다 (최대 {max_w}x{max_h})"
        elif "timeout" in error_str:
            return "이미지 처리 시간이 초과되었습니다. 더 작은 이미지를 사용해주세요."
        else:
            return "이미지 처리 중 오류가 발생했습니다."

    async def _process_gps_location(self, session: TelegramSession, gps_location: tuple, update: Update):
        """GPS 정보 처리 및 상호명 보정 시도"""
        from ..services.store_name_resolver import get_store_name_resolver, ResolutionStatus

        if not gps_location:
            return

        lat, lng = gps_location

        # LocationInfo 객체 생성
        location_info = LocationInfo(
            lat=lat,
            lng=lng,
            source="exif_gps"
        )

        # 위치 정보 업데이트 (기존 위치가 없거나 EXIF GPS가 더 정확한 경우)
        if not session.location or session.location.source != "telegram_location":
            session.location = location_info
            self.logger.info("GPS location extracted from image",
                           lat=lat,
                           lng=lng,
                           user_id=session.user_id)

        # 상호명이 입력되었지만 아직 해결되지 않은 경우 재시도
        if (session.raw_store_name and
            not session.resolved_store_name and
            session.state == ConversationState.WAITING_IMAGES):

            await update.message.reply_text("📍 사진에서 위치 정보를 발견했습니다. 상호명을 다시 확인해보겠습니다...")

            try:
                resolver = get_store_name_resolver()
                result = await resolver.resolve_store_name(session)

                if result.status == ResolutionStatus.SUCCESS:
                    session.resolved_store_name = result.resolved_name
                    update_session(session)
                    confirmation_msg = resolver.get_user_confirmation_message(result)
                    await update.message.reply_text(f"✅ {confirmation_msg}")

                    self.logger.info("Store name resolved using GPS from image",
                                   user_id=session.user_id,
                                   raw_name=session.raw_store_name,
                                   resolved_name=result.resolved_name)

                elif result.error_message:
                    await update.message.reply_text(f"⚠️ {result.error_message}")

            except Exception as e:
                self.logger.error("Store name resolution error with GPS",
                                error=e,
                                user_id=session.user_id)

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

        except (TypeError, IndexError, ZeroDivisionError, ValueError):
            return None

    async def cleanup_temp_files(self, user_id: int):
        """특정 사용자의 임시 파일 정리 (안정화 버전)"""
        try:
            # 레거시 임시 파일 정리
            pattern = f"tg_{user_id}_*"
            cleaned_legacy_count = 0
            for temp_file in self.temp_dir.glob(pattern):
                try:
                    temp_file.unlink()
                    cleaned_legacy_count += 1
                except Exception:
                    pass

            # 안정화된 클라이언트의 임시 파일 정리
            await self.image_client.cleanup_temp_files()

            if cleaned_legacy_count > 0:
                self.logger.info("User temp files cleaned",
                               user_id=user_id,
                               legacy_files_cleaned=cleaned_legacy_count)

        except Exception as e:
            self.logger.error("Error during user temp file cleanup",
                            error=e,
                            user_id=user_id)

    async def cleanup_old_temp_files(self, max_age_hours: int = TEMP_FILE_CLEANUP_HOURS):
        """오래된 임시 파일 정리 (안정화 버전)"""
        try:
            # 레거시 임시 디렉토리 정리
            from datetime import datetime, timedelta

            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            cleaned_legacy_count = 0

            for temp_file in self.temp_dir.glob("tg_*"):
                try:
                    if datetime.fromtimestamp(temp_file.stat().st_mtime) < cutoff_time:
                        temp_file.unlink()
                        cleaned_legacy_count += 1
                except Exception:
                    pass

            # 안정화된 클라이언트의 임시 파일 정리
            await self.image_client.cleanup_temp_files(max_age_hours)

            if cleaned_legacy_count > 0:
                self.logger.info("Old temp files cleaned",
                               legacy_files_cleaned=cleaned_legacy_count,
                               max_age_hours=max_age_hours)

        except Exception as e:
            self.logger.error("Error during old temp file cleanup", error=e)

    async def cleanup(self):
        """리소스 정리"""
        try:
            await self.image_client.close()
            self.logger.info("Image handler cleanup completed")
        except Exception as e:
            self.logger.error("Error during image handler cleanup", error=e)

    def get_handler_metrics(self) -> dict:
        """핸들러 메트릭 반환"""
        try:
            return self.image_client.get_metrics()
        except Exception as e:
            self.logger.error("Error getting handler metrics", error=e)
            return {"error": str(e)}

    # === 레거시 메소드들 (하위 호환성) ===

    async def _validate_image(self, image_path: Path) -> bool:
        """레거시 이미지 검증 (하위 호환성)"""
        try:
            is_valid, _ = await self.image_client.validator.validate_image_file(image_path)
            return is_valid
        except Exception:
            return False

    async def prepare_images_for_data_manager(self, session: TelegramSession) -> List[dict]:
        """DataManager에서 사용할 수 있는 형식으로 이미지 준비 (안정화 버전)"""
        if not session.images:
            return []

        try:
            # 이미지 경로들을 Path 객체로 변환
            image_paths = [Path(img_path_str) for img_path_str in session.images if Path(img_path_str).exists()]

            if not image_paths:
                self.logger.warning("No valid image paths found", user_id=session.user_id)
                return []

            # 안정화된 클라이언트로 업로드 준비
            processed_images = await self.image_client.upload_processed_images(image_paths)

            self.logger.info("Images prepared for data manager",
                           user_id=session.user_id,
                           original_count=len(session.images),
                           processed_count=len(processed_images))

            return processed_images

        except Exception as e:
            self.logger.error("Error preparing images for data manager",
                            error=e,
                            user_id=session.user_id)
            return []
