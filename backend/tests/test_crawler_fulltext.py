"""HIVE-83 크롤러 full-text 수집 단위 테스트 (네트워크 없음).

변경사항 커버:
- reddit_crawler: REDDIT_PRAW_MIN_BODY 필터 — 짧은 본문·링크 포스트 제외
- velog_crawler: VELOG_FETCH_FULL_BODY 제거 → _fetch_body 항상 호출, short_description 폴백 없음
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Reddit PRAW 크롤러 (_normalize_post + REDDIT_PRAW_MIN_BODY)
# ─────────────────────────────────────────────────────────────────────────────

def _reddit_post(selftext: str, title: str = "LLM agent tutorial") -> SimpleNamespace:
    """PRAW Submission 객체 최소 모사."""
    return SimpleNamespace(
        title=title,
        selftext=selftext,
        permalink="/r/MachineLearning/comments/abc/llm_agent",
        score=100,
        num_comments=20,
        created_utc=1_750_000_000.0,
    )


def test_reddit_short_body_filtered():
    from app.crawler.reddit_crawler import _normalize_post
    post = _reddit_post("LLM agent is great " * 5)   # ~100자 — min 300 미만
    assert _normalize_post(post) is None


def test_reddit_link_post_filtered():
    """selftext='' 인 링크 포스트는 body 0자 → 항상 제외."""
    from app.crawler.reddit_crawler import _normalize_post
    post = _reddit_post("")
    assert _normalize_post(post) is None


def test_reddit_long_body_passes():
    """300자 이상 본문은 AI 키워드 있으면 통과."""
    from app.crawler.reddit_crawler import _normalize_post
    body = "I built an LLM agent with RAG pipeline using langchain. " * 10  # ~560자
    post = _reddit_post(body)
    result = _normalize_post(post)
    assert result is not None
    assert result.source == "reddit"


def test_reddit_praw_min_body_env(monkeypatch):
    """REDDIT_PRAW_MIN_BODY 환경변수로 임계값 조정 가능."""
    monkeypatch.setenv("REDDIT_PRAW_MIN_BODY", "100")
    # 모듈을 다시 임포트해서 상수 재평가
    import importlib
    import app.crawler.reddit_crawler as m
    importlib.reload(m)
    body = "LLM agent " * 12   # ~120자 — 100 이상이므로 통과해야 함
    post = _reddit_post(body)
    assert m._normalize_post(post) is not None
    # 원복
    importlib.reload(m)


def test_reddit_min_body_does_not_affect_public_crawler():
    """REDDIT_PRAW_MIN_BODY와 REDDIT_MIN_BODY(public)는 별개 환경변수."""
    import app.crawler.reddit_crawler as praw_c
    import app.crawler.reddit_public_crawler as pub_c
    # 서로 다른 상수명 — 충돌 없음
    assert hasattr(praw_c, "REDDIT_PRAW_MIN_BODY")
    assert hasattr(pub_c, "REDDIT_MIN_BODY")
    assert not hasattr(praw_c, "REDDIT_MIN_BODY")  # PRAW crawler엔 없어야 함


# ─────────────────────────────────────────────────────────────────────────────
# Velog 크롤러 (_to_content — 항상 full body 수집)
# ─────────────────────────────────────────────────────────────────────────────

def _velog_post(url_slug: str = "my-llm-post", short_description: str = "짧은 티저") -> dict:
    return {
        "title": "LLM 에이전트 경험기",
        "url_slug": url_slug,
        "short_description": short_description,
        "released_at": "2026-06-01T00:00:00Z",
        "likes": 5,
        "comments_count": 2,
    }


LONG_BODY = "LLM 에이전트를 프로덕션에서 운영하며 배운 점을 공유합니다. " * 30  # ~1500자


def test_velog_always_calls_fetch_body(monkeypatch):
    """url_slug 있으면 short_description 무시하고 _fetch_body 항상 호출."""
    from app.crawler.velog_crawler import _to_content
    calls = {"n": 0}

    def fake_fetch(username, url_slug):
        calls["n"] += 1
        return LONG_BODY

    monkeypatch.setattr("app.crawler.velog_crawler._fetch_body", fake_fetch)
    monkeypatch.setattr("app.crawler.velog_crawler.time.sleep", lambda s: None)

    result = _to_content(_velog_post(), username="testuser")
    assert calls["n"] == 1
    assert result is not None


def test_velog_short_description_never_used(monkeypatch):
    """_fetch_body가 빈 문자열 반환해도 short_description으로 폴백하지 않는다."""
    from app.crawler.velog_crawler import _to_content
    monkeypatch.setattr("app.crawler.velog_crawler._fetch_body", lambda *a: "")
    monkeypatch.setattr("app.crawler.velog_crawler.time.sleep", lambda s: None)

    post = _velog_post(short_description="이 글은 정말 긴 내용을 담고 있습니다" * 50)
    result = _to_content(post, username="testuser")
    # short_description이 500자를 넘어도 _fetch_body="" 이면 None
    assert result is None


def test_velog_network_failure_drops_post(monkeypatch):
    """_fetch_body 네트워크 실패(_gql→None) → body="" → 포스트 제외."""
    from app.crawler.velog_crawler import _to_content
    monkeypatch.setattr("app.crawler.velog_crawler._fetch_body", lambda *a: "")
    monkeypatch.setattr("app.crawler.velog_crawler.time.sleep", lambda s: None)

    result = _to_content(_velog_post(), username="testuser")
    assert result is None


def test_velog_full_body_accepted(monkeypatch):
    """_fetch_body가 500자 이상 반환하면 ContentSchema 생성."""
    from app.crawler.velog_crawler import _to_content
    monkeypatch.setattr("app.crawler.velog_crawler._fetch_body", lambda *a: LONG_BODY)
    monkeypatch.setattr("app.crawler.velog_crawler.time.sleep", lambda s: None)

    result = _to_content(_velog_post(), username="testuser")
    assert result is not None
    assert result.source == "velog"
    assert len(result.body) >= 500


def test_velog_missing_url_slug_drops_post(monkeypatch):
    """url_slug 없으면 _fetch_body 호출 없이 body="" → 제외."""
    from app.crawler.velog_crawler import _to_content
    fetch_called = {"n": 0}

    def fake_fetch(*a):
        fetch_called["n"] += 1
        return LONG_BODY

    monkeypatch.setattr("app.crawler.velog_crawler._fetch_body", fake_fetch)
    monkeypatch.setattr("app.crawler.velog_crawler.time.sleep", lambda s: None)

    post = _velog_post(url_slug="")
    result = _to_content(post, username="testuser")
    assert result is None
    assert fetch_called["n"] == 0   # url_slug 없으면 호출 자체 안 함


def test_velog_no_fetch_full_body_constant():
    """VELOG_FETCH_FULL_BODY 상수가 완전히 제거됐는지 확인."""
    import app.crawler.velog_crawler as m
    assert not hasattr(m, "VELOG_FETCH_FULL_BODY")
