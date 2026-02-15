"""
네이버 블로그 포스팅 자동화 시스템 데이터 모델
블로그 포스트 생성과 관련된 모든 데이터 구조를 정의합니다.
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from pathlib import Path

class UserExperience(BaseModel):
    """사용자 경험 데이터"""
    images: List[str] = Field(..., description="업로드된 이미지 경로 목록")
    category: str = Field(..., description="카테고리 (맛집/제품/호텔/여행/뷰티/패션/IT/기타)")
    personal_review: str = Field(..., description="사용자 직접 작성 감상평")
    additional_notes: Optional[str] = Field(None, description="추가 메모")
    location: Optional[str] = Field(None, description="위치 정보")
    hashtags: List[str] = Field(default=[], description="관련 해시태그")
    rating: Optional[int] = Field(None, description="별점 (1-5)")
    visit_date: Optional[str] = Field(None, description="방문/사용 날짜")
    companion: Optional[str] = Field(None, description="동행자 (가족/친구/혼자/etc)")

    @field_validator('personal_review')
    @classmethod
    def validate_personal_review(cls, v):
        if len(v.strip()) < 50:
            raise ValueError("개인 감상평은 최소 50자 이상이어야 합니다")
        if len(v) > 1000:
            raise ValueError("개인 감상평은 1000자를 초과할 수 없습니다")
        return v.strip()

    @field_validator('category')
    @classmethod
    def validate_category(cls, v):
        allowed_categories = ["맛집", "제품", "호텔", "여행", "뷰티", "패션", "IT", "기타"]
        if v not in allowed_categories:
            raise ValueError(f"카테고리는 다음 중 하나여야 합니다: {', '.join(allowed_categories)}")
        return v

    @field_validator('rating')
    @classmethod
    def validate_rating(cls, v):
        if v is not None and (v < 1 or v > 5):
            raise ValueError("별점은 1-5 사이의 값이어야 합니다")
        return v

    @field_validator('images')
    @classmethod
    def validate_images(cls, v):
        if not v:
            raise ValueError("최소 1개의 이미지가 필요합니다")
        if len(v) > 10:
            raise ValueError("이미지는 최대 10개까지 업로드 가능합니다")
        return v

class BlogPost(BaseModel):
    """생성된 블로그 포스트 데이터"""
    id: str = Field(..., description="포스트 고유 ID")
    title: str = Field(..., description="포스트 제목")
    content: str = Field(..., description="포스트 본문")
    images: List[str] = Field(..., description="포함된 이미지 경로")
    category: str = Field(..., description="카테고리")
    hashtags: List[str] = Field(default=[], description="해시태그")
    quality_score: float = Field(..., description="품질 점수 (0-100)")
    naver_compliance_score: float = Field(..., description="네이버 정책 준수 점수 (0-100)")
    personal_experience_ratio: float = Field(..., description="개인 경험 비율 (0-1)")
    keyword_density: float = Field(..., description="키워드 밀도 (0-1)")
    created_at: datetime = Field(default_factory=datetime.now, description="생성 시간")
    metadata: Dict[str, Any] = Field(default={}, description="추가 메타데이터")

    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        if len(v.strip()) < 10:
            raise ValueError("제목은 최소 10자 이상이어야 합니다")
        if len(v) > 100:
            raise ValueError("제목은 100자를 초과할 수 없습니다")
        return v.strip()

    @field_validator('content')
    @classmethod
    def validate_content(cls, v):
        if len(v.strip()) < 1000:
            raise ValueError("본문은 최소 1000자 이상이어야 합니다")
        if len(v) > 5000:
            raise ValueError("본문은 5000자를 초과할 수 없습니다")
        return v.strip()

    @field_validator('quality_score')
    @classmethod
    def validate_quality_score(cls, v):
        if v < 0 or v > 100:
            raise ValueError("품질 점수는 0-100 사이의 값이어야 합니다")
        return v

    @field_validator('naver_compliance_score')
    @classmethod
    def validate_naver_compliance_score(cls, v):
        if v < 0 or v > 100:
            raise ValueError("네이버 정책 준수 점수는 0-100 사이의 값이어야 합니다")
        return v

    @field_validator('personal_experience_ratio')
    @classmethod
    def validate_personal_experience_ratio(cls, v):
        if v < 0 or v > 1:
            raise ValueError("개인 경험 비율은 0-1 사이의 값이어야 합니다")
        return v

    @field_validator('keyword_density')
    @classmethod
    def validate_keyword_density(cls, v):
        if v < 0 or v > 1:
            raise ValueError("키워드 밀도는 0-1 사이의 값이어야 합니다")
        return v

    @property
    def content_length(self) -> int:
        """본문 글자 수"""
        return len(self.content)

    @property
    def is_high_quality(self) -> bool:
        """고품질 콘텐츠 여부"""
        return (self.quality_score >= 70 and
                self.naver_compliance_score >= 80 and
                self.personal_experience_ratio >= 0.6)

class ContentGenerationRequest(BaseModel):
    """콘텐츠 생성 요청 데이터"""
    user_experience: UserExperience = Field(..., description="사용자 경험 데이터")
    target_length: int = Field(default=1500, description="목표 글자 수")
    tone: str = Field(default="친근하고 자연스러운", description="글의 톤")
    include_external_info: bool = Field(default=True, description="외부 정보 포함 여부")
    external_info_ratio: float = Field(default=0.3, description="외부 정보 비율 (0-1)")
    custom_instructions: Optional[str] = Field(None, description="추가 지시사항")

    @field_validator('target_length')
    @classmethod
    def validate_target_length(cls, v):
        if v < 1000 or v > 2500:
            raise ValueError("목표 글자 수는 1000-2500자 사이여야 합니다")
        return v

    @field_validator('external_info_ratio')
    @classmethod
    def validate_external_info_ratio(cls, v):
        if v < 0 or v > 0.5:
            raise ValueError("외부 정보 비율은 0-50% 사이여야 합니다")
        return v

class QualityValidationResult(BaseModel):
    """품질 검증 결과"""
    is_valid: bool = Field(..., description="검증 통과 여부")
    overall_score: float = Field(..., description="전체 점수")
    quality_score: float = Field(..., description="품질 점수")
    naver_compliance_score: float = Field(..., description="네이버 정책 준수 점수")
    personal_experience_ratio: float = Field(..., description="개인 경험 비율")
    keyword_density: float = Field(..., description="키워드 밀도")
    violations: List[str] = Field(default=[], description="위반 사항 목록")
    recommendations: List[str] = Field(default=[], description="개선 권장사항")
    validation_details: Dict[str, Any] = Field(default={}, description="상세 검증 정보")

class NaverPostingRequest(BaseModel):
    """네이버 블로그 포스팅 요청"""
    blog_post: BlogPost = Field(..., description="포스팅할 블로그 글")
    publish_immediately: bool = Field(default=True, description="즉시 발행 여부")
    allow_comments: bool = Field(default=True, description="댓글 허용 여부")
    blog_category: Optional[str] = Field(None, description="블로그 카테고리")
    tags: List[str] = Field(default=[], description="태그")

class NaverPostingResult(BaseModel):
    """네이버 블로그 포스팅 결과"""
    success: bool = Field(..., description="포스팅 성공 여부")
    post_url: Optional[str] = Field(None, description="포스팅된 글 URL")
    error_message: Optional[str] = Field(None, description="오류 메시지")
    posted_at: Optional[datetime] = Field(None, description="포스팅 시간")
    post_id: Optional[str] = Field(None, description="네이버 블로그 포스트 ID")

class ImageUploadData(BaseModel):
    """이미지 업로드 데이터"""
    filename: str = Field(..., description="원본 파일명")
    saved_path: str = Field(..., description="저장된 경로")
    file_size: int = Field(..., description="파일 크기 (bytes)")
    mime_type: str = Field(..., description="MIME 타입")
    uploaded_at: datetime = Field(default_factory=datetime.now, description="업로드 시간")
    thumbnail_path: Optional[str] = Field(None, description="썸네일 경로")

    @field_validator('file_size')
    @classmethod
    def validate_file_size(cls, v):
        max_size = 50 * 1024 * 1024  # 50MB
        if v > max_size:
            raise ValueError(f"파일 크기가 너무 큽니다. 최대 {max_size // (1024*1024)}MB까지 허용됩니다")
        return v

class ExternalInfoData(BaseModel):
    """외부 정보 수집 데이터"""
    category: str = Field(..., description="정보 카테고리")
    title: str = Field(..., description="정보 제목")
    content: str = Field(..., description="정보 내용")
    source: str = Field(..., description="정보 출처")
    collected_at: datetime = Field(default_factory=datetime.now, description="수집 시간")
    relevance_score: float = Field(default=0.0, description="관련성 점수 (0-1)")

class ProjectMetadata(BaseModel):
    """프로젝트 메타데이터"""
    project_id: str = Field(..., description="프로젝트 ID")
    name: str = Field(..., description="프로젝트 이름")
    created_at: datetime = Field(default_factory=datetime.now, description="생성 시간")
    last_modified: datetime = Field(default_factory=datetime.now, description="마지막 수정 시간")
    user_experience: UserExperience = Field(..., description="사용자 경험 데이터")
    blog_post: Optional[BlogPost] = Field(None, description="생성된 블로그 포스트")
    validation_result: Optional[QualityValidationResult] = Field(None, description="품질 검증 결과")
    posting_result: Optional[NaverPostingResult] = Field(None, description="포스팅 결과")
    status: str = Field(default="draft", description="상태 (draft/validated/posted/failed)")

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        allowed_statuses = ["draft", "validated", "posted", "failed"]
        if v not in allowed_statuses:
            raise ValueError(f"상태는 다음 중 하나여야 합니다: {', '.join(allowed_statuses)}")
        return v


# ============================================================
# Phase 2: 새로운 데이터 모델들 (설계안 기준)
# ============================================================

class UserDirectInput(BaseModel):
    """사용자 직접 입력 데이터 (위치, 해시태그 제거된 버전)"""
    category: str = Field(..., description="카테고리 (맛집/제품/호텔/여행/뷰티/패션/IT/기타)")
    rating: Optional[int] = Field(None, description="별점 (1-5)")
    visit_date: Optional[str] = Field(None, description="방문/사용 날짜")
    companion: Optional[str] = Field(None, description="동행자 (가족/친구/혼자/연인/동료)")
    personal_review: str = Field(..., description="개인 감상평 (위치 추론 소스)")
    ai_additional_script: Optional[str] = Field(None, description="AI 전달용 추가 스크립트")

    @field_validator('category')
    @classmethod
    def validate_category(cls, v):
        allowed_categories = ["맛집", "제품", "호텔", "여행", "뷰티", "패션", "IT", "기타"]
        if v not in allowed_categories:
            raise ValueError(f"카테고리는 다음 중 하나여야 합니다: {', '.join(allowed_categories)}")
        return v

    @field_validator('rating')
    @classmethod
    def validate_rating(cls, v):
        if v is not None and (v < 1 or v > 5):
            raise ValueError("별점은 1-5 사이의 값이어야 합니다")
        return v

    @field_validator('personal_review')
    @classmethod
    def validate_personal_review(cls, v):
        if len(v.strip()) < 50:
            raise ValueError("개인 감상평은 최소 50자 이상이어야 합니다")
        if len(v) > 1000:
            raise ValueError("개인 감상평은 1000자를 초과할 수 없습니다")
        return v.strip()

    @field_validator('companion')
    @classmethod
    def validate_companion(cls, v):
        if v is not None:
            allowed_companions = ["가족", "친구", "혼자", "연인", "동료"]
            if v not in allowed_companions:
                raise ValueError(f"동행자는 다음 중 하나여야 합니다: {', '.join(allowed_companions)}")
        return v


class LocationInfo(BaseModel):
    """위치 정보 상세 구조"""
    detected_location: Optional[str] = Field(None, description="추론된 위치명")
    coordinates: Optional[Tuple[float, float]] = Field(None, description="GPS 좌표 (latitude, longitude)")
    source: str = Field(..., description="추론 소스 (exif|text|none)")
    confidence: float = Field(..., description="신뢰도 (0.0-1.0)")

    @field_validator('source')
    @classmethod
    def validate_source(cls, v):
        allowed_sources = ["exif", "text", "none"]
        if v not in allowed_sources:
            raise ValueError(f"추론 소스는 다음 중 하나여야 합니다: {', '.join(allowed_sources)}")
        return v

    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v):
        if v < 0.0 or v > 1.0:
            raise ValueError("신뢰도는 0.0-1.0 사이의 값이어야 합니다")
        return v


class EXIFAnalysisResult(BaseModel):
    """EXIF 분석 결과"""
    gps_found: bool = Field(..., description="GPS 정보 발견 여부")
    coordinates: Optional[Tuple[float, float]] = Field(None, description="GPS 좌표")
    exif_confidence: float = Field(default=0.0, description="EXIF 기반 신뢰도")
    extraction_method: Optional[str] = Field(None, description="추출 방법")
    raw_exif_data: Dict[str, Any] = Field(default={}, description="원본 EXIF 데이터")


class TextLocationAnalysis(BaseModel):
    """텍스트 기반 위치 분석 결과"""
    detected_location: Optional[str] = Field(None, description="텍스트에서 추출된 위치명")
    extraction_method: str = Field(..., description="추출 방법 (pattern_matching|keyword_extraction)")
    matched_patterns: List[str] = Field(default=[], description="매칭된 패턴들")
    text_confidence: float = Field(..., description="텍스트 기반 신뢰도")
    candidate_locations: List[str] = Field(default=[], description="후보 위치들")


class HashtagCandidates(BaseModel):
    """해시태그 후보 생성 결과"""
    category_based: List[str] = Field(default=[], description="카테고리 기반 태그")
    rating_based: List[str] = Field(default=[], description="별점 기반 태그")
    companion_based: List[str] = Field(default=[], description="동행자 기반 태그")
    keyword_based: List[str] = Field(default=[], description="키워드 기반 태그")
    location_based: List[str] = Field(default=[], description="위치 기반 태그")


class HashtagRefinementResult(BaseModel):
    """해시태그 정제 결과"""
    deduplicated: List[str] = Field(default=[], description="중복 제거된 태그")
    semantic_filtered: List[str] = Field(default=[], description="의미 중복 제거된 태그")
    final_tags: List[str] = Field(default=[], description="최종 선택된 태그 (5-7개)")


class AIInferredData(BaseModel):
    """AI 자동 추론/생성 데이터"""
    location_analysis: Dict[str, Any] = Field(..., description="위치 분석 결과")
    hashtag_analysis: Dict[str, Any] = Field(..., description="해시태그 분석 결과")
    confidence_scores: Dict[str, float] = Field(..., description="신뢰도 점수들")
    processing_metadata: Dict[str, Any] = Field(default={}, description="처리 메타데이터")


class MetaJsonData(BaseModel):
    """meta.json 파일 구조 (불변 원본)"""
    project_id: str = Field(..., description="프로젝트 ID")
    created_at: datetime = Field(default_factory=datetime.now, description="생성 시간")
    user_input: UserDirectInput = Field(..., description="사용자 직접 입력")
    images: List[str] = Field(..., description="이미지 파일명 목록")
    settings: Dict[str, Any] = Field(default={}, description="생성 설정")

    @field_validator('images')
    @classmethod
    def validate_images(cls, v):
        if not v:
            raise ValueError("최소 1개의 이미지가 필요합니다")
        if len(v) > 10:
            raise ValueError("이미지는 최대 10개까지 업로드 가능합니다")
        return v


class AnalysisJsonData(BaseModel):
    """analysis.json 파일 구조 (AI 추론 결과, 재처리 가능)"""
    project_id: str = Field(..., description="프로젝트 ID")
    analysis_timestamp: datetime = Field(default_factory=datetime.now, description="분석 시간")
    location_analysis: Dict[str, Any] = Field(..., description="위치 분석 상세 결과")
    hashtag_analysis: Dict[str, Any] = Field(..., description="해시태그 분석 상세 결과")
    confidence_scores: Dict[str, float] = Field(..., description="내부 전용 신뢰도 점수")
    processing_metadata: Dict[str, str] = Field(default={}, description="처리 상태 메타데이터")


class GenerationReadyData(BaseModel):
    """generation_ready.json 파일 구조 (블로그 생성용 최종 데이터)"""
    project_id: str = Field(..., description="프로젝트 ID")
    generation_timestamp: datetime = Field(default_factory=datetime.now, description="생성 준비 시간")
    merged_data: Dict[str, Any] = Field(..., description="통합된 최종 데이터")
    generation_settings: Dict[str, Any] = Field(..., description="생성 설정")

    @field_validator('merged_data')
    @classmethod
    def validate_merged_data(cls, v):
        required_fields = ["category", "personal_review", "images"]
        for field in required_fields:
            if field not in v:
                raise ValueError(f"merged_data에 필수 필드 '{field}'가 없습니다")
        return v


class PipelineLogEntry(BaseModel):
    """파이프라인 로그 엔트리"""
    timestamp: datetime = Field(default_factory=datetime.now, description="로그 시간")
    stage: str = Field(..., description="처리 단계")
    status: str = Field(..., description="상태 (completed|failed|warning)")
    message: str = Field(..., description="로그 메시지")
    confidence: Optional[float] = Field(None, description="신뢰도 (해당되는 경우)")
    details: Dict[str, Any] = Field(default={}, description="추가 상세 정보")

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        allowed_statuses = ["completed", "failed", "warning", "info"]
        if v not in allowed_statuses:
            raise ValueError(f"상태는 다음 중 하나여야 합니다: {', '.join(allowed_statuses)}")
        return v