"""LLM Knowledge Tracing 서비스.

HIVE-23: 유저 읽음 이력 + 자가평가를 자연어 user_state 텍스트로 직렬화.
HIVE-22(GraphRAG) 추천 시 프롬프트 컨텍스트로 소비된다.

출력 예시:
    현재 레벨: 중급
    관심 분야: AI 워크플로우 & 자동화, 프롬프트 엔지니어링
    읽음 이력:
      - 프롬프트 엔지니어링: 3건 완료
      - RAG & 지식 관리: 1건 완료
      - Agentic AI: 미학습
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.constants import QUESTION_TO_NODES


def build_user_state(user_id: int, db: Session) -> str:
    """유저 상태를 자연어 텍스트로 직렬화하여 반환한다.

    HIVE-22(GraphRAG)에서 LLM 프롬프트 컨텍스트로 주입하기 위해 사용한다.
    유저가 존재하지 않으면 빈 문자열을 반환한다.
    """
    # 유저 기본 정보 조회
    user_row = db.execute(
        text(
            "SELECT current_level, onboarding_answers FROM users WHERE id = :uid"
        ),
        {"uid": user_id},
    ).fetchone()

    if user_row is None:
        return ""

    current_level = user_row.current_level or "입문"
    onboarding_answers: dict = user_row.onboarding_answers or {}

    # 관심 분야 추출 (온보딩 점수 1 이상인 문항의 노드, 중복 제거 후 순서 유지)
    interested_nodes: list[str] = []
    seen: set[str] = set()
    for question_key, node_names in QUESTION_TO_NODES.items():
        score = int(onboarding_answers.get(question_key) or 0)  # null 방어
        if score >= 1:
            for node_name in node_names:
                if node_name not in seen:
                    interested_nodes.append(node_name)
                    seen.add(node_name)

    # 노드별 읽음 건수 조회 (중복 읽음 이벤트 방지: DISTINCT content_id)
    # Note: parent_id IS NULL → 대주제 7개만 집계. 하위 노드 추가 시 쿼리 수정 필요.
    node_read_counts = db.execute(
        text(
            """
            SELECT cn.name, COUNT(DISTINCT ure.content_id) AS read_count
            FROM curriculum_nodes cn
            LEFT JOIN content_node_mapping cnm ON cnm.node_id = cn.id
            LEFT JOIN user_read_events ure
                ON ure.content_id = cnm.content_id AND ure.user_id = :uid
            WHERE cn.parent_id IS NULL
            GROUP BY cn.id, cn.name
            ORDER BY cn.id
            """
        ),
        {"uid": user_id},
    ).fetchall()

    # user_state 텍스트 조립
    lines: list[str] = []
    lines.append(f"현재 레벨: {current_level}")

    if interested_nodes:
        lines.append(f"관심 분야: {', '.join(interested_nodes)}")
    else:
        lines.append("관심 분야: 없음")

    if node_read_counts:
        lines.append("읽음 이력:")
        for row in node_read_counts:
            if row.read_count > 0:
                lines.append(f"  - {row.name}: {row.read_count}건 완료")
            else:
                lines.append(f"  - {row.name}: 미학습")
    else:
        lines.append("읽음 이력: 없음")

    return "\n".join(lines)
