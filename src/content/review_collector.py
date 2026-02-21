"""
네이버 블로그 검색 API를 활용한 리뷰 스니펫 수집 모듈
입력이 부족할 때 보강 모드에서 사용됩니다.
"""

import re
import logging
from typing import Dict, List
from collections import Counter

import requests

from src.config.settings import Settings

logger = logging.getLogger(__name__)


class NaverReviewCollector:
    """네이버 블로그 검색 API로 리뷰 스니펫을 수집하는 클래스"""

    SEARCH_URL = "https://openapi.naver.com/v1/search/blog.json"

    # 추출 대상 키워드 패턴 (일반적 후기 표현)
    REVIEW_KEYWORDS = [
        "친절", "불친절", "웨이팅", "대기", "줄", "예약",
        "양 많", "양이 많", "양이 적", "푸짐", "소량",
        "가성비", "가격대", "비싸", "저렴", "합리적",
        "분위기", "인테리어", "깔끔", "청결", "지저분",
        "주차", "접근성", "교통", "역 근처", "골목",
        "맛있", "맛없", "담백", "짭짤", "달달", "매콤",
        "혼밥", "단체", "데이트", "아이",
        "재방문", "또 가", "다시 가",
    ]

    # 수치/단정 표현 — 오류 리스크가 높아 제외
    EXCLUDE_PATTERNS = [
        r"\d+원",          # 가격
        r"\d+시",          # 영업시간
        r"\d+분",          # 소요시간
        r"주차\s?\d+대",   # 주차 대수
    ]

    def __init__(self):
        self.client_id = Settings.NAVER_CLIENT_ID
        self.client_secret = Settings.NAVER_CLIENT_SECRET

    def collect_review_snippets(
        self, store_name: str, location: str = ""
    ) -> List[str]:
        """
        상호+지역으로 네이버 블로그 검색 → 공통 키워드/문구 추출

        Args:
            store_name: 상호명
            location: 지역명 (선택)

        Returns:
            ["분위기 좋다는 후기 많음", "웨이팅 있다는 얘기 많음", ...] 형태 5~10개
        """
        if not self.client_id or not self.client_secret:
            logger.warning("네이버 API 키가 설정되지 않아 리뷰 수집을 건너뜁니다.")
            return []

        query = f"{store_name} {location}".strip() if location else store_name
        blog_results = self._search_blog_posts(query, display=10)

        if not blog_results:
            logger.info(f"블로그 검색 결과 없음: {query}")
            return []

        snippets = self._extract_common_keywords(blog_results)
        logger.info(f"리뷰 스니펫 {len(snippets)}개 수집 완료: {store_name}")
        return snippets

    def _search_blog_posts(self, query: str, display: int = 10) -> List[Dict]:
        """네이버 블로그 검색 API 호출"""
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }
        params = {
            "query": query,
            "display": display,
            "sort": "sim",
        }

        try:
            resp = requests.get(
                self.SEARCH_URL,
                headers=headers,
                params=params,
                timeout=Settings.API_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("items", [])
        except requests.RequestException as e:
            logger.error(f"네이버 블로그 검색 API 오류: {e}")
            return []

    def _extract_common_keywords(self, blog_results: List[Dict]) -> List[str]:
        """블로그 검색 결과에서 공통 키워드/형용사 추출"""
        # title + description 텍스트 합치기 (HTML 태그 제거)
        combined_text = ""
        for item in blog_results:
            title = re.sub(r"<[^>]+>", "", item.get("title", ""))
            desc = re.sub(r"<[^>]+>", "", item.get("description", ""))
            combined_text += f" {title} {desc}"

        # 제외 패턴에 해당하는 수치 표현 제거
        for pattern in self.EXCLUDE_PATTERNS:
            combined_text = re.sub(pattern, "", combined_text)

        # 키워드 빈도 카운트
        keyword_counts: Counter = Counter()
        for keyword in self.REVIEW_KEYWORDS:
            count = combined_text.count(keyword)
            if count >= 2:  # 최소 2회 이상 언급된 것만
                keyword_counts[keyword] = count

        # 빈도순 정렬 후 자연어 스니펫으로 변환
        snippets = []
        for keyword, count in keyword_counts.most_common(10):
            snippet = self._keyword_to_snippet(keyword, count, len(blog_results))
            if snippet:
                snippets.append(snippet)

        return snippets[:10]

    @staticmethod
    def _keyword_to_snippet(keyword: str, count: int, total_posts: int) -> str:
        """키워드를 자연어 스니펫으로 변환"""
        ratio = count / max(total_posts, 1)

        if ratio >= 1.5:
            frequency = "자주"
        elif ratio >= 0.8:
            frequency = "종종"
        else:
            frequency = "간간이"

        # 키워드별 자연어 매핑
        snippet_map = {
            "친절": f"직원이 친절하다는 후기가 {frequency} 보임",
            "불친절": f"서비스가 아쉽다는 후기가 {frequency} 보임",
            "웨이팅": f"웨이팅이 있다는 얘기가 {frequency} 보임",
            "대기": f"대기가 있다는 얘기가 {frequency} 보임",
            "줄": f"줄을 서야 한다는 후기가 {frequency} 보임",
            "예약": f"예약 관련 언급이 {frequency} 보임",
            "양 많": f"양이 많다는 후기가 {frequency} 보임",
            "양이 많": f"양이 많다는 후기가 {frequency} 보임",
            "양이 적": f"양이 적다는 후기가 {frequency} 보임",
            "푸짐": f"푸짐하다는 후기가 {frequency} 보임",
            "소량": f"양이 적다는 후기가 {frequency} 보임",
            "가성비": f"가성비가 좋다는 후기가 {frequency} 보임",
            "가격대": f"가격대 언급이 {frequency} 보임",
            "비싸": f"가격이 있는 편이라는 후기가 {frequency} 보임",
            "저렴": f"가격이 저렴하다는 후기가 {frequency} 보임",
            "합리적": f"가격이 합리적이라는 후기가 {frequency} 보임",
            "분위기": f"분위기 좋다는 후기가 {frequency} 보임",
            "인테리어": f"인테리어가 좋다는 후기가 {frequency} 보임",
            "깔끔": f"깔끔하다는 후기가 {frequency} 보임",
            "청결": f"청결하다는 후기가 {frequency} 보임",
            "지저분": f"청결 관련 아쉽다는 후기가 {frequency} 보임",
            "주차": f"주차 관련 언급이 {frequency} 보임",
            "접근성": f"접근성 관련 언급이 {frequency} 보임",
            "교통": f"교통 관련 언급이 {frequency} 보임",
            "역 근처": f"역 근처라는 언급이 {frequency} 보임",
            "골목": f"골목에 위치한다는 언급이 {frequency} 보임",
            "맛있": f"맛있다는 후기가 {frequency} 보임",
            "맛없": f"맛이 아쉽다는 후기가 {frequency} 보임",
            "담백": f"담백하다는 후기가 {frequency} 보임",
            "짭짤": f"짭짤하다는 후기가 {frequency} 보임",
            "달달": f"달달하다는 후기가 {frequency} 보임",
            "매콤": f"매콤하다는 후기가 {frequency} 보임",
            "혼밥": f"혼밥하기 좋다는 후기가 {frequency} 보임",
            "단체": f"단체 모임 관련 언급이 {frequency} 보임",
            "데이트": f"데이트하기 좋다는 후기가 {frequency} 보임",
            "아이": f"아이와 함께 방문한 후기가 {frequency} 보임",
            "재방문": f"재방문 의사가 있다는 후기가 {frequency} 보임",
            "또 가": f"또 가고 싶다는 후기가 {frequency} 보임",
            "다시 가": f"다시 가고 싶다는 후기가 {frequency} 보임",
        }

        return snippet_map.get(keyword, f"'{keyword}' 관련 언급이 {frequency} 보임")
