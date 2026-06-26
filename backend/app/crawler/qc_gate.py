"""HIVE-40 QC 게이트 — 적재 전 무료 휴리스틱 품질 필터.

위치: 정규화 후 · 태깅(Haiku) 전. 명백한 junk(미스라벨 소스/NSFW/빈 본문/저신뢰
서브레딧/답 없는 질문/X 저신호 트윗/배치 내 중복 등)를 LLM 비용을 들이기 전에 걸러낸다.

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

# 허용 소스. hn 미포함 = 자동거부.
#   - hn: HackerNews 폐기 결정(데이터 품질 미달).
#   - x: HIVE-28 시드유저(14인 전문가) 재작업 완료 → 포함. source 값은 "x"(소문자).
#   - github_discussions: GitHub Discussions(Q&A·토론형). 본문 정결, 경험/토론 결에 부합 → 포함.
ALLOWED_SOURCES = frozenset(
    {"velog", "tistory", "reddit", "github_trending", "github_discussions", "huggingface", "x"}
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

# ─── HIVE-50: X 전용 필터 상수 ───────────────────────────────────────────────

# X 최소 본문 길이. 실측(x_crawl_dump_500.json, 327건): 본문 길이 min 27 /
# 중앙값 260 / <100자 = 23건(7.0%) / <200자 = 72건(22.0%).
# x_crawler가 URL 제거·500자 절단을 이미 한 본문 기준이라, 100자 미만은
# 실질 인사이트 없는 한 줄 잡담일 확률이 높다 — precision 우선으로 100에 고정.
X_MIN_BODY_CHARS = 100

# X zero-engagement 컷의 "짧은 편" 경계. likes는 업스트림에서 깨진 사례가 있어
# (DB 실측 62/64건 likes=0, 원본 덤프는 ~80%가 likes>0) engagement 단독으로는
# 절대 거부하지 않는다. 짧고(<200자) AND 반응 전무(likes·comments 모두 0)일 때만 컷.
# 실측: <200자 & likes 0 = 16/327(4.9%), too_short와 합산 38/327 → 통과율 88.4%.
X_ZERO_ENGAGEMENT_MAX_CHARS = 200

# 외국 스크립트 우세 판정 최소 글자 수. 이보다 적으면 판단 보류=통과(precision 우선).
_FOREIGN_SCRIPT_MIN_CHARS = 20

# 지원 외 스크립트 코드포인트 범위(가나·한자·키릴·아랍·타이·히브리·데바나가리·벵골).
# record["language"]는 'und'로 깨져 오는 경우가 많아 신뢰하지 않고
# 텍스트 자체의 스크립트 분포로 판정한다. 실측: 덤프 327건 중 컷 0건(전부 영어).
_FOREIGN_SCRIPT_RANGES = (
    (0x3040, 0x30FF),  # 히라가나·가타카나
    (0x31F0, 0x31FF),  # 가타카나 음성 확장
    (0x3400, 0x4DBF),  # CJK 한자 확장 A
    (0x4E00, 0x9FFF),  # CJK 한자 기본
    (0xF900, 0xFAFF),  # CJK 호환 한자
    (0x0400, 0x052F),  # 키릴 + 보충
    (0x0600, 0x06FF),  # 아랍
    (0x0750, 0x077F),  # 아랍 보충
    (0x08A0, 0x08FF),  # 아랍 확장 A
    (0x0E00, 0x0E7F),  # 타이
    (0x0590, 0x05FF),  # 히브리
    (0x0900, 0x097F),  # 데바나가리
    (0x0980, 0x09FF),  # 벵골
)

# 한글 범위(완성형 음절 + 자모 + 호환 자모) — 라틴과 함께 "지원 스크립트"로 취급.
_HANGUL_RANGES = (
    (0xAC00, 0xD7AF),
    (0x1100, 0x11FF),
    (0x3130, 0x318F),
)

# ─── HIVE-50: 라틴 스크립트 2차 언어 판별(영어 vs 주요 라틴계 언어) ──────────
#
# 스크립트 휴리스틱만으로는 스페인어·포르투갈어 등 라틴계 언어가 전부 'en'으로
# 판정된다(실측: trending 덤프 215건에서 스페인어 하이프/마케팅 트윗이 그대로
# 통과, likes가 커서 zero_engagement도 안 걸림). 기능어(관사·전치사·대명사)
# 빈도 + 언어 특유 문자(¿ ¡ ñ ã õ ç ü ß) 신호로 2차 판별한다. stdlib only.
#
# precision 우선: 외국어 기능어 히트 >= _LATIN_FOREIGN_MIN_HITS AND
# > 영어 기능어 히트일 때만 비영어로 분류. 애매하거나 짧으면 영어 취급(통과).
# 단어 선정 원칙: 영어와 철자가 겹치는 기능어는 제외(do/no/as/was/am/man/hat/
# per/come/in/son/plus/os 등) — 영어 본문 오탐(false reject) 방지.

# 영어 기능어 — 외국어 히트와 비교할 기준선.
_EN_FUNCTION_WORDS = frozenset(
    """the a an and or but is are was were be been being to of in on at by for
    with from as that this these those it its you your i we they he she him her
    my our their not no have has had will would can could should shall may
    might what which who whom how when where why if all just about out up down
    so get got like more most now new here there then than them some any only
    also very much many do does did done make made use used""".split()
)

# 라틴계 외국어별 기능어. 영어 동철어 제외(위 원칙). 언어 간 공유어(de/que/la
# 등)는 각 언어에 중복 수록 — 최댓값 언어 하나만 고르므로 합산 인플레이션 없음.
_LATIN_LANG_FUNCTION_WORDS: dict[str, frozenset[str]] = {
    "es": frozenset(
        """el la los las un una unos unas que qué de del en es son está están
        estaba para por con sin se su sus lo le les más pero como cómo este
        esta esto ese esa eso aquí ahora muy todo toda todos todas nada hay ya
        también porque cuando donde sobre entre hasta desde te tu tus mi mis
        yo él ella ellos nosotros ustedes vosotros tenéis hacer hace tiene
        tienen puede puedes pueden quiero quieres si sí cada otro otra cosa
        cosas semana gratis nuevo nueva esto""".split()
    ),
    "pt": frozenset(
        """não nao você voce vocês uma um uns umas que de da das dos em na nas
        é são sao está estão esta para pra por com sem se seu sua seus suas
        mais mas como isso isto esse essa muito tudo todo já também tambem
        porque quando onde sobre entre até desde ele ela eles elas fazer faz
        tem têm pode podem foi ser está cada outro outra coisa coisas
        semana""".split()
    ),
    "fr": frozenset(
        """le les la des de du une et est sont dans pour par avec sans sur
        sous ce cette ces qui que quoi pas ne très tres vous nous je il elle
        ils elles mon ma mes ton ta tes sa ses mais comme aussi bien être etre
        avoir fait faire tout tous toute toutes votre notre vos nos cela ça
        voici voilà chaque chose semaine gratuit""".split()
    ),
    "de": frozenset(
        """der die das und nicht mit ist sind ein eine einen einem einer für
        auf aus dem den von zu im ich du er sie wir ihr es auch noch schon
        aber oder wenn wie wird werden kann können koennen haben sein sehr
        mehr diese dieser dieses beim durch über ueber gegen nur bei jetzt
        heute woche kostenlos""".split()
    ),
    "it": frozenset(
        """il lo la gli le un uno una che di da su tra fra è sono non più piu
        questo questa questi queste quello quella anche molto tutto tutti
        della delle dello degli nel nella sul sulla ho hai io tu lui lei noi
        voi loro mio mia fare può puo essere ci si se perché quando dove ogni
        cosa cose settimana gratis adesso""".split()
    ),
}

# 언어 특유 문자 신호(케이스폴드 후 카운트). 1자 = 기능어 1히트로 합산.
#   ¿ ¡ ñ → 스페인어 / ã õ → 포르투갈어 / ç → 포르투갈어·프랑스어 / ß ü → 독일어
_LATIN_LANG_CHAR_SIGNALS: dict[str, str] = {
    "es": "¿¡ñ",
    "pt": "ãõç",
    "fr": "ç",
    "de": "ßü",
}

# 비영어 분류 최소 기능어 히트 수. 미만이면 판단 보류=영어 취급(precision 우선).
# 3이면 영어 글의 외국어 차용구("de facto", "c'est la vie" 1~2회)는 안 걸린다.
_LATIN_FOREIGN_MIN_HITS = 3

# 라틴 단어 토큰(악센트 라틴 확장 포함). 아포스트로피는 분리("c'est"→"c","est").
_LATIN_WORD_RE = re.compile(r"[a-zà-öø-ÿāăēĕīĭōŏūŭ]+")


# ─────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _engagement_int(record: dict, key: str) -> int:
    """engagement[key]를 안전하게 int로. 없거나 비정상이면 0.

    engagement dict가 아예 없으면 최상위 키로 폴백한다 — 구버전 X 평탄 덤프
    (likes가 top-level 키) 호환. 폴백 없으면 실제 likes>0인 레코드가 0으로
    뭉개져 zero-engagement 판정이 오탐된다(precision 우선).
    """
    eng = record.get("engagement")
    if not isinstance(eng, dict):
        eng = record
    val = eng.get(key, 0)
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def _script_counts(text: str) -> tuple[int, int, int]:
    """텍스트의 (라틴, 한글, 지원외 외국 스크립트) 글자 수를 센다.

    이모지·숫자·구두점·수학기호(트위터의 𝗕𝗼𝗹𝗱 스타일 문자 등)는 어느 쪽에도
    세지 않는다 — 외국 스크립트로 오인해 거부하지 않기 위함(precision 우선).
    """
    latin = hangul = foreign = 0
    for ch in text:
        cp = ord(ch)
        if ("a" <= ch <= "z") or ("A" <= ch <= "Z") or (0x00C0 <= cp <= 0x024F):
            latin += 1
        elif any(lo <= cp <= hi for lo, hi in _HANGUL_RANGES):
            hangul += 1
        elif any(lo <= cp <= hi for lo, hi in _FOREIGN_SCRIPT_RANGES):
            foreign += 1
    return latin, hangul, foreign


def _is_foreign_script_dominant(text: str) -> bool:
    """지원 외 스크립트가 명백히 우세한지. 혼합/애매하면 False(통과)."""
    latin, hangul, foreign = _script_counts(text)
    if foreign < _FOREIGN_SCRIPT_MIN_CHARS:
        return False  # 표본 부족 — 판단 보류
    return foreign > latin + hangul


def guess_language_by_script(text: str) -> str | None:
    """스크립트 분포로 언어를 추정한다: 한글 우세→"ko", 라틴 우세→"en", 불명→None.

    업스트림 language 필드가 'und'로 깨지는 X 경로의 폴백용(x_crawler에서 재사용).
    한국어 기술 글은 라틴 용어(LLM, RAG 등)가 많이 섞이므로 한글을 먼저 본다.
    """
    latin, hangul, foreign = _script_counts(text)
    if hangul >= 10 and hangul >= foreign:
        return "ko"
    if latin >= 10 and latin > foreign:
        return "en"
    return None


def _refine_latin_language(text: str) -> str:
    """라틴 우세 텍스트를 기능어 빈도로 세분한다: "en" 또는 es/pt/fr/de/it.

    precision 우선 — 비영어 판정은 (히트 >= _LATIN_FOREIGN_MIN_HITS) AND
    (> 영어 기능어 히트)일 때만. 애매/짧음 → "en"(통과 방향).
    """
    folded = text.casefold()
    tokens = _LATIN_WORD_RE.findall(folded)
    en_hits = sum(1 for t in tokens if t in _EN_FUNCTION_WORDS)

    best_lang, best_hits = "en", 0
    for lang, words in _LATIN_LANG_FUNCTION_WORDS.items():
        hits = sum(1 for t in tokens if t in words)
        hits += sum(folded.count(ch) for ch in _LATIN_LANG_CHAR_SIGNALS.get(lang, ""))
        if hits > best_hits:
            best_lang, best_hits = lang, hits

    if best_hits >= _LATIN_FOREIGN_MIN_HITS and best_hits > en_hits:
        return best_lang
    return "en"


def detect_language(text: str) -> str | None:
    """스크립트 1차(guess_language_by_script) + 라틴이면 기능어 2차 세분.

    반환: "ko" / "en" / "es"·"pt"·"fr"·"de"·"it"(라틴계 비영어) / None(판별 불가).
    x_crawler의 language 폴백과 QC 게이트 언어 검사가 공유한다(HIVE-50).
    """
    base = guess_language_by_script(text)
    if base == "en":
        return _refine_latin_language(text)
    return base


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
        7. x 본문 < 100자                    → "too_short"
        8. x 외국 스크립트 우세 또는           → "language_not_supported"
           라틴계 비영어(es/pt/fr/de/it) 명백    (혼합/애매 시 통과 — precision 우선)
        9. x 짧은 편(<200자) AND 반응 전무    → "zero_engagement_short"
        10. 배치 내 중복 URL                 → "duplicate_url"
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

        # 7~9. x 전용 검사 (user 경로 제외) — HIVE-50.
        #      X는 업스트림 메타데이터를 신뢰할 수 없다(language='und' 다수,
        #      likes는 DB 실측 62/64건이 0으로 깨짐). 본문 텍스트 휴리스틱 중심으로 거른다.
        if not is_user and source == "x":
            body_len = len(body.strip())
            # 7. 최소 길이 — 실측(덤프 327건): <100자 = 23건(7.0%)만 컷. 중앙값 260.
            if body_len < X_MIN_BODY_CHARS:
                _reject(source, "too_short")
                continue
            # 8. 언어 — record["language"]는 불신('und' 다수). 2단계 판정:
            #    (a) 외국 스크립트(가나·한자·키릴 등) 명백 우세 → 거부.
            #    (b) 라틴 우세면 기능어 2차 세분 — es/pt/fr/de/it 명백 신호만
            #        거부, 영어·한국어·애매는 통과(precision 우선).
            #    실측: 덤프 327건(전부 영어) 컷 0 / trending 215건 스페인어 9건 컷.
            lang_text = f"{title}\n{body}"
            if _is_foreign_script_dominant(lang_text) or detect_language(
                lang_text
            ) in _LATIN_LANG_FUNCTION_WORDS:
                _reject(source, "language_not_supported")
                continue
            # 9. 짧은 편(<200자) AND 반응 전무(likes·comments 0)일 때만 컷 —
            #    실측 16/327(4.9%). likes 단독 거부는 업스트림 깨짐 때문에 하지 않는다.
            if (
                body_len < X_ZERO_ENGAGEMENT_MAX_CHARS
                and _engagement_int(record, "likes") == 0
                and _engagement_int(record, "comments") == 0
                and _engagement_int(record, "retweets") == 0
            ):
                _reject(source, "zero_engagement_short")
                continue

        # 10. 배치 내 중복 URL (빈 URL은 중복 판정에서 제외 — precision 우선)
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
