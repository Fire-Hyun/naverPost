"""
안정화된 이미지 처리 유틸리티
텔레그램 이미지 다운로드/처리/업로드를 안정적으로 처리
"""

import asyncio
import tempfile
import hashlib
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Union, BinaryIO
from dataclasses import dataclass
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import mimetypes

from PIL import Image, ImageOps, ExifTags
from PIL.ExifTags import TAGS, GPSTAGS
import aiofiles

from .http_client import StabilizedHTTPClient, create_telegram_client
from .exceptions import (
    ImageProcessingError, TelegramAPIError, TimeoutError,
    NonRetryableError, RetryableError, ParseError
)
from .structured_logger import get_logger

logger = get_logger("image_processor")


@dataclass
class ImageMetadata:
    """이미지 메타데이터"""
    filename: str
    size_bytes: int
    dimensions: Tuple[int, int]
    format: str
    content_type: str
    has_exif: bool = False
    gps_location: Optional[Tuple[float, float]] = None
    creation_time: Optional[datetime] = None


@dataclass
class ImageProcessingConfig:
    """이미지 처리 설정"""
    max_file_size_mb: float = 20.0
    min_file_size_bytes: int = 1024  # 1KB
    max_dimensions: Tuple[int, int] = (4096, 4096)
    min_dimensions: Tuple[int, int] = (50, 50)
    allowed_formats: List[str] = None
    enable_auto_resize: bool = True
    enable_auto_compress: bool = True
    compression_quality: int = 85
    temp_file_retention_hours: int = 24

    def __post_init__(self):
        if self.allowed_formats is None:
            self.allowed_formats = ['JPEG', 'PNG', 'WEBP', 'BMP', 'TIFF']


class ImageValidator:
    """이미지 검증 클래스"""

    def __init__(self, config: ImageProcessingConfig):
        self.config = config

    async def validate_image_file(self, file_path: Path) -> Tuple[bool, str]:
        """이미지 파일 검증"""
        try:
            # 파일 존재 확인
            if not file_path.exists():
                return False, "File does not exist"

            # 파일 크기 확인
            file_size = file_path.stat().st_size
            max_size = int(self.config.max_file_size_mb * 1024 * 1024)

            if file_size > max_size:
                return False, f"File size {file_size} exceeds maximum {max_size} bytes"

            if file_size < self.config.min_file_size_bytes:
                return False, f"File size {file_size} below minimum {self.config.min_file_size_bytes} bytes"

            # PIL을 사용한 이미지 검증
            try:
                with Image.open(file_path) as img:
                    # 포맷 확인
                    if img.format not in self.config.allowed_formats:
                        return False, f"Unsupported format: {img.format}"

                    # 치수 확인
                    width, height = img.size
                    max_w, max_h = self.config.max_dimensions
                    min_w, min_h = self.config.min_dimensions

                    if width > max_w or height > max_h:
                        return False, f"Dimensions {width}x{height} exceed maximum {max_w}x{max_h}"

                    if width < min_w or height < min_h:
                        return False, f"Dimensions {width}x{height} below minimum {min_w}x{min_h}"

                    # 이미지 무결성 검증
                    img.verify()

                return True, "Valid image"

            except Exception as e:
                return False, f"Invalid image format: {str(e)}"

        except Exception as e:
            logger.error("Image validation error", error=e, file_path=str(file_path))
            return False, f"Validation error: {str(e)}"

    async def validate_image_content(self, content: bytes, filename: str = "unknown") -> Tuple[bool, str]:
        """이미지 콘텐츠 검증"""
        if not content:
            return False, "Empty content"

        # 임시 파일로 저장 후 검증
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp_file:
            tmp_file.write(content)
            tmp_path = Path(tmp_file.name)

        try:
            return await self.validate_image_file(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)


class ImageProcessor:
    """이미지 처리 클래스"""

    def __init__(self, config: ImageProcessingConfig):
        self.config = config

    async def extract_metadata(self, file_path: Path) -> ImageMetadata:
        """이미지 메타데이터 추출"""
        try:
            file_size = file_path.stat().st_size
            content_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'

            with Image.open(file_path) as img:
                dimensions = img.size
                format_name = img.format

                # EXIF 데이터 확인
                exif = img.getexif()
                has_exif = bool(exif)
                gps_location = None
                creation_time = None

                if has_exif:
                    gps_location = self._extract_gps_from_exif(exif)
                    creation_time = self._extract_creation_time_from_exif(exif)

                return ImageMetadata(
                    filename=file_path.name,
                    size_bytes=file_size,
                    dimensions=dimensions,
                    format=format_name,
                    content_type=content_type,
                    has_exif=has_exif,
                    gps_location=gps_location,
                    creation_time=creation_time
                )

        except Exception as e:
            logger.error("Metadata extraction error", error=e, file_path=str(file_path))
            raise ImageProcessingError(f"Failed to extract metadata: {str(e)}", str(file_path), "metadata_extraction")

    def _extract_gps_from_exif(self, exif: dict) -> Optional[Tuple[float, float]]:
        """EXIF에서 GPS 좌표 추출"""
        try:
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
                return (lat, lng)

            return None

        except Exception:
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

    def _extract_creation_time_from_exif(self, exif: dict) -> Optional[datetime]:
        """EXIF에서 생성 시간 추출"""
        try:
            for tag, value in exif.items():
                tag_name = TAGS.get(tag, tag)
                if tag_name in ['DateTime', 'DateTimeOriginal', 'DateTimeDigitized']:
                    try:
                        return datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                    except ValueError:
                        continue
            return None
        except Exception:
            return None

    async def resize_image(self, file_path: Path, max_dimensions: Tuple[int, int] = None) -> Path:
        """이미지 리사이즈"""
        if max_dimensions is None:
            max_dimensions = self.config.max_dimensions

        try:
            with Image.open(file_path) as img:
                original_size = img.size

                # 리사이즈 필요 여부 확인
                if original_size[0] <= max_dimensions[0] and original_size[1] <= max_dimensions[1]:
                    return file_path  # 리사이즈 불필요

                # 비율 유지하면서 리사이즈
                img.thumbnail(max_dimensions, Image.LANCZOS)

                # 새 파일로 저장
                resized_path = file_path.with_name(f"resized_{file_path.name}")

                # EXIF 정보 유지
                if hasattr(img, '_getexif') and img._getexif() is not None:
                    img = ImageOps.exif_transpose(img)

                img.save(resized_path, format=img.format, quality=self.config.compression_quality, optimize=True)

                logger.info("Image resized",
                           original_size=original_size,
                           new_size=img.size,
                           file_path=str(file_path))

                return resized_path

        except Exception as e:
            logger.error("Image resize error", error=e, file_path=str(file_path))
            raise ImageProcessingError(f"Failed to resize image: {str(e)}", str(file_path), "resize")

    async def compress_image(self, file_path: Path, quality: int = None) -> Path:
        """이미지 압축"""
        if quality is None:
            quality = self.config.compression_quality

        try:
            original_size = file_path.stat().st_size

            with Image.open(file_path) as img:
                # 압축된 파일로 저장
                compressed_path = file_path.with_name(f"compressed_{file_path.name}")

                # EXIF 정보 유지
                if hasattr(img, '_getexif') and img._getexif() is not None:
                    img = ImageOps.exif_transpose(img)

                img.save(compressed_path, format=img.format, quality=quality, optimize=True)

                new_size = compressed_path.stat().st_size
                compression_ratio = (original_size - new_size) / original_size * 100

                logger.info("Image compressed",
                           original_size=original_size,
                           compressed_size=new_size,
                           compression_ratio=f"{compression_ratio:.1f}%",
                           file_path=str(file_path))

                return compressed_path

        except Exception as e:
            logger.error("Image compression error", error=e, file_path=str(file_path))
            raise ImageProcessingError(f"Failed to compress image: {str(e)}", str(file_path), "compress")


class StabilizedTelegramImageClient:
    """안정화된 텔레그램 이미지 클라이언트"""

    def __init__(self, bot_token: str, config: ImageProcessingConfig = None):
        self.bot_token = bot_token
        self.config = config or ImageProcessingConfig()
        self.validator = ImageValidator(self.config)
        self.processor = ImageProcessor(self.config)

        # HTTP 클라이언트 (텔레그램 API용)
        self.http_client = create_telegram_client(bot_token)

        # 임시 파일 디렉토리
        self.temp_dir = Path(tempfile.gettempdir()) / "naverpost_images"
        self.temp_dir.mkdir(exist_ok=True)

    def _mask_telegram_file_url(self, url: str) -> str:
        """텔레그램 파일 URL에서 bot token 마스킹"""
        token = self.bot_token
        if token and token in url:
            return url.replace(token, "***REDACTED***")
        return url

    async def close(self):
        """리소스 정리"""
        await self.http_client.close()

    @asynccontextmanager
    async def temp_file_context(self, suffix: str = ".jpg"):
        """임시 파일 컨텍스트 매니저"""
        temp_file = None
        try:
            # 유니크한 파일명 생성
            timestamp = int(time.time() * 1000)
            file_hash = hashlib.md5(f"{timestamp}_{suffix}".encode()).hexdigest()[:8]
            filename = f"temp_{timestamp}_{file_hash}{suffix}"
            temp_file = self.temp_dir / filename

            yield temp_file

        finally:
            if temp_file and temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass  # 삭제 실패는 무시

    async def download_telegram_image(self, file_id: str, max_retries: int = 3) -> Tuple[Path, ImageMetadata]:
        """텔레그램에서 이미지 다운로드 (안정화됨)"""

        # 파일 정보 조회
        try:
            with logger.external_call_context("telegram", "get_file", file_id):
                response = await self.http_client.get_json(f"/getFile", params={"file_id": file_id})

                if not response.get("ok"):
                    raise TelegramAPIError(f"Failed to get file info: {response.get('description', 'Unknown error')}")

                file_info = response["result"]
                file_path = file_info.get("file_path")
                file_size = file_info.get("file_size", 0)

                if not file_path:
                    raise TelegramAPIError("No file path in response")

                logger.info(
                    "Telegram getFile success",
                    file_id=file_id,
                    file_path=file_path,
                    file_size=file_size,
                    download_url_acquired=True
                )

                # 파일 크기 사전 검증
                max_size = int(self.config.max_file_size_mb * 1024 * 1024)
                if file_size > max_size:
                    raise NonRetryableError(f"File size {file_size} exceeds limit {max_size}")

        except Exception as e:
            logger.error(
                "Failed to get Telegram file info",
                error=e,
                file_id=file_id,
                download_url_acquired=False
            )
            raise

        # 파일 다운로드
        download_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
        masked_download_url = self._mask_telegram_file_url(download_url)
        file_extension = Path(file_path).suffix or ".jpg"
        expected_mime = mimetypes.guess_type(file_path)[0] or "application/octet-stream"

        async with self.temp_file_context(file_extension) as temp_file:
            try:
                with logger.external_call_context("telegram", "download_file", download_url):
                    response = await self.http_client.get(download_url)
                    content = response.content

                logger.info(
                    "Telegram file download completed",
                    file_id=file_id,
                    download_url=masked_download_url,
                    status_code=getattr(response, "status_code", None),
                    bytes=len(content) if content else 0,
                    expected_mime=expected_mime,
                    extension=file_extension
                )

                # 콘텐츠 사전 검증
                is_valid, validation_msg = await self.validator.validate_image_content(content, temp_file.name)
                if not is_valid:
                    raise NonRetryableError(f"Invalid image content: {validation_msg}")

                # 파일 저장
                async with aiofiles.open(temp_file, 'wb') as f:
                    await f.write(content)

                # 메타데이터 추출
                metadata = await self.processor.extract_metadata(temp_file)

                # 실제 파일로 복사 (temp_file_context 밖에서 사용하기 위해)
                final_path = self.temp_dir / f"download_{metadata.filename}"
                async with aiofiles.open(temp_file, 'rb') as src:
                    async with aiofiles.open(final_path, 'wb') as dst:
                        content = await src.read()
                        await dst.write(content)

                logger.info("Telegram image downloaded successfully",
                           file_id=file_id,
                           file_size=metadata.size_bytes,
                           dimensions=metadata.dimensions,
                           format=metadata.format)

                return final_path, metadata

            except Exception as e:
                logger.error("Telegram image download failed", error=e, file_id=file_id, url=download_url)
                raise

    async def process_image_for_upload(self, image_path: Path) -> Tuple[Path, ImageMetadata]:
        """업로드를 위한 이미지 처리"""
        try:
            # 유효성 검증
            is_valid, validation_msg = await self.validator.validate_image_file(image_path)
            if not is_valid:
                raise NonRetryableError(f"Image validation failed: {validation_msg}")

            current_path = image_path

            # 메타데이터 추출
            metadata = await self.processor.extract_metadata(current_path)

            # 자동 리사이즈 (필요시)
            if self.config.enable_auto_resize:
                width, height = metadata.dimensions
                max_w, max_h = self.config.max_dimensions

                if width > max_w or height > max_h:
                    logger.info("Image requires resizing",
                               current_size=metadata.dimensions,
                               max_size=self.config.max_dimensions)
                    current_path = await self.processor.resize_image(current_path)
                    metadata = await self.processor.extract_metadata(current_path)

            # 자동 압축 (필요시)
            if self.config.enable_auto_compress:
                # 파일 크기가 큰 경우 압축
                size_threshold = int(self.config.max_file_size_mb * 0.8 * 1024 * 1024)  # 80% 임계값

                if metadata.size_bytes > size_threshold:
                    logger.info("Image requires compression",
                               current_size=metadata.size_bytes,
                               threshold=size_threshold)
                    current_path = await self.processor.compress_image(current_path)
                    metadata = await self.processor.extract_metadata(current_path)

            logger.info("Image processing completed",
                       original_path=str(image_path),
                       final_path=str(current_path),
                       final_metadata=metadata.__dict__)

            return current_path, metadata

        except Exception as e:
            logger.error("Image processing failed", error=e, image_path=str(image_path))
            raise

    async def upload_processed_images(self, image_paths: List[Path]) -> List[Dict[str, Any]]:
        """처리된 이미지들을 업로드 준비"""
        results = []

        for image_path in image_paths:
            try:
                # 최종 처리
                processed_path, metadata = await self.process_image_for_upload(image_path)

                # 파일 읽기
                async with aiofiles.open(processed_path, 'rb') as f:
                    content = await f.read()

                result = {
                    'filename': metadata.filename,
                    'content': content,
                    'content_type': metadata.content_type,
                    'size': metadata.size_bytes,
                    'dimensions': metadata.dimensions,
                    'gps_location': metadata.gps_location,
                    'creation_time': metadata.creation_time.isoformat() if metadata.creation_time else None
                }

                results.append(result)
                logger.info("Image upload prepared", filename=metadata.filename, size=metadata.size_bytes)

            except Exception as e:
                logger.error("Failed to prepare image for upload", error=e, image_path=str(image_path))
                # 개별 이미지 실패는 전체를 중단하지 않음
                continue

        return results

    async def cleanup_temp_files(self, max_age_hours: int = None):
        """임시 파일 정리"""
        if max_age_hours is None:
            max_age_hours = self.config.temp_file_retention_hours

        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        cleaned_count = 0

        try:
            for temp_file in self.temp_dir.glob("*"):
                try:
                    if datetime.fromtimestamp(temp_file.stat().st_mtime) < cutoff_time:
                        temp_file.unlink()
                        cleaned_count += 1
                except Exception:
                    continue  # 개별 파일 삭제 실패는 무시

            if cleaned_count > 0:
                logger.info("Temp files cleaned", count=cleaned_count, max_age_hours=max_age_hours)

        except Exception as e:
            logger.error("Temp file cleanup error", error=e)

    def get_metrics(self) -> Dict[str, Any]:
        """이미지 처리 메트릭 반환"""
        try:
            temp_file_count = len(list(self.temp_dir.glob("*")))
            temp_dir_size = sum(f.stat().st_size for f in self.temp_dir.glob("*") if f.is_file())

            return {
                "temp_file_count": temp_file_count,
                "temp_dir_size_mb": round(temp_dir_size / (1024 * 1024), 2),
                "config": {
                    "max_file_size_mb": self.config.max_file_size_mb,
                    "max_dimensions": self.config.max_dimensions,
                    "compression_quality": self.config.compression_quality,
                    "auto_resize": self.config.enable_auto_resize,
                    "auto_compress": self.config.enable_auto_compress
                },
                "http_client": self.http_client.get_metrics_summary()
            }
        except Exception as e:
            logger.error("Error getting image processor metrics", error=e)
            return {"error": str(e)}


class StabilizedImageProcessor:
    """운영/점검 스크립트 호환용 이미지 최적화 래퍼."""

    def __init__(self, config: ImageProcessingConfig = None):
        self.config = config or ImageProcessingConfig()
        self.processor = ImageProcessor(self.config)

    async def optimize_image_for_telegram(self, file_path: str) -> str:
        """텔레그램 업로드 기준으로 이미지 리사이즈/압축을 적용."""
        current_path = Path(file_path)
        metadata = await self.processor.extract_metadata(current_path)

        max_w, max_h = self.config.max_dimensions
        if metadata.dimensions[0] > max_w or metadata.dimensions[1] > max_h:
            current_path = await self.processor.resize_image(current_path)
            metadata = await self.processor.extract_metadata(current_path)

        size_threshold = int(self.config.max_file_size_mb * 0.8 * 1024 * 1024)
        if metadata.size_bytes > size_threshold:
            current_path = await self.processor.compress_image(
                current_path,
                quality=self.config.compression_quality,
            )

        return str(current_path)

    async def extract_metadata(self, file_path: str) -> Dict[str, Any]:
        """기존 스크립트 포맷(dict)으로 메타데이터를 반환."""
        metadata = await self.processor.extract_metadata(Path(file_path))
        return {
            "filename": metadata.filename,
            "size_bytes": metadata.size_bytes,
            "dimensions": metadata.dimensions,
            "format": metadata.format,
            "content_type": metadata.content_type,
            "gps_coordinates": metadata.gps_location,
            "has_exif": metadata.has_exif,
        }


# === 편의 함수들 ===

async def download_and_process_telegram_images(bot_token: str, file_ids: List[str],
                                             config: ImageProcessingConfig = None) -> List[Dict[str, Any]]:
    """텔레그램 이미지 다운로드 및 처리 (편의 함수)"""
    client = StabilizedTelegramImageClient(bot_token, config)

    try:
        processed_images = []

        for file_id in file_ids:
            try:
                # 다운로드
                image_path, metadata = await client.download_telegram_image(file_id)

                # 업로드 준비
                upload_data = await client.upload_processed_images([image_path])

                if upload_data:
                    processed_images.extend(upload_data)

                # 다운로드한 파일 정리
                if image_path.exists():
                    image_path.unlink()

            except Exception as e:
                logger.error("Failed to process telegram image", error=e, file_id=file_id)
                continue  # 개별 이미지 실패는 건너뛰기

        return processed_images

    finally:
        await client.close()


def create_image_processing_config(**kwargs) -> ImageProcessingConfig:
    """이미지 처리 설정 생성"""
    return ImageProcessingConfig(**kwargs)
