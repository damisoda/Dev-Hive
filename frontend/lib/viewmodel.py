"""표시용 뷰모델 (HIVE-51) — '데이터 → 표시용 구조' 변환만 담당.

스트림릿 비의존(순수 파이썬). 렌더(st.*)는 lib/components.py·pages가 담당한다.
React/Next.js 이행 시 이 파일의 로직이 그대로 살아남는 층.
"""

# 피드백 버튼 (라벨, 내부 키). HIVE-37 — 백엔드 /feedback 타입 4종과 일치.
FEEDBACK_BUTTONS = [
    ("이해했어요", "understood"),
    ("어려워요", "too_hard"),
    ("더 보고 싶어요", "want_more"),
    ("관심없어요", "not_interested"),
]

# source 내부 값 → 표시 라벨 (HIVE-51). 필터 값은 원본 그대로, 표시만 보기 좋게.
SOURCE_LABELS = {
    "reddit": "Reddit",
    "hn": "Hacker News",
    "github_trending": "GitHub Trending",
    "huggingface": "Hugging Face",
    "velog": "Velog",
    "tistory": "Tistory",
    "x": "X (Twitter)",
    "user": "사용자 업로드",
}

# source → 뱃지 이모지 (HIVE-51 리디자인). 미등록 소스는 기본 📄.
SOURCE_EMOJI = {
    "velog": "✍️",
    "tistory": "📝",
    "reddit": "👽",
    "hn": "📰",
    "github_trending": "⭐",
    "huggingface": "🤗",
    "x": "🐦",
    "user": "🐝",
}


def source_label(source: str) -> str:
    """source 내부 값을 표시 라벨로. 미등록 값은 그대로."""
    return SOURCE_LABELS.get(source, source)


def source_badge(source: str) -> str:
    """source → '이모지 라벨' 뱃지 텍스트 (예: '✍️ Velog')."""
    return f"{SOURCE_EMOJI.get(source, '📄')} {source_label(source)}"


# ── 디자인 토큰: 알약(pill) 색 매핑 — 순수 표시 데이터 (렌더는 components가) ──

# 난이도 컬러 시스템: 입문=초록 / 중급=주황 / 고급=빨강
DIFFICULTY_COLORS = {
    "입문": {"fg": "#16a34a", "bg": "#e8f7ee"},
    "중급": {"fg": "#d97706", "bg": "#fdf3e2"},
    "고급": {"fg": "#dc2626", "bg": "#fdecec"},
}
_PILL_NEUTRAL = {"fg": "#5a5e72", "bg": "#eef0f6"}     # 미지정/기타 — 은은한 회색
_PILL_TYPE = {"fg": "#5b5bd6", "bg": "#ececfb"}        # content_type — 은은한 보라
_PILL_SOURCE = {"fg": "#3c3e54", "bg": "#f1f2f8"}      # source — 중립 회색

# content_type 내부 값 → 한글 라벨 + 한 줄 설명 (자가복제 거푸집 5타입)
CONTENT_TYPE_LABELS = {
    "experience": "경험",
    "tutorial": "튜토리얼",
    "concept": "개념",
    "tool": "툴",
    "discussion": "토론",
}
CONTENT_TYPE_DESCRIPTIONS = {
    "experience": "직접 부딪힌 실전 경험과 회고",
    "tutorial": "따라 하며 익히는 단계별 가이드",
    "concept": "원리를 잡아주는 개념 정리",
    "tool": "도구·라이브러리 소개와 사용기",
    "discussion": "관점이 오가는 토론과 의견",
}


def content_type_label(ct: str) -> str:
    """content_type 내부 값 → 한글 라벨. 미등록 값은 그대로."""
    return CONTENT_TYPE_LABELS.get(ct, ct)


def difficulty_pill(difficulty: str) -> dict:
    """난이도 → pill 표시 사양 {'text','fg','bg'}."""
    c = DIFFICULTY_COLORS.get(difficulty, _PILL_NEUTRAL)
    return {"text": difficulty, **c}


def content_pills(item: dict) -> list[dict]:
    """/content 아이템 → pill 목록 [{'text','fg','bg'}] — source/난이도/타입 순."""
    pills = []
    if item.get("source"):
        pills.append({"text": source_badge(item["source"]), **_PILL_SOURCE})
    if item.get("difficulty"):
        pills.append(difficulty_pill(item["difficulty"]))
    if item.get("content_type"):
        pills.append({"text": content_type_label(item["content_type"]), **_PILL_TYPE})
    return pills


def match_percent(score) -> int | None:
    """추천 적합도(0~1) → '매치 87%'용 정수 퍼센트. 없으면 None."""
    if score is None:
        return None
    return max(0, min(100, round(float(score) * 100)))


def mastery_label(m: float) -> str:
    """mastery(0~1) → 단계 라벨."""
    return "미학습" if m < 0.3 else ("학습중" if m < 0.7 else "숙련")


def content_meta(item: dict) -> str:
    """/content 아이템 → 카드 하단 메타 한 줄 (작성자 · 추천/댓글 · 품질)."""
    parts = []
    if item.get("author_name"):
        parts.append(f"by {item['author_name']}")
    if item.get("engagement_likes") is not None:
        parts.append(f"👍 추천 {item['engagement_likes']}")
        parts.append(f"💬 댓글 {item.get('engagement_comments', 0)}")
    if item.get("quality_score") is not None:
        parts.append(f"품질 {item['quality_score']:.2f}")
    return " · ".join(parts)


def curriculum_rows(topics: list[dict], mastery: dict) -> list[dict]:
    """학습 경로 행 [{'name','m','label','next'}] — 약한 개념부터 정렬.

    Auto-HKG 하위노드(auto=True)는 제외 — 대주제만(잡음 방지).
    mastery 키는 노드 id 문자열(예: 'topic:3'의 '3').
    next=True: 가장 약한 토픽(숙련 미만, 최대 2개) — '다음 추천 학습' 강조 뱃지용.
    """
    rows = []
    for n in topics:
        if n.get("auto"):
            continue
        try:
            nid = int(str(n["id"]).split(":")[1])
        except (IndexError, ValueError):
            continue
        m = float(mastery.get(str(nid), 0.0))
        rows.append({"name": n.get("label") or "?", "m": m, "label": mastery_label(m),
                     "next": False})
    rows.sort(key=lambda r: r["m"])   # 약한 개념 먼저
    for r in rows[:2]:                # 약한 순 상위 2개를 '다음 추천 학습'으로 강조
        if r["m"] < 0.7:
            r["next"] = True
    return rows


def recommendation_view(rec: dict) -> dict:
    """/recommend 아이템 → 추천 카드 표시 필드 정리.

    summary는 추천 확정 시 백그라운드 lazy 가공(HIVE-49) — 첫 로드엔 None일 수 있어
    summary_pending으로 '준비 중' 상태를 구분한다.
    """
    pills = []
    if rec.get("difficulty"):
        pills.append(difficulty_pill(rec["difficulty"]))
    if rec.get("content_type"):
        pills.append({"text": content_type_label(rec["content_type"]), **_PILL_TYPE})
    return {
        "content_id": rec["content_id"],
        "title": rec["title"],
        "url": rec.get("url"),                       # 없으면 비활성 링크('#') 렌더
        "summary": rec.get("summary"),
        "summary_pending": not rec.get("summary"),   # lazy 가공 미완 → '준비 중' 안내
        "pills": pills,
        "reason": rec.get("reason"),                 # GraphRAG 근거 = 차별점, 강조
        "score": rec.get("score"),
        "match": match_percent(rec.get("score")),    # '매치 87%' 표기용
    }
