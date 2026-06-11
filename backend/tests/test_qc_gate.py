"""HIVE-40 QC 게이트 단위 테스트.

가짜 정규화 dict로 각 거부 사유 1개씩 + precision우선 통과 + 정상 통과 +
리포트 구조를 검증한다. DB·네트워크 의존 없음(순수 함수).
"""
from app.crawler.qc_gate import (
    GITHUB_MIN_STARS,
    REDDIT_SUBREDDIT_ALLOW,
    X_MIN_BODY_CHARS,
    X_ZERO_ENGAGEMENT_MAX_CHARS,
    detect_language,
    guess_language_by_script,
    qc_gate,
)


def _rec(**kw) -> dict:
    """정규화 dict의 최소 형태. 키워드로 필요한 필드만 덮어쓴다."""
    base = {
        "title": "A reasonable post about building RAG pipelines",
        "source": "velog",
        "url": "https://velog.io/@user/some-post",
        "body": "본문 내용이 충분히 있습니다. 실전 경험을 정리했습니다.",
        "author_name": "user",
        "language": "ko",
        "published_at": "2026-01-01T00:00:00+00:00",
        "engagement": {"likes": 10, "comments": 3},
    }
    base.update(kw)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# 통과 케이스
# ─────────────────────────────────────────────────────────────────────────────

def test_velog_passes():
    passed, report = qc_gate([_rec(source="velog")])
    assert len(passed) == 1
    assert report["passed"] == 1
    assert report["rejected"] == 0


def test_huggingface_passes():
    rec = _rec(
        source="huggingface",
        url="https://huggingface.co/papers/2401.00001",
    )
    passed, _ = qc_gate([rec])
    assert len(passed) == 1


def test_tistory_passes():
    rec = _rec(source="tistory", url="https://user.tistory.com/42")
    passed, _ = qc_gate([rec])
    assert len(passed) == 1


def test_github_high_stars_passes():
    rec = _rec(
        source="github_trending",
        title="org/cool-llm-agent-framework",
        url="https://github.com/org/cool-llm-agent-framework",
        body="A production-ready agent framework.",
        engagement={"likes": GITHUB_MIN_STARS + 1, "comments": 0},
    )
    passed, _ = qc_gate([rec])
    assert len(passed) == 1


def test_reddit_allowed_subreddit_with_comments_passes():
    rec = _rec(
        source="reddit",
        title="How I fine-tuned a small model on my laptop",
        url="https://www.reddit.com/r/LocalLLaMA/comments/abc123/post/",
        body="Here is my full writeup of the experience.",
        engagement={"likes": 50, "comments": 12},
    )
    passed, _ = qc_gate([rec])
    assert len(passed) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 거부 케이스 — 각 사유 1개씩
# ─────────────────────────────────────────────────────────────────────────────

def test_hn_source_rejected():
    passed, report = qc_gate([_rec(source="hn")])
    assert len(passed) == 0
    assert report["by_reason"]["source_not_allowed"] == 1


def test_x_source_rejected():
    passed, report = qc_gate([_rec(source="X")])
    assert len(passed) == 0
    assert report["by_reason"]["source_not_allowed"] == 1


def test_nsfw_rejected():
    rec = _rec(
        source="reddit",
        title="NSFW hentai content here",
        url="https://www.reddit.com/r/LocalLLaMA/comments/x/y/",
    )
    passed, report = qc_gate([rec])
    assert len(passed) == 0
    assert report["by_reason"]["nsfw"] == 1


def test_nsfw_in_body_rejected():
    rec = _rec(
        source="velog",
        title="Totally normal title",
        body="...buy my onlyfans...",
    )
    passed, report = qc_gate([rec])
    assert len(passed) == 0
    assert report["by_reason"]["nsfw"] == 1


def test_empty_body_rejected():
    passed, report = qc_gate([_rec(source="velog", body="   \n  ")])
    assert len(passed) == 0
    assert report["by_reason"]["empty_body"] == 1


def test_none_body_rejected():
    passed, report = qc_gate([_rec(source="velog", body=None)])
    assert len(passed) == 0
    assert report["by_reason"]["empty_body"] == 1


def test_github_low_stars_rejected():
    rec = _rec(
        source="github_trending",
        title="org/tiny-toy-repo",
        url="https://github.com/org/tiny-toy-repo",
        body="early stage",
        engagement={"likes": GITHUB_MIN_STARS - 1, "comments": 0},
    )
    passed, report = qc_gate([rec])
    assert len(passed) == 0
    assert report["by_reason"]["low_stars"] == 1


def test_reddit_disallowed_subreddit_rejected():
    # ChatGPT는 allow에서 의도적으로 제외됨(소비자 푸념/NSFW 多).
    rec = _rec(
        source="reddit",
        title="ChatGPT keeps making mistakes",
        url="https://www.reddit.com/r/ChatGPT/comments/abc/post/",
        body="just venting about the model",
        engagement={"likes": 5, "comments": 4},
    )
    passed, report = qc_gate([rec])
    assert len(passed) == 0
    assert report["by_reason"]["subreddit_not_allowed"] == 1


def test_reddit_unanswered_question_rejected():
    rec = _rec(
        source="reddit",
        title="How do I run llama locally?",
        url="https://www.reddit.com/r/LocalLLaMA/comments/abc/post/",
        body="anyone know?",
        engagement={"likes": 1, "comments": 0},
    )
    passed, report = qc_gate([rec])
    assert len(passed) == 0
    assert report["by_reason"]["unanswered_qa"] == 1


def test_reddit_korean_unanswered_question_rejected():
    rec = _rec(
        source="reddit",
        title="로컬에서 llama 어떻게 돌리나요",  # '?' 없이도 질문형
        url="https://www.reddit.com/r/LocalLLaMA/comments/abc/post/",
        body="도와주세요",
        engagement={"likes": 1, "comments": 0},
    )
    passed, report = qc_gate([rec])
    assert len(passed) == 0
    assert report["by_reason"]["unanswered_qa"] == 1


def test_duplicate_url_rejected():
    a = _rec(source="velog", url="https://velog.io/@user/dup")
    b = _rec(source="velog", url="https://velog.io/@user/dup")
    passed, report = qc_gate([a, b])
    assert len(passed) == 1  # 첫 건만 통과
    assert report["by_reason"]["duplicate_url"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# precision 우선 — 애매하면 통과
# ─────────────────────────────────────────────────────────────────────────────

def test_reddit_subreddit_extraction_failure_passes():
    # URL에서 서브레딧을 못 뽑으면 거부하지 않고 통과(precision 우선).
    rec = _rec(
        source="reddit",
        title="A great experience writeup",
        url="https://www.reddit.com/some/weird/path/",  # /r/<name> 없음
        body="full content here",
        engagement={"likes": 10, "comments": 5},
    )
    passed, report = qc_gate([rec])
    assert len(passed) == 1
    assert report["rejected"] == 0


def test_nsfw_substring_not_falsely_flagged():
    # 'naked'는 단어경계 매치라 'snaked'/'unmasked' 같은 부분문자열은 통과해야 함.
    rec = _rec(
        source="velog",
        title="The class snaked through the analyzer",
        body="We unmasked a bug in the pipeline; nothing adult here.",
    )
    passed, report = qc_gate([rec])
    assert len(passed) == 1
    assert report["rejected"] == 0


def test_reddit_question_with_answers_passes():
    # 질문형이어도 댓글이 있으면(답이 있으면) 통과.
    rec = _rec(
        source="reddit",
        title="How do I run llama locally?",
        url="https://www.reddit.com/r/LocalLLaMA/comments/abc/post/",
        body="figured it out, sharing",
        engagement={"likes": 1, "comments": 8},
    )
    passed, _ = qc_gate([rec])
    assert len(passed) == 1


def test_reddit_non_question_no_comments_passes():
    # 비질문형이면 댓글 0이어도 통과(경험 공유글일 수 있음).
    rec = _rec(
        source="reddit",
        title="I built a local RAG stack over the weekend",
        url="https://www.reddit.com/r/LocalLLaMA/comments/abc/post/",
        body="here is what I learned",
        engagement={"likes": 30, "comments": 0},
    )
    passed, _ = qc_gate([rec])
    assert len(passed) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 견고성 — engagement/필드 누락 안전
# ─────────────────────────────────────────────────────────────────────────────

def test_missing_engagement_safe():
    rec = _rec(source="velog")
    del rec["engagement"]
    passed, _ = qc_gate([rec])
    assert len(passed) == 1  # velog는 engagement 불필요


def test_github_missing_engagement_treated_as_zero_stars():
    rec = _rec(
        source="github_trending",
        title="org/repo",
        url="https://github.com/org/repo",
        body="x",
    )
    del rec["engagement"]
    passed, report = qc_gate([rec])
    assert len(passed) == 0  # stars=0 < 최소 → low_stars
    assert report["by_reason"]["low_stars"] == 1


def test_none_source_and_url_safe():
    rec = _rec(source=None, url=None)
    passed, report = qc_gate([rec])
    assert len(passed) == 0  # None source는 허용 안 됨
    assert report["by_reason"]["source_not_allowed"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# 리포트 구조
# ─────────────────────────────────────────────────────────────────────────────

def test_report_structure_and_counts():
    records = [
        _rec(source="velog", url="https://velog.io/@u/1"),          # pass
        _rec(source="huggingface", url="https://huggingface.co/papers/1"),  # pass
        _rec(source="hn", url="https://news.ycombinator.com/item?id=1"),    # reject
        _rec(source="velog", body="", url="https://velog.io/@u/2"),         # reject empty
    ]
    passed, report = qc_gate(records)

    assert report["total"] == 4
    assert report["passed"] == 2
    assert report["rejected"] == 2
    assert len(passed) == 2

    # by_reason 합 == rejected
    assert sum(report["by_reason"].values()) == report["rejected"]
    assert report["by_reason"]["source_not_allowed"] == 1
    assert report["by_reason"]["empty_body"] == 1

    # by_source 구조 + 합 일치
    assert report["by_source"]["velog"] == {"passed": 1, "rejected": 1}
    assert report["by_source"]["huggingface"]["passed"] == 1
    assert report["by_source"]["hn"]["rejected"] == 1
    total_in_sources = sum(
        b["passed"] + b["rejected"] for b in report["by_source"].values()
    )
    assert total_in_sources == report["total"]


def test_empty_input():
    passed, report = qc_gate([])
    assert passed == []
    assert report == {
        "total": 0,
        "passed": 0,
        "rejected": 0,
        "by_reason": {},
        "by_source": {},
    }


def test_allow_list_excludes_chatgpt():
    # 명세 핵심: ChatGPT는 큐레이션에서 제외.
    assert "chatgpt" not in REDDIT_SUBREDDIT_ALLOW
    assert "localllama" in REDDIT_SUBREDDIT_ALLOW


# ── precision 보강: NSFW 오탐 제거(xxx/naked) ──────────────────────────────

def test_xxx_placeholder_not_nsfw():
    # 개발 플레이스홀더 xxx는 NSFW 아님(sk-xxx 키 예시, Feature/xxx 브랜치 등).
    rec = _rec(source="velog", body="Feature/xxx 브랜치에서 작업. 키는 sk-xxx 형식.")
    passed, report = qc_gate([rec])
    assert len(passed) == 1
    assert report["by_reason"] == {}


def test_naked_tech_term_not_nsfw():
    # "naked function/pointer" 같은 기술 용어는 NSFW 아님.
    rec = _rec(
        source="github_trending",
        url="https://github.com/o/r",
        body="A naked function pointer pattern in C.",
        engagement={"likes": 800, "comments": 0},
    )
    passed, _ = qc_gate([rec])
    assert len(passed) == 1


def test_lolicon_still_nsfw():
    rec = _rec(
        source="reddit",
        title="The lolicon strikes again",
        url="https://www.reddit.com/r/learnmachinelearning/comments/x/a/",
    )
    passed, report = qc_gate([rec])
    assert passed == []
    assert report["by_reason"].get("nsfw") == 1


def test_porn_still_nsfw():
    rec = _rec(source="velog", body="this is porn content")
    passed, report = qc_gate([rec])
    assert passed == []
    assert report["by_reason"].get("nsfw") == 1


# ── expected_source: 미스라벨 가드 + user 업로드 경로 ─────────────────────

def test_user_source_passes_with_expected_source():
    rec = _rec(source="user", url="user://anon/abc123")
    passed, report = qc_gate([rec], expected_source="user")
    assert len(passed) == 1
    assert "source_not_allowed" not in report["by_reason"]


def test_user_path_applies_nsfw():
    rec = _rec(source="user", title="lolicon", url="user://anon/x")
    passed, report = qc_gate([rec], expected_source="user")
    assert passed == []
    assert report["by_reason"].get("nsfw") == 1


def test_user_path_applies_empty_body():
    rec = _rec(source="user", body="   ", url="user://anon/x")
    passed, report = qc_gate([rec], expected_source="user")
    assert passed == []
    assert report["by_reason"].get("empty_body") == 1


def test_user_source_rejected_without_expected_source():
    # expected_source 없으면 source="user"는 허용목록 밖이라 거부(크롤 기본 동작).
    rec = _rec(source="user", url="user://anon/x")
    passed, report = qc_gate([rec])
    assert passed == []
    assert report["by_reason"].get("source_not_allowed") == 1


def test_expected_source_mismatch_rejected():
    # 미스라벨 가드: expected_source(github_trending) ≠ 레코드 source(velog) → 거부.
    rec = _rec(source="velog")
    passed, report = qc_gate([rec], expected_source="github_trending")
    assert passed == []
    assert report["by_reason"].get("source_mismatch") == 1


def test_expected_source_match_passes():
    rec = _rec(
        source="github_trending",
        url="https://github.com/o/r",
        body="README 내용",
        engagement={"likes": 900, "comments": 0},
    )
    passed, _ = qc_gate([rec], expected_source="github_trending")
    assert len(passed) == 1


# ── 서브레딧 호스트 앵커 / 한글 질문 endswith ─────────────────────────────

def test_subreddit_only_from_reddit_host():
    # reddit 외 호스트의 /r/ 경로는 서브레딧 오추출 안 함 → precision 우선 통과.
    rec = _rec(
        source="reddit",
        url="https://example.com/r/BannedSub/post",
        engagement={"likes": 1, "comments": 5},
    )
    passed, _ = qc_gate([rec])
    assert len(passed) == 1


# ─────────────────────────────────────────────────────────────────────────────
# HIVE-50: X 전용 필터 — too_short / language_not_supported / zero_engagement_short
# ─────────────────────────────────────────────────────────────────────────────

# 실측 덤프(x_crawl_dump_500.json) 형태를 본뜬 현실적 트윗 본문들.
_X_LONG_EN_BODY = (
    "Build AI Agents That Actually Work: sharing my full experience from "
    "production. Not just chatbots - agents that use tools, coordinate with "
    "other agents, and solve real problems. Here is the architecture, the "
    "eval setup, and the three mistakes that cost me a week of debugging."
)  # 약 300자 — 중앙값(260) 부근의 전형적 통과 트윗

_X_LONG_KO_BODY = (
    "LLM 에이전트를 프로덕션에 배포하면서 배운 점을 공유합니다. 툴 호출 실패 "
    "재시도 전략, 컨텍스트 윈도우 관리, 그리고 평가 파이프라인 구성까지 — "
    "특히 RAG 검색 품질이 전체 응답 품질을 좌우한다는 걸 실측으로 확인했고, "
    "임베딩 모델 교체만으로 정답률이 크게 올랐습니다. 자세한 수치는 스레드에."
)  # 한국어 장문 트윗 (>=100자)

_X_JA_BODY = (
    "大規模言語モデルの推論を高速化する方法について解説します。"
    "量子化と蒸留を組み合わせることで、精度を維持しながら推論速度を大幅に改善できます。"
    "具体的なベンチマーク結果とコード例はリポジトリを参照してください。"
)  # 일본어 우세 본문 (>=100자, 외국 스크립트)


def _x_rec(**kw) -> dict:
    """X 레코드의 정규화 dict 형태(ContentSchema.to_dict)."""
    base = _rec(
        source="x",
        title=_X_LONG_EN_BODY[:120],
        body=_X_LONG_EN_BODY,
        url="https://x.com/swyx/status/1973338922194252059",
        author_name="swyx",
        language="und",  # 업스트림이 'und'로 깨져 와도 게이트는 신뢰하지 않음
        engagement={"likes": 92, "comments": 7},
    )
    base.update(kw)
    return base


def test_x_long_english_tweet_passes():
    # language='und'여도 본문이 라틴 우세면 통과(필드 불신, 텍스트로 판정).
    passed, report = qc_gate([_x_rec()])
    assert len(passed) == 1
    assert report["rejected"] == 0


def test_x_korean_tweet_passes():
    rec = _x_rec(
        title=_X_LONG_KO_BODY[:120],
        body=_X_LONG_KO_BODY,
        engagement={"likes": 12, "comments": 1},
    )
    passed, report = qc_gate([rec])
    assert len(passed) == 1
    assert report["rejected"] == 0


def test_x_short_body_rejected():
    rec = _x_rec(body="grok is so much fun to use, try the api today")  # <100자
    passed, report = qc_gate([rec])
    assert passed == []
    assert report["by_reason"]["too_short"] == 1


def test_x_min_body_boundary():
    # 경계: 정확히 100자면 통과(미만만 컷).
    body = "a" * X_MIN_BODY_CHARS
    passed, _ = qc_gate([_x_rec(body=body, engagement={"likes": 5, "comments": 0})])
    assert len(passed) == 1


def test_x_foreign_script_rejected():
    rec = _x_rec(title=_X_JA_BODY[:120], body=_X_JA_BODY)
    passed, report = qc_gate([rec])
    assert passed == []
    assert report["by_reason"]["language_not_supported"] == 1


def test_x_mixed_script_passes():
    # 영어 본문에 일본어 인용이 일부 섞인 경우 — 라틴 우세라 통과(애매=통과).
    rec = _x_rec(body=_X_LONG_EN_BODY + " 日本語の引用が少しあります。")
    passed, report = qc_gate([rec])
    assert len(passed) == 1
    assert report["rejected"] == 0


def test_x_zero_engagement_short_rejected():
    # 짧은 편(<200자) AND likes·comments 모두 0 → 컷.
    rec = _x_rec(
        body=_X_LONG_EN_BODY[:150],
        engagement={"likes": 0, "comments": 0},
    )
    passed, report = qc_gate([rec])
    assert passed == []
    assert report["by_reason"]["zero_engagement_short"] == 1


def test_x_zero_engagement_long_passes():
    # 반응이 전무해도 본문이 충분히 길면(>=200자) 통과 — likes는 업스트림 깨짐 가능.
    assert len(_X_LONG_EN_BODY) >= X_ZERO_ENGAGEMENT_MAX_CHARS
    rec = _x_rec(engagement={"likes": 0, "comments": 0})
    passed, report = qc_gate([rec])
    assert len(passed) == 1
    assert report["rejected"] == 0


def test_x_short_with_likes_passes():
    # 100~200자 사이라도 반응이 있으면 통과.
    rec = _x_rec(
        body=_X_LONG_EN_BODY[:150],
        engagement={"likes": 30, "comments": 0},
    )
    passed, _ = qc_gate([rec])
    assert len(passed) == 1


def test_x_flat_toplevel_likes_fallback():
    # 구버전 평탄 덤프 호환: engagement dict 없이 top-level likes만 있어도
    # zero-engagement로 오탐하지 않음.
    rec = _x_rec(body=_X_LONG_EN_BODY[:150])
    del rec["engagement"]
    rec["likes"] = 92
    passed, report = qc_gate([rec])
    assert len(passed) == 1
    assert report["rejected"] == 0


def test_x_user_upload_bypasses_x_checks():
    # user 업로드 경로(is_user)는 다른 소스 전용 검사처럼 X 검사도 우회한다.
    rec = _x_rec(body="short user-pasted tweet about an llm agent", engagement={"likes": 0, "comments": 0})
    passed, report = qc_gate([rec], expected_source="user")
    assert len(passed) == 1
    assert report["rejected"] == 0


def test_guess_language_by_script():
    assert guess_language_by_script(_X_LONG_EN_BODY) == "en"
    assert guess_language_by_script(_X_LONG_KO_BODY) == "ko"
    assert guess_language_by_script("👍🔥💯 12345 !!!") is None  # 판별 불가


# ─────────────────────────────────────────────────────────────────────────────
# HIVE-50: 라틴 2차 언어 세분 — 스페인어 등 라틴계 비영어 거부 (실데이터 보강)
# ─────────────────────────────────────────────────────────────────────────────

# 실측(/tmp/x_trending_only.json)에서 스크립트 휴리스틱을 통과하던 스페인어
# 하이프/마케팅 트윗 본뜬 본문 — likes가 커서 zero_engagement도 안 걸리던 케이스.
_X_ES_BODY = (
    "He encontrado una herramienta con más de 10.000 creativos en vídeo para "
    "crear anuncios con IA. Están organizados por categorías y puedes usarlos "
    "gratis esta semana. Le das un objetivo y trabaja solo durante horas."
)

_X_PT_BODY = (
    "Você não vai acreditar nesta ferramenta de IA. Ela cria agentes que "
    "trabalham sozinhos por horas, e tudo isso de graça. Já testei com uma "
    "base de código enorme e o resultado foi muito além do que eu esperava."
)

_X_FR_BODY = (
    "J'ai trouvé un outil incroyable pour créer des agents IA. Vous lui "
    "donnez un objectif et il travaille seul pendant des heures, avec une "
    "mémoire infinie. C'est gratuit cette semaine et le résultat est très "
    "impressionnant pour les développeurs."
)

# 영어 본문 + 스페인어 차용구 소량 — precision 우선으로 통과해야 한다.
_X_EN_WITH_LOANWORDS_BODY = (
    "Shipped my LLM agent de facto standard eval suite today. The fiesta "
    "starts now: it runs every benchmark, writes the report, and posts it "
    "to Slack. No mas manual eval runs for my team. Here is the repo and "
    "the full writeup of the architecture."
)


def test_x_spanish_tweet_rejected():
    rec = _x_rec(
        title=_X_ES_BODY[:120],
        body=_X_ES_BODY,
        engagement={"likes": 276293, "comments": 900},  # 하이프 트윗 — likes로 못 거름
    )
    passed, report = qc_gate([rec])
    assert passed == []
    assert report["by_reason"]["language_not_supported"] == 1


def test_x_portuguese_tweet_rejected():
    rec = _x_rec(title=_X_PT_BODY[:120], body=_X_PT_BODY)
    passed, report = qc_gate([rec])
    assert passed == []
    assert report["by_reason"]["language_not_supported"] == 1


def test_x_french_tweet_rejected():
    rec = _x_rec(title=_X_FR_BODY[:120], body=_X_FR_BODY)
    passed, report = qc_gate([rec])
    assert passed == []
    assert report["by_reason"]["language_not_supported"] == 1


def test_x_english_with_spanish_loanwords_passes():
    # 외국어 기능어 히트가 영어 히트를 못 넘으면 영어 취급(precision 우선).
    rec = _x_rec(
        title=_X_EN_WITH_LOANWORDS_BODY[:120], body=_X_EN_WITH_LOANWORDS_BODY
    )
    passed, report = qc_gate([rec])
    assert len(passed) == 1
    assert report["rejected"] == 0


def test_x_korean_tweet_still_passes_after_latin_refinement():
    # 한글 우세 본문은 라틴 세분을 타지 않고 그대로 통과해야 한다.
    rec = _x_rec(title=_X_LONG_KO_BODY[:120], body=_X_LONG_KO_BODY)
    passed, report = qc_gate([rec])
    assert len(passed) == 1
    assert report["rejected"] == 0


def test_detect_language_refines_latin():
    assert detect_language(_X_ES_BODY) == "es"
    assert detect_language(_X_PT_BODY) == "pt"
    assert detect_language(_X_FR_BODY) == "fr"
    assert detect_language(_X_LONG_EN_BODY) == "en"
    assert detect_language(_X_LONG_KO_BODY) == "ko"
    assert detect_language("👍🔥💯 12345 !!!") is None


def test_detect_language_short_ambiguous_treated_as_english():
    # 짧은 라틴 텍스트(기능어 히트 < 3)는 판단 보류 → "en"(통과 방향).
    assert detect_language("vamos amigos, gran fiesta tech meetup tonight") == "en"


def test_korean_midword_not_false_question():
    # "...앱은가 보다"는 '보다'로 끝나므로 질문 아님(은가 부분일치 오탐 방지).
    rec = _rec(
        source="reddit",
        title="내가 만든 앱은가 보다",
        url="https://www.reddit.com/r/learnmachinelearning/comments/x/a/",
        engagement={"likes": 1, "comments": 0},
    )
    passed, report = qc_gate([rec])
    assert len(passed) == 1
    assert "unanswered_qa" not in report["by_reason"]
