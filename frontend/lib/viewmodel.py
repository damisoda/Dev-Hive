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


def source_label(source: str) -> str:
    """source 내부 값을 표시 라벨로. 미등록 값은 그대로."""
    return SOURCE_LABELS.get(source, source)


def mastery_label(m: float) -> str:
    """mastery(0~1) → 단계 라벨."""
    return "미학습" if m < 0.3 else ("학습중" if m < 0.7 else "숙련")


def content_badges(item: dict) -> list[dict]:
    """/content 아이템 → 배지 목록 [{'text', 'code'}]. code=True면 코드 칩 스타일."""
    badges = []
    if item.get("source"):
        badges.append({"text": source_label(item["source"]), "code": True})
    if item.get("author_name"):
        badges.append({"text": item["author_name"], "code": False})
    if item.get("difficulty"):
        badges.append({"text": item["difficulty"], "code": True})
    if item.get("content_type"):
        badges.append({"text": item["content_type"], "code": True})
    if item.get("quality_score") is not None:
        badges.append({"text": f"품질 {item['quality_score']:.2f}", "code": False})
    return badges


def curriculum_rows(topics: list[dict], mastery: dict) -> list[dict]:
    """학습 경로 행 [{'name','m','label'}] — 약한 개념부터 정렬.

    Auto-HKG 하위노드(auto=True)는 제외 — 대주제만(잡음 방지).
    mastery 키는 노드 id 문자열(예: 'topic:3'의 '3').
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
        rows.append({"name": n.get("label") or "?", "m": m, "label": mastery_label(m)})
    rows.sort(key=lambda r: r["m"])   # 약한 개념 먼저
    return rows


def recommendation_view(rec: dict) -> dict:
    """/recommend 아이템 → 추천 카드 표시 필드 정리.

    summary는 추천 확정 시 백그라운드 lazy 가공(HIVE-49) — 첫 로드엔 None일 수 있어
    summary_pending으로 '준비 중' 상태를 구분한다.
    """
    badges = []
    if rec.get("difficulty"):
        badges.append({"text": rec["difficulty"], "code": True})
    if rec.get("content_type"):
        badges.append({"text": rec["content_type"], "code": True})
    return {
        "content_id": rec["content_id"],
        "title": rec["title"],
        "url": rec.get("url"),                       # 없으면 비활성 링크('#') 렌더
        "summary": rec.get("summary"),
        "summary_pending": not rec.get("summary"),   # lazy 가공 미완 → '준비 중' 안내
        "badges": badges,
        "reason": rec.get("reason"),                 # GraphRAG 근거 = 차별점, 강조
        "score": rec.get("score"),
    }
