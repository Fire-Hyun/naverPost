#!/usr/bin/env python3
"""
네이버 블로그 안정화 클라이언트
TypeScript 기반 naver-poster 분석을 통한 Python 구현

주요 안정화 기능:
- 다중 전략 기반 DOM 탐색
- 포괄적 에러 분류 및 재시도 로직
- 세션 관리 및 자동 복구
- 임시저장 검증 및 실패 복구
"""

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple
from contextlib import asynccontextmanager
from enum import Enum

import aiofiles
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Frame, TimeoutError as PlaywrightTimeoutError

from .exceptions import (
    NaverBlogError, RetryableError, NonRetryableError, RateLimitError,
    SessionError, EditorError, VerificationError, EnvironmentConfigError
)
from .http_client import StabilizedHTTPClient
from .structured_logger import get_logger, log_context

logger = get_logger("naver_blog_client")


class BlogPostStatus(Enum):
    """블로그 포스트 상태"""
    DRAFT = "draft"
    TEMP_SAVED = "temp_saved"
    PUBLISHED = "published"
    FAILED = "failed"


class FailureCategory(Enum):
    """실패 카테고리 분류"""
    SESSION_EXPIRED = "session_expired"
    IFRAME_ACQUISITION = "iframe_acquisition"
    EDITOR_INTERACTION = "editor_interaction"
    TEMP_SAVE_VERIFICATION = "temp_save_verification"
    PLACE_ATTACHMENT = "place_attachment"
    IMAGE_UPLOAD = "image_upload"
    NETWORK_ERROR = "network_error"
    DOM_STRUCTURE_CHANGE = "dom_structure_change"
    RATE_LIMIT = "rate_limit"
    ENV_NO_XSERVER = "env_no_xserver"
    PLAYWRIGHT_LAUNCH_FAILED = "playwright_launch_failed"
    NAVER_AUTH_FAILED = "naver_auth_failed"
    NAVER_UPLOAD_FAILED = "naver_upload_failed"
    NETWORK_DNS = "network_dns"
    UNKNOWN = "unknown"


@dataclass
class BlogPostData:
    """블로그 포스트 데이터"""
    title: str
    body: str
    image_paths: List[str] = None
    place_name: Optional[str] = None
    tags: List[str] = None
    category: Optional[str] = None
    visibility: str = "public"  # public, protected, private

    def __post_init__(self):
        if self.image_paths is None:
            self.image_paths = []
        if self.tags is None:
            self.tags = []


@dataclass
class TempSaveResult:
    """임시저장 결과"""
    success: bool
    verified_via: str = "none"  # toast, draft_list, both, none
    toast_message: Optional[str] = None
    draft_found: bool = False
    draft_title: Optional[str] = None
    error_message: Optional[str] = None
    screenshots: List[str] = None
    failure_category: FailureCategory = FailureCategory.UNKNOWN

    def __post_init__(self):
        if self.screenshots is None:
            self.screenshots = []


@dataclass
class SessionInfo:
    """세션 정보"""
    user_data_dir: str
    is_logged_in: bool
    blog_id: Optional[str] = None
    last_activity: Optional[float] = None
    login_indicators_found: List[str] = None

    def __post_init__(self):
        if self.login_indicators_found is None:
            self.login_indicators_found = []


class NaverBlogStabilizedClient:
    """
    네이버 블로그 안정화 클라이언트

    TypeScript naver-poster 분석을 기반으로 한 포괄적 안정화 구현:
    - 다중 전략 기반 DOM 탐색
    - 세션 관리 및 자동 복구
    - 임시저장 검증 및 재시도
    - 포괄적 에러 분류 및 처리
    """

    # 네이버 로그인 상태 인디케이터 (TypeScript 분석 기반)
    LOGIN_INDICATORS = [
        'iframe#mainFrame',           # 로그인된 블로그 메인
        '.se-toolbar',                # SmartEditor 툴바
        '.blog_author',               # 블로그 작성자 정보
        'a[href*="logout"]',          # 로그아웃 링크
        '[data-clk="gnb.login"]',     # 네이버 메인 로그인 상태
        '.MyView',                    # 네이버 메인 마이뷰
        '.area_profile',              # 프로필 영역
        'a[href*="naver.com/profile"]' # 프로필 링크
    ]

    LOGOUT_INDICATORS = [
        '#id',                        # 로그인 폼 ID 입력
        '.btn_login',                 # 로그인 버튼
        'input[name="id"]',           # 로그인 ID 필드
        '.login_title'                # 로그인 페이지 제목
    ]

    @staticmethod
    def _resolve_headless(headless: Optional[bool] = None) -> bool:
        """환경변수 기반 headless 모드 결정 및 XServer 감지"""
        if headless is not None:
            resolved = headless
        else:
            env_val = os.environ.get("PLAYWRIGHT_HEADLESS", os.environ.get("HEADLESS", "true"))
            resolved = env_val.lower() == "true"

        # headed 모드 요청 시 DISPLAY 확인
        if not resolved:
            display = os.environ.get("DISPLAY")
            wayland = os.environ.get("WAYLAND_DISPLAY")
            if not display and not wayland:
                logger.warning(
                    "[ENV_NO_XSERVER] headed 모드 요청이나 DISPLAY 미설정. "
                    "headless=true로 자동 폴백합니다. "
                    "해결: HEADLESS=true 또는 xvfb-run -a 사용"
                )
                resolved = True

        return resolved

    def __init__(
        self,
        user_data_dir: Optional[str] = None,
        headless: Optional[bool] = None,
        slow_mo: int = 0,
        artifacts_dir: Optional[str] = None,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        enable_logging: bool = True
    ):
        self.user_data_dir = user_data_dir or "./.secrets/naver_user_data_dir"
        self.headless = self._resolve_headless(headless)
        self.slow_mo = slow_mo
        self.artifacts_dir = artifacts_dir or "./artifacts"
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.enable_logging = enable_logging

        # 내부 상태
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.editor_frame: Optional[Frame] = None
        self.session_info: Optional[SessionInfo] = SessionInfo(
            user_data_dir=self.user_data_dir, is_logged_in=False
        )
        self.operation_id: str = str(uuid.uuid4())[:8]

        # HTTP 클라이언트 (API 호출용)
        self.http_client = StabilizedHTTPClient(service_name="naver_blog")

        # 아티팩트 디렉토리 생성
        Path(self.artifacts_dir).mkdir(parents=True, exist_ok=True)

        if enable_logging:
            logger.info("NaverBlogStabilizedClient initialized",
                       operation_id=self.operation_id,
                       user_data_dir=self.user_data_dir,
                       headless=self.headless)

    @asynccontextmanager
    async def browser_session(self):
        """브라우저 세션 컨텍스트 매니저"""
        playwright = None
        try:
            playwright = await async_playwright().start()

            # Persistent context 생성 (세션 유지)
            Path(self.user_data_dir).mkdir(parents=True, exist_ok=True)

            self.context = await playwright.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                slow_mo=self.slow_mo,
                viewport={'width': 1400, 'height': 900},
                locale='ko-KR',
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                args=['--disable-blink-features=AutomationControlled']
            )

            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

            # 세션 정보 초기화
            self.session_info = SessionInfo(
                user_data_dir=self.user_data_dir,
                is_logged_in=False,
                last_activity=time.time()
            )

            logger.info("Browser session started", operation_id=self.operation_id)

            yield

        except Exception as e:
            error_msg = str(e).lower()
            # XServer/headed 관련 크래시 선제 감지
            if "xserver" in error_msg or ("headless" in error_msg and "xvfb" in error_msg) or "target page, context or browser has been closed" in error_msg:
                logger.error(
                    "[ENV_NO_XSERVER] 브라우저가 즉시 종료됨. "
                    "headed 모드에서 XServer 없이 실행한 것으로 판단됩니다.",
                    operation_id=self.operation_id
                )
                raise EnvironmentConfigError(
                    "브라우저 실행 실패: XServer 없는 환경에서 headed 모드 실행 불가. "
                    "HEADLESS=true로 설정하거나 xvfb-run -a 로 실행하세요.",
                    error_code=EnvironmentConfigError.ENV_NO_XSERVER,
                    resolution="HEADLESS=true 환경변수 설정 또는 xvfb-run -a 사용"
                ) from e
            logger.error("Browser session error", operation_id=self.operation_id, error=e)
            raise
        finally:
            if self.context:
                await self.context.close()
            if playwright:
                await playwright.stop()

            logger.info("Browser session closed", operation_id=self.operation_id)

    async def _classify_error(self, error: Exception, operation: str, context: Dict[str, Any] = None) -> FailureCategory:
        """에러 분류 및 카테고리 할당"""
        context = context or {}
        error_str = str(error).lower()

        # 네트워크 관련 에러
        if any(keyword in error_str for keyword in ['timeout', 'network', 'connection', 'dns']):
            return FailureCategory.NETWORK_ERROR

        # 세션 관련 에러
        if any(keyword in error_str for keyword in ['login', 'session', 'expired', 'logout']):
            return FailureCategory.SESSION_EXPIRED

        # iframe/DOM 관련 에러
        if any(keyword in error_str for keyword in ['frame', 'iframe', 'mainframe']):
            return FailureCategory.IFRAME_ACQUISITION

        # 에디터 상호작용 에러
        if any(keyword in error_str for keyword in ['contenteditable', 'toolbar', 'editor']):
            return FailureCategory.EDITOR_INTERACTION

        # 임시저장 관련 에러
        if any(keyword in error_str for keyword in ['temp', 'save', 'draft', 'toast']):
            return FailureCategory.TEMP_SAVE_VERIFICATION

        # 장소 첨부 에러
        if any(keyword in error_str for keyword in ['place', 'map', '장소', '지도']):
            return FailureCategory.PLACE_ATTACHMENT

        # 이미지 업로드 에러
        if any(keyword in error_str for keyword in ['image', 'upload', 'photo', '사진']):
            return FailureCategory.IMAGE_UPLOAD

        # Rate limit 에러
        if any(keyword in error_str for keyword in ['rate', 'limit', 'throttle']):
            return FailureCategory.RATE_LIMIT

        # DOM 구조 변경 (셀렉터 탐지 실패)
        if operation.endswith('_not_found') or 'selector' in error_str:
            return FailureCategory.DOM_STRUCTURE_CHANGE

        return FailureCategory.UNKNOWN

    async def _capture_failure_evidence(
        self,
        operation: str,
        category: FailureCategory,
        additional_context: Dict[str, Any] = None
    ) -> List[str]:
        """실패 증거 수집 (스크린샷, HTML 덤프, 메타데이터)"""
        if not self.page:
            return []

        screenshots = []
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        failure_dir = Path(self.artifacts_dir) / "failures" / f"{timestamp}_{operation}_{category.value}"
        failure_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. 메인 페이지 스크린샷
            main_screenshot = failure_dir / "01_main_page.png"
            await self.page.screenshot(path=str(main_screenshot), full_page=True)
            screenshots.append(str(main_screenshot))

            # 2. HTML 덤프
            html_dump = failure_dir / "02_page_content.html"
            content = await self.page.content()
            async with aiofiles.open(html_dump, 'w', encoding='utf-8') as f:
                await f.write(content)

            # 3. iframe 스크린샷 (에디터가 있는 경우)
            if self.editor_frame:
                try:
                    iframe_screenshot = failure_dir / "03_iframe_editor.png"
                    await self.editor_frame.screenshot(path=str(iframe_screenshot))
                    screenshots.append(str(iframe_screenshot))
                except:
                    pass

            # 4. 실패 보고서 JSON
            report = {
                "timestamp": timestamp,
                "operation_id": self.operation_id,
                "operation": operation,
                "failure_category": category.value,
                "page_url": self.page.url(),
                "session_info": self.session_info.__dict__ if self.session_info else None,
                "additional_context": additional_context or {},
                "screenshots": screenshots
            }

            report_path = failure_dir / "00_failure_report.json"
            async with aiofiles.open(report_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(report, indent=2, ensure_ascii=False))

            logger.error("Failure evidence captured",
                        operation=operation,
                        category=category.value,
                        evidence_dir=str(failure_dir),
                        screenshots=len(screenshots))

        except Exception as e:
            logger.error("Failed to capture evidence", operation=operation, error=e)

        return screenshots

    async def check_login_status(self) -> bool:
        """로그인 상태 확인"""
        if not self.page:
            return False

        with log_context(operation="check_login_status", operation_id=self.operation_id):
            try:
                url = self.page.url()
                logger.info("Checking login status", url=url)

                # 네이버 메인 페이지면 로그인 성공
                if url in ['https://www.naver.com/', 'https://naver.com/']:
                    logger.info("Naver main page detected - logged in")
                    self._update_session_info(is_logged_in=True, indicators=['main_page'])
                    return True

                # 블로그 글쓰기 페이지에서 에디터 확인
                if 'blog.naver.com' in url and 'Write' in url:
                    editor_exists = await self.page.query_selector('iframe[id*="frame"]') or await self.page.query_selector('.se-toolbar')
                    if editor_exists:
                        logger.info("Blog editor detected - logged in")
                        self._update_session_info(is_logged_in=True, indicators=['blog_editor'])
                        return True

                # 로그아웃 상태 인디케이터 확인
                for selector in self.LOGOUT_INDICATORS:
                    element = await self.page.query_selector(selector)
                    if element:
                        logger.warning("Logout indicator detected", selector=selector)
                        self._update_session_info(is_logged_in=False, indicators=[f"logout:{selector}"])
                        return False

                # 로그인 상태 인디케이터 확인
                found_indicators = []
                for selector in self.LOGIN_INDICATORS:
                    element = await self.page.query_selector(selector)
                    if element:
                        found_indicators.append(selector)

                if found_indicators:
                    logger.info("Login indicators found", indicators=found_indicators)
                    self._update_session_info(is_logged_in=True, indicators=found_indicators)
                    return True

                # 로그인 페이지 URL 확인
                if any(domain in url for domain in ['nid.naver.com/nidlogin', 'logins.naver.com']):
                    logger.warning("Login page URL detected")
                    self._update_session_info(is_logged_in=False, indicators=['login_url'])
                    return False

                logger.warning("Login status unclear - assuming not logged in")
                self._update_session_info(is_logged_in=False, indicators=[])
                return False

            except Exception as e:
                logger.error("Login status check failed", error=e)
                category = await self._classify_error(e, "check_login_status")
                await self._capture_failure_evidence("check_login_status", category)
                return False

    def _update_session_info(self, is_logged_in: bool, indicators: List[str]):
        """세션 정보 업데이트"""
        if self.session_info:
            self.session_info.is_logged_in = is_logged_in
            self.session_info.login_indicators_found = indicators
            self.session_info.last_activity = time.time()

    async def navigate_to_write_page(self, blog_id: Optional[str] = None) -> bool:
        """블로그 글쓰기 페이지로 이동"""
        if not self.page:
            raise SessionError("Page not initialized")

        with log_context(operation="navigate_to_write", operation_id=self.operation_id):
            try:
                blog_id = blog_id or "jun12310"  # 기본값
                write_url = f"https://blog.naver.com/{blog_id}?Redirect=Write&"

                logger.info("Navigating to write page", url=write_url)

                await self.page.goto(
                    write_url,
                    wait_until='domcontentloaded',
                    timeout=self.timeout_seconds * 1000
                )

                # 페이지 로딩 대기
                await asyncio.sleep(3)

                # 로그인 상태 재확인
                is_logged_in = await self.check_login_status()
                if not is_logged_in:
                    raise SessionError("Not logged in after navigation to write page")

                logger.info("Successfully navigated to write page")
                return True

            except Exception as e:
                logger.error("Navigation to write page failed", error=e)
                category = await self._classify_error(e, "navigate_to_write")
                await self._capture_failure_evidence("navigate_to_write", category,
                                                   {"target_url": write_url, "blog_id": blog_id})
                raise SessionError(f"Navigation failed: {str(e)}")

    async def acquire_editor_frame(self) -> bool:
        """에디터 iframe 획득"""
        if not self.page:
            raise SessionError("Page not initialized")

        with log_context(operation="acquire_editor_frame", operation_id=self.operation_id):
            try:
                logger.info("Acquiring editor iframe")

                # 전략 1: mainFrame iframe 대기
                try:
                    await self.page.wait_for_selector('iframe#mainFrame', timeout=15000)
                    frame = self.page.frame('mainFrame')
                    if frame:
                        self.editor_frame = frame
                        logger.success("Editor iframe acquired (mainFrame)")
                        return True
                except PlaywrightTimeoutError:
                    logger.warning("mainFrame iframe not found, trying fallback")

                # 전략 2: 모든 프레임 탐색
                for frame in self.page.frames():
                    url = frame.url
                    if 'PostWriteForm' in url or 'SmartEditor' in url:
                        self.editor_frame = frame
                        logger.success("Editor iframe acquired via URL matching", url=url[:60])
                        return True

                # 전략 3: 시간 기반 대기 후 재시도
                logger.info("Waiting additional time for iframe loading")
                await asyncio.sleep(5)

                frame = self.page.frame('mainFrame')
                if frame:
                    self.editor_frame = frame
                    logger.success("Editor iframe acquired after additional wait")
                    return True

                raise EditorError("Editor iframe not found after all strategies")

            except Exception as e:
                logger.error("Editor frame acquisition failed", error=e)
                category = await self._classify_error(e, "acquire_editor_frame")
                await self._capture_failure_evidence("acquire_editor_frame", category)
                raise EditorError(f"Frame acquisition failed: {str(e)}")

    async def wait_for_editor_ready(self) -> bool:
        """에디터 로딩 완료 대기"""
        if not self.editor_frame:
            raise EditorError("Editor frame not acquired")

        with log_context(operation="wait_editor_ready", operation_id=self.operation_id):
            try:
                logger.info("Waiting for editor readiness")

                # 에디터 인디케이터들 (TypeScript 분석 기반)
                editor_indicators = [
                    '.se-toolbar',                    # SE ONE 툴바
                    '.se-content',                    # 에디터 콘텐츠
                    '[placeholder="제목"]',            # 제목 placeholder
                    '.se-documentTitle .se-text-paragraph',  # 제목 문단
                    '[contenteditable="true"]'        # 편집 가능 영역
                ]

                for selector in editor_indicators:
                    try:
                        await self.editor_frame.wait_for_selector(selector, timeout=20000)
                        logger.success("Editor ready", indicator=selector)
                        await asyncio.sleep(2)  # 안정화 대기
                        await self._dismiss_popups()
                        return True
                    except PlaywrightTimeoutError:
                        continue

                # 최후의 수단: 시간 기반 대기
                logger.warning("Editor indicators not found, using time-based wait")
                await asyncio.sleep(10)
                await self._dismiss_popups()

                # contenteditable 영역 확인
                editable = await self.editor_frame.query_selector('[contenteditable="true"]')
                if editable:
                    logger.success("Editor ready via contenteditable detection")
                    return True

                raise EditorError("Editor not ready after all strategies")

            except Exception as e:
                logger.error("Editor readiness wait failed", error=e)
                category = await self._classify_error(e, "wait_editor_ready")
                await self._capture_failure_evidence("wait_editor_ready", category)
                raise EditorError(f"Editor readiness failed: {str(e)}")

    async def _dismiss_popups(self):
        """팝업/안내 레이어 닫기"""
        if not self.editor_frame:
            return

        popup_selectors = [
            '.se-popup-button-close',
            '.se-help-panel-close-button',
            '.se-help-panel .se-help-panel-close-button',
            '[class*="help"] button[class*="close"]',
            '.btn_close',
            '[class*="guide"] button[class*="close"]',
            '[class*="tooltip"] button[class*="close"]',
            '.layer_popup .btn_close',
            '.se-popup-alert .se-popup-button-confirm',
            '.se-popup-alert button',
            '.se-popup-confirm button',
            '.se-popup-button-ok',
            '.se-popup-button-confirm'
        ]

        for selector in popup_selectors:
            try:
                elements = await self.editor_frame.query_selector_all(selector)
                for element in elements:
                    if await element.is_visible():
                        await element.click()
                        await asyncio.sleep(0.3)
                        logger.info("Popup dismissed", selector=selector)
            except:
                pass

        # aria-label 기반 닫기 버튼
        try:
            buttons = await self.editor_frame.query_selector_all('button')
            for button in buttons:
                aria_label = await button.get_attribute('aria-label')
                if aria_label and ('닫기' in aria_label or 'close' in aria_label.lower()):
                    if await button.is_visible():
                        await button.click()
                        await asyncio.sleep(0.3)
                        logger.info("Popup dismissed via aria-label")
                        break
        except:
            pass

    async def input_title(self, title: str) -> bool:
        """제목 입력"""
        if not self.editor_frame:
            raise EditorError("Editor frame not acquired")

        with log_context(operation="input_title", operation_id=self.operation_id):
            try:
                title = title.strip()
                logger.info("Inputting title", title=title)

                # 팝업 처리 강화
                await self._dismiss_popups()
                await asyncio.sleep(1)

                # 제목 입력 대상 셀렉터들 (TypeScript 분석 기반)
                target_selectors = [
                    '.se-documentTitle [contenteditable="true"]',
                    '.se-documentTitle .se-text-paragraph',
                    '[placeholder="제목"]',
                    '.se-documentTitle [role="textbox"]'
                ]

                for selector in target_selectors:
                    try:
                        element = await self.editor_frame.query_selector(selector)
                        if not element:
                            continue

                        await element.click(force=True)
                        await self.page.keyboard.press('Control+a')
                        await self.page.keyboard.press('Backspace')
                        await self.page.keyboard.insert_text(title)
                        await asyncio.sleep(0.25)

                        # 입력 확인
                        title_area = await self.editor_frame.evaluate('''
                            () => {
                                const root = document.querySelector('.se-documentTitle');
                                return (root?.textContent || '').replace(/\\s+/g, ' ').trim();
                            }
                        ''')

                        if title[:min(8, len(title))] in title_area:
                            logger.success("Title input successful",
                                         selector=selector,
                                         confirmed_text=title_area)
                            return True

                    except Exception as e:
                        logger.warning("Title input strategy failed",
                                     selector=selector, error=str(e))
                        continue

                raise EditorError("All title input strategies failed")

            except Exception as e:
                logger.error("Title input failed", error=e, title=title)
                category = await self._classify_error(e, "input_title")
                await self._capture_failure_evidence("input_title", category, {"title": title})
                raise EditorError(f"Title input failed: {str(e)}")

    async def input_body(self, body: str) -> bool:
        """본문 입력"""
        if not self.editor_frame or not self.page:
            raise EditorError("Editor frame or page not initialized")

        with log_context(operation="input_body", operation_id=self.operation_id):
            try:
                logger.info("Inputting body", length=len(body))

                async def type_body_lines():
                    """본문을 줄 단위로 입력"""
                    lines = body.split('\n')
                    for i, line in enumerate(lines):
                        if line.strip():
                            await self.page.keyboard.insert_text(line)
                        if i < len(lines) - 1:
                            await self.page.keyboard.press('Enter')

                # 전략 1: 제목 영역에서 Enter로 본문 이동
                try:
                    title_element = await self.editor_frame.query_selector(
                        '.se-documentTitle [contenteditable="true"], .se-documentTitle .se-text-paragraph'
                    )
                    if title_element:
                        await title_element.click(force=True)
                        await self.page.keyboard.press('End')
                        await self.page.keyboard.press('Enter')
                        await type_body_lines()
                        await asyncio.sleep(0.4)
                        logger.success("Body input successful (strategy 1)")
                        return True
                except Exception as e:
                    logger.warning("Body input strategy 1 failed", error=str(e))

                # 전략 2: 본문 영역 직접 타겟팅
                body_selectors = [
                    '.se-components-content .se-text-paragraph[contenteditable="true"]',
                    '.se-component-text .se-text-paragraph[contenteditable="true"]',
                    '.se-main-container [contenteditable="true"]',
                    '.se-content [contenteditable="true"]'
                ]

                for selector in body_selectors:
                    try:
                        elements = await self.editor_frame.query_selector_all(selector)
                        for element in elements:
                            if not await element.is_visible():
                                continue

                            # 제목 영역인지 확인
                            is_title = await element.evaluate(
                                'el => !!el.closest(".se-documentTitle")'
                            )
                            if is_title:
                                continue

                            await element.click(force=True)
                            await type_body_lines()
                            await asyncio.sleep(0.3)
                            logger.success("Body input successful (strategy 2)",
                                         selector=selector)
                            return True

                    except Exception as e:
                        logger.warning("Body input strategy failed",
                                     selector=selector, error=str(e))
                        continue

                # 디버깅 정보 수집
                await self._collect_editor_debug_info()
                raise EditorError("All body input strategies failed")

            except Exception as e:
                logger.error("Body input failed", error=e)
                category = await self._classify_error(e, "input_body")
                await self._capture_failure_evidence("input_body", category,
                                                   {"body_length": len(body)})
                raise EditorError(f"Body input failed: {str(e)}")

    async def _collect_editor_debug_info(self):
        """에디터 디버깅 정보 수집"""
        if not self.editor_frame:
            return

        try:
            debug_info = await self.editor_frame.evaluate('''
                () => {
                    const editables = Array.from(document.querySelectorAll('[contenteditable="true"]'));
                    return {
                        url: location.href,
                        editableCount: editables.length,
                        hasTextParagraph: !!document.querySelector('.se-text-paragraph'),
                        hasComponentsContent: !!document.querySelector('.se-components-content'),
                        hasMainContainer: !!document.querySelector('.se-main-container'),
                        editables: editables.slice(0, 10).map((el, idx) => ({
                            idx,
                            tag: el.tagName,
                            className: el.className,
                            visible: el.offsetWidth > 0 && el.offsetHeight > 0,
                            inTitle: !!el.closest('.se-documentTitle'),
                            text: (el.textContent || '').trim().slice(0, 50)
                        }))
                    };
                }
            ''')

            debug_path = Path(self.artifacts_dir) / f"editor_debug_{int(time.time())}.json"
            async with aiofiles.open(debug_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(debug_info, indent=2, ensure_ascii=False))

            logger.info("Editor debug info collected", path=str(debug_path))

        except Exception as e:
            logger.warning("Failed to collect editor debug info", error=e)

    async def click_temp_save(self) -> bool:
        """임시저장 버튼 클릭"""
        if not self.editor_frame or not self.page:
            raise EditorError("Editor frame or page not initialized")

        with log_context(operation="click_temp_save", operation_id=self.operation_id):
            try:
                logger.info("Clicking temp save button")

                async def prepare_for_temp_save():
                    """임시저장 전 준비 작업"""
                    await self._dismiss_popups()
                    await self.page.keyboard.press('Escape')
                    await asyncio.sleep(0.3)
                    await self.page.keyboard.press('Escape')

                    # 오버레이/팝업 강제 제거
                    try:
                        await self.editor_frame.evaluate('''
                            () => {
                                document.querySelectorAll('.se-popup-dim, .se-popup-dim-transparent, [class*="dimmed"], [class*="overlay"]')
                                    .forEach(el => {
                                        el.style.display = 'none';
                                        el.style.pointerEvents = 'none';
                                    });
                            }
                        ''')
                        await self.page.evaluate('''
                            () => {
                                document.querySelectorAll('.se-popup-dim, .se-popup-dim-transparent, [class*="dimmed"], [class*="overlay"]')
                                    .forEach(el => {
                                        el.style.display = 'none';
                                        el.style.pointerEvents = 'none';
                                    });
                            }
                        ''')
                    except:
                        pass

                # 임시저장 버튼 클릭 전략들 (TypeScript 분석 기반)
                strategies = [
                    # 전략 1: 에디터 툴바 영역 버튼 (evaluate 기반)
                    self._temp_save_strategy_1,
                    # 전략 2: 확장 셀렉터 기반 (force click)
                    self._temp_save_strategy_2,
                    # 전략 3: iframe 내 저장 버튼 재탐색
                    self._temp_save_strategy_3,
                    # 전략 4: 키보드 단축키
                    self._temp_save_strategy_4,
                    # 전략 5: 메인 페이지 상단 저장 버튼
                    self._temp_save_strategy_5
                ]

                for i, strategy in enumerate(strategies, 1):
                    try:
                        await prepare_for_temp_save()
                        if await strategy():
                            logger.success("Temp save button clicked", strategy=i)
                            return True
                    except Exception as e:
                        logger.warning("Temp save strategy failed",
                                     strategy=i, error=str(e))

                raise EditorError("All temp save button strategies failed")

            except Exception as e:
                logger.error("Temp save button click failed", error=e)
                category = await self._classify_error(e, "click_temp_save")
                await self._capture_failure_evidence("click_temp_save", category)
                raise EditorError(f"Temp save click failed: {str(e)}")

    async def _temp_save_strategy_1(self) -> bool:
        """임시저장 전략 1: 에디터 툴바 영역 버튼 (evaluate 기반)"""
        return await self.editor_frame.evaluate('''
            () => {
                const clickable = Array.from(
                    document.querySelectorAll(
                        '.se-toolbar button, .se-toolbar [role="button"], .se-tool button, .se-tool [role="button"], .btn_save, button[data-name="save"], button[class*="save_btn"], [class*="save_btn"]'
                    )
                );
                for (const el of clickable) {
                    const text = (el.textContent || '').replace(/\\s+/g, '');
                    const className = typeof el.className === 'string' ? el.className : '';
                    if (className.includes('save_count_btn')) continue;
                    const isSaveText = text.includes('임시저장') || text === '저장';
                    if (isSaveText && el.offsetWidth > 0 && el.offsetHeight > 0) {
                        el.setAttribute('data-codex-save-clicked', `${text}|${el.tagName}|${el.className}`);
                        el.click();
                        return true;
                    }
                }
                return false;
            }
        ''')

    async def _temp_save_strategy_2(self) -> bool:
        """임시저장 전략 2: 확장 셀렉터 기반 (force click)"""
        selectors = [
            '.btn_save', '#btn_save', '[class*="temp_save"]', '[class*="draft"]',
            '.se-toolbar-save-button', '.se-save-button', '.toolbar_save',
            '[data-name="save"]', 'button[class*="save_btn"]', '[class*="save_btn"]',
            'button[title*="저장"]', 'button[aria-label*="저장"]'
        ]

        for selector in selectors:
            elements = await self.editor_frame.query_selector_all(selector)
            for element in elements:
                if not await element.is_visible():
                    continue

                class_name = await element.get_attribute('class') or ''
                if 'save_count_btn' in class_name:
                    continue

                text = (await element.text_content() or '').replace(' ', '')
                if text and '임시저장' not in text and '저장' not in text:
                    continue

                await element.click(force=True)
                return True

        return False

    async def _temp_save_strategy_3(self) -> bool:
        """임시저장 전략 3: iframe 내 저장 버튼 재탐색"""
        selectors = [
            '.se-toolbar .btn_save', '.se-toolbar-save-button',
            '.se-save-button', '[data-name="save"]',
            'button[class*="save_btn"]', '[class*="save_btn"]'
        ]

        for selector in selectors:
            element = await self.editor_frame.query_selector(selector)
            if element and await element.is_visible():
                await element.click(force=True)
                return True

        return False

    async def _temp_save_strategy_4(self) -> bool:
        """임시저장 전략 4: 키보드 단축키"""
        await self.page.keyboard.press('Control+s')
        await asyncio.sleep(1)
        return True

    async def _temp_save_strategy_5(self) -> bool:
        """임시저장 전략 5: 메인 페이지 상단 저장 버튼"""
        menu_buttons = await self.page.query_selector_all(
            '.top_menu button, .menu_area button, .header_area button, button[data-name="save"]'
        )

        for button in menu_buttons:
            text = (await button.text_content() or '').replace(' ', '')
            if text and '임시저장' in text and await button.is_visible():
                await button.click()
                return True

        return False

    async def verify_temp_save(self, expected_title: str, max_retries: int = 1) -> TempSaveResult:
        """임시저장 검증 (TypeScript TempSaveVerifier 기반)"""
        if not self.editor_frame or not self.page:
            raise VerificationError("Editor frame or page not initialized")

        with log_context(operation="verify_temp_save", operation_id=self.operation_id):
            try:
                expected_title = expected_title.strip()
                logger.info("Starting temp save verification", expected_title=expected_title)

                result = TempSaveResult(success=False, verified_via="none")

                # 1. 토스트 메시지 검증
                toast_result = await self._verify_toast_message()
                if toast_result["success"]:
                    result.verified_via = "toast"
                    result.toast_message = toast_result["message"]

                # 2. 임시글함 검증
                draft_result = await self._verify_draft_list(expected_title)
                if draft_result["success"]:
                    result.draft_found = True
                    result.draft_title = draft_result["title"]
                    result.verified_via = "both" if result.verified_via == "toast" else "draft_list"

                if result.verified_via != "none":
                    result.success = True
                    logger.success("Temp save verification successful",
                                 verified_via=result.verified_via)
                    return result

                # 실패 시 증거 수집
                result.error_message = "토스트/임시글함 검증 모두 실패"
                category = FailureCategory.TEMP_SAVE_VERIFICATION
                result.failure_category = category
                result.screenshots = await self._capture_failure_evidence(
                    "verify_temp_save", category,
                    {"expected_title": expected_title, "verified_via": result.verified_via}
                )

                logger.error("Temp save verification failed")
                return result

            except Exception as e:
                logger.error("Temp save verification exception", error=e)
                category = await self._classify_error(e, "verify_temp_save")
                screenshots = await self._capture_failure_evidence("verify_temp_save", category,
                                                                 {"expected_title": expected_title})
                return TempSaveResult(
                    success=False,
                    verified_via="none",
                    error_message=f"검증 중 예외: {str(e)}",
                    failure_category=category,
                    screenshots=screenshots
                )

    async def _verify_toast_message(self) -> Dict[str, Any]:
        """토스트 메시지 검증"""
        logger.info("Verifying toast message")

        selectors = [
            '[class*="toast"]', '[class*="snackbar"]', '[class*="alert"]',
            '[class*="notification"]', '[class*="message"]', '[role="alert"]'
        ]
        selector_str = ', '.join(selectors)

        # 저장 직후 바로 사라질 수 있어서 짧게 여러 번 폴링
        for i in range(8):
            try:
                # frame과 page에서 동시에 탐색
                frame_messages, page_messages = await asyncio.gather(
                    self._find_success_messages_in_scope(
                        lambda: self.editor_frame.evaluate(
                            f'''
                            (selector) => {{
                                const els = document.querySelectorAll(selector);
                                return Array.from(els).map(el => el.textContent || '').filter(Boolean);
                            }}
                            ''',
                            selector_str
                        )
                    ),
                    self._find_success_messages_in_scope(
                        lambda: self.page.evaluate(
                            f'''
                            (selector) => {{
                                const els = document.querySelectorAll(selector);
                                return Array.from(els).map(el => el.textContent || '').filter(Boolean);
                            }}
                            ''',
                            selector_str
                        )
                    ),
                    return_exceptions=True
                )

                if isinstance(frame_messages, str):
                    logger.success("Toast verification successful (frame)", message=frame_messages)
                    return {"success": True, "message": frame_messages}

                if isinstance(page_messages, str):
                    logger.success("Toast verification successful (page)", message=page_messages)
                    return {"success": True, "message": page_messages}

                await asyncio.sleep(0.5)

            except Exception as e:
                logger.debug("Toast polling iteration failed", iteration=i, error=str(e))

        logger.warning("Toast message verification failed")
        return {"success": False}

    async def _find_success_messages_in_scope(self, loader_func) -> Optional[str]:
        """스코프 내에서 성공 메시지 탐색"""
        try:
            texts = await loader_func()
            for raw_text in texts:
                text = ' '.join(raw_text.split()).strip()
                if not text:
                    continue
                if self._is_failure_message(text):
                    continue
                if self._is_success_message(text):
                    return text
            return None
        except:
            return None

    def _is_success_message(self, text: str) -> bool:
        """성공 메시지 패턴 확인"""
        patterns = [
            r'임시\s*저장\s*완료',
            r'저장\s*완료',
            r'저장되었습니다',
            r'임시\s*저장됨',
            r'글이\s*저장',
            r'포스트\s*저장'
        ]
        import re
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)

    def _is_failure_message(self, text: str) -> bool:
        """실패 메시지 패턴 확인"""
        patterns = [
            r'저장\s*실패',
            r'저장\s*오류',
            r'저장\s*불가',
            r'네트워크\s*오류',
            r'다시\s*시도'
        ]
        import re
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)

    async def _verify_draft_list(self, expected_title: str) -> Dict[str, Any]:
        """임시글함 목록 검증"""
        logger.info("Verifying draft list")

        await self._wait_for_save_signal()
        panel_result = await self._verify_draft_panel_in_editor(expected_title)
        if panel_result["success"]:
            return panel_result

        logger.warning("Draft list verification failed")
        return {"success": False}

    async def _verify_draft_panel_in_editor(self, expected_title: str) -> Dict[str, Any]:
        """에디터 내 임시저장 패널 검증"""
        try:
            # 임시저장 카운트 버튼 찾기
            count_button = await self.editor_frame.query_selector(
                'button[class*="save_count_btn"], [class*="save_count_btn"]'
            )
            if not count_button:
                logger.warning("Temp save count button not found")
                return {"success": False}

            for attempt in range(1, 4):
                await count_button.click(force=True)
                await asyncio.sleep(0.5)

                panel_info = await self.editor_frame.evaluate('''
                    () => {
                        const raw = (document.body.innerText || '')
                            .split('\\n')
                            .map(s => s.trim())
                            .filter(Boolean);

                        const sectionIdx = raw.findIndex(line => line.includes('임시저장 글'));
                        if (sectionIdx < 0) {
                            return { ok: false, reason: 'panel_text_not_found', count: null, titles: [] };
                        }

                        const panelLines = raw.slice(sectionIdx, Math.min(sectionIdx + 40, raw.length));
                        const countLine = panelLines.find(line => /^총\\s*\\d+개$/.test(line)) || null;
                        const count = countLine ? Number((countLine.match(/\\d+/) || [])[0]) : null;

                        const titles = panelLines.filter(line =>
                            line !== '임시저장 글' &&
                            !/^총\\s*\\d+개$/.test(line) &&
                            !/^\\d{4}\\.\\d{2}\\.\\d{2}/.test(line) &&
                            !['편집', '팝업닫기', '임시저장', '저장'].includes(line)
                        );

                        return { ok: true, reason: 'ok', count, titles };
                    }
                ''')

                if not panel_info["ok"]:
                    logger.warning("Draft panel attempt failed",
                                 attempt=attempt, reason=panel_info["reason"])
                    continue

                matched_title = self._match_expected_title(expected_title, panel_info["titles"])
                if matched_title:
                    logger.success("Draft found in panel",
                                 matched_title=matched_title,
                                 count=panel_info["count"])
                    return {"success": True, "title": matched_title}

                logger.warning("Draft title not detected in panel",
                             attempt=attempt,
                             count=panel_info["count"],
                             titles=panel_info["titles"])
                await asyncio.sleep(0.6)

            return {"success": False}

        except Exception as e:
            logger.warning("Draft panel verification exception", error=e)
            return {"success": False}

    def _match_expected_title(self, expected_title: str, candidate_titles: List[str]) -> Optional[str]:
        """기대 제목과 후보 제목들 매칭"""
        normalized_expected = ' '.join(expected_title.split()).strip()
        if not normalized_expected:
            return None

        for candidate in candidate_titles:
            normalized_candidate = ' '.join(candidate.split()).strip()
            if not normalized_candidate:
                continue

            # 정확한 매치
            if normalized_candidate == normalized_expected:
                return candidate

            # 부분 매치 (12자 또는 전체 길이 중 작은 것)
            pivot_length = min(12, len(normalized_expected))
            pivot = normalized_expected[:pivot_length]
            if len(pivot) >= 6 and pivot in normalized_candidate:
                return candidate

        return None

    async def _wait_for_save_signal(self):
        """저장 신호 대기"""
        for i in range(8):
            try:
                found = await self.editor_frame.evaluate('''
                    () => {
                        const text = (document.body.innerText || '').replace(/\\s+/g, ' ');
                        return /자동저장|저장됨|저장 완료|저장되었습니다/.test(text);
                    }
                ''')
                if found:
                    return
            except:
                pass
            await asyncio.sleep(0.5)

    async def upload_images(self, image_paths: List[str]) -> bool:
        """이미지 업로드"""
        if not image_paths:
            logger.info("No images to upload")
            return True

        if not self.editor_frame or not self.page:
            raise EditorError("Editor frame or page not initialized")

        with log_context(operation="upload_images", operation_id=self.operation_id):
            try:
                logger.info("Starting image upload", count=len(image_paths))

                # 1. 사진 버튼 클릭
                photo_clicked = await self._click_photo_button()
                if not photo_clicked:
                    raise EditorError("Photo button not found")

                await asyncio.sleep(1.5)

                # 2. 파일 업로드
                uploaded = await self._upload_image_files(image_paths)
                if not uploaded:
                    raise EditorError("Image file upload failed")

                # 3. 업로드 완료 대기
                logger.info("Waiting for image upload completion")
                await asyncio.sleep(3)

                try:
                    await self.editor_frame.wait_for_selector(
                        '.se-image-resource, .se-component-image, img[src*="blogfiles"], img[src*="postfiles"]',
                        timeout=30000
                    )
                    logger.success("Image upload confirmation successful")
                except PlaywrightTimeoutError:
                    logger.warning("Image elements not confirmed but continuing")

                # 4. 닫기/완료 버튼
                await asyncio.sleep(1)
                try:
                    done_button = await self.editor_frame.query_selector(
                        '.se-popup-close-button, .se-popup-button-confirm, .se-section-done-button'
                    )
                    if done_button and await done_button.is_visible():
                        await done_button.click()
                        await asyncio.sleep(0.5)
                except:
                    pass

                logger.success("Image upload completed", count=len(image_paths))
                return True

            except Exception as e:
                logger.error("Image upload failed", error=e, count=len(image_paths))
                category = await self._classify_error(e, "upload_images")
                await self._capture_failure_evidence("upload_images", category,
                                                   {"image_count": len(image_paths),
                                                    "image_paths": image_paths})
                raise EditorError(f"Image upload failed: {str(e)}")

    async def _click_photo_button(self) -> bool:
        """사진 버튼 클릭"""
        strategies = [
            # 전략 1: 텍스트 기반
            self._photo_button_strategy_text,
            # 전략 2: 데이터 속성 기반
            self._photo_button_strategy_data,
            # 전략 3: 첫 번째 툴바 버튼
            self._photo_button_strategy_first_toolbar
        ]

        for i, strategy in enumerate(strategies, 1):
            try:
                if await strategy():
                    logger.success("Photo button clicked", strategy=i)
                    return True
            except Exception as e:
                logger.warning("Photo button strategy failed", strategy=i, error=str(e))

        return False

    async def _photo_button_strategy_text(self) -> bool:
        """사진 버튼 전략 1: 텍스트 기반"""
        buttons = await self.editor_frame.query_selector_all('button')
        for button in buttons:
            text = await button.text_content()
            if text and text.strip() == '사진':
                await button.click()
                return True
        return False

    async def _photo_button_strategy_data(self) -> bool:
        """사진 버튼 전략 2: 데이터 속성 기반"""
        selector = '[data-name="image"], [data-name="photo"], [data-log="image"]'
        element = await self.editor_frame.query_selector(selector)
        if element:
            await element.click()
            return True
        return False

    async def _photo_button_strategy_first_toolbar(self) -> bool:
        """사진 버튼 전략 3: 첫 번째 툴바 버튼"""
        first_button = await self.editor_frame.query_selector('.se-toolbar-item:first-child button')
        if first_button:
            text = await first_button.text_content()
            if text and '사진' in text:
                await first_button.click()
                return True
        return False

    async def _upload_image_files(self, image_paths: List[str]) -> bool:
        """이미지 파일 업로드"""
        strategies = [
            # 전략 1: fileChooser 이벤트 + "내 PC" 버튼
            lambda: self._upload_strategy_file_chooser(image_paths),
            # 전략 2: iframe 내 input[type=file]
            lambda: self._upload_strategy_iframe_input(image_paths),
            # 전략 3: 메인 page의 input[type=file]
            lambda: self._upload_strategy_page_input(image_paths)
        ]

        for i, strategy in enumerate(strategies, 1):
            try:
                if await strategy():
                    logger.success("Image file upload successful", strategy=i)
                    return True
            except Exception as e:
                logger.warning("Image upload strategy failed", strategy=i, error=str(e))

        return False

    async def _upload_strategy_file_chooser(self, image_paths: List[str]) -> bool:
        """업로드 전략 1: fileChooser 이벤트"""
        pc_labels = ['내 PC', 'PC에서', '컴퓨터에서']
        all_buttons = await self.editor_frame.query_selector_all('button, a, span, div[role="button"]')

        for button in all_buttons:
            text = await button.text_content()
            if text and any(label in text for label in pc_labels) and await button.is_visible():
                try:
                    async with asyncio.timeout(5):
                        file_chooser_task = asyncio.create_task(
                            self.page.wait_for_event('filechooser')
                        )
                        await button.click()
                        file_chooser = await file_chooser_task
                        await file_chooser.set_files(image_paths)
                        logger.success("File chooser upload completed", count=len(image_paths))
                        return True
                except asyncio.TimeoutError:
                    logger.warning("File chooser timeout")
                    continue

        return False

    async def _upload_strategy_iframe_input(self, image_paths: List[str]) -> bool:
        """업로드 전략 2: iframe 내 input[type=file]"""
        file_inputs = await self.editor_frame.query_selector_all('input[type="file"]')
        for input_element in file_inputs:
            try:
                await input_element.set_input_files(image_paths)
                logger.success("Iframe input upload completed", count=len(image_paths))
                return True
            except:
                continue
        return False

    async def _upload_strategy_page_input(self, image_paths: List[str]) -> bool:
        """업로드 전략 3: 페이지 레벨 input[type=file]"""
        file_inputs = await self.page.query_selector_all('input[type="file"]')
        for input_element in file_inputs:
            try:
                await input_element.set_input_files(image_paths)
                logger.success("Page-level input upload completed", count=len(image_paths))
                return True
            except:
                continue
        return False

    async def attach_place(self, place_name: str) -> bool:
        """장소 첨부"""
        if not self.editor_frame or not self.page:
            raise EditorError("Editor frame or page not initialized")

        with log_context(operation="attach_place", operation_id=self.operation_id):
            try:
                logger.info("Starting place attachment", place_name=place_name)

                # 1. 장소 버튼 클릭
                if not await self._click_place_button():
                    raise EditorError("Place button not found")

                # 2. 장소 검색
                if not await self._search_place(place_name):
                    raise EditorError("Place search failed")

                # 3. 결과 선택
                selected = await self._select_first_place_result()
                if not selected:
                    logger.info("Result selection skipped (single result assumed)")

                # 4. 확인 버튼 클릭
                if not await self._confirm_place_selection():
                    logger.warning("Place confirm button click failed")
                    return False

                await asyncio.sleep(1)
                logger.success("Place attachment completed", place_name=place_name)
                return True

            except Exception as e:
                logger.error("Place attachment failed", error=e, place_name=place_name)
                category = await self._classify_error(e, "attach_place")
                await self._capture_failure_evidence("attach_place", category,
                                                   {"place_name": place_name})
                raise EditorError(f"Place attachment failed: {str(e)}")

    async def _click_place_button(self) -> bool:
        """장소 버튼 클릭"""
        strategies = [
            # 전략 1: '장소' 텍스트
            lambda: self._place_button_text_strategy('장소'),
            # 전략 2: '지도' 텍스트
            lambda: self._place_button_text_strategy('지도'),
            # 전략 3: 데이터 속성
            lambda: self._place_button_data_strategy(),
            # 전략 4: aria-label
            lambda: self._place_button_aria_strategy(),
            # 전략 5: 툴바 내 텍스트
            lambda: self._place_button_toolbar_strategy()
        ]

        for i, strategy in enumerate(strategies, 1):
            try:
                if await strategy():
                    logger.success("Place button clicked", strategy=i)
                    return True
            except Exception as e:
                logger.warning("Place button strategy failed", strategy=i, error=str(e))

        return False

    async def _place_button_text_strategy(self, text: str) -> bool:
        """장소 버튼 텍스트 전략"""
        buttons = await self.editor_frame.query_selector_all('button')
        for button in buttons:
            button_text = await button.text_content()
            if button_text and text in button_text:
                await button.click()
                return True
        return False

    async def _place_button_data_strategy(self) -> bool:
        """장소 버튼 데이터 속성 전략"""
        selector = '[data-name="map"], [data-name="place"], [data-log="map"]'
        element = await self.editor_frame.query_selector(selector)
        if element:
            await element.click()
            return True
        return False

    async def _place_button_aria_strategy(self) -> bool:
        """장소 버튼 aria-label 전략"""
        selector = '[aria-label*="장소"], [aria-label*="지도"]'
        element = await self.editor_frame.query_selector(selector)
        if element:
            await element.click()
            return True
        return False

    async def _place_button_toolbar_strategy(self) -> bool:
        """장소 버튼 툴바 전략"""
        buttons = await self.editor_frame.query_selector_all('.se-toolbar button, .toolbar_area button')
        for button in buttons:
            text = await button.text_content()
            if text and ('장소' in text or '지도' in text):
                await button.click()
                return True
        return False

    async def _search_place(self, query: str) -> bool:
        """장소 검색"""
        await asyncio.sleep(1.5)  # 장소 검색 레이어 로딩 대기

        # 검색 입력창 탐색 전략들
        search_input = None
        strategies = [
            lambda: self.editor_frame.query_selector('input[placeholder*="장소"]'),
            lambda: self.editor_frame.query_selector('input[placeholder*="검색"]'),
            lambda: self.editor_frame.query_selector('input[placeholder*="상호"]'),
            lambda: self.editor_frame.query_selector('.se-map-search-input input'),
            lambda: self.editor_frame.query_selector('.se-place-search-input input'),
            lambda: self.editor_frame.query_selector('.map_search input'),
            lambda: self.editor_frame.query_selector('.place_search input[type="text"]'),
        ]

        for strategy in strategies:
            try:
                search_input = await strategy()
                if search_input:
                    break
            except:
                continue

        # 팝업/레이어 내 텍스트 입력 필드 (폴백)
        if not search_input:
            inputs = await self.editor_frame.query_selector_all(
                '.se-popup input[type="text"], .layer_popup input[type="text"], .se-layer input[type="text"]'
            )
            if inputs:
                search_input = inputs[0]

        if not search_input:
            logger.error("Place search input not found")
            return False

        # 검색어 입력 및 검색 실행
        await search_input.click()
        await search_input.fill('')
        await search_input.fill(query)
        logger.info("Place search query entered", query=query)

        await asyncio.sleep(0.5)
        await search_input.press('Enter')
        await asyncio.sleep(2)

        return True

    async def _select_first_place_result(self) -> bool:
        """첫 번째 장소 검색 결과 선택"""
        strategies = [
            # 전략 1: 검색 결과 목록 아이템
            lambda: self._place_result_list_strategy(),
            # 전략 2: 결과 내 클릭 가능한 항목
            lambda: self._place_result_clickable_strategy(),
            # 전략 3: 텍스트 기반 첫 번째 결과
            lambda: self._place_result_text_strategy(),
            # 전략 4: 단일 결과 카드
            lambda: self._place_result_card_strategy()
        ]

        for strategy in strategies:
            try:
                if await strategy():
                    logger.success("Place search result selected")
                    return True
            except:
                continue

        return False

    async def _place_result_list_strategy(self) -> bool:
        """장소 결과 목록 전략"""
        selectors = [
            '.se-map-search-result-item:first-child',
            '.se-place-search-result li:first-child',
            '.map_search_list li:first-child',
            '.search_result_list li:first-child',
            '.place_list li:first-child'
        ]

        for selector in selectors:
            element = await self.editor_frame.query_selector(selector)
            if element:
                await element.click()
                return True

        return False

    async def _place_result_clickable_strategy(self) -> bool:
        """장소 결과 클릭 가능 요소 전략"""
        selectors = [
            '.se-map-search-result button:first-of-type',
            '.se-map-search-result a:first-of-type',
            '.search_result button:first-of-type'
        ]

        for selector in selectors:
            element = await self.editor_frame.query_selector(selector)
            if element:
                await element.click()
                return True

        return False

    async def _place_result_text_strategy(self) -> bool:
        """장소 결과 텍스트 전략"""
        items = await self.editor_frame.query_selector_all(
            '[class*="search"] li, [class*="result"] li, [class*="place"] li'
        )

        for item in items:
            text = await item.text_content()
            if text and text.strip():
                await item.click()
                return True

        return False

    async def _place_result_card_strategy(self) -> bool:
        """장소 결과 카드 전략"""
        cards = await self.editor_frame.query_selector_all(
            '[class*="map"] [class*="item"], [class*="place"] [class*="item"], [class*="search"] [class*="name"]'
        )

        for card in cards:
            if await card.is_visible():
                await card.click()
                return True

        return False

    async def _confirm_place_selection(self) -> bool:
        """장소 선택 확인"""
        await asyncio.sleep(1)

        strategies = [
            # 전략 1: 텍스트 기반 확인/적용 버튼
            lambda: self._place_confirm_text_strategy(),
            # 전략 2: 셀렉터 기반
            lambda: self._place_confirm_selector_strategy()
        ]

        for strategy in strategies:
            try:
                if await strategy():
                    logger.success("Place selection confirmed")
                    return True
            except:
                continue

        # 확인 버튼이 없을 수 있음 (자동 적용)
        logger.info("Place confirm button not found (auto-applied)")
        return True

    async def _place_confirm_text_strategy(self) -> bool:
        """장소 확인 텍스트 전략"""
        buttons = await self.editor_frame.query_selector_all('button')
        import re
        confirm_pattern = re.compile(r'확인|적용|완료|추가|등록')

        for button in buttons:
            text = await button.text_content()
            if text and confirm_pattern.search(text) and await button.is_visible():
                await button.click()
                return True

        return False

    async def _place_confirm_selector_strategy(self) -> bool:
        """장소 확인 셀렉터 전략"""
        selectors = [
            '.se-popup-button-confirm',
            '.se-map-confirm',
            '.btn_confirm',
            '.btn_ok',
            'button.confirm'
        ]

        for selector in selectors:
            element = await self.editor_frame.query_selector(selector)
            if element:
                await element.click()
                return True

        return False

    async def create_temp_save_post(
        self,
        post_data: BlogPostData,
        blog_id: Optional[str] = None,
        verify_save: bool = True
    ) -> TempSaveResult:
        """임시저장 포스트 생성 (메인 워크플로우)"""
        with log_context(operation="create_temp_save_post", operation_id=self.operation_id):
            logger.info("Starting temp save post creation",
                       title=post_data.title,
                       body_length=len(post_data.body),
                       image_count=len(post_data.image_paths),
                       place_name=post_data.place_name)

            async with self.browser_session():
                try:
                    # 1. 로그인 상태 확인
                    if not await self.check_login_status():
                        raise SessionError("Not logged in")

                    # 2. 글쓰기 페이지 이동
                    await self.navigate_to_write_page(blog_id)

                    # 3. 에디터 프레임 획득
                    await self.acquire_editor_frame()

                    # 4. 에디터 준비 대기
                    await self.wait_for_editor_ready()

                    # 5. 제목 입력
                    await self.input_title(post_data.title)

                    # 6. 본문 입력
                    await self.input_body(post_data.body)

                    # 7. 이미지 업로드 (있는 경우)
                    if post_data.image_paths:
                        await self.upload_images(post_data.image_paths)

                    # 8. 장소 첨부 (있는 경우)
                    if post_data.place_name:
                        await self.attach_place(post_data.place_name)

                    # 9. 임시저장 실행
                    await self.click_temp_save()

                    # 10. 임시저장 검증
                    if verify_save:
                        result = await self.verify_temp_save(post_data.title, max_retries=1)
                        logger.info("Temp save post creation completed",
                                   success=result.success,
                                   verified_via=result.verified_via)
                        return result
                    else:
                        logger.info("Temp save post creation completed (verification skipped)")
                        return TempSaveResult(success=True, verified_via="skipped")

                except Exception as e:
                    logger.error("Temp save post creation failed", error=e)
                    category = await self._classify_error(e, "create_temp_save_post")
                    screenshots = await self._capture_failure_evidence(
                        "create_temp_save_post", category,
                        {
                            "post_title": post_data.title,
                            "body_length": len(post_data.body),
                            "image_count": len(post_data.image_paths),
                            "place_name": post_data.place_name
                        }
                    )
                    return TempSaveResult(
                        success=False,
                        verified_via="none",
                        error_message=str(e),
                        failure_category=category,
                        screenshots=screenshots
                    )


# 편의 함수들
async def create_naver_blog_post(
    title: str,
    body: str,
    image_paths: List[str] = None,
    place_name: Optional[str] = None,
    blog_id: Optional[str] = None,
    headless: bool = True,
    verify_save: bool = True
) -> TempSaveResult:
    """네이버 블로그 포스트 생성 편의 함수"""
    post_data = BlogPostData(
        title=title,
        body=body,
        image_paths=image_paths or [],
        place_name=place_name
    )

    client = NaverBlogStabilizedClient(
        headless=headless,
        enable_logging=True
    )

    return await client.create_temp_save_post(
        post_data=post_data,
        blog_id=blog_id,
        verify_save=verify_save
    )


async def test_naver_blog_health() -> Dict[str, Any]:
    """네이버 블로그 시스템 헬스체크"""
    client = NaverBlogStabilizedClient(headless=True)

    async with client.browser_session():
        health_info = {
            "timestamp": time.time(),
            "login_status": False,
            "editor_accessible": False,
            "session_info": None,
            "errors": []
        }

        try:
            # 로그인 상태 확인
            health_info["login_status"] = await client.check_login_status()
            health_info["session_info"] = client.session_info.__dict__ if client.session_info else None

            if health_info["login_status"]:
                # 에디터 접근성 테스트
                try:
                    await client.navigate_to_write_page()
                    await client.acquire_editor_frame()
                    await client.wait_for_editor_ready()
                    health_info["editor_accessible"] = True
                except Exception as e:
                    health_info["errors"].append(f"Editor access failed: {str(e)}")

        except Exception as e:
            health_info["errors"].append(f"Health check failed: {str(e)}")

        return health_info


if __name__ == "__main__":
    # 기본 테스트
    import sys

    async def main():
        if len(sys.argv) > 1 and sys.argv[1] == "health":
            health = await test_naver_blog_health()
            print(json.dumps(health, indent=2, ensure_ascii=False))
        else:
            result = await create_naver_blog_post(
                title="테스트 포스트",
                body="테스트 내용입니다.",
                headless=False
            )
            print(f"Result: {result}")

    asyncio.run(main())