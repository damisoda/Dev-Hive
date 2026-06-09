"""HIVE-40 QC 게이트 — 적재 전 무료 휴리스틱 품질 필터.

위치: 정규화 후 · 태깅(Haiku) 전. 명백한 junk(미스라벨 소스/NSFW/빈 본문/저신뢰
서브레딧/답 없는 질문/배치 내 중복 등)를 LLM 비용을 들이기 전에 걸러낸다.

설계 원칙 — **precision 우선**:
    애매하면 통과시킨다. 좋은 경험글을 오탐으로 버리는 비용이, 노이즈 일부가
    통과하는 비용보다 크다. "확실한 junk"만 거른다.

범위 밖(여기서 하지 않음):
    - 뉴스/저품질(quality_score) 판정은 태깅 **후** 단계에서 처리한다.
    - 입력은 정규화된 dict(`ContentSchema.to_dict`)만 가정한다.

입력 레코드 키: title, source, url, body, author_name, language,
published_at, engagement{likes, comments}.
"""
from __future__ import annotations

import re

# ─────────────────────────────────────────────────────────────────────────────
# 튜닝 가능한 설정 상수
# ─────────────────────────────────────────────────────────────────────────────

# 허용 소스. hn·X 미포함 = 자동거부.
#   - hn: HackerNews 폐기 결정(데이터 품질 미달).
#   - X: 재작업 전이라 현재 파이프라인에서 제외.
ALLOWED_SOURCES = frozenset(
    {"velog", "tistory", "reddit", "github_trending", "huggingface"}
)

# github_trending 최소 star 수. stars = engagement.likes(github_crawler가 매핑).
# stars = "써볼 만하다"는 사회적 증거. 실측 분포(300건): ≥500→18% / ≥300→26% / ≥100→60%.
# 100 = 명백한 토이레포(<100)만 컷하고 볼륨 확보(팀장 결정). 튜닝 가능.
GITHUB_MIN_STARS = 100

# 큐레이션된 경험-풍부 서브레딧.
# 근거: reddit_crawler.DEFAULT_SUBREDDITS를 기준으로 잡되,
#   - 소비자 푸념·밈·NSFW가 많은 `ChatGPT`는 제외(저신호).
#   - 실전 빌드/학습 중심 서브레딧(learnmachinelearning, NoCode, n8n 등)을 보강.
# 매칭은 대소문자 무시(Reddit 서브레딧명은 대소문자 구분 없음) — casefold 비교.
REDDIT_SUBREDDIT_ALLOW = frozenset(
    s.casefold()
    for s in {
        # reddit_crawler.DEFAULT_SUBREDDITS 계열(ChatGPT 제외)
        "MachineLearning",
        "LocalLLaMA",
        "LocalLLM",
        "ArtificialIntelligence",
        "ArtificialInteligence",  # DEFAULT_SUBREDDITS의 오탈자 변형까지 허용
        "LangChain",
        "OpenAI",
        # 실전 빌드·학습 중심 보강(경험글 밀도 높음)
        "learnmachinelearning",
        "LLMDevs",
        "PromptEngineering",
        "NoCode",
        "n8n",
        "ClaudeAI",
    }
)

# NSFW 패턴 — 확실한 음란/성인물 신호만. 단어경계로 오탐 최소화.
# (예: "nude"가 "denude"류에 끼지 않도록 \b 사용)
NSFW_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\blolicon\b",
        r"\bnsfw\b",
        r"\bporn\w*",          # porn, porno, pornography ...
        r"\bhentai\b",
        r"\bnudes?\b",
        r"\bonlyfans\b",
        r"\bcamgirl\b",
        r"음란",
        r"성인물",
        r"야동",
    )
)

# reddit 질문형 제목 시작어(영문). 소문자 비교.
_QUESTION_STARTERS = (
    "how",
    "why",
    "what",
    "which",
    "who",
    "where",
    "when",
    "is",
    "are",
    "do",
    "does",
    "did",
    "should",
    "can",
    "could",
    "would",
    "will",
    "any",  # "anyone ...?", "any tips ...?"
)

# 한글 질문형 어미(제목 끝). '?'가 없어도 질문으로 판정.
_KOREAN_QUESTION_ENDINGS = (
    "나요",
    "가요",
    "까요",
    "은가",
    "는가",
    "을까",
    "ㄹ까",
    "인가요",
    "되나요",
    "뭐죠",
    "뭔가요",
)

# Reddit 퍼머링크에서 서브레딧 추출: reddit.com/r/<name>/...
# 호스트 앵커로 외부 링크 글의 url에서 오추출 방지(예: example.com/r/X).
_SUBREDDIT_RE = re.compile(r"reddit\.com/r/([A-Za-z0-9_]+)", re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _engagement_int(record: dict, key: str) -> int:
    """engagement[key]를 안전하게 int로. 없거나 비정상이면 0."""
    eng = record.get("engagement")
    if not isinstance(eng, dict):
        return 0
    val = eng.get(key, 0)
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def _is_nsfw(title: str, body: str) -> bool:
    haystack = f"{title}\n{body}"
    return any(p.search(haystack) for p in NSFW_PATTERNS)


def _extract_subreddit(url: str) -> str | None:
    """Reddit URL에서 서브레딧명을 추출. 실패하면 None."""
    if not url:
        return None
    match = _SUBREDDIT_RE.search(url)
    return match.group(1) if match else None


def _looks_like_question(title: str) -> bool:
    """제목이 질문형인지. 영문(? 끝 / 의문사 시작) + 한글 의문 어미."""
    stripped = title.strip()
    if not stripped:
        return False
    if stripped.endswith("?") or stripped.endswith("？"):
        return True
    # 영문 의문사로 시작
    lowered = stripped.casefold()
    first_word = re.split(r"[\s,]+", lowered, maxsplit=1)[0]
    # 구두점 제거한 첫 단어로도 비교(예: "what's")
    first_token = re.sub(r"[^a-z]", "", first_word)
    if first_token in _QUESTION_STARTERS:
        return True
    # 한글 질문형 어미(제목 끝). 부분일치(은가/는가 중간삽입) 오탐을 막기 위해 endswith만.
    return any(stripped.endswith(end) for end in _KOREAN_QUESTION_ENDINGS)


# ─────────────────────────────────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────────────────────────────────

def qc_gate(
    records: list[dict], *, expected_source: str | None = None
) -> tuple[list[dict], dict]:
    """크롤/업로드 레코드에 QC 게이트를 적용한다.

    Args:
        records: 정규화된 dict 리스트(`ContentSchema.to_dict` 형태).
        expected_source: 지정 시 —
            (a) 크롤 소스명("github_trending" 등)이면 레코드 source가 그것과 다를 때
                "source_mismatch"로 거부(미스라벨 강제정정).
            (b) "user"면 소스 허용목록·star·서브레딧·Q&A 검사를 건너뛰고
                NSFW·빈본문·중복만 적용한다(유저 업로드 공통 게이트 — 자가복제 일관성).
            None이면 크롤 기본 동작.

    Returns:
        (passed, report)
          - passed: 게이트를 통과한 레코드 리스트(입력 순서 유지).
          - report: 로깅용 거부 리포트 dict.
              {
                "total": N, "passed": M, "rejected": K,
                "by_reason": {사유: 건수},
                "by_source": {source: {"passed": x, "rejected": y}},
              }

    검사 순서(첫 매치 시 거부 + 사유 기록). precision 우선:
        1. source ∉ ALLOWED_SOURCES        → "source_not_allowed"
        2. NSFW (title+body 매치)           → "nsfw"
        3. 빈 본문                           → "empty_body"
        4. github_trending stars < 최소     → "low_stars"
        5. reddit 서브레딧 ∉ allow           → "subreddit_not_allowed"
                                              (추출 실패 시 통과 — precision 우선)
        6. reddit 답 없는 질문(comments==0)  → "unanswered_qa"
        7. 배치 내 중복 URL                  → "duplicate_url"
    """
    passed: list[dict] = []
    by_reason: dict[str, int] = {}
    by_source: dict[str, dict[str, int]] = {}
    seen_urls: set[str] = set()

    def _bump_source(source: str, key: str) -> None:
        bucket = by_source.setdefault(source, {"passed": 0, "rejected": 0})
        bucket[key] += 1

    def _reject(source: str, reason: str) -> None:
        by_reason[reason] = by_reason.get(reason, 0) + 1
        _bump_source(source, "rejected")

    is_user = expected_source == "user"

    for record in records:
        source = record.get("source") or "__none__"
        title = record.get("title") or ""
        body = record.get("body") or ""
        url = record.get("url") or ""

        # 0. 미스라벨 강제정정: expected_source(크롤 소스)와 레코드 source 불일치 거부.
        if expected_source is not None and not is_user and source != expected_source:
            _reject(source, "source_mismatch")
            continue

        # 1. 허용 소스 (hn·X 자동거부). user 업로드 경로는 허용목록을 우회.
        if not is_user and source not in ALLOWED_SOURCES:
            _reject(source, "source_not_allowed")
            continue

        # 2. NSFW
        if _is_nsfw(title, body):
            _reject(source, "nsfw")
            continue

        # 3. 빈 본문
        if not body.strip():
            _reject(source, "empty_body")
            continue

        # 4. github_trending: star 미달 (user 경로 제외)
        if not is_user and source == "github_trending":
            if _engagement_int(record, "likes") < GITHUB_MIN_STARS:
                _reject(source, "low_stars")
                continue

        # 5·6. reddit 전용 검사 (user 경로 제외)
        if not is_user and source == "reddit":
            subreddit = _extract_subreddit(url)
            # 추출 실패 → 통과(precision 우선). 추출 성공 시에만 allow 검사.
            if subreddit is not None and subreddit.casefold() not in REDDIT_SUBREDDIT_ALLOW:
                _reject(source, "subreddit_not_allowed")
                continue
            # 답 없는 Q&A: 질문형 제목 AND 댓글 0
            if _looks_like_question(title) and _engagement_int(record, "comments") == 0:
                _reject(source, "unanswered_qa")
                continue

        # 7. 배치 내 중복 URL (빈 URL은 중복 판정에서 제외 — precision 우선)
        if url and url in seen_urls:
            _reject(source, "duplicate_url")
            continue
        if url:
            seen_urls.add(url)

        passed.append(record)
        _bump_source(source, "passed")

    report = {
        "total": len(records),
        "passed": len(passed),
        "rejected": len(records) - len(passed),
        "by_reason": by_reason,
        "by_source": by_source,
    }
    return passed, report
