"""
사용자 경험 처리 모듈
EXIF 데이터 추출, 위치 추론, 키워드 추출 등 사용자 경험 데이터를 분석하는 모듈입니다.
"""

import re
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

# PIL이 없는 경우를 대비한 조건부 import
try:
    from PIL import Image
    from PIL.ExifTags import TAGS, GPSTAGS
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from src.content.models import (
    UserDirectInput, EXIFAnalysisResult, TextLocationAnalysis,
    LocationInfo, PipelineLogEntry
)
from src.utils.exceptions import FileProcessingError


class EXIFProcessor:
    """EXIF 데이터 추출 및 처리 클래스"""

    @staticmethod
    def extract_exif_data(image_path: Path) -> EXIFAnalysisResult:
        """이미지에서 EXIF 데이터 추출"""

        if not PIL_AVAILABLE:
            return EXIFAnalysisResult(
                gps_found=False,
                coordinates=None,
                exif_confidence=0.0,
                extraction_method="no_pil_library",
                raw_exif_data={}
            )

        if not image_path.exists():
            return EXIFAnalysisResult(
                gps_found=False,
                coordinates=None,
                exif_confidence=0.0,
                extraction_method="file_not_found",
                raw_exif_data={}
            )

        try:
            with Image.open(image_path) as img:
                # EXIF 데이터 추출
                exif_data = img._getexif()

                if exif_data is None:
                    return EXIFAnalysisResult(
                        gps_found=False,
                        coordinates=None,
                        exif_confidence=0.0,
                        extraction_method="no_exif_data",
                        raw_exif_data={}
                    )

                # EXIF 데이터를 읽기 가능한 형태로 변환
                readable_exif = {}
                gps_info = {}

                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id, tag_id)
                    readable_exif[tag] = value

                    # GPS 정보 추출
                    if tag == "GPSInfo":
                        for gps_tag_id, gps_value in value.items():
                            gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                            gps_info[gps_tag] = gps_value

                # GPS 좌표 변환
                coordinates = EXIFProcessor._extract_gps_coordinates(gps_info)

                return EXIFAnalysisResult(
                    gps_found=coordinates is not None,
                    coordinates=coordinates,
                    exif_confidence=0.9 if coordinates else 0.0,
                    extraction_method="pil_extraction",
                    raw_exif_data={
                        "exif": readable_exif,
                        "gps": gps_info
                    }
                )

        except Exception as e:
            return EXIFAnalysisResult(
                gps_found=False,
                coordinates=None,
                exif_confidence=0.0,
                extraction_method="extraction_failed",
                raw_exif_data={"error": str(e)}
            )

    @staticmethod
    def _extract_gps_coordinates(gps_info: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        """GPS 정보에서 좌표 추출 및 변환"""

        try:
            # 필수 GPS 태그 확인
            required_tags = ['GPSLatitude', 'GPSLatitudeRef', 'GPSLongitude', 'GPSLongitudeRef']
            for tag in required_tags:
                if tag not in gps_info:
                    return None

            # 위도 계산
            lat_dms = gps_info['GPSLatitude']
            lat_ref = gps_info['GPSLatitudeRef']
            latitude = EXIFProcessor._dms_to_decimal(lat_dms, lat_ref)

            # 경도 계산
            lon_dms = gps_info['GPSLongitude']
            lon_ref = gps_info['GPSLongitudeRef']
            longitude = EXIFProcessor._dms_to_decimal(lon_dms, lon_ref)

            return (latitude, longitude)

        except Exception:
            return None

    @staticmethod
    def _dms_to_decimal(dms: Tuple, ref: str) -> float:
        """도분초(DMS) 형식을 십진도(Decimal) 형식으로 변환"""
        degrees, minutes, seconds = dms
        decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600

        # 남위 또는 서경인 경우 음수로 변환
        if ref in ['S', 'W']:
            decimal = -decimal

        return decimal


class LocationInferenceEngine:
    """텍스트 기반 위치 추론 엔진"""

    # 위치 패턴 정의 (우선순위별)
    LOCATION_PATTERNS = {
        "specific_place": {
            "pattern": r"([가-힣]+(?:역|점|센터|몰|타워|빌딩|마트|호텔|리조트|카페|상회|식당|레스토랑|펜션|모텔|게스트하우스|클럽|바|주점|술집))",
            "confidence_weight": 0.9,
            "examples": ["강남역", "롯데타워", "이마트", "곤지암리조트", "이진상회"]
        },
        "district": {
            "pattern": r"([가-힣]+구\s?[가-힣]+동)",
            "confidence_weight": 0.8,
            "examples": ["강남구 신사동", "마포구 홍대동"]
        },
        "area": {
            "pattern": r"([가-힣]{2,}(?:동|시))",
            "confidence_weight": 0.6,
            "examples": ["홍대동", "부산시"]
        },
        "area_gu": {
            "pattern": r"([가-힣]{2,}구)(?![가-힣])",
            "confidence_weight": 0.7,
            "examples": ["강남구", "마포구"]
        },
        "landmark": {
            "pattern": r"([가-힣]+(?:대학교|공원|시장|교|산|강|해변|공항|스키장|놀이공원|워터파크))",
            "confidence_weight": 0.7,
            "examples": ["연세대학교", "남대문시장", "한강", "곤지암리조트스키장"]
        },
        "subway_line": {
            "pattern": r"([가-힣0-9]+호선\s?[가-힣]+역?)",
            "confidence_weight": 0.8,
            "examples": ["2호선 강남역", "1호선 종각"]
        }
    }

    # 제외할 키워드 (위치가 아닌 단어들)
    EXCLUDE_KEYWORDS = {
        "친구", "가족", "연인", "동료", "혼자", "사람", "불구", "모두", "여러", "많이",
        "조금", "정말", "너무", "아주", "매우", "꽤", "상당", "거의", "완전", "전혀",
        "그냥", "바로", "다시", "또", "더", "덜", "좀", "잠깐", "계속", "항상",
        "가끔", "때로", "간혹", "자주", "늘", "언제나", "결국", "마침내", "드디어"
    }

    @classmethod
    def infer_location_from_text(cls, text: str) -> TextLocationAnalysis:
        """텍스트에서 위치 정보 추론"""

        detected_locations = []
        matched_patterns = []
        confidence_scores = []

        # 각 패턴별로 매칭 시도
        for pattern_name, pattern_info in cls.LOCATION_PATTERNS.items():
            pattern = pattern_info["pattern"]
            weight = pattern_info["confidence_weight"]

            matches = re.findall(pattern, text)

            for match in matches:
                # 제외 키워드 필터링
                if match in cls.EXCLUDE_KEYWORDS:
                    continue

                # 너무 짧은 매칭 제외 (1글자)
                if len(match) < 2:
                    continue

                detected_locations.append({
                    "location": match,
                    "pattern_type": pattern_name,
                    "confidence": weight,
                    "raw_match": match
                })
                matched_patterns.append(match)

        if not detected_locations:
            return TextLocationAnalysis(
                detected_location=None,
                extraction_method="pattern_matching",
                matched_patterns=[],
                text_confidence=0.0,
                candidate_locations=[]
            )

        # 최고 신뢰도 위치 선택
        best_location = max(detected_locations, key=lambda x: x["confidence"])

        # 후보 위치들 (중복 제거)
        candidate_locations = list(set(loc["location"] for loc in detected_locations))

        return TextLocationAnalysis(
            detected_location=best_location["location"],
            extraction_method="pattern_matching",
            matched_patterns=list(set(matched_patterns)),
            text_confidence=best_location["confidence"],
            candidate_locations=candidate_locations
        )

    @classmethod
    def normalize_location_name(cls, location: str) -> str:
        """위치명 정규화"""
        if not location:
            return location

        # 기본 정규화 규칙
        location = location.strip()

        # 역명 정규화: "강남역 근처" → "강남역"
        location = re.sub(r'\s*(근처|앞|옆|쪽)\s*', '', location)

        # 중복 공백 제거
        location = re.sub(r'\s+', ' ', location)

        return location

    @classmethod
    def calculate_location_confidence(cls, text_analysis: TextLocationAnalysis, exif_result: EXIFAnalysisResult) -> float:
        """EXIF와 텍스트 분석을 종합한 최종 신뢰도 계산"""

        # EXIF GPS 데이터가 있으면 높은 신뢰도
        if exif_result.gps_found and exif_result.coordinates:
            return 0.95

        # 텍스트 기반 신뢰도 반환
        return text_analysis.text_confidence


class KeywordExtractor:
    """키워드 추출 클래스"""

    # 카테고리별 키워드 패턴
    CATEGORY_KEYWORDS = {
        "맛집": {
            "food_types": r"(이탈리안|한식|중식|일식|양식|카페|디저트|파스타|피자|스테이크|초밥|라멘)",
            "food_items": r"(알리오올리오|까르보나라|마르게리타|티라미수|라떼|아메리카노)",
            "taste_words": r"(맛있|달콤|짭짤|매콤|부드러|고소|신선|향긋)"
        },
        "호텔": {
            "hotel_types": r"(호텔|리조트|펜션|게스트하우스|모텔|풀빌라)",
            "amenities": r"(수영장|스파|조식|뷔페|피트니스|라운지|바)",
            "service_words": r"(친절|깔끔|럭셔리|편안|아늑|깨끗)"
        },
        "제품": {
            "product_types": r"(화장품|의류|전자제품|가전|액세서리|신발)",
            "quality_words": r"(품질|성능|디자인|가성비|내구성|실용)"
        }
    }

    @classmethod
    def extract_keywords(cls, text: str, category: str) -> List[str]:
        """텍스트에서 카테고리별 키워드 추출"""

        keywords = []

        if category in cls.CATEGORY_KEYWORDS:
            category_patterns = cls.CATEGORY_KEYWORDS[category]

            for pattern_type, pattern in category_patterns.items():
                matches = re.findall(pattern, text)
                keywords.extend(matches)

        # 중복 제거 및 정렬
        return list(set(keywords))


class ExperienceProcessor:
    """사용자 경험 통합 처리 클래스"""

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.images_dir = project_dir / "images"

    def process_user_experience(self, user_input: UserDirectInput, images: List[str]) -> Dict[str, Any]:
        """사용자 경험 데이터 통합 처리"""

        # 1. EXIF 분석 (첫 번째 이미지만 분석)
        exif_result = self._analyze_first_image_exif(images)

        # 2. 텍스트 기반 위치 추론
        text_analysis = LocationInferenceEngine.infer_location_from_text(user_input.personal_review)

        # 3. 최종 위치 결정
        final_location = self._determine_final_location(exif_result, text_analysis)

        # 4. 키워드 추출
        extracted_keywords = KeywordExtractor.extract_keywords(user_input.personal_review, user_input.category)

        # 5. 위치 분석 결과 구성
        location_analysis = {
            "exif_results": exif_result.model_dump(),
            "text_analysis": text_analysis.model_dump(),
            "final_location": final_location.model_dump()
        }

        return {
            "location_analysis": location_analysis,
            "extracted_keywords": extracted_keywords
        }

    def _analyze_first_image_exif(self, images: List[str]) -> EXIFAnalysisResult:
        """첫 번째 이미지의 EXIF 분석"""

        if not images:
            return EXIFAnalysisResult(
                gps_found=False,
                coordinates=None,
                exif_confidence=0.0,
                extraction_method="no_images",
                raw_exif_data={}
            )

        first_image_path = self.images_dir / images[0]
        return EXIFProcessor.extract_exif_data(first_image_path)

    def _determine_final_location(self, exif_result: EXIFAnalysisResult, text_analysis: TextLocationAnalysis) -> LocationInfo:
        """EXIF와 텍스트 분석을 종합한 최종 위치 결정"""

        # EXIF GPS 데이터 우선
        if exif_result.gps_found and exif_result.coordinates:
            return LocationInfo(
                detected_location="GPS 좌표 기반",  # TODO: 좌표를 주소로 변환 필요
                coordinates=exif_result.coordinates,
                source="exif",
                confidence=exif_result.exif_confidence
            )

        # 텍스트 분석 결과 사용
        if text_analysis.detected_location:
            normalized_location = LocationInferenceEngine.normalize_location_name(text_analysis.detected_location)

            return LocationInfo(
                detected_location=normalized_location,
                coordinates=None,
                source="text",
                confidence=text_analysis.text_confidence
            )

        # 모두 실패
        return LocationInfo(
            detected_location=None,
            coordinates=None,
            source="none",
            confidence=0.0
        )

    def build_image_path(self, filename: str) -> Path:
        """이미지 파일 경로 생성"""
        return self.images_dir / filename

    def check_images_exist(self, images: List[str]) -> Dict[str, bool]:
        """이미지 파일 존재 확인"""
        return {
            filename: self.build_image_path(filename).exists()
            for filename in images
        }