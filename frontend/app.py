"""Dev-Hive Streamlit 진입점.

좌측 사이드바에 현재 프로필 정보와 페이지 목록을 표시한다.
프로필이 없으면 메인 영역에서 온보딩(이름 + 자가평가 3문항)을 진행하고,
POST /auth/profile로 프로필을 생성하면서 초기 레벨(user_state)을 설정한다.
"""

import streamlit as st

from lib.api import create_profile, get_profile

st.set_page_config(page_title="Dev-Hive", layout="wide", page_icon=":bee:")

# 온보딩 자가평가 3문항. 직군은 Layer 1에서 개발자로 고정한다.
# options: (보기 라벨, 점수). 점수는 backend의 compute_initial_level과 합산 기준이 일치한다.
ONBOARDING_QUESTIONS = [
    {
        "key": "ai_tool_usage",
        "label": "AI 코딩 도구(Cursor, Claude Code, Copilot 등)를 얼마나 써봤나요?",
        "options": [("거의 안 써봤다", 0), ("가끔 쓴다", 1), ("매일 쓴다", 2)],
    },
    {
        "key": "llm_understanding",
        "label": "LLM·프롬프트 엔지니어링을 얼마나 이해하나요?",
        "options": [("개념만 안다", 0), ("직접 써본다", 1), ("워크플로에 녹여 쓴다", 2)],
    },
    {
        "key": "advanced_topics",
        "label": "RAG·Agent 같은 심화 주제를 다뤄본 적 있나요?",
        "options": [("없다", 0), ("조금 안다", 1), ("직접 구현해봤다", 2)],
    },
]

st.title("Dev-Hive")
st.caption("커뮤니티의 경험이 곧 다른 사람의 학습이 되는 플랫폼")

# 사이드바: 프로필 표시 또는 안내
with st.sidebar:
    st.header("내 프로필")
    if "user_id" not in st.session_state:
        st.info("온보딩을 완료해주세요.")
    else:
        profile = get_profile(st.session_state["user_id"])
        if profile:
            st.success(f"{profile['display_name']} ({profile['persona']})")
            st.caption(f"현재 레벨: {profile.get('current_level', '입문')}")
            if st.button("프로필 재설정"):
                for k in ["user_id", "display_name", "persona", "current_level"]:
                    st.session_state.pop(k, None)
                st.rerun()

# 메인 영역
if "user_id" not in st.session_state:
    st.subheader("시작하기 전에")
    st.write("몇 가지 질문으로 학습 출발점을 정합니다. 직군은 개발자로 설정됩니다.")

    name = st.text_input("이름", key="onboarding_name")
    answers = {}
    for q in ONBOARDING_QUESTIONS:
        labels = [opt[0] for opt in q["options"]]
        choice = st.radio(q["label"], labels, index=0, key=f"onboarding_{q['key']}")
        answers[q["key"]] = dict(q["options"])[choice]

    if st.button("시작하기", type="primary"):
        if not name.strip():
            st.warning("이름을 입력해주세요.")
        else:
            profile = create_profile(name.strip(), "개발자", answers)
            if profile:
                st.session_state["user_id"] = profile["user_id"]
                st.session_state["display_name"] = profile["display_name"]
                st.session_state["persona"] = profile["persona"]
                st.session_state["current_level"] = profile.get("current_level", "입문")
                st.rerun()
else:
    st.subheader("온보딩 완료")
    st.write("이제 숙련도에 맞춘 학습 경로와 추천을 볼 수 있어요.")
    st.page_link("pages/2_커리큘럼.py", label="내 커리큘럼 보러가기 →")
    st.caption(
        "좌측 사이드바: **커리큘럼**(추천) · **피드**(탐색) · **그래프**(전체 지도) · "
        "**업로드**(내 글 기여) · **프로필**"
    )
