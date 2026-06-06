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

from app.services.constants import (
    DEFAULT_GAIN,
    DEFAULT_INITIAL_MASTERY,
    DIFFICULTY_TO_GAIN,
    ONBOARDING_SCORE_TO_MASTERY,
    QUESTION_TO_NODES,
)


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
    # Note: parent_id IS NULL → 대주제 7개만 집계 (사람이 읽는 설명용이라 대주제 단위로 충분).
    #       estimate_mastery는 전체 노드를 보므로 노드 범위가 다름 — 의도된 차이.
    #       하위 노드 추가 시 이 텍스트에도 포함할지는 그때 재검토.
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


def estimate_mastery(user_id: int, db: Session) -> dict[int, float]:
    """노드별 mastery(숙련도)를 0~1 숫자로 추정하여 반환한다 (BKT-lite).

    HIVE-22(GraphRAG)의 난이도 성분(0.4) 정렬에 사용된다. 약한 개념(낮은 mastery)에는
    선행 콘텐츠를, 강한 개념(높은 mastery)에는 후행/심화 콘텐츠를 정렬하기 위한 숫자 입력.

    읽음 수 자체는 mastery가 아니므로(많이 읽었다고 이해한 건 아님), 읽음 이벤트를
    BKT 학습전이(p ← p + (1-p)·gain)로 누적해 수렴시킨다. 콘텐츠 난이도가 높을수록 gain ↑.

    반환: {node_id: mastery(0.0~1.0)} — 전체 curriculum_nodes 포함.
          유저가 존재하지 않으면 빈 dict.

    Note:
    - relevance_score는 의도적으로 미반영. HIVE-22 랭킹의 관련성 성분(0.3)과 이중계산 방지.
    - 하위노드(parent_id 존재)는 온보딩 신호가 없어 DEFAULT_INITIAL_MASTERY로 시작.
      읽음 이력이 해당 노드에 매핑되면 자동으로 갱신됨(전체 노드 순회 설계).
    """
    # 유저 존재 확인 + 온보딩 답변 조회
    user_row = db.execute(
        text("SELECT onboarding_answers FROM users WHERE id = :uid"),
        {"uid": user_id},
    ).fetchone()
    if user_row is None:
        return {}

    onboarding_answers: dict = user_row.onboarding_answers or {}

    # 전체 노드 로드 (id ↔ name). 하위노드 확장 자동 대응.
    node_rows = db.execute(
        text("SELECT id, name FROM curriculum_nodes")
    ).fetchall()
    name_to_id = {r.name: r.id for r in node_rows}

    # 1) 초기 mastery: 모든 노드 기본값 → 온보딩 신호 있는 노드는 점수 기반값으로 덮어씀
    mastery: dict[int, float] = {r.id: DEFAULT_INITIAL_MASTERY for r in node_rows}
    for question_key, node_names in QUESTION_TO_NODES.items():
        score = int(onboarding_answers.get(question_key) or 0)  # null 방어
        init_val = ONBOARDING_SCORE_TO_MASTERY.get(score, DEFAULT_INITIAL_MASTERY)
        for node_name in node_names:
            node_id = name_to_id.get(node_name)
            if node_id is not None:
                mastery[node_id] = init_val

    # 2) 읽음 이벤트 BKT 업데이트 (시간순, 콘텐츠 중복 제거)
    #    (node_id, content) 단위로 묶고 first_read 순으로 정렬해 한 콘텐츠는 노드당 1회만 반영.
    #    Note: relevance_score는 보지 않으므로 매핑 강도(약/강)와 무관하게 동일 gain 적용.
    #          loader가 relevance >= 0.5인 노드만 매핑한다는 전제(약한 매핑은 애초에 없음)에 의존.
    read_rows = db.execute(
        text(
            """
            SELECT cnm.node_id, c.difficulty, MIN(ure.read_at) AS first_read
            FROM user_read_events ure
            JOIN content c ON c.id = ure.content_id
            JOIN content_node_mapping cnm ON cnm.content_id = c.id
            WHERE ure.user_id = :uid
            GROUP BY cnm.node_id, c.id, c.difficulty
            ORDER BY first_read
            """
        ),
        {"uid": user_id},
    ).fetchall()

    for row in read_rows:
        if row.node_id not in mastery:
            # content_node_mapping이 가리키는 노드가 curriculum_nodes에 없으면 스킵(방어)
            continue
        gain = DIFFICULTY_TO_GAIN.get(row.difficulty, DEFAULT_GAIN)
        p = mastery[row.node_id]
        mastery[row.node_id] = p + (1.0 - p) * gain

    # 부동소수 정리
    return {nid: round(val, 4) for nid, val in mastery.items()}
