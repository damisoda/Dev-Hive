"""profile_vector 생성 및 갱신 서비스.

HIVE-30: 온보딩 답변 + 읽음 이력으로 user.profile_vector(1536) 생성.
OpenAI API 불필요 — content.text_embedding(이미 DB에 적재)을 평균내는 방식.

설계 (9번 — 온보딩 + 읽음 동적 혼합):
- 온보딩 점수 0인 노드는 완전 제외 (폴백 없음)
- 온보딩 점수 1 → 1배 가중, 점수 2 → 2배 가중 (Python에서 계산)
- 읽음 이력이 쌓일수록 온보딩 비중 줄고 읽음 비중 늘어남:
    읽음 0건  → 온보딩 100%
    읽음 5건  → 온보딩 50% + 읽음 50%
    읽음 20건+ → 온보딩 10% + 읽음 90%
- all-zero(0,0,0): 온보딩 벡터 NULL 유지 → quality_score 폴백
- all-high(2,2,2): 전체 노드지만 점수 2배 가중으로 계산 → all-zero와 구분됨

Note: pgvector는 vector * numeric 연산 미지원 → 가중 평균을 Python에서 계산 후 DB에 저장.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

# 온보딩 문항 키 → 관심 curriculum_node 이름 매핑
_QUESTION_TO_NODES: dict[str, list[str]] = {
    "ai_tool_usage": ["AI 워크플로우 & 자동화", "프롬프트 엔지니어링"],
    "llm_understanding": ["AI 엔지니어링", "RAG & 지식 관리"],
    "advanced_topics": ["Agentic AI", "멀티모달 AI", "오픈소스 AI"],
}

_ONBOARDING_WEIGHT_MAX = 1.0
_ONBOARDING_WEIGHT_MIN = 0.1
_READ_COUNT_SCALE = 20


def _calc_onboarding_weight(read_count: int) -> float:
    """읽음 건수에 따라 온보딩 가중치를 동적으로 계산한다 (선형 감소).

    읽음 0건 → 1.0, 읽음 20건+ → 0.1
    """
    ratio = min(read_count / _READ_COUNT_SCALE, 1.0)
    return _ONBOARDING_WEIGHT_MAX - ratio * (_ONBOARDING_WEIGHT_MAX - _ONBOARDING_WEIGHT_MIN)


def _compute_onboarding_vector(
    onboarding_answers: dict, db: Session
) -> list[float] | None:
    """온보딩 답변 기반 가중 평균 벡터를 Python에서 계산하여 반환한다.

    점수 0인 노드 제외, 점수 1 → 1배, 점수 2 → 2배 가중.
    관심 노드가 없거나 임베딩 데이터가 없으면 None 반환.
    """
    # 노드별 가중치 수집
    node_weights: dict[str, int] = {}
    for question_key, node_names in _QUESTION_TO_NODES.items():
        score = int(onboarding_answers.get(question_key, 0))
        if score >= 1:
            for node_name in node_names:
                node_weights[node_name] = score

    if not node_weights:
        return None

    # 노드별 평균 임베딩 조회
    placeholders = ", ".join(f":n{i}" for i, _ in enumerate(node_weights))
    params = {f"n{i}": name for i, name in enumerate(node_weights)}

    rows = db.execute(
        text(
            f"""
            SELECT cn.name, AVG(c.text_embedding) AS avg_vec
            FROM content c
            JOIN content_node_mapping cnm ON cnm.content_id = c.id
            JOIN curriculum_nodes cn ON cn.id = cnm.node_id
            WHERE cn.name IN ({placeholders})
              AND c.text_embedding IS NOT NULL
            GROUP BY cn.name
            """
        ),
        params,
    ).fetchall()

    if not rows:
        return None

    # Python에서 가중 평균 계산
    weighted_sum: list[float] = []
    total_weight = 0.0

    for row in rows:
        weight = float(node_weights.get(row.name, 1))
        raw = row.avg_vec
        if isinstance(raw, str):
            vec = [float(v) for v in raw.strip("[]").split(",")]
        else:
            vec = [float(v) for v in raw]
        if not weighted_sum:
            weighted_sum = [0.0] * len(vec)
        for j in range(len(vec)):
            weighted_sum[j] += vec[j] * weight
        total_weight += weight

    if total_weight == 0:
        return None

    return [v / total_weight for v in weighted_sum]


def _save_vector(user_id: int, vec: list[float], db: Session) -> None:
    """계산된 벡터를 DB의 profile_vector에 저장한다."""
    vec_str = "[" + ",".join(str(v) for v in vec) + "]"
    db.execute(
        text("UPDATE users SET profile_vector = (:vec)::vector WHERE id = :uid"),
        {"vec": vec_str, "uid": user_id},
    )
    db.commit()


def build_initial_vector(user_id: int, onboarding_answers: dict, db: Session) -> None:
    """온보딩 답변 기반으로 profile_vector 초기값을 설정한다.

    읽음 이력 0건 → 온보딩 100%.
    all-zero(0,0,0)이면 NULL 유지 → rule_based.py의 quality_score 폴백으로 처리.
    """
    vec = _compute_onboarding_vector(onboarding_answers, db)
    if vec is not None:
        _save_vector(user_id, vec, db)


def update_from_read_history(user_id: int, db: Session) -> None:
    """읽음 이력 기반으로 profile_vector를 동적 혼합 방식으로 갱신한다.

    읽음 건수에 따라 온보딩 비중을 줄이고 읽음 이력 비중을 늘린다.
    """
    # 유저 온보딩 답변 + 읽음 건수 조회
    user_row = db.execute(
        text(
            """
            SELECT u.onboarding_answers,
                   COUNT(ure.id) AS read_count
            FROM users u
            LEFT JOIN user_read_events ure ON ure.user_id = u.id
            WHERE u.id = :uid
            GROUP BY u.id, u.onboarding_answers
            """
        ),
        {"uid": user_id},
    ).fetchone()

    if user_row is None:
        return

    onboarding_answers: dict = user_row.onboarding_answers or {}
    read_count: int = user_row.read_count or 0

    # 읽음 평균 벡터 조회
    read_row = db.execute(
        text(
            """
            SELECT AVG(c.text_embedding) AS avg_vec, COUNT(*) AS cnt
            FROM content c
            JOIN user_read_events ure ON ure.content_id = c.id
            WHERE ure.user_id = :uid
              AND c.text_embedding IS NOT NULL
            """
        ),
        {"uid": user_id},
    ).fetchone()

    has_read_vec = read_row is not None and read_row.cnt > 0
    if has_read_vec:
        raw = read_row.avg_vec
        if isinstance(raw, str):
            raw = raw.strip("[]")
            read_vec = [float(v) for v in raw.split(",")]
        else:
            read_vec = [float(v) for v in raw]
    else:
        read_vec = None

    # 온보딩 벡터 계산
    onboarding_vec = _compute_onboarding_vector(onboarding_answers, db)

    if onboarding_vec is None and read_vec is None:
        return

    if onboarding_vec is None:
        # all-zero + 읽음 있음 → 읽음 벡터만 사용
        _save_vector(user_id, read_vec, db)
        return

    if read_vec is None:
        # 읽음 없음 → 온보딩 벡터만 사용
        _save_vector(user_id, onboarding_vec, db)
        return

    # 동적 혼합: 읽음 건수에 따라 가중치 조정
    w_onboarding = _calc_onboarding_weight(read_count)
    w_read = 1.0 - w_onboarding

    dim = len(onboarding_vec)
    mixed = [
        onboarding_vec[j] * w_onboarding + read_vec[j] * w_read
        for j in range(dim)
    ]
    _save_vector(user_id, mixed, db)
