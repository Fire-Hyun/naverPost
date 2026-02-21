"""
parse_visit_date 단위 테스트
"""

import sys
import importlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

# telegram 패키지 없이도 validators 모듈만 직접 로드
_spec = importlib.util.spec_from_file_location(
    "validators",
    str(__import__("pathlib").Path(__file__).resolve().parent.parent / "src" / "telegram" / "utils" / "validators.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
parse_visit_date = _mod.parse_visit_date


KST = ZoneInfo("Asia/Seoul")


def _today_kst() -> str:
    return datetime.now(KST).strftime("%Y%m%d")


def _yesterday_kst() -> str:
    return (datetime.now(KST) - timedelta(days=1)).strftime("%Y%m%d")


# ── 키워드 입력 ──────────────────────────────


class TestKeywordInput:
    def test_오늘(self):
        result, err = parse_visit_date("오늘")
        assert err is None
        assert result == _today_kst()

    def test_today(self):
        result, err = parse_visit_date("today")
        assert err is None
        assert result == _today_kst()

    def test_어제(self):
        result, err = parse_visit_date("어제")
        assert err is None
        assert result == _yesterday_kst()

    def test_yesterday(self):
        result, err = parse_visit_date("yesterday")
        assert err is None
        assert result == _yesterday_kst()

    def test_keyword_case_insensitive(self):
        result, err = parse_visit_date("TODAY")
        assert err is None
        assert result == _today_kst()

    def test_keyword_with_whitespace(self):
        result, err = parse_visit_date("  어제  ")
        assert err is None
        assert result == _yesterday_kst()


# ── YYYYMMDD 형식 ────────────────────────────


class TestYYYYMMDD:
    def test_valid_date(self):
        result, err = parse_visit_date("20260101")
        assert err is None
        assert result == "20260101"

    def test_leap_year_valid(self):
        result, err = parse_visit_date("20240229")
        assert err is None
        assert result == "20240229"

    def test_leap_year_invalid(self):
        result, err = parse_visit_date("20230229")
        assert result is None
        assert "존재하지 않는 날짜" in err

    def test_invalid_month_day(self):
        result, err = parse_visit_date("20260230")
        assert result is None
        assert "존재하지 않는 날짜" in err

    def test_invalid_month_13(self):
        result, err = parse_visit_date("20261301")
        assert result is None
        assert "존재하지 않는 날짜" in err


# ── YYYY-MM-DD 형식 ──────────────────────────


class TestHyphenFormat:
    def test_valid_hyphen(self):
        result, err = parse_visit_date("2026-02-12")
        assert err is None
        assert result == "20260212"

    def test_leap_year_hyphen(self):
        result, err = parse_visit_date("2024-02-29")
        assert err is None
        assert result == "20240229"

    def test_invalid_hyphen(self):
        result, err = parse_visit_date("2023-02-29")
        assert result is None
        assert "존재하지 않는 날짜" in err


# ── 잘못된 입력 ──────────────────────────────


class TestInvalidInput:
    def test_empty_string(self):
        result, err = parse_visit_date("")
        assert result is None
        assert err is not None

    def test_whitespace_only(self):
        result, err = parse_visit_date("   ")
        assert result is None
        assert err is not None

    def test_letters(self):
        result, err = parse_visit_date("abcdefgh")
        assert result is None
        assert "형식" in err

    def test_short_number(self):
        result, err = parse_visit_date("202601")
        assert result is None
        assert "형식" in err

    def test_long_number(self):
        result, err = parse_visit_date("202601011")
        assert result is None
        assert "형식" in err

    def test_mixed_chars(self):
        result, err = parse_visit_date("2026ab01")
        assert result is None
        assert "형식" in err

    def test_unknown_keyword(self):
        result, err = parse_visit_date("내일")
        assert result is None
        assert "형식" in err


# ── 타임존 적용 확인 ─────────────────────────


class TestTimezone:
    def test_uses_kst_by_default(self):
        """기본 타임존이 Asia/Seoul인지 확인"""
        result, err = parse_visit_date("오늘")
        expected = datetime.now(KST).strftime("%Y%m%d")
        assert result == expected
        assert err is None
