"""레벨업 판정 (HIVE-36).

읽음 이벤트 직후, 현재 레벨 노드들의 평균 mastery가 임계값을 넘으면 다음 레벨로 승급.
- mastery는 HIVE-23 estimate_mastery 재사용 ("읽음 수"가 아니라 "이해 추정치"로 판정).
- 레벨이 3개(입문/중급/고급)뿐이라 한 칸 점프가 크므로 보수적 임계값 사용
  (너무 빨리 올라가 콘텐츠를 못 따라가는 상황 방지).
- 개발경력(시니어) 속도 보정은 두지 않는다 — 개발경력은 초기 레벨에서 이미 반영했고,
  레벨업까지 빨라지면 이중 혜택 + 과속 위험.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.constants import (
    LEVEL_ORDER,
    LEVEL_UP_ENGAGED_FLOOR,
    LEVEL_UP_THRESHOLD,
)
from app.services.knowledge_tracing import estimate_mastery


def check_and_level_up(user_id: int, db: Session) -> dict | None:
    """현재 레벨 기준 평균 mastery가 임계값 이상이면 한 단계 승급한다.

    승급 시 {"new_level": <레벨>} 반환, 아니면 None.
    고급(최고 레벨)이거나 유저/마스터리 없으면 None.
    """
    row = db.execute(
        text("SELECT current_level FROM users WHERE id = :uid"),
        {"uid": user_id},
    ).fetchone()
    if row is None:
        return None

    current = row.current_level or "입문"
    threshold = LEVEL_UP_THRESHOLD.get(current)
    if threshold is None:
        return None  # 고급 → 더 올릴 레벨 없음

    mastery = estimate_mastery(user_id, db)
    if not mastery:
        return None

    # 대주제(parent_id IS NULL)만 평균낸다.
    # estimate_mastery는 전체 노드를 반환하는데, Auto-HKG(HIVE-21)가 하위 노드를 만들면
    # 온보딩 신호 없는 0.0 노드가 분모에 끼어 평균을 끌어내려 승급이 막힌다 → 대주제로 한정.
    top_node_ids = {
        r.id
        for r in db.execute(
            text("SELECT id FROM curriculum_nodes WHERE parent_id IS NULL")
        ).fetchall()
    }
    # HIVE-95: "읽음으로 학습한" 대주제(mastery > 온보딩 상한)만 평균낸다.
    # 전체 대주제 평균은 일부만 깊게 판 유저(예: read27·mastery 0.895)를 입문에 고착시킨다.
    # 온보딩만 있고 안 읽은 토픽(≤0.2)은 분모에서 제외 → 실제 학습한 영역으로 판정.
    top_masteries = [
        v for nid, v in mastery.items()
        if nid in top_node_ids and v > LEVEL_UP_ENGAGED_FLOOR
    ]
    if not top_masteries:
        return None  # 아직 읽음으로 학습한 대주제 없음 → 승급 보류

    avg_mastery = sum(top_masteries) / len(top_masteries)
    if avg_mastery < threshold:
        return None

    next_level = LEVEL_ORDER[LEVEL_ORDER.index(current) + 1]
    # 조건부 UPDATE: 동시 요청 경쟁 시 한 번만 승급되도록 current_level을 WHERE로 고정
    result = db.execute(
        text(
            "UPDATE users SET current_level = :lv "
            "WHERE id = :uid AND current_level = :cur"
        ),
        {"lv": next_level, "uid": user_id, "cur": current},
    )
    db.commit()
    # 0행이면 경쟁에서 졌거나 이미 다른 요청이 승급시킨 것 → 거짓 성공 응답 방지
    if result.rowcount == 0:
        return None
    return {"new_level": next_level}
