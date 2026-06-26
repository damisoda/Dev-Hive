"""services 패키지 공통 상수.

curriculum_nodes 관련 매핑 등 여러 서비스에서 공유하는 상수를 정의한다.
"""

# 온보딩 문항 키 → 관심 curriculum_node 이름 매핑
# onboarding_answers 예시: {"ai_tool_usage": 2, "llm_understanding": 1, "advanced_topics": 0}
QUESTION_TO_NODES: dict[str, list[str]] = {
    "ai_tool_usage": ["AI 워크플로우 & 자동화", "프롬프트 엔지니어링"],
    "llm_understanding": ["AI 엔지니어링", "RAG & 지식 관리"],
    "advanced_topics": ["Agentic AI", "멀티모달 AI", "오픈소스 AI"],
}

# ── BKT-lite mastery 추정 파라미터 (HIVE-23) ──────────────────────────
# 데이터로 fit한 값이 아니라 휴리스틱 하드코딩. 추후 평가 데이터 확보 시 튜닝 대상.
#
# 온보딩 자가평가 점수 → mastery 초기값.
# 읽음≠이해이고 자가평가는 신뢰도 낮은 신호이므로, 온보딩은 '약한 사전확률'로만 반영한다.
# 범위를 0.0~0.2로 낮게 둬서, 실제 읽음(BKT gain)이 항상 자가평가를 추월할 수 있게 한다.
# (높게 두면 "자가평가만 높고 안 읽은 유저"가 "낮게 평가했지만 실제로 읽은 유저"보다
#  mastery가 높아지는 역전이 발생 → HIVE-22 난이도 정렬이 뒤집힘)
ONBOARDING_SCORE_TO_MASTERY: dict[int, float] = {0: 0.0, 1: 0.1, 2: 0.2}

# 온보딩 신호가 없는 노드(하위노드 등)의 기본 초기 mastery
DEFAULT_INITIAL_MASTERY: float = 0.0

# 콘텐츠 난이도 → 읽음 1건당 mastery 상승폭(gain).
# BKT 학습전이: p ← p + (1-p)·gain 형태로 적용되어 자연 수렴(감쇠 내장).
# 어려운 글을 읽어낼수록 이해 기여가 크다고 가정해 난이도가 높을수록 gain ↑.
DIFFICULTY_TO_GAIN: dict[str, float] = {"입문": 0.10, "중급": 0.15, "고급": 0.20}
DEFAULT_GAIN: float = 0.05  # difficulty NULL/미지정 콘텐츠


# ── 페르소나별 온보딩 구성 (HIVE-36) ──────────────────────────────────
# 직군별 요소(문항 점수키·노드매핑)는 페르소나별, 레벨 계산/레벨업 로직은 공통.
# 현재 개발자만. 직군 추가 시 이 딕셔너리에 키만 추가하면 레벨 로직은 그대로 재사용된다.
#   baseline_keys/ai_keys = {온보딩 답변 키: 해당 문항 만점}
#   - baseline: 일반 직무(개발) 역량  /  ai: AI 도메인 숙련도
# 페르소나별 레벨 산정 파라미터까지 함께 둔다.
# 레벨 경계(ai_beginner_max/ai_mid_max)도 페르소나별 — ai_keys 만점이 직군마다 다를 수 있어
# 전역 매직넘버로 두면 직군 추가 시 compute_initial_level을 또 고쳐야 한다(확장성 깨짐).
#   - ai_beginner_max: ai_score가 이 값 이하면 입문
#   - ai_mid_max     : ai_score가 이 값 이하면 중급, 초과면 고급. 이 값이 "중급 상단"이며
#                      시니어 보정이 발동하는 지점.
#   - senior_baseline_min: baseline_score가 이 값 이상이면 시니어
DEFAULT_PERSONA = "개발자"
PERSONA_ONBOARDING: dict[str, dict] = {
    "개발자": {
        "baseline_keys": {"dev_career": 3, "prod_experience": 2},          # 0~5
        "ai_keys": {"ai_tool_usage": 2, "llm_understanding": 2, "advanced_topics": 2},  # 0~6
        "question_to_nodes": QUESTION_TO_NODES,  # AI 문항 → 관심 노드 (페르소나별)
        "ai_beginner_max": 1,        # ai 0~1 → 입문
        "ai_mid_max": 4,             # ai 2~4 → 중급, 5~6 → 고급 (4=중급 상단=시니어 보정점)
        "senior_baseline_min": 4,    # baseline 5점 만점 중 4 이상이면 시니어
    },
}

# 레벨업 임계값: 현재 레벨에서 평균 mastery가 이 값 이상이면 다음 레벨로 승급.
# 레벨이 3개(입문/중급/고급)뿐이라 한 칸 점프가 크다 → 못 따라가는 위험을 막기 위해
# 보수적으로(현재 레벨 주제를 확실히 익혔을 때만) 둔다. mastery는 HIVE-23 산출물 재사용.
LEVEL_UP_THRESHOLD: dict[str, float] = {"입문": 0.6, "중급": 0.75}
LEVEL_ORDER: list[str] = ["입문", "중급", "고급"]


# ── 피드백 / influence_score (HIVE-37) ────────────────────────────────
# 피드백 종류 (콘텐츠 1건당 유저 1개, 최신값으로 upsert)
FEEDBACK_TYPES = frozenset({"understood", "too_hard", "want_more", "not_interested"})
# 추천에서 제외할 피드백 (현재 상태 기반 — 피드백 취소/변경 시 즉시 복구)
FEEDBACK_EXCLUDE = frozenset({"understood", "not_interested"})

# influence_score = (읽은수 × 난이도가중 + streak × 0.5) × 레벨가중
# 곱셈(가중)이라 활동이 0이면 레벨 높아도 0 (공짜 점수 없음). 정수 반올림 저장.
INFLUENCE_DIFFICULTY_WEIGHT: dict[str, int] = {"입문": 1, "중급": 2, "고급": 3}
INFLUENCE_DEFAULT_DIFFICULTY_WEIGHT: int = 1  # difficulty NULL/미지정
INFLUENCE_STREAK_WEIGHT: float = 0.5
INFLUENCE_LEVEL_MULTIPLIER: dict[str, float] = {"입문": 1.0, "중급": 1.15, "고급": 1.3}

# rule_based 피드백 점수 가중 (휴리스틱, 데이터 fit 아님 — 추후 튜닝 대상)
# want_more 중심과의 유사도 보너스 / too_hard 난이도 감점
FEEDBACK_WANT_MORE_WEIGHT: float = 0.3
FEEDBACK_TOO_HARD_PENALTY: float = 0.2

# ── GraphRAG 피드백 반영 가중 (HIVE-48) ───────────────────────────────
# 휴리스틱(데이터 fit 아님 — 추후 튜닝 대상). graphrag 4성분(W_REL/W_DIFF/W_PATH/W_DIV)은
# 건드리지 않고, want_more와 recency는 별도 보너스 항으로만 더한다.
#   - WANT_MORE_GRAPHRAG_WEIGHT: centered 코사인(0~1) 보너스 스케일.
#   - RECENCY_GRAPHRAG_WEIGHT: 시간 감쇠(0~1) 보너스 스케일. 중급·고급 전용(HIVE-106).
#     두 보너스 합산 최대값(0.15+0.15=0.30)이 W_REL(0.30)과 같으므로 두 신호가
#     동시에 최대일 때 관련성 역전 가능. 각 값을 낮추면 역전 위험 감소.
#   - RECENCY_HALF_LIFE_DAYS: 신선도 반감기(일). 90일마다 점수 절반으로 감쇠. 튜닝 대상.
#   - MASTERY_TOO_HARD_DELTA / MASTERY_UNDERSTOOD_ALPHA: 대표 토픽 mastery를 직접 가감해
#     난이도 성분(W_DIFF)이 쉬운/어려운 쪽으로 정렬되게 한다(전역 감점 대신 토픽별 정교).
FEEDBACK_WANT_MORE_GRAPHRAG_WEIGHT: float = 0.15
RECENCY_GRAPHRAG_WEIGHT: float = 0.15
RECENCY_HALF_LIFE_DAYS: int = 90
MASTERY_TOO_HARD_DELTA: float = 0.2
MASTERY_UNDERSTOOD_ALPHA: float = 0.15
