"""
블로그 글 생성 모듈
해시태그 자동 생성, 콘텐츠 생성 준비 등을 담당하는 모듈입니다.
"""

import re
from typing import Dict, List, Any, Optional, Set
from pathlib import Path
from datetime import datetime

from src.content.models import (
    UserDirectInput, LocationInfo, HashtagCandidates,
    HashtagRefinementResult, PipelineLogEntry
)


class HashtagGenerator:
    """해시태그 자동 생성 클래스"""

    # 카테고리별 기본 태그 매핑
    CATEGORY_HASHTAGS = {
        "맛집": ["#맛집", "#음식", "#food", "#restaurant"],
        "제품": ["#제품리뷰", "#추천템", "#product", "#review"],
        "호텔": ["#호텔", "#숙박", "#여행", "#hotel", "#travel"],
        "여행": ["#여행", "#관광", "#travel", "#trip"],
        "뷰티": ["#뷰티", "#화장품", "#beauty", "#cosmetics"],
        "패션": ["#패션", "#스타일", "#fashion", "#style"],
        "IT": ["#IT", "#기술", "#tech", "#technology"],
        "기타": ["#일상", "#라이프스타일", "#lifestyle"]
    }

    # 별점별 기본 태그
    RATING_HASHTAGS = {
        5: ["#강추", "#최고", "#완벽", "#대만족"],
        4: ["#추천", "#좋아요", "#만족", "#괜찮"],
        3: ["#보통", "#그냥그냥", "#나쁘지않아"],
        2: ["#아쉬워요", "#부족", "#별로"],
        1: ["#실망", "#최악", "#비추천"]
    }

    # 동행자별 기본 태그
    COMPANION_HASHTAGS = {
        "가족": ["#가족여행", "#family", "#가족나들이", "#가족식사"],
        "친구": ["#친구와함께", "#friends", "#친구들과", "#우정"],
        "연인": ["#데이트", "#couple", "#연인", "#로맨틱"],
        "동료": ["#회식", "#동료", "#직장", "#팀워크"],
        "혼자": ["#혼자", "#solo", "#나만의시간", "#힐링"]
    }

    @classmethod
    def generate_candidate_hashtags(cls, user_input: UserDirectInput, location_info: LocationInfo, extracted_keywords: List[str]) -> HashtagCandidates:
        """모든 후보 해시태그 생성"""

        candidates = HashtagCandidates()

        # 1. 카테고리 기반 태그
        if user_input.category in cls.CATEGORY_HASHTAGS:
            candidates.category_based = cls.CATEGORY_HASHTAGS[user_input.category][:2]  # 최대 2개

        # 2. 별점 기반 태그
        if user_input.rating and user_input.rating in cls.RATING_HASHTAGS:
            candidates.rating_based = cls.RATING_HASHTAGS[user_input.rating][:2]  # 최대 2개

        # 3. 동행자 기반 태그
        if user_input.companion and user_input.companion in cls.COMPANION_HASHTAGS:
            candidates.companion_based = cls.COMPANION_HASHTAGS[user_input.companion][:2]  # 최대 2개

        # 4. 키워드 기반 태그 (추출된 키워드를 해시태그로 변환)
        candidates.keyword_based = cls._convert_keywords_to_hashtags(extracted_keywords)

        # 5. 위치 기반 태그 (location_info가 None이 아닐 때만)
        if location_info.detected_location:
            candidates.location_based = cls._generate_location_hashtags(location_info.detected_location, user_input.category)

        return candidates

    @classmethod
    def _convert_keywords_to_hashtags(cls, keywords: List[str]) -> List[str]:
        """추출된 키워드를 해시태그로 변환"""
        hashtags = []

        for keyword in keywords:
            if keyword and len(keyword) >= 2:  # 2글자 이상인 키워드만
                # 해시태그 형태로 변환
                hashtag = f"#{keyword}"
                hashtags.append(hashtag)

        return hashtags[:4]  # 최대 4개

    @classmethod
    def _generate_location_hashtags(cls, location: str, category: str) -> List[str]:
        """위치 정보를 기반으로 해시태그 생성"""
        hashtags = []

        if not location:
            return hashtags

        # 기본 위치 태그
        location_parts = cls._parse_location_components(location)

        for part in location_parts:
            # 기본 지역 태그
            hashtags.append(f"#{part}")

            # 카테고리와 결합된 위치 태그
            if category == "맛집":
                hashtags.append(f"#{part}맛집")
            elif category == "호텔":
                hashtags.append(f"#{part}숙박")
            elif category == "여행":
                hashtags.append(f"#{part}여행")

        return hashtags[:3]  # 최대 3개

    @classmethod
    def _parse_location_components(cls, location: str) -> List[str]:
        """위치명에서 해시태그로 사용할 구성요소 추출"""
        components = []

        # 역명 추출 (예: "강남역" -> "강남")
        station_match = re.search(r'([가-힣]+)역', location)
        if station_match:
            components.append(station_match.group(1))

        # 구 이름 추출 (예: "강남구" -> "강남")
        gu_match = re.search(r'([가-힣]+)구', location)
        if gu_match:
            components.append(gu_match.group(1))

        # 동 이름 추출 (예: "신사동" -> "신사")
        dong_match = re.search(r'([가-힣]+)동', location)
        if dong_match:
            components.append(dong_match.group(1))

        # 일반 지역명 (예: "홍대", "명동")
        area_match = re.search(r'([가-힣]{2,4})(?:근처|앞|쪽)?', location)
        if area_match and area_match.group(1) not in components:
            components.append(area_match.group(1))

        # 중복 제거 및 2글자 이상만 반환
        return list(set(comp for comp in components if len(comp) >= 2))

    @classmethod
    def refine_hashtags(cls, candidates: HashtagCandidates) -> HashtagRefinementResult:
        """해시태그 정제 파이프라인"""

        # 1단계: 모든 후보 태그 수집
        all_candidates = []
        all_candidates.extend(candidates.category_based)
        all_candidates.extend(candidates.rating_based)
        all_candidates.extend(candidates.companion_based)
        all_candidates.extend(candidates.keyword_based)
        all_candidates.extend(candidates.location_based)

        # 2단계: 중복 제거
        deduplicated = list(dict.fromkeys(all_candidates))

        # 3단계: 의미 중복 제거
        semantic_filtered = cls._remove_semantic_duplicates(deduplicated)

        # 4단계: 우선순위 점수 기반 정렬
        scored_tags = cls._calculate_priority_scores(semantic_filtered, candidates)

        # 5단계: 최종 상위 N개 선택 (5-7개 제한)
        final_tags = cls._select_top_hashtags(scored_tags, max_count=6)

        return HashtagRefinementResult(
            deduplicated=deduplicated,
            semantic_filtered=semantic_filtered,
            final_tags=final_tags
        )

    @classmethod
    def _remove_semantic_duplicates(cls, hashtags: List[str]) -> List[str]:
        """의미적으로 중복된 해시태그 제거"""

        # 의미 중복 규칙 정의
        semantic_groups = {
            # 위치 관련 중복
            "location": {
                "patterns": [
                    (r"#([가-힣]+)역맛집", r"#\1맛집"),  # #강남역맛집 -> #강남맛집
                    (r"#([가-힣]+)구맛집", r"#\1맛집"),  # #강남구맛집 -> #강남맛집
                    (r"#([가-힣]+)역", r"#\1"),         # #강남역 -> #강남 (맛집 태그와 함께 있을 때)
                ]
            },
            # 평가 관련 중복
            "rating": {
                "duplicates": {
                    "#강추": ["#최고", "#완벽", "#대만족"],
                    "#추천": ["#좋아요", "#만족"],
                    "#별로": ["#실망", "#비추천"]
                }
            },
            # 카테고리 관련 중복
            "category": {
                "duplicates": {
                    "#맛집": ["#음식", "#restaurant"],
                    "#여행": ["#travel", "#trip"],
                    "#뷰티": ["#beauty", "#화장품"]
                }
            }
        }

        filtered = hashtags.copy()

        # 패턴 기반 중복 제거
        for group_name, group_rules in semantic_groups.items():
            if "patterns" in group_rules:
                filtered = cls._apply_pattern_deduplication(filtered, group_rules["patterns"])

        # 중복 목록 기반 제거
        for group_name, group_rules in semantic_groups.items():
            if "duplicates" in group_rules:
                filtered = cls._apply_duplicate_list_deduplication(filtered, group_rules["duplicates"])

        return filtered

    @classmethod
    def _apply_pattern_deduplication(cls, hashtags: List[str], patterns: List[tuple]) -> List[str]:
        """패턴 기반 중복 제거"""
        result = []

        for hashtag in hashtags:
            normalized = hashtag

            # 각 패턴에 대해 정규화 적용
            for from_pattern, to_pattern in patterns:
                if re.match(from_pattern, hashtag):
                    normalized = re.sub(from_pattern, to_pattern, hashtag)
                    break

            # 정규화된 태그가 이미 결과에 없으면 추가
            if normalized not in result:
                result.append(normalized)

        return result

    @classmethod
    def _apply_duplicate_list_deduplication(cls, hashtags: List[str], duplicate_rules: Dict[str, List[str]]) -> List[str]:
        """중복 목록 기반 제거"""
        result = []

        for hashtag in hashtags:
            should_add = True

            # 우선순위가 높은 태그가 이미 있으면 중복 태그는 제외
            for primary_tag, duplicates in duplicate_rules.items():
                if hashtag in duplicates and primary_tag in hashtags:
                    should_add = False
                    break

            if should_add:
                result.append(hashtag)

        return result

    @classmethod
    def _calculate_priority_scores(cls, hashtags: List[str], candidates: HashtagCandidates) -> List[tuple]:
        """우선순위 점수 계산"""

        # 우선순위 가중치
        priority_weights = {
            "category_based": 1.0,      # 카테고리 태그 최우선
            "location_based": 0.9,      # 위치 태그 높은 우선순위
            "keyword_based": 0.8,       # 키워드 태그 중간 우선순위
            "rating_based": 0.7,        # 별점 태그 낮은 우선순위
            "companion_based": 0.6      # 동행자 태그 최낮은 우선순위
        }

        scored_tags = []

        for hashtag in hashtags:
            score = 0.0

            # 각 카테고리에서의 점수 계산
            if hashtag in candidates.category_based:
                score = priority_weights["category_based"]
            elif hashtag in candidates.location_based:
                score = priority_weights["location_based"]
            elif hashtag in candidates.keyword_based:
                score = priority_weights["keyword_based"]
            elif hashtag in candidates.rating_based:
                score = priority_weights["rating_based"]
            elif hashtag in candidates.companion_based:
                score = priority_weights["companion_based"]

            # 태그 길이와 품질에 따른 추가 점수
            score += cls._calculate_quality_bonus(hashtag)

            scored_tags.append((hashtag, score))

        # 점수순으로 정렬 (내림차순)
        return sorted(scored_tags, key=lambda x: x[1], reverse=True)

    @classmethod
    def _calculate_quality_bonus(cls, hashtag: str) -> float:
        """해시태그 품질에 따른 보너스 점수"""
        bonus = 0.0

        # 길이 보너스 (너무 길거나 짧으면 감점)
        tag_len = len(hashtag) - 1  # # 제외
        if 3 <= tag_len <= 6:
            bonus += 0.1
        elif tag_len < 2:
            bonus -= 0.2

        # 한글/영어 조합 확인 (너무 많은 영어는 감점)
        if re.search(r'[a-zA-Z]', hashtag):
            if len(re.findall(r'[a-zA-Z]', hashtag)) < len(hashtag) // 2:
                bonus += 0.05
            else:
                bonus -= 0.1

        return bonus

    @classmethod
    def _select_top_hashtags(cls, scored_tags: List[tuple], max_count: int = 6) -> List[str]:
        """최종 상위 해시태그 선택"""

        if not scored_tags:
            return []

        # 점수가 0보다 큰 태그만 선택
        valid_tags = [tag for tag, score in scored_tags if score > 0]

        # 최대 개수만큼 선택
        return valid_tags[:max_count]


class ContentStructureBuilder:
    """블로그 콘텐츠 구조 구성 클래스"""

    @staticmethod
    def build_content_structure(user_input: UserDirectInput, location_info: LocationInfo,
                               hashtags: List[str], images: List[str]) -> Dict[str, Any]:
        """블로그 콘텐츠 생성을 위한 구조화된 데이터 구성"""

        # 위치 처리 전략
        location_context = ContentStructureBuilder._determine_location_context(location_info)

        # 콘텐츠 요소 분석
        content_elements = ContentStructureBuilder._analyze_content_elements(user_input.personal_review)

        # 생성 가이드라인 구성
        generation_guidelines = {
            "location_strategy": location_context["strategy"],
            "location_mention": location_context["mention_text"],
            "personal_experience_focus": True,
            "external_info_allowed": True,
            "tone": "친근하고 자연스러운",
            "avoid_patterns": [
                "AI가 작성한 것 같은 표현",
                "총정리하면",
                "도움이 되셨다면",
                "마무리하겠습니다"
            ]
        }

        return {
            "user_data": {
                "category": user_input.category,
                "rating": user_input.rating,
                "visit_date": user_input.visit_date,
                "companion": user_input.companion,
                "personal_review": user_input.personal_review,
                "ai_additional_script": user_input.ai_additional_script
            },
            "location_info": {
                "detected_location": location_info.detected_location,
                "context": location_context
            },
            "hashtags": hashtags,
            "images": images,
            "content_elements": content_elements,
            "generation_guidelines": generation_guidelines
        }

    @staticmethod
    def _determine_location_context(location_info: LocationInfo) -> Dict[str, Any]:
        """위치 정보 컨텍스트 결정"""

        if not location_info.detected_location:
            return {
                "strategy": "location_generic",
                "mention_text": None,
                "description": "구체적 지역명 언급 회피"
            }

        return {
            "strategy": "location_specific",
            "mention_text": location_info.detected_location,
            "description": f"추론된 위치 활용: {location_info.detected_location}",
            "confidence": location_info.confidence
        }

    @staticmethod
    def _analyze_content_elements(personal_review: str) -> Dict[str, Any]:
        """개인 감상평에서 콘텐츠 요소 분석"""

        # 감정 표현 추출
        positive_words = re.findall(r'(맛있|좋|훌륭|완벽|최고|만족|추천)', personal_review)
        negative_words = re.findall(r'(별로|아쉬|실망|부족|나빠)', personal_review)

        # 구체적 묘사 추출
        descriptive_phrases = re.findall(r'([가-힣\s]{10,30})', personal_review)

        return {
            "sentiment": {
                "positive_count": len(positive_words),
                "negative_count": len(negative_words),
                "overall_tone": "positive" if len(positive_words) > len(negative_words) else "neutral"
            },
            "descriptive_elements": descriptive_phrases[:3],  # 최대 3개
            "review_length": len(personal_review),
            "personal_indicators": len(re.findall(r'(제가|저는|개인적으로|직접)', personal_review))
        }


class BlogContentGenerator:
    """OpenAI API를 사용한 블로그 글 생성 클래스"""

    def __init__(self, openai_api_key: Optional[str] = None):
        """
        Args:
            openai_api_key: OpenAI API 키. None인 경우 환경변수에서 로드
        """
        try:
            import openai
            self.openai = openai

            if openai_api_key:
                self.openai.api_key = openai_api_key
            else:
                # 환경변수에서 로드
                import os
                api_key = os.getenv('OPENAI_API_KEY')
                if not api_key:
                    raise ValueError("OpenAI API 키가 설정되지 않았습니다. OPENAI_API_KEY 환경변수를 설정하거나 생성자 매개변수로 전달하세요.")
                self.openai.api_key = api_key

            self.client = openai.OpenAI(api_key=self.openai.api_key)

        except ImportError:
            raise ImportError("openai 패키지가 설치되지 않았습니다. pip install openai로 설치하세요.")

    def generate_blog_post(self, generation_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        generation_ready.json 데이터를 기반으로 블로그 포스트 생성

        Args:
            generation_data: generation_ready.json의 데이터

        Returns:
            생성된 블로그 포스트 및 메타데이터
        """
        try:
            # 데이터 추출
            merged_data = generation_data["merged_data"]
            settings = generation_data["generation_settings"]

            # 프롬프트 생성
            prompt = self._build_generation_prompt(merged_data, settings)

            # 환경변수에서 OpenAI 설정 로드
            import os
            model_name = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')
            max_tokens = int(os.getenv('OPENAI_MAX_TOKENS', '2000'))
            temperature = float(os.getenv('OPENAI_TEMPERATURE', '0.7'))

            # OpenAI API 호출
            response = self.client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt()
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                presence_penalty=0.6,
                frequency_penalty=0.3
            )

            generated_content = response.choices[0].message.content.strip()

            # 후처리
            processed_content = self._post_process_content(generated_content, merged_data)

            # 결과 구성
            return {
                "success": True,
                "generated_content": processed_content,
                "metadata": {
                    "model_used": model_name,
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                    "generation_timestamp": datetime.now().isoformat(),
                    "target_length": settings["target_length"],
                    "actual_length": len(processed_content)
                },
                "quality_metrics": self._calculate_quality_metrics(processed_content, merged_data),
                "raw_response": generated_content
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": datetime.now().isoformat()
            }

    def _get_system_prompt(self) -> str:
        """시스템 프롬프트 반환"""
        return """너는 실제 사람이 직접 방문하고 쓴 네이버 맛집 블로그 작성자다.
블로그 마케팅 AI가 아니다.

[핵심 스타일 규칙]

1. 인위적인 서론 금지
   - "오늘은 소개하려고 합니다"
   - "특별한 경험을 나누고 싶어"
   - "여러분께 추천드립니다"
   이런 문장 절대 사용 금지

2. 말하듯이 작성
   - 문장 짧게 (15-25자)
   - 줄바꿈 많이
   - 한 문단 1~3문장

3. 사진 중심 구조로 작성
   - (사진) 표시를 자연스럽게 중간중간 배치
   - 사진 다음에는 짧은 설명만

4. 과한 감정 표현 금지
   - "완벽했습니다"
   - "최고였습니다"
   - "강력 추천드립니다"
   이런 문장 금지

5. 실제 방문자 느낌 유지
   - 가격 언급
   - 위치 언급
   - 주차 여부
   - 사람이 많았는지
   - 기다렸는지
   - 솔직한 아쉬운 점 1개는 포함

6. 해시태그는 글 맨 아래 5개 이하만 작성

7. 광고/홍보 느낌 절대 금지
   - "강력 추천"
   - "꼭 방문해보세요"
   - "완벽"
   - "인생 맛집"
   사용 금지

8. 1200자 내외로 작성
9. 문장 길이를 평균 15자~25자로 유지하라.
완성도보다 자연스러움을 우선하라.
약간 어색해도 인간이 쓴 것처럼 보여야 한다.

[톤 예시]
❌ AI 느낌: "저의 만족도는 5점 만점에 5점이었습니다."
⭐ 사람 느낌: "생각보다 괜찮았어요.", "다음에 또 갈 듯."

[글 구조]
- 방문 계기 (짧게)
- 위치 + 접근성
- (사진)
- 내부 분위기
- (사진)
- 메뉴 설명
- (사진)
- 음식 비주얼
- 맛 평가 (솔직하게)
- 가격 대비 느낌
- 재방문 의사
- 해시태그"""

    def _build_generation_prompt(self, merged_data: Dict[str, Any], settings: Dict[str, Any]) -> str:
        """개선된 생성 프롬프트 구성"""

        # 기본 정보 추출
        category = merged_data["category"]
        rating = merged_data.get("rating", 0)
        companion = merged_data.get("companion", "")
        visit_date = merged_data.get("visit_date", "")
        location = merged_data.get("location", "")
        personal_review = merged_data["personal_review"]
        ai_additional_script = merged_data.get("ai_additional_script", "")
        hashtags = merged_data.get("hashtags", [])

        # 원본 리뷰에서 핵심 키워드 추출
        import re
        key_terms = re.findall(r'[가-힣a-zA-Z0-9]{2,}(?:점|집|카페|리조트|상회|디자인)', personal_review)
        specific_items = re.findall(r'[가-힣a-zA-Z0-9]{3,}(?=이었|였|했|됐)', personal_review)

        # 해시태그에서 키워드 추출 (# 제거)
        hashtag_keywords = [tag.replace('#', '') for tag in hashtags if tag.startswith('#')]

        # 자연스러운 네이버 맛집 블로그 프롬프트 구성
        prompt = f"""다음 정보를 바탕으로 실제 사람이 쓴 것 같은 자연스러운 네이버 맛집 블로그를 1200자 내외로 작성해라.

[방문 정보]
- 카테고리: {category}
- 별점: {rating}/5점 {"⭐" * rating if rating else ""}
- 동행자: {companion or "혼자"}
- 방문일: {visit_date or "최근"}
- 위치: {location or "위치 정보 없음"}

[실제 경험담 - 이걸 기반으로 써라]
{personal_review}

[핵심 키워드 - 자연스럽게 포함할 것]
- 장소/브랜드명: {', '.join(key_terms[:3]) if key_terms else "구체적 장소명 언급"}
- 특별한 요소: {', '.join(specific_items[:2]) if specific_items else "독특한 특징 묘사"}

[추가 요청]
{ai_additional_script or "없음"}

[이미지 개수: {len(merged_data.get('images', []))}장]
글 중간중간에 (사진) 표시를 {len(merged_data.get('images', []))}번 자연스럽게 넣어라.

[사용할 해시태그]
{', '.join(hashtag_keywords[:5]) if hashtag_keywords else "맛집, 음식"}

[필수 작성 규칙]
1. 문장 길이 15-25자로 짧게
2. 줄바꿈 자주 사용
3. 한 문단 최대 3문장
4. 솔직한 아쉬운 점 1개 포함
5. 가격 언급 필수
6. 위치/접근성 언급
7. 사람 많았는지/기다렸는지 언급
8. 재방문 의사 표현

[금지 표현]
- "오늘은 소개하려고", "여러분께", "추천드립니다"
- "완벽했습니다", "최고였습니다", "강력 추천"
- "총정리하면", "도움이 되셨다면"

[글 구조]
1. 방문 계기 (왜 갔는지)
2. 위치/찾기 쉬운지
3. (사진) - 외관
4. 내부 분위기
5. (사진) - 인테리어
6. 메뉴 선택
7. (사진) - 음식
8. 맛 솔직 평가
9. 가격 언급
10. 아쉬운 점 1개
11. 재방문 의사
12. 해시태그 (맨 마지막, 5개 이하)

**톤**: 친구한테 얘기하듯 자연스럽게.
"생각보다 괜찮았어요", "다음에 또 갈 듯" 이런 느낌으로.
완성도보다 자연스러움이 중요해."""

        return prompt

    def _post_process_content(self, content: str, merged_data: Dict[str, Any]) -> str:
        """자연스러운 네이버 블로그 스타일로 후처리"""

        # 1. 불필요한 따옴표 제거
        content = content.strip('"\'')

        # 2. AI 전형 표현 강력 필터링
        ai_patterns = [
            r'오늘은? 소개하려고\s*,?',
            r'특별한 경험을 나누고 싶어\s*,?',
            r'여러분께? 추천드립니다?\s*,?',
            r'완벽했습니다\s*,?',
            r'최고였습니다\s*,?',
            r'강력 추천드립니다?\s*,?',
            r'총정리하면\s*,?',
            r'도움이 되셨다면\s*,?',
            r'마무리하겠습니다\s*,?',
            r'꼭 방문해보세요\s*,?',
            r'인생 맛집\s*,?',
            r'여러분\s*,?',
            r'모든 분들께\s*,?'
        ]
        for pattern in ai_patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE)

        # 3. 해시태그 처리 (맨 마지막에 5개 이하만)
        hashtags = merged_data.get("hashtags", [])

        # 기존 해시태그 제거 (글 중간에 있을 수 있음)
        content = re.sub(r'#[가-힣a-zA-Z0-9_]+', '', content)

        # 맨 마지막에 해시태그 추가 (5개 이하)
        if hashtags:
            clean_hashtags = hashtags[:5]
            content = content.rstrip() + f"\n\n{' '.join(clean_hashtags)}"

        # 4. 문장 길이 조정 (너무 긴 문장 분리)
        lines = content.split('\n')
        processed_lines = []

        for line in lines:
            line = line.strip()
            if len(line) > 50 and '.' in line:
                # 긴 문장을 적절히 분리
                sentences = line.split('.')
                for i, sentence in enumerate(sentences[:-1]):  # 마지막 빈 문자열 제외
                    if sentence.strip():
                        processed_lines.append(sentence.strip() + '.')
                if sentences[-1].strip():  # 마지막 부분이 있으면
                    processed_lines.append(sentences[-1].strip())
            elif line:
                processed_lines.append(line)

        content = '\n'.join(processed_lines)

        # 5. 과도한 줄바꿈 정리 (하지만 짧은 문단 유지)
        content = re.sub(r'\n{4,}', '\n\n\n', content)  # 4개 이상 → 3개로

        # 6. (사진) 표시 정리
        content = re.sub(r'\s*\(사진\)\s*', '\n\n(사진)\n\n', content)

        return content.strip()

    def _calculate_quality_metrics(self, content: str, merged_data: Dict[str, Any]) -> Dict[str, Any]:
        """생성된 콘텐츠 품질 지표 계산"""

        # 기본 지표
        char_count = len(content)
        word_count = len(content.split())
        paragraph_count = len([p for p in content.split('\n\n') if p.strip()])

        # 개인 경험 비율 (원본 리뷰 단어들이 얼마나 포함되었는지)
        original_words = set(merged_data["personal_review"].split())
        content_words = set(content.split())
        experience_overlap = len(original_words & content_words) / max(len(original_words), 1)

        # 해시태그 포함률
        hashtags = merged_data.get("hashtags", [])
        hashtag_included = sum(1 for tag in hashtags if tag in content)
        hashtag_inclusion_rate = hashtag_included / max(len(hashtags), 1)

        # AI 전형 표현 감지
        ai_patterns = ['총정리하면', '도움이 되셨다면', '마무리하겠습니다', '여러분', '모든 분들께']
        ai_expression_count = sum(1 for pattern in ai_patterns if pattern in content)

        return {
            "char_count": char_count,
            "word_count": word_count,
            "paragraph_count": paragraph_count,
            "experience_overlap_ratio": round(experience_overlap, 2),
            "hashtag_inclusion_rate": round(hashtag_inclusion_rate, 2),
            "ai_expression_count": ai_expression_count,
            "quality_score": round(
                (experience_overlap * 0.4 +
                 hashtag_inclusion_rate * 0.3 +
                 (1 - min(ai_expression_count / 3, 1)) * 0.3) * 100, 1
            )
        }


class DateBasedBlogGenerator:
    """날짜 기반 디렉토리 구조를 지원하는 블로그 생성기"""

    def __init__(self, openai_api_key: Optional[str] = None):
        """
        Args:
            openai_api_key: OpenAI API 키. None인 경우 환경변수에서 로드
        """
        # 기본 BlogContentGenerator 초기화
        self.content_generator = BlogContentGenerator(openai_api_key)

        # 데이터 매니저 import
        try:
            from src.storage.data_manager import data_manager
            self.data_manager = data_manager
        except ImportError:
            raise ImportError("data_manager를 import할 수 없습니다.")

    def generate_and_save_blog_post(self, date_directory: str) -> Dict[str, Any]:
        """
        날짜 디렉토리에서 AI 요청 데이터를 로드하고 블로그 글을 생성하여 저장 (트랜잭션 방식)

        Args:
            date_directory: 날짜 디렉토리명 (yyyyMMdd 또는 yyyyMMdd_n)

        Returns:
            생성 결과 및 저장 정보
        """
        from src.config.settings import Settings
        import shutil

        directory_created = False
        try:
            # 1단계: 기본 검증
            ai_request_data = self.data_manager.load_ai_request(date_directory)
            if not ai_request_data:
                raise ValueError(f"AI 요청 데이터가 없습니다: {date_directory}")

            # 디렉토리 존재 여부 확인 (없으면 생성해야 함)
            base_path = Settings.DATA_DIR / date_directory
            if not base_path.exists():
                directory_created = True

            self.data_manager.date_manager.append_log(
                date_directory,
                "Starting blog generation process"
            )

            # 2단계: 블로그 생성
            generation_result = self.content_generator.generate_blog_post(ai_request_data)

            if not generation_result["success"]:
                # 생성 실패 로그 기록
                self.data_manager.date_manager.append_log(
                    date_directory,
                    f"Blog generation failed: {generation_result.get('error', 'Unknown error')}",
                    "ERROR"
                )

                # 실패 시 디렉토리 정리
                if directory_created and base_path.exists():
                    try:
                        shutil.rmtree(base_path)
                        print(f"[Blog Generation] Cleaned up failed directory: {base_path}")
                    except Exception as cleanup_error:
                        print(f"[Blog Generation] Failed to cleanup directory: {cleanup_error}")

                return generation_result

            # 3단계: 생성 성공 - 결과 저장
            generated_content = generation_result["generated_content"]
            metadata = generation_result["metadata"]

            # 마크다운 형식으로 저장
            blog_file_path = self.data_manager.save_blog_result(
                date_directory,
                generated_content,
                metadata
            )

            # 성공 로그 기록
            self.data_manager.date_manager.append_log(
                date_directory,
                f"Blog generated successfully: {len(generated_content)} chars, {metadata['total_tokens']} tokens"
            )

            # 확장된 결과 반환
            return {
                **generation_result,
                "date_directory": date_directory,
                "blog_file_path": str(blog_file_path),
                "saved_at": datetime.now().isoformat()
            }

        except Exception as e:
            # 오류 로그 기록
            self.data_manager.date_manager.append_log(
                date_directory,
                f"Blog generation failed with exception: {str(e)}",
                "ERROR"
            )

            # 실패 시 디렉토리 정리 (새로 생성된 경우만)
            if directory_created:
                base_path = Settings.DATA_DIR / date_directory
                if base_path.exists():
                    try:
                        shutil.rmtree(base_path)
                        print(f"[Blog Generation] Cleaned up failed directory: {base_path}")
                    except Exception as cleanup_error:
                        print(f"[Blog Generation] Failed to cleanup directory: {cleanup_error}")

            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "date_directory": date_directory,
                "timestamp": datetime.now().isoformat()
            }

    def generate_from_session_data(self, date_directory: str, force_regenerate: bool = False) -> Dict[str, Any]:
        """
        포스팅 세션 데이터로부터 블로그 글 생성

        Args:
            date_directory: 날짜 디렉토리명
            force_regenerate: 기존 결과가 있어도 강제로 재생성할지 여부

        Returns:
            생성 결과
        """
        try:
            # 기존 블로그 결과 확인
            if not force_regenerate:
                existing_blog = self.data_manager.load_blog_result(date_directory)
                if existing_blog:
                    self.data_manager.date_manager.append_log(
                        date_directory,
                        "Blog already exists, skipping generation"
                    )
                    return {
                        "success": True,
                        "message": "이미 생성된 블로그 글이 있습니다",
                        "date_directory": date_directory,
                        "existing_content": existing_blog,
                        "action": "skipped"
                    }

            # 메타데이터 로드
            metadata = self.data_manager.load_metadata(date_directory)
            if not metadata:
                raise ValueError(f"메타데이터가 없습니다: {date_directory}")

            # AI 처리 데이터 준비 (위치 분석, 해시태그 등이 아직 없는 경우)
            if not self.data_manager.load_ai_request(date_directory):
                # 기본 처리 데이터 생성
                processing_data = self._prepare_basic_processing_data(metadata)
                self.data_manager.save_ai_processing_data(date_directory, processing_data)

                self.data_manager.date_manager.append_log(
                    date_directory,
                    "Basic processing data created"
                )

            # 블로그 생성 및 저장
            return self.generate_and_save_blog_post(date_directory)

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "date_directory": date_directory,
                "timestamp": datetime.now().isoformat()
            }

    def _prepare_basic_processing_data(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """기본 AI 처리 데이터 준비"""
        user_input = metadata.get("user_input", {})

        # 기본 해시태그 생성
        hashtag_generator = HashtagGenerator()

        # 더미 위치 정보 (실제로는 위치 추론 시스템을 사용)
        dummy_location_info = LocationInfo(
            detected_location=user_input.get("location", ""),
            confidence=0.5,
            source="text"
        )

        # 더미 유저 입력 (해시태그 생성용)
        dummy_user_input = UserDirectInput(
            category=user_input.get("category", "기타"),
            personal_review=user_input.get("personal_review", ""),
            rating=user_input.get("rating", 3),
            companion=user_input.get("companion", ""),
            ai_additional_script=user_input.get("ai_additional_script", "")
        )

        # 키워드 추출 (간단한 버전)
        extracted_keywords = self._extract_simple_keywords(user_input.get("personal_review", ""))

        # 해시태그 생성
        hashtag_candidates = hashtag_generator.generate_candidate_hashtags(
            dummy_user_input,
            dummy_location_info,
            extracted_keywords
        )
        hashtag_refinement = hashtag_generator.refine_hashtags(hashtag_candidates)

        return {
            "location_analysis": {
                "final_location": dummy_location_info.detected_location,
                "confidence": dummy_location_info.confidence
            },
            "hashtag_analysis": {
                "candidates": hashtag_candidates.__dict__ if hasattr(hashtag_candidates, '__dict__') else {},
                "final_hashtags": hashtag_refinement.final_tags if hasattr(hashtag_refinement, 'final_tags') else []
            },
            "final_location": dummy_location_info.detected_location,
            "final_hashtags": hashtag_refinement.final_tags if hasattr(hashtag_refinement, 'final_tags') else []
        }

    def _extract_simple_keywords(self, text: str) -> List[str]:
        """간단한 키워드 추출"""
        # 한글 명사 패턴 추출
        korean_words = re.findall(r'[가-힣]{2,}', text)

        # 빈도 기반 필터링
        word_counts = {}
        for word in korean_words:
            word_counts[word] = word_counts.get(word, 0) + 1

        # 빈도순 정렬하여 상위 키워드 반환
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        return [word for word, count in sorted_words[:5]]

    def batch_generate_blogs(self, date_directories: List[str]) -> Dict[str, Any]:
        """여러 날짜 디렉토리에 대해 배치 블로그 생성"""
        results = {}
        total_success = 0
        total_failed = 0

        for date_dir in date_directories:
            try:
                result = self.generate_from_session_data(date_dir)
                results[date_dir] = result

                if result["success"]:
                    total_success += 1
                else:
                    total_failed += 1

            except Exception as e:
                results[date_dir] = {
                    "success": False,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
                total_failed += 1

        return {
            "batch_results": results,
            "summary": {
                "total_processed": len(date_directories),
                "successful": total_success,
                "failed": total_failed,
                "success_rate": total_success / len(date_directories) if date_directories else 0
            },
            "completed_at": datetime.now().isoformat()
        }


# 전역 인스턴스
date_based_blog_generator = DateBasedBlogGenerator()
