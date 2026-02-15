"""
상호명 보정 및 검증 서비스
"""

import re
import logging
from typing import Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum

from .place_search import PlaceSearchProvider, get_place_search_provider, SearchStatus, PlaceCandidate
from ..models.session import LocationInfo, TelegramSession


class ResolutionStatus(Enum):
    """상호명 보정 결과 상태"""
    SUCCESS = "success"
    NEEDS_LOCATION = "needs_location"  # 위치 정보 필요
    NOT_FOUND = "not_found"  # 검색 결과 없음
    API_ERROR = "api_error"  # API 오류
    INVALID_FORMAT = "invalid_format"  # 입력 형식 오류


@dataclass
class ResolutionResult:
    """상호명 보정 결과"""
    status: ResolutionStatus
    resolved_name: Optional[str] = None
    confidence: float = 0.0  # 신뢰도 (0.0-1.0)
    fallback_used: bool = False  # nearest 검색으로 fallback했는지
    candidate: Optional[PlaceCandidate] = None
    error_message: Optional[str] = None
    log_details: Optional[str] = None


class StoreNameResolver:
    """상호명 보정 및 검증 서비스"""

    def __init__(self, provider: Optional[PlaceSearchProvider] = None):
        self.provider = provider or get_place_search_provider()
        self.logger = logging.getLogger(__name__)

        # 상호명 패턴 설정
        self.MIN_SIMILARITY_THRESHOLD = 0.6  # 최소 유사도 임계값
        self.HIGH_CONFIDENCE_THRESHOLD = 0.8  # 높은 신뢰도 임계값
        self.MAX_DISTANCE_METERS = 2000  # 최대 허용 거리 (2km)

    def parse_store_name(self, raw_input: str) -> Tuple[bool, str, str]:
        """
        상호명 입력을 파싱하여 지점명 포함 여부 확인

        Args:
            raw_input: 사용자 입력 상호명

        Returns:
            Tuple[bool, str, str]: (지점명포함여부, 브랜드명, 지점명)
        """
        # 정규화: 공백 정리, 특수문자 제거
        normalized = re.sub(r'\s+', ' ', raw_input.strip())

        # 지점명 패턴들
        branch_patterns = [
            r'(.+?)\s*([가-힣]+(?:역|점|지점|매장|센터|타워|빌딩|동|로|길)\d*점?)$',
            r'(.+?)\s*([가-힣A-Za-z0-9]+점)$',
            r'(.+?)\s*([가-힣A-Za-z0-9]+지점)$',
            r'(.+?)\s*([가-힣A-Za-z0-9]+매장)$'
        ]

        for pattern in branch_patterns:
            match = re.match(pattern, normalized)
            if match:
                brand = match.group(1).strip()
                branch = match.group(2).strip()
                # 브랜드명이 너무 짧으면 지점명이 아닐 가능성이 높음
                if len(brand) >= 2:
                    self.logger.info(f"Parsed store name: brand='{brand}', branch='{branch}'")
                    return True, brand, branch

        # 지점명이 없는 경우
        self.logger.info(f"No branch detected in: '{normalized}'")
        return False, normalized, ""

    def validate_input_format(self, raw_input: str) -> Tuple[bool, str]:
        """
        입력 형식 검증

        Args:
            raw_input: 사용자 입력

        Returns:
            Tuple[bool, str]: (유효여부, 오류메시지)
        """
        if not raw_input or not raw_input.strip():
            return False, "상호명을 입력해주세요."

        normalized = raw_input.strip()

        # 최소 길이 체크
        if len(normalized) < 2:
            return False, "상호명은 2글자 이상 입력해주세요."

        # 최대 길이 체크
        if len(normalized) > 100:
            return False, "상호명이 너무 깁니다. 100글자 이하로 입력해주세요."

        # 숫자나 특수문자만 있는 경우
        if re.match(r'^[\d\s\-_\.\,\!\?\#\@\$\%\^\&\*\(\)\[\]\{\}\|\\\/<>]+$', normalized):
            return False, "상호명은 '브랜드명' 또는 '브랜드명 지점명' 형태로 입력해주세요."

        return True, ""

    async def resolve_store_name(self, session: TelegramSession) -> ResolutionResult:
        """
        세션의 상호명을 보정/검증

        Args:
            session: 텔레그램 세션

        Returns:
            ResolutionResult: 보정 결과
        """
        raw_input = session.raw_store_name
        location = session.location

        # 입력 검증
        is_valid, error_msg = self.validate_input_format(raw_input)
        if not is_valid:
            return ResolutionResult(
                status=ResolutionStatus.INVALID_FORMAT,
                error_message=error_msg
            )

        # 상호명 파싱
        has_branch, brand, branch = self.parse_store_name(raw_input)

        log_details = f"입력: '{raw_input}' | 브랜드: '{brand}' | 지점: '{branch}' | 위치: {location is not None}"
        self.logger.info(f"Store name resolution started: {log_details}")

        if has_branch:
            # 지점명이 있는 경우: 검색 후 존재 여부 확인
            return await self._resolve_with_branch(raw_input, brand, branch, location, log_details)
        else:
            # 지점명이 없는 경우: 위치 기반 nearest 검색 필요
            return await self._resolve_without_branch(brand, location, log_details)

    async def _resolve_with_branch(
        self,
        raw_input: str,
        brand: str,
        branch: str,
        location: Optional[LocationInfo],
        log_details: str
    ) -> ResolutionResult:
        """지점명이 있는 상호명 보정"""

        # 1단계: 정확한 상호명으로 검색
        search_result = await self.provider.search_by_name(raw_input, location)

        if search_result.status == SearchStatus.SUCCESS and search_result.candidates:
            # 검색 결과 중 가장 유사한 것 선택
            best_candidate = search_result.candidates[0]

            # 유사도 검증
            if best_candidate.similarity_score >= self.MIN_SIMILARITY_THRESHOLD:
                confidence = min(best_candidate.similarity_score, 0.9)  # 최대 90%

                detailed_log = f"{log_details} | 검색성공 | 후보: '{best_candidate.name}' | 유사도: {best_candidate.similarity_score:.2f}"
                if location and best_candidate.distance:
                    detailed_log += f" | 거리: {best_candidate.distance:.0f}m"
                self.logger.info(detailed_log)

                return ResolutionResult(
                    status=ResolutionStatus.SUCCESS,
                    resolved_name=best_candidate.name,
                    confidence=confidence,
                    candidate=best_candidate,
                    log_details=detailed_log
                )

        # 2단계: 검색 실패 시 위치 기반 fallback
        if location:
            self.logger.info(f"{log_details} | 검색실패, nearest로 fallback")
            return await self._fallback_to_nearest(brand, location, f"{log_details} | fallback")
        else:
            return ResolutionResult(
                status=ResolutionStatus.NEEDS_LOCATION,
                error_message="입력하신 상호명을 찾을 수 없습니다. 위치 정보를 공유해주시거나 정확한 지점명을 입력해주세요.",
                log_details=f"{log_details} | 검색실패, 위치없어서 fallback 불가"
            )

    async def _resolve_without_branch(
        self,
        brand: str,
        location: Optional[LocationInfo],
        log_details: str
    ) -> ResolutionResult:
        """지점명이 없는 상호명 보정 (nearest 검색 필수)"""

        if not location:
            return ResolutionResult(
                status=ResolutionStatus.NEEDS_LOCATION,
                error_message="지점명이 없어서 위치 기반으로 가장 가까운 지점을 찾아드릴게요. 위치 정보를 공유해주세요.",
                log_details=f"{log_details} | 지점명 없음, 위치정보 필요"
            )

        return await self._fallback_to_nearest(brand, location, f"{log_details} | 지점명 없음")

    async def _fallback_to_nearest(
        self,
        keyword: str,
        location: LocationInfo,
        log_details: str
    ) -> ResolutionResult:
        """위치 기반 가장 가까운 지점 검색"""

        search_result = await self.provider.search_nearest(keyword, location)

        if search_result.status == SearchStatus.SUCCESS and search_result.candidates:
            best_candidate = search_result.candidates[0]

            # 거리 검증
            if best_candidate.distance and best_candidate.distance > self.MAX_DISTANCE_METERS:
                return ResolutionResult(
                    status=ResolutionStatus.NOT_FOUND,
                    error_message=f"가까운 {keyword} 지점을 찾을 수 없습니다. (가장 가까운 곳도 {best_candidate.distance/1000:.1f}km 떨어져 있어요)",
                    log_details=f"{log_details} | 최근접 지점이 너무 멀음: {best_candidate.distance:.0f}m"
                )

            confidence = 0.7  # nearest 검색의 기본 신뢰도

            # 거리가 가까울수록 신뢰도 증가
            if best_candidate.distance:
                if best_candidate.distance <= 500:  # 500m 이내
                    confidence = 0.9
                elif best_candidate.distance <= 1000:  # 1km 이내
                    confidence = 0.8

            detailed_log = f"{log_details} | nearest 검색성공 | 후보: '{best_candidate.name}' | 거리: {best_candidate.distance:.0f}m"
            self.logger.info(detailed_log)

            return ResolutionResult(
                status=ResolutionStatus.SUCCESS,
                resolved_name=best_candidate.name,
                confidence=confidence,
                fallback_used=True,
                candidate=best_candidate,
                log_details=detailed_log
            )

        elif search_result.status == SearchStatus.NOT_FOUND:
            return ResolutionResult(
                status=ResolutionStatus.NOT_FOUND,
                error_message=f"현재 위치 주변에서 '{keyword}' 지점을 찾을 수 없습니다.",
                log_details=f"{log_details} | nearest 검색결과 없음"
            )
        else:
            return ResolutionResult(
                status=ResolutionStatus.API_ERROR,
                error_message=f"장소 검색 중 오류가 발생했습니다: {search_result.error_message}",
                log_details=f"{log_details} | API 오류: {search_result.error_message}"
            )

    def get_user_confirmation_message(self, result: ResolutionResult) -> str:
        """
        사용자 확인 메시지 생성

        Args:
            result: 보정 결과

        Returns:
            str: 사용자에게 보여줄 메시지
        """
        if result.status != ResolutionStatus.SUCCESS:
            return result.error_message or "상호명 보정에 실패했습니다."

        candidate = result.candidate
        confidence_text = ""

        if result.confidence >= 0.9:
            confidence_text = " (확실)"
        elif result.confidence >= 0.7:
            confidence_text = " (추정)"
        else:
            confidence_text = " (불확실)"

        message = f"🏪 상호명: {result.resolved_name}{confidence_text}"

        if candidate:
            if candidate.address:
                message += f"\n📍 주소: {candidate.address}"

            if candidate.distance:
                if candidate.distance < 1000:
                    message += f"\n📏 거리: {candidate.distance:.0f}m"
                else:
                    message += f"\n📏 거리: {candidate.distance/1000:.1f}km"

        if result.fallback_used:
            message += "\n\n💡 위치를 기반으로 가장 가까운 지점을 선택했습니다."

        return message


# 전역 인스턴스
_store_name_resolver: Optional[StoreNameResolver] = None


def get_store_name_resolver() -> StoreNameResolver:
    """전역 StoreNameResolver 인스턴스 반환"""
    global _store_name_resolver
    if _store_name_resolver is None:
        _store_name_resolver = StoreNameResolver()
    return _store_name_resolver