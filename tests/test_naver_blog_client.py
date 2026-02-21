#!/usr/bin/env python3
"""
네이버 블로그 안정화 클라이언트 테스트

포괄적인 단위 테스트 및 통합 테스트 스위트
- 모든 주요 실패 패턴에 대한 테스트
- TypeScript 분석 기반 시나리오 검증
- 에러 분류 및 재시도 로직 테스트
"""

import pytest
import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from typing import Dict, List, Any

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.naver_blog_client import (
    NaverBlogStabilizedClient, BlogPostData, TempSaveResult,
    FailureCategory, BlogPostStatus, SessionInfo,
    create_naver_blog_post, test_naver_blog_health
)
from src.utils.exceptions import (
    NaverBlogError, SessionError, EditorError, VerificationError,
    RetryableError, NonRetryableError
)


@pytest.fixture
def temp_artifacts_dir():
    """임시 아티팩트 디렉토리"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_playwright():
    """Playwright 모킹"""
    with patch('src.utils.naver_blog_client.async_playwright') as mock:
        playwright = AsyncMock()
        context = AsyncMock()
        page = AsyncMock()
        frame = AsyncMock()

        mock.return_value.start.return_value = playwright
        playwright.chromium.launch_persistent_context.return_value = context
        context.pages = [page]
        context.new_page.return_value = page
        # Playwright 동기 메서드들은 Mock으로 설정 (AsyncMock 아님)
        page.frame = Mock(return_value=frame)
        page.frames = Mock(return_value=[frame])
        page.url = Mock(return_value="https://blog.naver.com/test?Redirect=Write&")

        yield {
            'playwright': playwright,
            'context': context,
            'page': page,
            'frame': frame
        }


@pytest.fixture
def sample_post_data():
    """샘플 포스트 데이터"""
    return BlogPostData(
        title="테스트 블로그 포스트",
        body="이것은 테스트 본문입니다.\n두 번째 줄입니다.",
        image_paths=["/test/image1.jpg", "/test/image2.jpg"],
        place_name="강남역",
        tags=["테스트", "자동화"],
        category="일상"
    )


class TestNaverBlogStabilizedClient:
    """네이버 블로그 안정화 클라이언트 테스트"""

    def test_initialization(self, temp_artifacts_dir):
        """클라이언트 초기화 테스트"""
        client = NaverBlogStabilizedClient(
            artifacts_dir=temp_artifacts_dir,
            headless=True,
            timeout_seconds=10
        )

        assert client.artifacts_dir == temp_artifacts_dir
        assert client.headless is True
        assert client.timeout_seconds == 10
        assert client.max_retries == 3
        assert Path(temp_artifacts_dir).exists()

    @pytest.mark.asyncio
    async def test_error_classification(self, temp_artifacts_dir):
        """에러 분류 테스트"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)

        test_cases = [
            (Exception("timeout occurred"), "network_test", FailureCategory.NETWORK_ERROR),
            (Exception("login required"), "session_test", FailureCategory.SESSION_EXPIRED),
            (Exception("iframe not found"), "frame_test", FailureCategory.IFRAME_ACQUISITION),
            (Exception("contenteditable failed"), "editor_test", FailureCategory.EDITOR_INTERACTION),
            (Exception("temp save failed"), "save_test", FailureCategory.TEMP_SAVE_VERIFICATION),
            (Exception("place not found"), "place_test", FailureCategory.PLACE_ATTACHMENT),
            (Exception("image upload error"), "image_test", FailureCategory.IMAGE_UPLOAD),
            (Exception("rate limit exceeded"), "rate_test", FailureCategory.RATE_LIMIT),
            (Exception("selector_not_found"), "selector_test", FailureCategory.DOM_STRUCTURE_CHANGE),
            (Exception("unknown error"), "unknown_test", FailureCategory.UNKNOWN)
        ]

        for error, operation, expected_category in test_cases:
            category = await client._classify_error(error, operation)
            assert category == expected_category, f"Failed for {operation}: {error}"

    @pytest.mark.asyncio
    async def test_login_status_check_success(self, mock_playwright, temp_artifacts_dir):
        """로그인 상태 확인 성공 테스트"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)
        mock_page = mock_playwright['page']

        # 네이버 메인 페이지 시뮬레이션
        mock_page.url.return_value = "https://www.naver.com/"
        client.page = mock_page

        result = await client.check_login_status()
        assert result is True
        assert client.session_info.is_logged_in is True
        assert 'main_page' in client.session_info.login_indicators_found

    @pytest.mark.asyncio
    async def test_login_status_check_blog_editor(self, mock_playwright, temp_artifacts_dir):
        """블로그 에디터 로그인 상태 확인 테스트"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)
        mock_page = mock_playwright['page']

        # 블로그 글쓰기 페이지 + 에디터 존재
        mock_page.url.return_value = "https://blog.naver.com/test?Redirect=Write&"
        mock_page.query_selector.return_value = AsyncMock()  # 에디터 존재
        client.page = mock_page

        result = await client.check_login_status()
        assert result is True
        assert client.session_info.is_logged_in is True

    @pytest.mark.asyncio
    async def test_login_status_check_logout_detected(self, mock_playwright, temp_artifacts_dir):
        """로그아웃 상태 감지 테스트"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)
        mock_page = mock_playwright['page']

        # 로그인 페이지
        mock_page.url.return_value = "https://nid.naver.com/nidlogin"
        mock_page.query_selector.side_effect = lambda sel: AsyncMock() if sel == '#id' else None
        client.page = mock_page

        result = await client.check_login_status()
        assert result is False
        assert client.session_info.is_logged_in is False

    @pytest.mark.asyncio
    async def test_editor_frame_acquisition_success(self, mock_playwright, temp_artifacts_dir):
        """에디터 프레임 획득 성공 테스트"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)
        mock_page = mock_playwright['page']
        mock_frame = mock_playwright['frame']

        # mainFrame 프레임 존재
        mock_page.wait_for_selector.return_value = None
        mock_page.frame.return_value = mock_frame
        client.page = mock_page

        result = await client.acquire_editor_frame()
        assert result is True
        assert client.editor_frame == mock_frame

    @pytest.mark.asyncio
    async def test_editor_frame_acquisition_fallback(self, mock_playwright, temp_artifacts_dir):
        """에디터 프레임 획득 폴백 테스트"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)
        mock_page = mock_playwright['page']
        mock_frame = mock_playwright['frame']

        # mainFrame 실패, URL 매칭 성공 (PlaywrightTimeoutError로 전략 1 실패 시뮬레이션)
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        mock_page.wait_for_selector.side_effect = PlaywrightTimeoutError("timeout")
        mock_page.frame.return_value = None
        mock_frame.url = "https://blog.naver.com/PostWriteForm"
        mock_page.frames.return_value = [mock_frame]
        client.page = mock_page

        result = await client.acquire_editor_frame()
        assert result is True
        assert client.editor_frame == mock_frame

    @pytest.mark.asyncio
    async def test_editor_frame_acquisition_failure(self, mock_playwright, temp_artifacts_dir):
        """에디터 프레임 획득 실패 테스트"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)
        mock_page = mock_playwright['page']

        # 모든 전략 실패
        mock_page.wait_for_selector.side_effect = Exception("timeout")
        mock_page.frame.return_value = None
        mock_page.frames.return_value = []
        client.page = mock_page

        with patch.object(client, '_capture_failure_evidence', return_value=[]):
            with pytest.raises(EditorError):
                await client.acquire_editor_frame()

    @pytest.mark.asyncio
    async def test_title_input_success(self, mock_playwright, temp_artifacts_dir):
        """제목 입력 성공 테스트"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)
        mock_page = mock_playwright['page']
        mock_frame = mock_playwright['frame']

        # 제목 입력 성공 시뮬레이션
        mock_element = AsyncMock()
        mock_frame.query_selector.return_value = mock_element
        mock_frame.evaluate.return_value = "테스트 제목"

        client.page = mock_page
        client.editor_frame = mock_frame

        with patch.object(client, '_dismiss_popups'):
            result = await client.input_title("테스트 제목")
            assert result is True

    @pytest.mark.asyncio
    async def test_title_input_failure(self, mock_playwright, temp_artifacts_dir):
        """제목 입력 실패 테스트"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)
        mock_page = mock_playwright['page']
        mock_frame = mock_playwright['frame']

        # 모든 셀렉터 실패
        mock_frame.query_selector.return_value = None

        client.page = mock_page
        client.editor_frame = mock_frame

        with patch.object(client, '_dismiss_popups'):
            with patch.object(client, '_capture_failure_evidence', return_value=[]):
                with pytest.raises(EditorError):
                    await client.input_title("테스트 제목")

    @pytest.mark.asyncio
    async def test_body_input_success_strategy1(self, mock_playwright, temp_artifacts_dir):
        """본문 입력 성공 테스트 (전략 1)"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)
        mock_page = mock_playwright['page']
        mock_frame = mock_playwright['frame']

        # 제목 영역에서 Enter로 본문 이동 전략
        mock_title_element = AsyncMock()
        mock_frame.query_selector.return_value = mock_title_element

        client.page = mock_page
        client.editor_frame = mock_frame

        result = await client.input_body("테스트 본문\n두 번째 줄")
        assert result is True

    @pytest.mark.asyncio
    async def test_temp_save_verification_toast_success(self, mock_playwright, temp_artifacts_dir):
        """임시저장 검증 - 토스트 메시지 성공"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)
        mock_page = mock_playwright['page']
        mock_frame = mock_playwright['frame']

        client.page = mock_page
        client.editor_frame = mock_frame

        # 토스트 메시지 성공 시뮬레이션
        with patch.object(client, '_verify_toast_message', return_value={"success": True, "message": "임시저장 완료"}):
            with patch.object(client, '_verify_draft_list', return_value={"success": False}):
                result = await client.verify_temp_save("테스트 제목")

                assert result.success is True
                assert result.verified_via == "toast"
                assert result.toast_message == "임시저장 완료"

    @pytest.mark.asyncio
    async def test_temp_save_verification_draft_success(self, mock_playwright, temp_artifacts_dir):
        """임시저장 검증 - 임시글함 성공"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)
        mock_page = mock_playwright['page']
        mock_frame = mock_playwright['frame']

        client.page = mock_page
        client.editor_frame = mock_frame

        # 임시글함 검증 성공 시뮬레이션
        with patch.object(client, '_verify_toast_message', return_value={"success": False}):
            with patch.object(client, '_verify_draft_list', return_value={"success": True, "title": "테스트 제목"}):
                result = await client.verify_temp_save("테스트 제목")

                assert result.success is True
                assert result.verified_via == "draft_list"
                assert result.draft_found is True
                assert result.draft_title == "테스트 제목"

    @pytest.mark.asyncio
    async def test_temp_save_verification_both_success(self, mock_playwright, temp_artifacts_dir):
        """임시저장 검증 - 토스트 + 임시글함 모두 성공"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)
        mock_page = mock_playwright['page']
        mock_frame = mock_playwright['frame']

        client.page = mock_page
        client.editor_frame = mock_frame

        with patch.object(client, '_verify_toast_message', return_value={"success": True, "message": "저장됨"}):
            with patch.object(client, '_verify_draft_list', return_value={"success": True, "title": "테스트"}):
                result = await client.verify_temp_save("테스트 제목")

                assert result.success is True
                assert result.verified_via == "both"

    @pytest.mark.asyncio
    async def test_temp_save_verification_failure(self, mock_playwright, temp_artifacts_dir):
        """임시저장 검증 실패 테스트"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)
        mock_page = mock_playwright['page']
        mock_frame = mock_playwright['frame']

        client.page = mock_page
        client.editor_frame = mock_frame

        with patch.object(client, '_verify_toast_message', return_value={"success": False}):
            with patch.object(client, '_verify_draft_list', return_value={"success": False}):
                with patch.object(client, '_capture_failure_evidence', return_value=["screenshot.png"]):
                    result = await client.verify_temp_save("테스트 제목")

                    assert result.success is False
                    assert result.verified_via == "none"
                    assert result.error_message == "토스트/임시글함 검증 모두 실패"
                    assert result.failure_category == FailureCategory.TEMP_SAVE_VERIFICATION

    def test_success_message_patterns(self, temp_artifacts_dir):
        """성공 메시지 패턴 테스트"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)

        success_messages = [
            "임시저장 완료",
            "임시 저장 완료",
            "저장 완료",
            "저장되었습니다",
            "임시저장됨",
            "글이 저장",
            "포스트 저장"
        ]

        for msg in success_messages:
            assert client._is_success_message(msg), f"Failed to detect success: {msg}"

    def test_failure_message_patterns(self, temp_artifacts_dir):
        """실패 메시지 패턴 테스트"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)

        failure_messages = [
            "저장 실패",
            "저장 오류",
            "저장 불가",
            "네트워크 오류",
            "다시 시도"
        ]

        for msg in failure_messages:
            assert client._is_failure_message(msg), f"Failed to detect failure: {msg}"

    def test_title_matching(self, temp_artifacts_dir):
        """제목 매칭 테스트"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)

        expected_title = "테스트 블로그 포스트 제목입니다"
        candidates = [
            "테스트 블로그 포스트 제목입니다",  # 정확한 매치
            "테스트 블로그 포스트 제목입니다 (임시저장)",  # 후보에 추가 텍스트
            "테스트 블로그 어쩌고",  # 부분 매치
            "완전히 다른 제목",  # 매치 안됨
            ""  # 빈 문자열
        ]

        results = [
            client._match_expected_title(expected_title, candidates),
            client._match_expected_title("테스트 블로그", candidates[:3]),
            client._match_expected_title("", candidates),
            client._match_expected_title(expected_title, ["완전히 다른 제목"])
        ]

        assert results[0] in ["테스트 블로그 포스트 제목입니다", "테스트 블로그 포스트 제목입니다 (임시저장)"]
        assert results[1] is not None
        assert results[2] is None
        assert results[3] is None

    @pytest.mark.asyncio
    async def test_image_upload_no_images(self, mock_playwright, temp_artifacts_dir):
        """이미지 업로드 - 이미지 없음"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)
        client.page = mock_playwright['page']
        client.editor_frame = mock_playwright['frame']

        result = await client.upload_images([])
        assert result is True

    @pytest.mark.asyncio
    async def test_image_upload_success(self, mock_playwright, temp_artifacts_dir):
        """이미지 업로드 성공"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)
        client.page = mock_playwright['page']
        client.editor_frame = mock_playwright['frame']

        with patch.object(client, '_click_photo_button', return_value=True):
            with patch.object(client, '_upload_image_files', return_value=True):
                client.editor_frame.wait_for_selector.return_value = None
                result = await client.upload_images(["/test/image.jpg"])
                assert result is True

    @pytest.mark.asyncio
    async def test_place_attachment_success(self, mock_playwright, temp_artifacts_dir):
        """장소 첨부 성공"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)
        client.page = mock_playwright['page']
        client.editor_frame = mock_playwright['frame']

        with patch.object(client, '_click_place_button', return_value=True):
            with patch.object(client, '_search_place', return_value=True):
                with patch.object(client, '_select_first_place_result', return_value=True):
                    with patch.object(client, '_confirm_place_selection', return_value=True):
                        result = await client.attach_place("강남역")
                        assert result is True

    @pytest.mark.asyncio
    async def test_create_temp_save_post_success(self, mock_playwright, temp_artifacts_dir, sample_post_data):
        """임시저장 포스트 생성 성공 테스트"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)

        # 모든 단계 성공 시뮬레이션
        with patch.object(client, 'check_login_status', return_value=True):
            with patch.object(client, 'navigate_to_write_page', return_value=True):
                with patch.object(client, 'acquire_editor_frame', return_value=True):
                    with patch.object(client, 'wait_for_editor_ready', return_value=True):
                        with patch.object(client, 'input_title', return_value=True):
                            with patch.object(client, 'input_body', return_value=True):
                                with patch.object(client, 'upload_images', return_value=True):
                                    with patch.object(client, 'attach_place', return_value=True):
                                        with patch.object(client, 'click_temp_save', return_value=True):
                                            with patch.object(client, 'verify_temp_save') as mock_verify:
                                                mock_verify.return_value = TempSaveResult(
                                                    success=True,
                                                    verified_via="both"
                                                )

                                                with patch.object(client, 'browser_session'):
                                                    result = await client.create_temp_save_post(sample_post_data)

                                                    assert result.success is True
                                                    assert result.verified_via == "both"

    @pytest.mark.asyncio
    async def test_create_temp_save_post_session_failure(self, mock_playwright, temp_artifacts_dir, sample_post_data):
        """임시저장 포스트 생성 - 세션 실패"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)

        with patch.object(client, 'check_login_status', return_value=False):
            with patch.object(client, '_capture_failure_evidence', return_value=["screenshot.png"]):
                with patch.object(client, 'browser_session'):
                    result = await client.create_temp_save_post(sample_post_data)

                    assert result.success is False
                    assert result.failure_category in [
                        FailureCategory.SESSION_EXPIRED,
                        FailureCategory.UNKNOWN
                    ]

    @pytest.mark.asyncio
    async def test_create_temp_save_post_editor_failure(self, mock_playwright, temp_artifacts_dir, sample_post_data):
        """임시저장 포스트 생성 - 에디터 실패"""
        client = NaverBlogStabilizedClient(artifacts_dir=temp_artifacts_dir)

        with patch.object(client, 'check_login_status', return_value=True):
            with patch.object(client, 'navigate_to_write_page', return_value=True):
                with patch.object(client, 'acquire_editor_frame', side_effect=EditorError("Frame not found")):
                    with patch.object(client, '_capture_failure_evidence', return_value=[]):
                        with patch.object(client, 'browser_session'):
                            result = await client.create_temp_save_post(sample_post_data)

                            assert result.success is False
                            assert "Frame not found" in result.error_message


class TestConvenienceFunctions:
    """편의 함수 테스트"""

    @pytest.mark.asyncio
    async def test_create_naver_blog_post_function(self):
        """create_naver_blog_post 함수 테스트"""
        with patch('src.utils.naver_blog_client.NaverBlogStabilizedClient') as MockClient:
            mock_client = MockClient.return_value
            mock_client.create_temp_save_post = AsyncMock(return_value=TempSaveResult(
                success=True,
                verified_via="toast"
            ))

            result = await create_naver_blog_post(
                title="테스트",
                body="내용",
                headless=True
            )

            assert result.success is True
            assert result.verified_via == "toast"
            MockClient.assert_called_once()

    @pytest.mark.asyncio
    async def test_naver_blog_health_check(self):
        """네이버 블로그 헬스체크 테스트"""
        with patch('src.utils.naver_blog_client.NaverBlogStabilizedClient') as MockClient:
            mock_client = MockClient.return_value
            mock_client.check_login_status = AsyncMock(return_value=True)
            mock_client.navigate_to_write_page = AsyncMock(return_value=True)
            mock_client.acquire_editor_frame = AsyncMock(return_value=True)
            mock_client.wait_for_editor_ready = AsyncMock(return_value=True)
            mock_client.session_info = SessionInfo(
                user_data_dir="/test",
                is_logged_in=True,
                blog_id="test"
            )
            # async context manager 올바른 mock 설정
            mock_cm = AsyncMock()
            mock_cm.__aenter__ = AsyncMock(return_value=None)
            mock_cm.__aexit__ = AsyncMock(return_value=False)
            mock_client.browser_session = Mock(return_value=mock_cm)

            health = await test_naver_blog_health()

            assert health["login_status"] is True
            assert health["editor_accessible"] is True
            assert health["session_info"]["is_logged_in"] is True
            assert len(health["errors"]) == 0


class TestBlogPostData:
    """BlogPostData 모델 테스트"""

    def test_blog_post_data_initialization(self):
        """BlogPostData 초기화 테스트"""
        data = BlogPostData(title="제목", body="내용")

        assert data.title == "제목"
        assert data.body == "내용"
        assert data.image_paths == []
        assert data.tags == []
        assert data.place_name is None
        assert data.visibility == "public"

    def test_blog_post_data_full(self):
        """BlogPostData 전체 데이터 테스트"""
        data = BlogPostData(
            title="테스트 제목",
            body="테스트 내용",
            image_paths=["/img1.jpg", "/img2.jpg"],
            place_name="강남역",
            tags=["태그1", "태그2"],
            category="일상",
            visibility="private"
        )

        assert len(data.image_paths) == 2
        assert len(data.tags) == 2
        assert data.place_name == "강남역"
        assert data.category == "일상"
        assert data.visibility == "private"


class TestTempSaveResult:
    """TempSaveResult 모델 테스트"""

    def test_temp_save_result_success(self):
        """TempSaveResult 성공 케이스 테스트"""
        result = TempSaveResult(
            success=True,
            verified_via="both",
            toast_message="저장 완료",
            draft_found=True,
            draft_title="테스트 제목"
        )

        assert result.success is True
        assert result.verified_via == "both"
        assert result.toast_message == "저장 완료"
        assert result.draft_found is True
        assert result.draft_title == "테스트 제목"
        assert result.screenshots == []

    def test_temp_save_result_failure(self):
        """TempSaveResult 실패 케이스 테스트"""
        result = TempSaveResult(
            success=False,
            error_message="검증 실패",
            failure_category=FailureCategory.TEMP_SAVE_VERIFICATION,
            screenshots=["fail1.png", "fail2.png"]
        )

        assert result.success is False
        assert result.error_message == "검증 실패"
        assert result.failure_category == FailureCategory.TEMP_SAVE_VERIFICATION
        assert len(result.screenshots) == 2


# 통합 테스트 (실제 브라우저 필요)
@pytest.mark.integration
class TestNaverBlogIntegration:
    """네이버 블로그 통합 테스트 (실제 환경)"""

    @pytest.mark.skipif(not __import__('os').environ.get('RUN_INTEGRATION_TESTS'), reason="Integration tests disabled")
    @pytest.mark.asyncio
    async def test_real_login_status_check(self, temp_artifacts_dir):
        """실제 로그인 상태 확인 테스트"""
        client = NaverBlogStabilizedClient(
            artifacts_dir=temp_artifacts_dir,
            headless=True
        )

        async with client.browser_session():
            await client.navigate_to_write_page()
            login_status = await client.check_login_status()

            # 로그인 상태에 따라 결과 확인
            if login_status:
                print("✅ 로그인 상태 확인됨")
                assert client.session_info.is_logged_in is True
            else:
                print("⚠️ 로그아웃 상태 - 로그인 필요")
                assert client.session_info.is_logged_in is False

    @pytest.mark.skipif(not __import__('os').environ.get('RUN_INTEGRATION_TESTS'), reason="Integration tests disabled")
    @pytest.mark.asyncio
    async def test_real_health_check(self):
        """실제 헬스체크 테스트"""
        health = await test_naver_blog_health()

        print(f"Health check result: {json.dumps(health, indent=2, ensure_ascii=False)}")

        assert "login_status" in health
        assert "editor_accessible" in health
        assert "session_info" in health
        assert isinstance(health["errors"], list)


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
    config.addinivalue_line(
        "markers",
        "integration: mark test as integration test requiring real browser"
    )


if __name__ == "__main__":
    # 단위 테스트 실행
    pytest.main([__file__, "-v", "--tb=short"])