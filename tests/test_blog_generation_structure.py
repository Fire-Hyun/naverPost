from pathlib import Path
import re

from src.content.blog_generator import BlogContentGenerator, OLD_TONE_PATTERNS


def _heading_lines(content: str):
    return [line.strip() for line in content.splitlines() if line.strip().startswith("**") and line.strip().endswith("**")]


def test_postprocess_enforces_bold_headings_and_conclusion_position():
    raw = (
        "도착하자마자 동선이 편했다.\n\n"
        "분위기는 깔끔했네요.\n\n"
        "주차는 건물 지하에 바로 연결되어 있었어요.\n\n"
        "주차 출차도 비교적 빠르게 진행됐어요.\n\n"
        "다음에 만나요!\n\n"
        "비용은 1인 2만원대로 계산됐어요.\n\n"
        "비용 기준으로 보면 양을 감안해 부담이 크지 않았어요."
    )
    processed = BlogContentGenerator._enforce_bold_heading_structure(
        raw,
        merged_data={
            "store_name": "테스트매장",
            "personal_review": "주차는 지하 주차장을 이용했고 비용은 1인 2만원대였어요.",
        },
    )
    headings = _heading_lines(processed)
    assert "**첫 방문기**" in headings
    assert "**주차정보**" in headings
    assert "**비용정보**" in headings
    assert "**총평**" in headings
    assert processed.rstrip().endswith("다음에 만나요!")
    for heading in headings:
        title = heading.strip("*")
        assert 2 <= len(title) <= 12
        assert not any(ch in title for ch in ".?!")

    before_conclusion, _, conclusion_tail = processed.partition("**총평**")
    assert "다음에 만나요" not in before_conclusion
    assert "다음에 만나요" in conclusion_tail


def test_tone_guard_blocks_old_style_expressions():
    text = "분위기가 좋았네요. 다음엔 또 가겠더라고요."
    guarded = BlogContentGenerator._apply_tone_guard(text)
    for pattern in OLD_TONE_PATTERNS:
        assert pattern not in guarded


def test_heading_normalizer_enforces_short_noun_like_title():
    normalized = BlogContentGenerator.sanitize_section_heading("제주도점은 KFC 옆 엘리베이터를 타고 올라갑니다.", "첫 방문기")
    assert normalized == "첫 방문기"


def test_load_ai_additional_scripts_from_file(tmp_path: Path):
    script_file = tmp_path / "ai_additional_scripts.md"
    script_file.write_text("꼭 반영할 추가 포인트", encoding="utf-8")
    loaded = BlogContentGenerator.load_ai_additional_scripts(tmp_path)
    assert "꼭 반영할 추가 포인트" in loaded
    assert "ai_additional_scripts.md" in loaded


def test_prompt_includes_loaded_ai_additional_scripts():
    generator = BlogContentGenerator.__new__(BlogContentGenerator)
    merged_data = {
        "category": "맛집",
        "personal_review": "기본 방문 후기입니다.",
        "ai_additional_script": "메타데이터 추가 요청",
        "ai_additional_scripts": "[ai_additional_scripts.md]\n파일 기반 추가 요청",
        "hashtags": [],
        "images": [],
        "store_name": "테스트식당",
        "location": "제주",
    }
    prompt = generator._build_generation_prompt(
        merged_data=merged_data,
        settings={"target_length": 1200},
        review_snippets=[],
        sufficiency_result={"filled_fields": [], "missing_fields": []},
    )
    assert "파일 기반 추가 요청" in prompt


def test_polite_normalizer_removes_banmal_endings():
    raw = "주차 동선은 단순하다.\n비용은 나쁘지 않다.\n좌석 간격은 넉넉해요."
    normalized = BlogContentGenerator._normalize_polite_sentence_endings(raw)
    banmal_lines = [
        line for line in normalized.splitlines()
        if re.search(r'다\.$', line.strip()) and not re.search(r'(요\.|니다\.)$', line.strip())
    ]
    assert banmal_lines == []


def test_postprocess_keeps_polite_tone_ratio():
    generator = BlogContentGenerator.__new__(BlogContentGenerator)
    raw = (
        "도착하자마자 동선이 편하다.\n\n"
        "주차는 지하로 내려가면 된다.\n\n"
        "비용은 1인 기준으로 무난했다.\n\n"
        "전체적으로 다시 가고 싶다."
    )
    processed = generator._post_process_content(
        raw,
        merged_data={"hashtags": [], "images": []},
    )
    lines = [line.strip() for line in processed.splitlines() if line.strip() and not line.strip().startswith("**")]
    banmal_count = sum(
        1 for line in lines
        if re.search(r'다\.$', line) and not re.search(r'(요\.|니다\.)$', line)
    )
    polite_count = sum(1 for line in lines if re.search(r'(요\.|니다\.)$', line))
    assert banmal_count == 0
    assert polite_count / max(len(lines), 1) >= 0.7


def test_conditional_sections_removed_when_info_missing():
    raw = (
        "분위기가 차분했어요.\n\n"
        "음식 흐름이 매끄러워서 식사 템포가 좋았어요.\n\n"
        "**주차정보**\n\n"
        "정보 없음.\n\n"
        "**비용정보**\n\n"
        "잘 모르겠어요.\n\n"
        "**총평**\n\n"
        "전체적으로 만족스러웠어요."
    )
    processed = BlogContentGenerator._enforce_bold_heading_structure(
        raw,
        merged_data={"store_name": "테스트매장", "personal_review": "첫 방문 후기"},
    )
    headings = _heading_lines(processed)
    assert "**주차정보**" not in headings
    assert "**비용정보**" not in headings


def test_conditional_cost_section_exists_when_info_available():
    raw = (
        "처음 방문 동선은 어렵지 않았어요.\n\n"
        "**비용정보**\n\n"
        "점심 기준 1인 23000원 정도였어요.\n\n"
        "구성 대비 가격이 납득 가능했어요.\n\n"
        "**총평**\n\n"
        "다시 방문할 의향이 있어요."
    )
    processed = BlogContentGenerator._enforce_bold_heading_structure(
        raw,
        merged_data={"store_name": "테스트매장", "personal_review": "가격은 1인 23000원이었어요."},
    )
    headings = _heading_lines(processed)
    assert "**비용정보**" in headings
    assert "23000원" in processed


def test_first_person_expression_is_present_after_postprocess():
    generator = BlogContentGenerator.__new__(BlogContentGenerator)
    raw = (
        "입구 동선이 단순했어요.\n\n"
        "음식 밸런스가 안정적이었어요.\n\n"
        "**총평**\n\n"
        "전체적으로 무난했어요."
    )
    processed = generator._post_process_content(
        raw,
        merged_data={"store_name": "하이디라오 제주도점", "hashtags": [], "images": []},
    )
    assert ("다녀왔어요" in processed) or ("소개하겠습니다" in processed) or ("저는" in processed)


def test_regression_1817_output_gets_bold_subheadings():
    """2026-02-19 18:17 생성본처럼 소제목이 없는 본문을 회귀 검증한다."""
    generator = BlogContentGenerator.__new__(BlogContentGenerator)
    raw = (
        "하이디라오는 많이 듣던 곳이었어요.\n"
        "제주도에서 첫 방문한 곳이기도 했죠.\n"
        "[사진1]\n"
        "제가 갔던 그날은 발렌타인데이였는데요.\n"
        "꽃 선물까지 받았답니다.\n"
        "가게는 거대한 KFC 옆에 있어요.\n"
        "엘리베이터를 타면 5층에 위치해 있더라구요.\n"
        "미리 예약하거나 캐치테이블로 줄 세우면 웨이팅 없이 입장 가능할 것 같아요.\n"
        "[사진2]\n"
        "음식을 먹다 보면 중국의 변검 퍼포먼스를 보여줍니다.\n"
        "볼거리가 많아서 재미있더라구요.\n"
        "[사진3]\n"
        "메뉴 중에서 유명한 건희소스로 선택했어요.\n"
        "맛있었습니다.\n"
        "[사진4]\n"
        "그리고 디저트로 한라봉을 주더라구요.\n"
        "제주도점에서만 제공하는 건지 모르겠네요.\n"
        "(혹시 아시는 분은 댓글 남겨주세요)\n"
        "[사진5]\n"
        "새우완자의 식감이 정말 탱글하고 맛있었습니다.\n"
        "새우완자는 무조건 추천해요.\n"
        "[사진6]\n"
        "[사진7]\n"
        "[사진8]\n"
        "음식의 맛은 제 스타일이 아니었지만,\n"
        "볼거리가 많아서 재미있게 먹었습니다.\n"
        "[사진9]\n"
        "재방문 의사 있습니다.\n"
        "[사진10]\n"
    )
    processed = generator._post_process_content(
        raw,
        merged_data={
            "store_name": "하이디라오 제주도점",
            "personal_review": "변검 퍼포먼스가 인상적이었고 건희소스, 한라봉, 새우완자가 기억에 남았어요.",
            "hashtags": ["#맛집", "#맛있었음", "#한라봉이", "#있는건지", "#미리"],
            "images": [f"{i}.jpg" for i in range(1, 11)],
        },
    )
    headings = _heading_lines(processed)
    assert "**첫 방문기**" in headings
    assert "**총평**" in headings
    assert processed.count("**") >= 4  # 최소 2개 소제목(여닫는 ** 쌍)


def test_generate_blog_post_enforces_headings_when_model_omits_them():
    """모델 응답이 소제목 없이 와도 generate_blog_post 경로에서 보정되는지 검증."""
    model_output = (
        "TITLE: 하이디라오 제주도점, 발렌타인데이 방문기\n\n"
        "하이디라오는 많이 듣던 곳이었어요.\n"
        "[사진1]\n"
        "변검 퍼포먼스가 눈길을 끌었어요.\n"
        "[사진2]\n"
        "건희소스가 인상적이었고 새우완자도 괜찮았어요.\n"
        "재방문 의사는 있어요."
    )

    class _FakeMessage:
        def __init__(self, content: str):
            self.content = content

    class _FakeChoice:
        def __init__(self, content: str):
            self.message = _FakeMessage(content)

    class _FakeUsage:
        prompt_tokens = 100
        completion_tokens = 200
        total_tokens = 300

    class _FakeCompletions:
        @staticmethod
        def create(**kwargs):
            return type(
                "FakeResponse",
                (),
                {"choices": [_FakeChoice(model_output)], "usage": _FakeUsage()},
            )()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    generator = BlogContentGenerator.__new__(BlogContentGenerator)
    generator.client = _FakeClient()
    result = generator.generate_blog_post(
        {
            "merged_data": {
                "category": "맛집",
                "store_name": "하이디라오 제주도점",
                "personal_review": "변검 퍼포먼스가 재미있었고 건희소스가 맛있었어요.",
                "hashtags": ["#맛집", "#하이디라오"],
                "images": ["1.jpg", "2.jpg"],
            },
            "generation_settings": {"target_length": 1200},
        }
    )

    assert result["success"] is True
    headings = _heading_lines(result["generated_content"])
    assert "**첫 방문기**" in headings
    assert "**총평**" in headings
