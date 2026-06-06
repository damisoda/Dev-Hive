"""profile_vector 생성 및 갱신 서비스.

HIVE-30: 온보딩 답변 + 읽음 이력으로 user.profile_vector(1536) 생성.
OpenAI API 불필요 — content.text_embedding(이미 DB에 적재)을 평균내는 방식.

흐름:
1. 온보딩 시: 답변 기반으로 관심 curriculum_node 파악 → 해당 노드에 연결된
   콘텐츠들의 text_embedding 평균 → profile_vector 초기값 설정
2. 읽음 이벤트 시: 해당 유저가 읽은 전체 콘텐츠의 text_embedding 평균 →
   profile_vector 갱신
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

# 온보딩 문항 키 → 관심 curriculum_node 이름 매핑
# onboarding_answers 예시: {"ai_tool_usage": 2, "llm_understanding": 1, "advanced_topics": 0}
# 점수 합산이 아니라, 각 문항 점수가 1 이상이면 해당 토픽 노드를 관심사로 간주.
_QUESTION_TO_NODES: dict[str, list[str]] = {
    "ai_tool_usage": ["AI 워크플로우 & 자동화", "프롬프트 엔지니어링"],
    "llm_understanding": ["AI 엔지니어링", "RAG & 지식 관리"],
    "advanced_topics": ["Agentic AI", "멀티모달 AI", "오픈소스 AI"],
}


def build_initial_vector(user_id: int, onboarding_answers: dict, db: Session) -> None:
    """온보딩 답변 기반으로 profile_vector 초기값을 설정한다.

    관심 노드에 연결된 콘텐츠들의 text_embedding 평균을 profile_vector로 저장.
    해당 노드 콘텐츠에 text_embedding이 없으면 아무 것도 하지 않는다(NULL 유지).
    """
    # 관심 노드 이름 수집 (답변 점수 1 이상인 문항)
    interested_node_names: list[str] = []
    for question_key, node_names in _QUESTION_TO_NODES.items():
        score = int(onboarding_answers.get(question_key, 0))
        if score >= 1:
            interested_node_names.extend(node_names)

    if not interested_node_names:
        # 모든 문항 0점이면 전체 콘텐츠 평균으로 폴백
        interested_node_names = [
            name
            for names in _QUESTION_TO_NODES.values()
            for name in names
        ]

    # 관심 노드에 연결된 콘텐츠들의 text_embedding 평균 계산
    placeholders = ", ".join(f":n{i}" for i in range(len(interested_node_names)))
    params = {f"n{i}": name for i, name in enumerate(interested_node_names)}
    params["uid"] = user_id

    result = db.execute(
        text(
            f"""
            UPDATE users
            SET profile_vector = (
                SELECT AVG(c.text_embedding)
                FROM content c
                JOIN content_node_mapping cnm ON cnm.content_id = c.id
                JOIN curriculum_nodes cn ON cn.id = cnm.node_id
                WHERE cn.name IN ({placeholders})
                  AND c.text_embedding IS NOT NULL
            )
            WHERE id = :uid
              AND (
                  SELECT COUNT(*) FROM content c
                  JOIN content_node_mapping cnm ON cnm.content_id = c.id
                  JOIN curriculum_nodes cn ON cn.id = cnm.node_id
                  WHERE cn.name IN ({placeholders})
                    AND c.text_embedding IS NOT NULL
              ) > 0
            """
        ),
        params,
    )
    db.commit()


def update_from_read_history(user_id: int, db: Session) -> None:
    """읽음 이력 기반으로 profile_vector를 갱신한다.

    해당 유저가 읽은 전체 콘텐츠의 text_embedding 평균을 profile_vector로 업데이트.
    읽은 콘텐츠 중 text_embedding이 있는 것이 하나도 없으면 아무 것도 하지 않는다.
    """
    db.execute(
        text(
            """
            UPDATE users
            SET profile_vector = (
                SELECT AVG(c.text_embedding)
                FROM content c
                JOIN user_read_events ure ON ure.content_id = c.id
                WHERE ure.user_id = :uid
                  AND c.text_embedding IS NOT NULL
            )
            WHERE id = :uid
              AND (
                  SELECT COUNT(*)
                  FROM content c
                  JOIN user_read_events ure ON ure.content_id = c.id
                  WHERE ure.user_id = :uid
                    AND c.text_embedding IS NOT NULL
              ) > 0
            """
        ),
        {"uid": user_id},
    )
    db.commit()
