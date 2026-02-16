#!/usr/bin/env python3
"""
Phase 2 테스트 스크립트 - 웹 인터페이스 없이 블로그 글 생성 파이프라인 테스트

사용법:
    python3 scripts/test_generate.py [project_id]

예시:
    python3 scripts/test_generate.py 20260207_001
    python3 scripts/test_generate.py  # 기본값: 20260207_001 사용
"""

import sys
import json
import os
import stat
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

# 프로젝트 루트를 파이썬 경로에 추가 (scripts/ 아래로 이동했기 때문)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

try:
    from src.content.models import (
        MetaJsonData, AnalysisJsonData, GenerationReadyData,
        UserDirectInput, PipelineLogEntry
    )
    from src.content.experience_processor import ExperienceProcessor
    from src.content.blog_generator import HashtagGenerator, ContentStructureBuilder
    from src.utils.exceptions import FileProcessingError
    MODULES_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some modules not available: {e}")
    print("Running in basic mode without full functionality")
    MODULES_AVAILABLE = False

class PipelineRunner:
    """테스트 파이프라인 실행 클래스"""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.project_dir = Path(f"data/{project_id}")
        self.meta_path = self.project_dir / "meta.json"
        self.analysis_path = self.project_dir / "analysis.json"
        self.generation_ready_path = self.project_dir / "generation_ready.json"
        self.logs_dir = self.project_dir / "logs"

        # 디렉토리 생성
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def log_event(self, stage: str, status: str, message: str, confidence: Optional[float] = None):
        """구조화된 로그 기록"""
        log_entry = PipelineLogEntry(
            stage=stage,
            status=status,
            message=message,
            confidence=confidence
        )

        # 콘솔 출력
        print(f"[{log_entry.timestamp}] {stage.upper()} - {status}: {message}")
        if confidence is not None:
            print(f"  └─ Confidence: {confidence:.2f}")

        # JSON 로그 파일에 기록
        log_file = self.logs_dir / "pipeline_log.json"

        if log_file.exists():
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        else:
            logs = []

        logs.append(log_entry.model_dump(mode='json'))

        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2, default=str)

    def load_and_validate_meta(self) -> MetaJsonData:
        """meta.json 로드 및 검증"""
        self.log_event("meta_loading", "info", f"Loading meta.json from {self.meta_path}")

        if not self.meta_path.exists():
            raise FileProcessingError(
                f"meta.json 파일을 찾을 수 없습니다: {self.meta_path}",
                file_path=str(self.meta_path)
            )

        try:
            with open(self.meta_path, 'r', encoding='utf-8') as f:
                meta_data = json.load(f)

            # Pydantic 모델로 검증
            validated_meta = MetaJsonData(**meta_data)

            self.log_event("meta_loading", "completed", "meta.json 로드 및 검증 완료")
            return validated_meta

        except Exception as e:
            self.log_event("meta_loading", "failed", f"meta.json 로드 실패: {str(e)}")
            raise FileProcessingError(f"meta.json 처리 실패: {str(e)}", str(self.meta_path))

    def check_images_exist(self, meta_data: MetaJsonData) -> Dict[str, bool]:
        """이미지 파일 존재 확인"""
        self.log_event("image_check", "info", "이미지 파일 존재 확인 중")

        images_status = {}
        images_dir = self.project_dir / "images"

        for filename in meta_data.images:
            image_path = images_dir / filename
            exists = image_path.exists()
            images_status[filename] = exists

            if exists:
                file_size = image_path.stat().st_size
                self.log_event("image_check", "info", f"이미지 발견: {filename} ({file_size} bytes)")
            else:
                self.log_event("image_check", "warning", f"이미지 누락: {filename}")

        found_count = sum(images_status.values())
        total_count = len(images_status)

        self.log_event("image_check", "completed", f"이미지 확인 완료: {found_count}/{total_count} 발견")

        return images_status

    def run_exif_analysis(self, meta_data: MetaJsonData) -> Dict[str, Any]:
        """EXIF 분석 실행"""
        self.log_event("exif_analysis", "info", "EXIF 데이터 추출 시작")

        if not MODULES_AVAILABLE:
            # Fallback to mock data
            exif_result = {
                "gps_found": False,
                "coordinates": None,
                "exif_confidence": 0.0,
                "extraction_method": "mock_fallback",
                "raw_exif_data": {}
            }
            self.log_event("exif_analysis", "completed", "EXIF 분석 완료 (Fallback)", confidence=0.0)
            return exif_result

        # 실제 EXIF 처리기 사용
        processor = ExperienceProcessor(self.project_dir)
        result = processor.process_user_experience(meta_data.user_input, meta_data.images)

        exif_result = result["location_analysis"]["exif_results"]
        confidence = exif_result.get("exif_confidence", 0.0)

        self.log_event("exif_analysis", "completed", "EXIF 분석 완료", confidence=confidence)
        return exif_result

    def run_location_inference(self, meta_data: MetaJsonData, exif_result: Dict[str, Any]) -> Dict[str, Any]:
        """위치 추론 실행"""
        self.log_event("location_inference", "info", "텍스트 기반 위치 추론 시작")

        if not MODULES_AVAILABLE:
            # Fallback to simple pattern matching
            personal_review = meta_data.user_input.personal_review
            location = None
            confidence = 0.0
            matched_patterns = []

            if "강남역" in personal_review:
                location = "서울특별시 강남구 강남역 근처"
                confidence = 0.85
                matched_patterns = ["강남역"]
            elif "홍대" in personal_review:
                location = "서울특별시 마포구 홍대 근처"
                confidence = 0.80
                matched_patterns = ["홍대"]

            text_analysis = {
                "detected_location": location,
                "extraction_method": "fallback_pattern_matching",
                "matched_patterns": matched_patterns,
                "text_confidence": confidence,
                "candidate_locations": matched_patterns
            }

            final_location = {
                "location": location,
                "coordinates": None,
                "source": "text" if location else "none",
                "confidence": confidence
            }
        else:
            # 실제 위치 추론 엔진 사용
            processor = ExperienceProcessor(self.project_dir)
            result = processor.process_user_experience(meta_data.user_input, meta_data.images)
            location_analysis = result["location_analysis"]

            text_analysis = location_analysis["text_analysis"]
            final_location = location_analysis["final_location"]

        status = "completed"
        message = f"위치 추론 완료: {final_location.get('detected_location') or final_location.get('location') or '추론 실패'}"
        self.log_event("location_inference", status, message, confidence=final_location['confidence'])

        return {
            "exif_results": exif_result,
            "text_analysis": text_analysis,
            "final_location": final_location
        }

    def run_hashtag_generation(self, meta_data: MetaJsonData, location_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """해시태그 생성 실행"""
        self.log_event("hashtag_generation", "info", "해시태그 자동 생성 시작")

        user_input = meta_data.user_input
        final_location_data = location_analysis["final_location"]

        if not MODULES_AVAILABLE:
            # Fallback to simple rule-based generation
            candidates = self._generate_simple_hashtags(user_input, final_location_data.get("detected_location") or final_location_data.get("location"))
            refined_tags = {
                "deduplicated": list(dict.fromkeys([tag for tags in candidates.values() for tag in tags])),
                "semantic_filtered": list(dict.fromkeys([tag for tags in candidates.values() for tag in tags])),
                "final_tags": list(dict.fromkeys([tag for tags in candidates.values() for tag in tags]))[:6]
            }
            confidence = 0.8 if refined_tags["final_tags"] else 0.0
        else:
            # 실제 해시태그 생성기 사용
            from src.content.models import LocationInfo

            # LocationInfo 객체 생성
            location_info = LocationInfo(
                detected_location=final_location_data.get("detected_location") or final_location_data.get("location"),
                coordinates=final_location_data.get("coordinates"),
                source=final_location_data["source"],
                confidence=final_location_data["confidence"]
            )

            # 키워드 추출
            processor = ExperienceProcessor(self.project_dir)
            result = processor.process_user_experience(user_input, meta_data.images)
            extracted_keywords = result.get("extracted_keywords", [])

            # 해시태그 후보 생성
            candidates_obj = HashtagGenerator.generate_candidate_hashtags(user_input, location_info, extracted_keywords)
            candidates = candidates_obj.model_dump()

            # 해시태그 정제
            refined_result = HashtagGenerator.refine_hashtags(candidates_obj)
            refined_tags = refined_result.model_dump()

            confidence = 0.92 if refined_tags["final_tags"] else 0.0

        self.log_event("hashtag_generation", "completed", f"해시태그 생성 완료: {len(refined_tags['final_tags'])}개", confidence=confidence)

        return {
            "candidate_tags": candidates,
            "refined_tags": refined_tags,
            "tag_confidence": confidence
        }

    def _generate_simple_hashtags(self, user_input: UserDirectInput, location: Optional[str]) -> Dict[str, List[str]]:
        """간단한 해시태그 생성 (Fallback)"""
        candidates = {
            "category_based": [],
            "rating_based": [],
            "companion_based": [],
            "keyword_based": [],
            "location_based": []
        }

        # 카테고리 기반
        if user_input.category == "맛집":
            candidates["category_based"] = ["#맛집", "#음식"]

        # 별점 기반
        if user_input.rating == 5:
            candidates["rating_based"] = ["#강추", "#최고"]
        elif user_input.rating == 4:
            candidates["rating_based"] = ["#추천", "#좋아요"]

        # 동행자 기반
        if user_input.companion == "가족":
            candidates["companion_based"] = ["#가족식사"]

        # 간단한 키워드 추출
        review = user_input.personal_review
        if "이탈리안" in review:
            candidates["keyword_based"].append("#이탈리안")
        if "파스타" in review:
            candidates["keyword_based"].append("#파스타")
        if "알리오올리오" in review:
            candidates["keyword_based"].append("#알리오올리오")

        # 위치 기반 (location이 None이 아닐 때만)
        if location:
            if "강남" in location:
                candidates["location_based"] = ["#강남맛집"]

        return candidates

    def save_analysis_results(self, meta_data: MetaJsonData, location_analysis: Dict[str, Any], hashtag_analysis: Dict[str, Any]):
        """analysis.json 저장"""
        self.log_event("save_analysis", "info", f"analysis.json 저장 중: {self.analysis_path}")

        analysis_data = AnalysisJsonData(
            project_id=meta_data.project_id,
            location_analysis=location_analysis,
            hashtag_analysis=hashtag_analysis,
            confidence_scores={
                "location_detection": location_analysis["final_location"]["confidence"],
                "hashtag_generation": hashtag_analysis["tag_confidence"],
                "overall_analysis": (location_analysis["final_location"]["confidence"] + hashtag_analysis["tag_confidence"]) / 2
            },
            processing_metadata={
                "exif_parsing_status": "completed",
                "location_inference_status": "completed",
                "hashtag_generation_status": "completed"
            }
        )

        with open(self.analysis_path, 'w', encoding='utf-8') as f:
            json.dump(analysis_data.model_dump(mode='json'), f, ensure_ascii=False, indent=2, default=str)

        self.log_event("save_analysis", "completed", "analysis.json 저장 완료")

    def save_generation_ready_data(self, meta_data: MetaJsonData, analysis_data: Dict[str, Any]):
        """generation_ready.json 저장 (confidence 제외)"""
        self.log_event("save_generation_ready", "info", f"generation_ready.json 저장 중: {self.generation_ready_path}")

        # analysis.json에서 최종 데이터 추출
        final_location = analysis_data["location_analysis"]["final_location"]
        location = final_location.get("detected_location") or final_location.get("location")
        hashtags = analysis_data["hashtag_analysis"]["refined_tags"]["final_tags"]

        merged_data = {
            "category": meta_data.user_input.category,
            "rating": meta_data.user_input.rating,
            "visit_date": meta_data.user_input.visit_date,
            "companion": meta_data.user_input.companion,
            "personal_review": meta_data.user_input.personal_review,
            "ai_additional_script": meta_data.user_input.ai_additional_script,
            "location": location,  # None 가능
            "hashtags": hashtags,
            "images": meta_data.images
        }

        generation_ready = GenerationReadyData(
            project_id=meta_data.project_id,
            merged_data=merged_data,
            generation_settings=meta_data.settings
        )

        with open(self.generation_ready_path, 'w', encoding='utf-8') as f:
            json.dump(generation_ready.model_dump(mode='json'), f, ensure_ascii=False, indent=2, default=str)

        self.log_event("save_generation_ready", "completed", "generation_ready.json 저장 완료")

    def make_meta_readonly(self):
        """meta.json을 읽기 전용으로 설정"""
        if self.meta_path.exists():
            os.chmod(self.meta_path, stat.S_IREAD)
            self.log_event("meta_protection", "completed", "meta.json 읽기 전용으로 설정")

    def run_full_pipeline(self):
        """전체 파이프라인 실행"""
        try:
            print(f"\n🚀 Phase 2 테스트 파이프라인 시작")
            print(f"   프로젝트 ID: {self.project_id}")
            print(f"   프로젝트 경로: {self.project_dir}")
            print("=" * 60)

            # 1. meta.json 로드 및 검증
            meta_data = self.load_and_validate_meta()

            # 2. 이미지 파일 존재 확인
            images_status = self.check_images_exist(meta_data)

            # 3. meta.json 읽기 전용 설정
            self.make_meta_readonly()

            # 4. EXIF 분석
            exif_result = self.run_exif_analysis(meta_data)

            # 5. 위치 추론
            location_analysis = self.run_location_inference(meta_data, exif_result)

            # 6. 해시태그 생성
            hashtag_analysis = self.run_hashtag_generation(meta_data, location_analysis)

            # 7. analysis.json 저장
            analysis_full = {
                "location_analysis": location_analysis,
                "hashtag_analysis": hashtag_analysis
            }
            self.save_analysis_results(meta_data, location_analysis, hashtag_analysis)

            # 8. generation_ready.json 저장
            self.save_generation_ready_data(meta_data, analysis_full)

            print("\n✅ 파이프라인 실행 완료!")
            print("=" * 60)

            # 결과 요약 출력
            final_location_data = location_analysis["final_location"]
            final_location = final_location_data.get("detected_location") or final_location_data.get("location")
            final_hashtags = hashtag_analysis["refined_tags"]["final_tags"]

            print(f"📍 추론된 위치: {final_location or '추론 실패'}")
            print(f"🏷️  생성된 해시태그: {', '.join(final_hashtags) if final_hashtags else '없음'}")
            print(f"📁 생성된 파일:")
            print(f"   - {self.analysis_path}")
            print(f"   - {self.generation_ready_path}")
            print(f"📝 로그 파일: {self.logs_dir / 'pipeline_log.json'}")

            self.log_event("pipeline", "completed", "전체 파이프라인 실행 성공")

        except Exception as e:
            self.log_event("pipeline", "failed", f"파이프라인 실행 실패: {str(e)}")
            print(f"\n❌ 파이프라인 실행 실패: {str(e)}")
            raise


def main():
    """메인 실행 함수"""
    # 명령행 인수 처리
    if len(sys.argv) > 1:
        project_id = sys.argv[1]
    else:
        project_id = "20260207_001"

    print(f"Phase 2 테스트 파이프라인 - 프로젝트 ID: {project_id}")

    # 파이프라인 실행
    runner = PipelineRunner(project_id)
    runner.run_full_pipeline()


if __name__ == "__main__":
    main()
