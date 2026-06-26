"""
콘텐츠 가공(synthesis) 모듈 — HIVE-41.

태깅이 낸 content_type으로 타입별 분기하여 Haiku를 호출하고,
원문(크롤/유저)을 **사용자 가치 카드**(synthesized_card)로 변환한다.

설계(content_synthesis_model.md) 결정:
- 위치 = 태깅 후·임베딩 전. content_type 5타입(거푸집)이 분기 키.
- 카드 = 공통헤더 {one_liner, key_takeaways[]} + content_type별 바디.
- **raw 금지·환각 금지**: 원문에 없는 사실은 빈 배열/null. diary 서사가 아니라 구체 발견만.
- 임베딩은 원문 고정. 가공본은 별도(synthesis JSONB) 저장 → 표시/GraphRAG 근거 전용.
- graceful: 키 부재·LLM 실패·알 수 없는 content_type → None 반환(적재는 계속).
- HIVE-90: post-hoc grounding 필터 — LLM 출력 후 원문에 근거 없는 배열 항목 제거.

tagger.py와 동일 패턴(클라이언트 주입, JSON 출력, 코드블록 제거 후 json.loads).
"""
import json
import logging
import re

import anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
# 가공 카드 출력 토큰 상한. 한국어/장문 콘텐츠는 토큰이 무거워 1024로는 JSON이 잘려
# (stop_reason=max_tokens) 카드가 통째로 누락된다(실측: velog 1.4만자 → 1474토큰 필요).
# 3072로 헤드룸 확보. 그래도 잘리면 아래에서 경고 로깅한다.
MAX_OUTPUT_TOKENS = 3072

# 공통헤더(전 타입 공통) — 피드 카드에 노출. 펼치면 타입별 바디.
_COMMON_HEADER = (
    "공통 헤더(모든 타입):\n"
    '  "one_liner": 이 글이 주는 핵심 가치를 한 문장으로 (string)\n'
    '  "key_takeaways": 독자가 가져갈 핵심 3~5개 (string 배열)\n'
)

# content_type별 바디 스펙(키 + 의미). 프롬프트에 그대로 주입한다.
# raw 서사가 아니라 "원문에서 추출한 구체 사실"만 담는다.
_BODY_SPECS: dict[str, str] = {
    "experience": (
        "experience 바디(diary 서사는 버리고 구체적 발견만 담는다):\n"
        '  "context": 어떤 상황/문제에서 한 경험인지 (string)\n'
        '  "findings": 실제로 알아낸 구체적 발견 (string 배열)\n'
        '  "pitfalls": 겪은 삽질/함정/실수 (string 배열)\n'
        '  "numbers": 등장한 구체 수치(성능·비용·시간 등). 원문에 수치가 없으면 빈 배열 (string 배열)\n'
        '  "verdict": 결론/한 줄 평가 (string)\n'
    ),
    "tool": (
        "tool 바디:\n"
        '  "what": 이 도구가 무엇인지 (string)\n'
        '  "when_to_use": 언제/어떤 상황에 쓰면 좋은지 (string)\n'
        '  "how": 사용 방법/단계 (string 배열)\n'
        '  "requirements": 필요 환경/전제(설치·계정·의존성 등). 없으면 null (string 또는 null)\n'
        '  "gotchas": 주의할 점/한계 (string 배열)\n'
    ),
    "concept": (
        "concept 바디:\n"
        '  "definition": 개념의 정의 (string)\n'
        '  "mechanism": 작동 원리/메커니즘 (string 배열)\n'
        '  "comparisons": 유사 개념과의 비교(X vs Y). 없으면 빈 배열 (string 배열)\n'
        '  "when_matters": 언제/왜 중요한지 (string)\n'
    ),
    "tutorial": (
        "tutorial 바디:\n"
        '  "goal": 이 튜토리얼로 무엇을 달성하는지 (string)\n'
        '  "steps": 재현 절차를 순서대로 (string 배열)\n'
        '  "result": 따라 하면 얻는 결과물 (string)\n'
        '  "notes": 주의할 점/팁 (string 배열)\n'
    ),
    "discussion": (
        "discussion 바디:\n"
        '  "claim": 글이 내세우는 핵심 주장 (string)\n'
        '  "arguments": 주장을 뒷받침하는 논거 (string 배열)\n'
        '  "counterpoints": 반론/반대 관점 (string 배열)\n'
        '  "conclusion": 토론의 결론/정리 (string)\n'
    ),
}

# 타입별 기대 키(검증/형태 보정용). 헤더 키는 공통.
_HEADER_KEYS = ("one_liner", "key_takeaways")
_BODY_KEYS: dict[str, tuple[str, ...]] = {
    "experience": ("context", "findings", "pitfalls", "numbers", "verdict"),
    "tool": ("what", "when_to_use", "how", "requirements", "gotchas"),
    "concept": ("definition", "mechanism", "comparisons", "when_matters"),
    "tutorial": ("goal", "steps", "result", "notes"),
    "discussion": ("claim", "arguments", "counterpoints", "conclusion"),
}

# 바디 키 중 배열로 강제할 키(나머지는 단일 값).
_ARRAY_BODY_KEYS: dict[str, set[str]] = {
    "experience": {"findings", "pitfalls", "numbers"},
    "tool": {"how", "gotchas"},
    "concept": {"mechanism", "comparisons"},
    "tutorial": {"steps", "notes"},
    "discussion": {"arguments", "counterpoints"},
}


# ── HIVE-90: grounding 필터 ──────────────────────────────────────────────────
# 한글(2자↑) / 영문(3자↑) 의미 토큰 추출 후 스톱워드 제거.
# 완전 일치가 아닌 body 내 부분문자열 검색 → 조사 변형·어미 변화에 강함.

# grounding 전용 불용어. 언어 감지용 qc_gate._EN_FUNCTION_WORDS와 목적이 다르므로 별도 관리.
_KO_STOP = frozenset({
    "이", "가", "은", "는", "을", "를", "의", "에", "에서", "로", "으로",
    "와", "과", "하고", "이나", "이고", "도", "만", "까지", "부터", "한",
    "하다", "있다", "없다", "되다", "이다", "않다", "한다", "됩니다", "있습니다",
    "것", "수", "등", "및", "또한", "또는", "그리고", "하지만", "그러나",
    "따라서", "때문에", "위해", "대해", "통해", "위한", "대한", "통한",
})
_EN_STOP = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "are", "was",
    "were", "been", "being", "have", "has", "had", "not", "but", "its",
    "can", "will", "may", "also", "into", "when", "then", "more",
})
_GROUNDING_THRESHOLD = float(0.25)  # 핵심 토큰 25% 이상 body에 등장해야 근거 있음


def _content_tokens(text: str) -> list[str]:
    # [A-Z]{2,}: AI·ML·DB 등 2자 대문자 약어 포함 (3자 미만 영문은 [a-zA-Z]{3,}에서 탈락)
    words = re.findall(r"[가-힣]{2,}|[A-Z]{2,}|[a-zA-Z]{3,}", text)
    return [w.lower() for w in words if w.lower() not in _KO_STOP and w.lower() not in _EN_STOP]


def _is_grounded(
    statement: str, body_lower: str, body_en_words: set[str] | None = None
) -> bool:
    """statement 핵심 토큰의 _GROUNDING_THRESHOLD 이상이 body에 등장하면 근거 있음.

    한글: 형태소 변화를 고려해 부분 문자열 검색.
    영문: 오탐 방지를 위해 단어 단위(whole-word) 검색.
    body_en_words: 호출자가 미리 계산해 전달하면 재계산을 생략한다(성능).
    """
    toks = _content_tokens(statement)
    if not toks:
        return True
    if body_en_words is None:
        body_en_words = set(re.findall(r"[a-z]+", body_lower))

    def _hit(t: str) -> bool:
        if re.match(r"^[가-힣]+$", t):
            return t in body_lower          # 한글: 부분 문자열
        return t in body_en_words           # 영문: 전체 단어

    matched = sum(1 for t in toks if _hit(t))
    return matched / len(toks) >= _GROUNDING_THRESHOLD


def _apply_grounding(card: dict, body: str) -> dict:
    """card 배열 및 단일값 필드에서 body에 근거 없는 항목을 제거한다(HIVE-90)."""
    body_stripped = (body or "").strip()
    if not body_stripped:
        return card
    body_lower = body_stripped.lower()
    body_en_words = set(re.findall(r"[a-z]+", body_lower))  # 한 번 계산 후 모든 항목에 공유
    content_type = card.get("content_type", "")
    array_keys = _ARRAY_BODY_KEYS.get(content_type, set()) | {"key_takeaways"}

    result = dict(card)
    removed_total = 0

    # 배열 필드: 근거 없는 항목 제거
    for key in array_keys:
        if key not in result or not isinstance(result[key], list):
            continue
        before = result[key]
        result[key] = [
            item for item in before
            if not isinstance(item, str) or _is_grounded(item, body_lower, body_en_words)
        ]
        removed = len(before) - len(result[key])
        if removed:
            removed_total += removed
            logger.debug("grounding 필터: key=%s %d항목 제거", key, removed)

    # 단일값 문자열 필드: 근거 없으면 None으로 설정 (one_liner 포함)
    scalar_keys = (set(_BODY_KEYS.get(content_type, ())) - array_keys) | {"one_liner"}
    for key in scalar_keys:
        val = result.get(key)
        if isinstance(val, str) and not _is_grounded(val, body_lower, body_en_words):
            result[key] = None
            removed_total += 1
            logger.debug("grounding 필터: key=%s 단일값 제거", key)

    if removed_total:
        logger.warning(
            "grounding 필터: 총 %d항목 제거 (content_type=%s) — 원문 미근거 항목",
            removed_total, content_type,
        )
    return result


# ─────────────────────────────────────────────────────────────────────────────

def _build_system_prompt(content_type: str) -> str:
    """content_type에 맞는 가공 시스템 프롬프트를 만든다."""
    body_spec = _BODY_SPECS[content_type]
    return (
        "너는 개발 커뮤니티의 콘텐츠 가공 도우미다. "
        f"아래 원문을 읽고 content_type='{content_type}'에 맞는 **가공 카드**를 JSON으로 만든다.\n\n"
        "목적: 독자에게 원문(raw)을 그대로 주지 않고, 학습 가치만 뽑아 구조화한다.\n\n"
        "절대 규칙:\n"
        "- 각 항목을 작성하기 전에 원문에서 해당 내용이 실제로 등장하는지 먼저 확인한다.\n"
        "- 원문에 있는 내용만 쓴다. 원문에 없는 사실·절차·수치를 지어내지 않는다(환각 금지).\n"
        "- 해당 정보가 원문에 없으면 배열은 빈 배열([]), 단일 값은 null로 둔다.\n"
        "- 원문 문장을 그대로 길게 복붙하지 않는다. 핵심만 간결히 재서술한다.\n"
        "- 모든 텍스트는 한국어로 출력한다.\n\n"
        "출력 JSON 구조:\n"
        f"{_COMMON_HEADER}"
        f"{body_spec}\n"
        "출력 규칙:\n"
        "- JSON 객체만 출력한다. 코드블록/설명 문장을 JSON 밖에 쓰지 않는다.\n"
        "- 위에 명시한 키만 포함한다(공통 헤더 키 + 해당 타입 바디 키)."
    )


def _parse_card(raw_text: str) -> dict:
    """Haiku 응답 텍스트에서 코드블록을 제거하고 JSON으로 파싱한다(tagger와 동일)."""
    raw = re.sub(r"^```json\s*", "", raw_text.strip())
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _coerce_card(parsed: dict, content_type: str) -> dict | None:
    """파싱 결과를 카드 스키마에 맞춰 보정한다.

    - 공통 헤더 키가 둘 다 없으면(완전 헛출력) None.
    - 누락 키는 채운다: 배열 기대 키 → []，단일 키 → None/"".
    - 명세 밖 키는 버린다(프롬프트 일탈 방지).
    """
    if not isinstance(parsed, dict):
        return None
    # 헤더가 통째로 비면 가공 실패로 간주
    if not any(k in parsed for k in _HEADER_KEYS):
        return None

    card: dict = {"content_type": content_type}

    # 공통 헤더
    one_liner = parsed.get("one_liner")
    card["one_liner"] = one_liner if isinstance(one_liner, str) else None
    takeaways = parsed.get("key_takeaways")
    card["key_takeaways"] = [str(t) for t in takeaways] if isinstance(takeaways, list) else []

    # 타입별 바디 — 배열 기대 키는 list로, 그 외는 원값(없으면 None) 유지.
    array_keys = _ARRAY_BODY_KEYS[content_type]
    for key in _BODY_KEYS[content_type]:
        val = parsed.get(key)
        if key in array_keys:
            # 배열 키: str 요소만 유지(dict/list 같은 형식위반 요소는 버림 — 깨진 표시값 방지).
            card[key] = [v for v in val if isinstance(v, str)] if isinstance(val, list) else []
        else:
            # 단일값 키: str만 허용. 형식위반(list/dict/number 등)은 None(환각·형식 계약).
            card[key] = val if isinstance(val, str) else None

    return card


def synthesize(item: dict, tags: dict, client: anthropic.Anthropic) -> dict | None:
    """단일 콘텐츠를 content_type별로 가공해 synthesized_card dict를 반환한다.

    Args:
        item:   원문 dict (title/body 등). title+body를 가공 입력으로 쓴다.
        tags:   tagger 결과 dict. content_type으로 분기한다.
        client: Anthropic 클라이언트(주입).

    Returns:
        synthesized_card dict. 다음 경우엔 None(graceful, 적재는 계속):
        - content_type 키 부재 또는 알 수 없는 타입
        - Haiku 호출/파싱 실패
        - 응답이 카드로 보정 불가(헤더 전무)
    """
    content_type = tags.get("content_type") if isinstance(tags, dict) else None
    if content_type not in _BODY_SPECS:
        return None  # 키 부재 / 알 수 없는 타입 → 가공 생략

    title = item.get("title", "") if isinstance(item, dict) else ""
    body = item.get("body", "") if isinstance(item, dict) else ""
    if not (title or body):
        return None  # 가공할 원문 자체가 없음

    user_msg = json.dumps({"title": title, "body": body}, ensure_ascii=False)

    try:
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=_build_system_prompt(content_type),
            messages=[{"role": "user", "content": user_msg}],
        )
        # 출력이 토큰 상한에 걸리면 JSON이 잘려 파싱 실패→None이 된다.
        # graceful None이 원인을 숨기지 않도록 경고로 가시화한다.
        if getattr(message, "stop_reason", None) == "max_tokens":
            logger.warning(
                "가공 출력이 max_tokens(%s)로 잘림 — content_type=%s title=%s",
                MAX_OUTPUT_TOKENS, content_type, (item.get("title") or "")[:60],
            )
        raw = message.content[0].text
        parsed = _parse_card(raw)
    except Exception:
        # LLM 오류/JSON 파싱 실패/응답 형식 이상 — 모두 graceful None.
        return None

    card = _coerce_card(parsed, content_type)
    if card is None:
        return None
    card = _apply_grounding(card, body)
    all_array_keys = _ARRAY_BODY_KEYS.get(content_type, set()) | {"key_takeaways"}
    if not any(card.get(k) for k in all_array_keys):
        logger.warning(
            "grounding 필터: 배열 항목 전체 제거 — None 반환 (content_type=%s)", content_type
        )
        return None
    return card
