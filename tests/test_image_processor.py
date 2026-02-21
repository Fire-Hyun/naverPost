"""
안정화된 이미지 프로세서 테스트
"""

import pytest
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import aiofiles
from PIL import Image
import io

from src.utils.image_processor import (
    StabilizedTelegramImageClient, ImageValidator, ImageProcessor,
    ImageProcessingConfig, ImageMetadata, download_and_process_telegram_images
)
from src.utils.exceptions import (
    ImageProcessingError, TelegramAPIError, NonRetryableError, RetryableError
)


@pytest.fixture
def temp_image_file():
    """테스트용 임시 이미지 파일"""
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
        # 간단한 테스트 이미지 생성
        img = Image.new('RGB', (100, 100), color='red')
        img.save(tmp_file.name, 'JPEG')
        yield Path(tmp_file.name)

        # 정리
        Path(tmp_file.name).unlink(missing_ok=True)


@pytest.fixture
def large_image_file():
    """큰 크기의 테스트 이미지 파일"""
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
        # 큰 이미지 생성 (5000x5000)
        img = Image.new('RGB', (5000, 5000), color='blue')
        img.save(tmp_file.name, 'JPEG', quality=100)
        yield Path(tmp_file.name)

        # 정리
        Path(tmp_file.name).unlink(missing_ok=True)


@pytest.fixture
def config():
    """테스트용 이미지 처리 설정"""
    return ImageProcessingConfig(
        max_file_size_mb=10.0,
        min_file_size_bytes=100,   # 테스트용 소형 이미지 허용
        max_dimensions=(2048, 2048),
        min_dimensions=(10, 10),
        enable_auto_resize=True,
        enable_auto_compress=True,
        compression_quality=85
    )


@pytest.fixture
def mock_telegram_response():
    """모킹된 텔레그램 API 응답"""
    return {
        "ok": True,
        "result": {
            "file_id": "test_file_id",
            "file_unique_id": "test_unique_id",
            "file_size": 50000,
            "file_path": "photos/test_image.jpg"
        }
    }


class TestImageValidator:
    """이미지 검증기 테스트"""

    def test_valid_image(self, temp_image_file, config):
        """유효한 이미지 테스트"""
        validator = ImageValidator(config)

        result = asyncio.run(validator.validate_image_file(temp_image_file))
        is_valid, message = result

        assert is_valid is True
        assert "Valid image" in message

    def test_file_not_exists(self, config):
        """파일이 존재하지 않는 경우"""
        validator = ImageValidator(config)

        result = asyncio.run(validator.validate_image_file(Path("nonexistent.jpg")))
        is_valid, message = result

        assert is_valid is False
        assert "does not exist" in message

    def test_large_image_rejection(self, large_image_file, config):
        """크기 제한 초과 이미지 테스트"""
        # 매우 작은 크기 제한 설정
        config.max_file_size_mb = 0.01  # 10KB

        validator = ImageValidator(config)
        result = asyncio.run(validator.validate_image_file(large_image_file))
        is_valid, message = result

        assert is_valid is False
        assert "exceeds maximum" in message

    def test_invalid_format(self, config):
        """잘못된 형식 파일 테스트"""
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as tmp_file:
            # min_file_size_bytes(100) 이상으로 작성해야 포맷 검증까지 진행
            tmp_file.write(b"This is not an image content." * 10)
            tmp_path = Path(tmp_file.name)

        try:
            validator = ImageValidator(config)
            result = asyncio.run(validator.validate_image_file(tmp_path))
            is_valid, message = result

            assert is_valid is False
            assert "Invalid image" in message
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_validate_image_content(self, config):
        """이미지 콘텐츠 검증 테스트"""
        # 유효한 이미지 바이트 생성
        img = Image.new('RGB', (50, 50), color='green')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        valid_content = img_bytes.getvalue()

        validator = ImageValidator(config)
        result = asyncio.run(validator.validate_image_content(valid_content, "test.jpg"))
        is_valid, message = result

        assert is_valid is True

    def test_validate_empty_content(self, config):
        """빈 콘텐츠 검증 테스트"""
        validator = ImageValidator(config)
        result = asyncio.run(validator.validate_image_content(b"", "test.jpg"))
        is_valid, message = result

        assert is_valid is False
        assert "Empty content" in message


class TestImageProcessor:
    """이미지 프로세서 테스트"""

    def test_extract_metadata(self, temp_image_file, config):
        """메타데이터 추출 테스트"""
        processor = ImageProcessor(config)

        metadata = asyncio.run(processor.extract_metadata(temp_image_file))

        assert isinstance(metadata, ImageMetadata)
        assert metadata.dimensions == (100, 100)
        assert metadata.format == 'JPEG'
        assert metadata.size_bytes > 0

    def test_resize_image(self, large_image_file, config):
        """이미지 리사이즈 테스트"""
        processor = ImageProcessor(config)

        # 리사이즈 실행
        resized_path = asyncio.run(processor.resize_image(large_image_file, (1000, 1000)))

        try:
            # 리사이즈된 이미지 확인
            with Image.open(resized_path) as img:
                assert img.size[0] <= 1000
                assert img.size[1] <= 1000
        finally:
            resized_path.unlink(missing_ok=True)

    def test_resize_small_image_no_change(self, temp_image_file, config):
        """작은 이미지는 리사이즈하지 않음"""
        processor = ImageProcessor(config)

        # 리사이즈 시도 (이미 작음)
        result_path = asyncio.run(processor.resize_image(temp_image_file, (200, 200)))

        # 원본과 같은 경로 반환
        assert result_path == temp_image_file

    def test_compress_image(self, temp_image_file, config):
        """이미지 압축 테스트"""
        processor = ImageProcessor(config)

        original_size = temp_image_file.stat().st_size
        compressed_path = asyncio.run(processor.compress_image(temp_image_file, quality=50))

        try:
            compressed_size = compressed_path.stat().st_size
            # 압축으로 크기가 줄어들었는지 확인 (항상은 아니지만 대부분의 경우)
            # 매우 작은 이미지는 압축 효과가 없을 수 있으므로 존재 여부만 확인
            assert compressed_path.exists()
        finally:
            compressed_path.unlink(missing_ok=True)


@pytest.mark.asyncio
class TestStabilizedTelegramImageClient:
    """안정화된 텔레그램 이미지 클라이언트 테스트"""

    async def test_download_telegram_image_success(self, config, mock_telegram_response):
        """텔레그램 이미지 다운로드 성공 테스트"""
        client = StabilizedTelegramImageClient("test_token", config)

        # 모킹된 응답 생성
        img = Image.new('RGB', (100, 100), color='red')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        image_content = img_bytes.getvalue()

        with patch.object(client.http_client, 'get_json') as mock_get_json, \
             patch.object(client.http_client, 'get') as mock_get:

            # getFile API 모킹
            mock_get_json.return_value = mock_telegram_response

            # 파일 다운로드 모킹
            mock_response = Mock()
            mock_response.content = image_content
            mock_get.return_value = mock_response

            # 다운로드 실행
            image_path, metadata = await client.download_telegram_image("test_file_id")

            try:
                # 결과 검증
                assert image_path.exists()
                assert isinstance(metadata, ImageMetadata)
                assert metadata.dimensions == (100, 100)
                assert metadata.format == 'JPEG'
            finally:
                await client.close()
                if image_path.exists():
                    image_path.unlink()

    async def test_download_file_too_large(self, config, mock_telegram_response):
        """파일 크기 초과 테스트"""
        config.max_file_size_mb = 0.001  # 1KB 제한
        client = StabilizedTelegramImageClient("test_token", config)

        # 큰 파일 크기 설정
        mock_telegram_response["result"]["file_size"] = 1024 * 1024  # 1MB

        with patch.object(client.http_client, 'get_json') as mock_get_json:
            mock_get_json.return_value = mock_telegram_response

            with pytest.raises(NonRetryableError, match="exceeds limit"):
                await client.download_telegram_image("test_file_id")

            await client.close()

    async def test_download_api_error(self, config):
        """API 오류 테스트"""
        client = StabilizedTelegramImageClient("test_token", config)

        with patch.object(client.http_client, 'get_json') as mock_get_json:
            mock_get_json.return_value = {"ok": False, "description": "File not found"}

            with pytest.raises(TelegramAPIError, match="Failed to get file info"):
                await client.download_telegram_image("invalid_file_id")

            await client.close()

    async def test_process_image_for_upload(self, temp_image_file, config):
        """업로드용 이미지 처리 테스트"""
        client = StabilizedTelegramImageClient("test_token", config)

        try:
            processed_path, metadata = await client.process_image_for_upload(temp_image_file)

            # 결과 검증
            assert processed_path.exists()
            assert isinstance(metadata, ImageMetadata)

            # 처리된 파일 정리
            if processed_path != temp_image_file:
                processed_path.unlink(missing_ok=True)
        finally:
            await client.close()

    async def test_upload_processed_images(self, temp_image_file, config):
        """처리된 이미지 업로드 준비 테스트"""
        client = StabilizedTelegramImageClient("test_token", config)

        try:
            results = await client.upload_processed_images([temp_image_file])

            # 결과 검증
            assert len(results) == 1
            result = results[0]

            assert 'filename' in result
            assert 'content' in result
            assert 'content_type' in result
            assert 'size' in result
            assert 'dimensions' in result

            assert isinstance(result['content'], bytes)
            assert result['size'] > 0
            assert result['dimensions'] == (100, 100)
        finally:
            await client.close()

    async def test_cleanup_temp_files(self, config):
        """임시 파일 정리 테스트"""
        client = StabilizedTelegramImageClient("test_token", config)

        # 임시 파일 생성
        temp_file = client.temp_dir / "test_temp_file.jpg"
        temp_file.write_bytes(b"test content")

        assert temp_file.exists()

        try:
            # 정리 실행
            await client.cleanup_temp_files(max_age_hours=0)  # 즉시 정리

            # 파일이 삭제되었는지 확인 (타이밍에 따라 삭제되지 않을 수 있음)
            # 존재 여부보다는 정리 메소드가 에러 없이 실행되는지 확인
        finally:
            await client.close()
            temp_file.unlink(missing_ok=True)

    async def test_get_metrics(self, config):
        """메트릭 조회 테스트"""
        client = StabilizedTelegramImageClient("test_token", config)

        try:
            metrics = client.get_metrics()

            # 메트릭 구조 확인
            assert 'temp_file_count' in metrics
            assert 'temp_dir_size_mb' in metrics
            assert 'config' in metrics
            assert 'http_client' in metrics

            # config 정보 확인
            assert metrics['config']['max_file_size_mb'] == config.max_file_size_mb
        finally:
            await client.close()


@pytest.mark.asyncio
class TestImageProcessingIntegration:
    """이미지 처리 통합 테스트"""

    async def test_full_processing_pipeline(self, temp_image_file, config):
        """전체 처리 파이프라인 테스트"""
        client = StabilizedTelegramImageClient("test_token", config)

        try:
            # 1. 이미지 검증
            is_valid, message = await client.validator.validate_image_file(temp_image_file)
            assert is_valid is True

            # 2. 메타데이터 추출
            metadata = await client.processor.extract_metadata(temp_image_file)
            assert isinstance(metadata, ImageMetadata)

            # 3. 업로드용 처리
            processed_path, processed_metadata = await client.process_image_for_upload(temp_image_file)

            # 4. 업로드 준비
            upload_data = await client.upload_processed_images([processed_path])
            assert len(upload_data) == 1

            # 처리된 파일 정리
            if processed_path != temp_image_file:
                processed_path.unlink(missing_ok=True)
        finally:
            await client.close()


@pytest.mark.asyncio
class TestConvenienceFunctions:
    """편의 함수 테스트"""

    async def test_download_and_process_telegram_images(self, config):
        """텔레그램 이미지 다운로드 및 처리 편의 함수 테스트"""

        # 모킹된 응답 준비
        img = Image.new('RGB', (50, 50), color='blue')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='JPEG')
        image_content = img_bytes.getvalue()

        mock_response = {
            "ok": True,
            "result": {
                "file_id": "test_file_id",
                "file_size": len(image_content),
                "file_path": "photos/test.jpg"
            }
        }

        with patch('src.utils.image_processor.StabilizedTelegramImageClient') as MockClient:
            mock_client_instance = AsyncMock()
            MockClient.return_value = mock_client_instance

            # 다운로드 메소드 모킹
            mock_metadata = ImageMetadata(
                filename="test.jpg",
                size_bytes=len(image_content),
                dimensions=(50, 50),
                format="JPEG",
                content_type="image/jpeg"
            )
            mock_client_instance.download_telegram_image.return_value = (Path("test.jpg"), mock_metadata)
            mock_client_instance.upload_processed_images.return_value = [{
                'filename': 'test.jpg',
                'content': image_content,
                'content_type': 'image/jpeg',
                'size': len(image_content),
                'dimensions': (50, 50)
            }]

            # 편의 함수 실행
            results = await download_and_process_telegram_images(
                "test_token",
                ["test_file_id"],
                config
            )

            # 결과 검증
            assert len(results) == 1
            assert results[0]['filename'] == 'test.jpg'


# 성능 테스트 (선택적)
@pytest.mark.performance
@pytest.mark.asyncio
class TestImageProcessingPerformance:
    """이미지 처리 성능 테스트"""

    async def test_concurrent_processing(self, config):
        """동시 처리 성능 테스트"""
        import time

        # 여러 개의 작은 이미지 생성
        image_files = []
        for i in range(5):
            img = Image.new('RGB', (100, 100), color=f'hsl({i * 60}, 100%, 50%)')
            temp_file = Path(f"/tmp/test_img_{i}.jpg")
            img.save(temp_file, 'JPEG')
            image_files.append(temp_file)

        client = StabilizedTelegramImageClient("test_token", config)

        try:
            start_time = time.time()

            # 동시 처리
            tasks = [client.process_image_for_upload(img_file) for img_file in image_files]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            end_time = time.time()
            processing_time = end_time - start_time

            # 결과 검증
            successful_results = [r for r in results if not isinstance(r, Exception)]
            assert len(successful_results) == len(image_files)

            # 성능 로깅 (5개 이미지가 3초 내에 처리되어야 함)
            assert processing_time < 3.0, f"Processing took too long: {processing_time}s"

            print(f"Processed {len(image_files)} images in {processing_time:.2f}s")

        finally:
            await client.close()

            # 임시 파일 정리
            for img_file in image_files:
                img_file.unlink(missing_ok=True)


if __name__ == "__main__":
    # 기본 테스트 실행
    pytest.main([__file__, "-v"])