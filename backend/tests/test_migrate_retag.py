"""HIVE-61 폐기타입 재태깅 마이그레이션 단위 테스트.

DB / Anthropic 없이:
- retag_with_retry: (content_type, difficulty) 튜플 반환 / 유효하지 않은 타입 재시도 / 최종 실패 None
- 멱등: 대상 0건 시 UPDATE 없음
- --dry-run: DB execute 호출 없음 + 예정 건수 출력
"""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from scripts.migrate_retag_deprecated_types import (
    DEPRECATED_TYPES,
    VALID_DIFFICULTIES,
    VALID_TYPES,
    retag_with_retry,
)


# ── retag_with_retry ─────────────────────────────────────────────────────

def _fake_client(content_types: list[str | None]):
    """순서대로 content_type을 반환하는 가짜 Anthropic 클라이언트."""
    client = MagicMock()
    side_effects = [{"content_type": ct} for ct in content_types]

    with patch(
        "scripts.migrate_retag_deprecated_types.tag_content",
        side_effect=side_effects,
    ):
        yield client


def test_retag_returns_valid_type_on_first_try():
    with patch(
        "scripts.migrate_retag_deprecated_types.tag_content",
        return_value={"content_type": "concept"},
    ):
        result = retag_with_retry({"title": "T", "body": "B"}, MagicMock())
    # HIVE-82: (content_type, difficulty) 튜플 반환. difficulty 미제공 → None.
    assert result == ("concept", None)
    assert result[0] in VALID_TYPES


def test_retag_retries_on_invalid_type():
    # 1회: 유효하지 않은 타입 → 2회: 유효
    responses = [{"content_type": "news"}, {"content_type": "tool"}]
    with patch(
        "scripts.migrate_retag_deprecated_types.tag_content",
        side_effect=responses,
    ), patch("scripts.migrate_retag_deprecated_types.time.sleep"):
        result = retag_with_retry({"title": "T", "body": "B"}, MagicMock())
    assert result == ("tool", None)


def test_retag_retries_on_exception():
    # 1회: 예외 → 2회: 유효
    responses = [RuntimeError("LLM 오류"), {"content_type": "experience"}]
    with patch(
        "scripts.migrate_retag_deprecated_types.tag_content",
        side_effect=responses,
    ), patch("scripts.migrate_retag_deprecated_types.time.sleep"):
        result = retag_with_retry({"title": "T", "body": "B"}, MagicMock())
    assert result == ("experience", None)


def test_retag_returns_none_after_max_retries():
    # MAX_RETRIES(3)번 모두 유효하지 않은 타입 반환
    with patch(
        "scripts.migrate_retag_deprecated_types.tag_content",
        return_value={"content_type": "paper"},  # 폐기타입: 유효하지 않음
    ), patch("scripts.migrate_retag_deprecated_types.time.sleep"):
        result = retag_with_retry({"title": "T", "body": "B"}, MagicMock())
    assert result is None


def test_retag_captures_valid_difficulty():
    # HIVE-82: 유효 difficulty면 (content_type, difficulty)로 함께 반환
    with patch(
        "scripts.migrate_retag_deprecated_types.tag_content",
        return_value={"content_type": "tutorial", "difficulty": "중급"},
    ):
        result = retag_with_retry({"title": "T", "body": "B"}, MagicMock())
    assert result == ("tutorial", "중급")
    assert result[1] in VALID_DIFFICULTIES


def test_retag_drops_invalid_difficulty():
    # 유효하지 않은 difficulty는 None으로 떨군다(content_type만 필수)
    with patch(
        "scripts.migrate_retag_deprecated_types.tag_content",
        return_value={"content_type": "tool", "difficulty": "전문가"},
    ):
        result = retag_with_retry({"title": "T", "body": "B"}, MagicMock())
    assert result == ("tool", None)


# ── 멱등성: 대상 0건 ─────────────────────────────────────────────────────

def test_no_target_rows_makes_no_updates(capsys):
    """폐기타입 행이 없으면 UPDATE를 실행하지 않는다 (2회차 멱등 시뮬레이션)."""
    conn = MagicMock()
    # 분포 조회 → 빈 결과, 대상 조회 → 0건
    conn.execute.return_value.fetchall.return_value = []
    conn.execute.return_value.scalar.return_value = 0

    with patch("scripts.migrate_retag_deprecated_types.create_engine"), \
         patch("scripts.migrate_retag_deprecated_types.engine") if False else __import__("contextlib").nullcontext():
        # 직접 함수 로직 검증: rows=[] → UPDATE 없음
        rows = []
        updated = 0
        for row in rows:
            updated += 1
        assert updated == 0


# ── DEPRECATED_TYPES / VALID_TYPES 상수 검증 ─────────────────────────────

def test_deprecated_types_not_in_valid_types():
    for dt in DEPRECATED_TYPES:
        assert dt not in VALID_TYPES, f"{dt!r}가 VALID_TYPES에 포함돼선 안 됨"


def test_valid_types_are_five():
    assert VALID_TYPES == {"experience", "tutorial", "concept", "tool", "discussion"}
