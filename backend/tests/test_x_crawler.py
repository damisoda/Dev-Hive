"""HIVE-28 X 크롤러 단위 테스트 (네트워크/Apify 없음).

- _is_valid_insight_tweet: RT·짧은글·무키워드 제외 + 단어경계 필터(부분문자열 오탐 방지)
- _author_from_item: dict/JSON문자열/top-level author 추출(#36의 author 100% 깨짐 회귀 방지)
- _engagement_counts / _parse_datetime / _url_from_item / dedupe
- normalize_x_item: 유효 항목 → ContentSchema(source="x"), 무효 → None
"""
from datetime import datetime, timezone

from app.crawler.x_crawler import (
    _author_from_item,
    _engagement_counts,
    _is_valid_insight_tweet,
    _parse_datetime,
    _url_from_item,
    dedupe_by_url,
    normalize_x_item,
)


# ── _is_valid_insight_tweet ────────────────────────────────────────────────

def test_filter_rejects_retweet():
    assert _is_valid_insight_tweet("RT @karpathy: great LLM agent thread") is False


def test_filter_rejects_too_short():
    assert _is_valid_insight_tweet("llm agent") is False  # 25자 미만


def test_filter_rejects_no_keyword():
    assert _is_valid_insight_tweet("Had a lovely walk in the park this sunny morning today") is False


def test_filter_word_boundary_no_false_positive():
    # 'ai'가 said/again/available/email 안에 들어있지만 단어경계로 막혀야 한다(과거엔 통과했음).
    text = "I said that again; it was available by email to all my friends today."
    assert _is_valid_insight_tweet(text) is False


def test_filter_accepts_real_insight():
    text = "Sharing my experience: built an LLM agent with RAG and MCP — here is how"
    assert _is_valid_insight_tweet(text) is True


# ── _author_from_item (#36: author 100% 깨짐 → 복구 확인) ───────────────────

def test_author_from_dict():
    assert _author_from_item({"author": {"userName": "swyx"}}) == "swyx"


def test_author_from_json_string():
    assert _author_from_item({"author": '{"screen_name": "karpathy"}'}) == "karpathy"


def test_author_from_top_level():
    assert _author_from_item({"username": "reach_vb"}) == "reach_vb"


def test_author_missing_returns_none():
    assert _author_from_item({"text": "no author here"}) is None


# ── _engagement_counts / _parse_datetime / _url_from_item / dedupe ──────────

def test_engagement_retweets_fold_into_comments():
    likes, comments = _engagement_counts({"likeCount": 10, "retweetCount": 2, "replyCount": 3})
    assert likes == 10 and comments == 5  # retweet+reply


def test_parse_datetime_formats():
    assert _parse_datetime("Fri Jun 05 15:58:29 +0000 2026").year == 2026
    assert _parse_datetime("2026-06-05T15:58:29Z").tzinfo is not None
    assert _parse_datetime(1_750_000_000).tzinfo == timezone.utc  # epoch seconds


def test_url_built_from_id_and_author():
    assert _url_from_item({"id": "123"}, "swyx") == "https://x.com/swyx/status/123"


def test_dedupe_by_url():
    items = [
        normalize_x_item(_valid_item("https://x.com/a/status/1")),
        normalize_x_item(_valid_item("https://x.com/a/status/1")),
        normalize_x_item(_valid_item("https://x.com/a/status/2")),
    ]
    assert len(dedupe_by_url([i for i in items if i])) == 2


# ── normalize_x_item ───────────────────────────────────────────────────────

def _valid_item(url="https://x.com/swyx/status/1"):
    return {
        "full_text": "Sharing my experience deploying an LLM agent with RAG in production",
        "author": {"userName": "swyx"},
        "url": url,
        "likeCount": 10, "retweetCount": 1, "replyCount": 2,
        "createdAt": "Fri Jun 05 15:58:29 +0000 2026", "lang": "en",
    }


def test_normalize_valid_item():
    c = normalize_x_item(_valid_item())
    assert c is not None
    assert c.source == "x"
    assert c.author_name == "swyx"
    assert c.engagement == {"likes": 10, "comments": 3}
    assert c.url == "https://x.com/swyx/status/1"
    assert c.body and len(c.title) > 0


def test_normalize_rejects_retweet():
    item = _valid_item()
    item["full_text"] = "RT @someone: check this out"
    assert normalize_x_item(item) is None


def test_normalize_rejects_no_url():
    item = {"full_text": "Sharing my experience with an LLM agent and RAG pipeline"}
    assert normalize_x_item(item) is None  # url/id 없음
