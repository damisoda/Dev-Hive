"""Dev-Hive Streamlit 진입점.

좌측 사이드바에 현재 프로필 정보와 페이지 목록을 표시한다.
프로필이 없으면 메인 영역에서 온보딩(이름 + 직군 선택 + 직군별 문항)을 진행하고,
POST /auth/profile로 프로필을 생성하면서 초기 레벨을 설정한다.
"""

import streamlit as st
from lib.ui import style

from lib.api import create_profile, get_profile

st.set_page_config(page_title="Dev-Hive", layout="wide", page_icon=":bee:")
style()

# 페르소나별 온보딩 문항 (HIVE-36). 직군마다 문항 세트가 다르다.
# 현재 개발자만. 직군 추가 시 이 딕셔너리에 키만 추가하면 된다 (백엔드 레벨 로직 공통).
# options: (보기 라벨, 점수). 점수 키·배점은 backend PERSONA_ONBOARDING과 일치한다.
PERSONA_QUESTIONS = {
    "개발자": [
        # ── 개발 baseline (일반 개발 역량) ──
        {
            "key": "dev_career",
            "label": "개발 경력이 얼마나 되나요?",
            "options": [("1년 미만", 0), ("1~3년", 1), ("3~7년", 2), ("7년 이상", 3)],
        },
        {
            "key": "prod_experience",
            "label": "실서비스(프로덕션) 개발에 참여해본 경험이 있나요?",
            "options": [("없음·학습용만", 0), ("일부 참여한다", 1), ("주도적으로 개발·운영한다", 2)],
        },
        # ── AI 숙련도 ──
        {
            "key": "ai_tool_usage",
            "label": "AI 코딩 도구(Cursor, Claude Code, Copilot 등)를 얼마나 써봤나요?",
            "options": [("거의 안 써봤다", 0), ("가끔 쓴다", 1), ("매일 쓴다", 2)],
        },
        {
            "key": "llm_understanding",
            "label": "LLM·프롬프트 엔지니어링을 얼마나 이해하고 있나요?",
            "options": [("개념만 안다", 0), ("직접 써본다", 1), ("워크플로에 녹여 쓴다", 2)],
        },
        {
            "key": "advanced_topics",
            "label": "RAG·Agent 같은 심화 주제를 다뤄본 적 있나요?",
            "options": [("없다", 0), ("조금 안다", 1), ("직접 구현해봤다", 2)],
        },
    ],
}
# 직군 선택지. 현재 개발자만 노출, 직군 추가 시 여기에 더한다.
PERSONA_OPTIONS = ["개발자"]

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

    # 직군 선택 (현재 개발자만, 향후 직군별 문항 분기)
    persona = st.radio("직군을 선택하세요", PERSONA_OPTIONS, index=0, key="onboarding_persona")

    answers = {}
    for q in PERSONA_QUESTIONS[persona]:
        labels = [opt[0] for opt in q["options"]]
        choice = st.radio(q["label"], labels, index=0, key=f"onboarding_{q['key']}")
        answers[q["key"]] = dict(q["options"])[choice]

    if st.button("시작하기", type="primary"):
        if not name.strip():
            st.warning("이름을 입력해주세요.")
        else:
            profile = create_profile(name.strip(), persona, answers)
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
