import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.services.blog_workflow import BlogWorkflowService


def _service() -> BlogWorkflowService:
    return BlogWorkflowService.__new__(BlogWorkflowService)


def test_extract_naver_post_report_from_stdout():
    svc = _service()
    payload = {
        "draft_summary": {"success": True},
        "image_summary": {"status": "partial", "uploaded_count": 2, "requested_count": 3},
    }
    stdout = f"line1\nNAVER_POST_RESULT_JSON:{json.dumps(payload)}\nline2"

    parsed = svc._extract_naver_post_report(stdout, "")
    assert parsed is not None
    assert parsed["draft_summary"]["success"] is True
    assert parsed["image_summary"]["status"] == "partial"


def test_detect_transient_failure_from_report_attempts():
    svc = _service()
    report = {
        "steps": {
            "C": {
                "data": {
                    "attempts": [
                        {"attempt": 1, "transient_failure": True},
                    ]
                }
            }
        }
    }

    assert svc._is_transient_naver_failure("", "", report) is True


def test_detect_authentication_error_from_message():
    svc = _service()
    report = {
        "steps": {
            "F": {
                "message": "로그인 세션 만료로 임시저장 실패",
            }
        }
    }

    assert svc._is_authentication_error("", "", report) is True
