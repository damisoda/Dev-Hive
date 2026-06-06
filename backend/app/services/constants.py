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
