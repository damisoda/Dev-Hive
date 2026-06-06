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
