"""Dev-Hive Streamlit 진입점.

좌측 사이드바에 현재 프로필 정보와 페이지 목록을 표시한다.
프로필이 없으면 임시 입력 받아 POST /auth/profile로 생성한다.
"""

import streamlit as st

from lib.api import create_profile, get_profile

st.set_page_config(page_title="Dev-Hive", layout="wide", page_icon=":bee:")

st.title("Dev-Hive")
st.caption("커뮤니티의 경험이 곧 다른 사람의 학습이 되는 플랫폼")

# 사이드바: 프로필 표시 또는 생성
with st.sidebar:
    st.header("내 프로필")
    if "user_id" not in st.session_state:
        st.info("프로필을 먼저 생성해주세요.")
        name = st.text_input("이름", key="signup_name")
        persona = st.selectbox("직군", ["개발자", "마케터", "기획자"], index=0)
        if st.button("프로필 생성", type="primary"):
            if not name.strip():
                st.warning("이름을 입력해주세요.")
            else:
                profile = create_profile(name.strip(), persona)
                if profile:
                    st.session_state["user_id"] = profile["user_id"]
                    st.session_state["display_name"] = profile["display_name"]
                    st.session_state["persona"] = profile["persona"]
                    st.rerun()
    else:
        profile = get_profile(st.session_state["user_id"])
        if profile:
            st.success(f"{profile['display_name']} ({profile['persona']})")
            if st.button("프로필 재설정"):
                for k in ["user_id", "display_name", "persona"]:
                    st.session_state.pop(k, None)
                st.rerun()

# 메인 영역
if "user_id" not in st.session_state:
    st.info("← 좌측에서 프로필을 먼저 생성한 뒤 페이지를 이용해주세요.")
else:
    st.markdown(
        "좌측 사이드바의 **피드 / 커리큘럼 / 프로필** 페이지를 이용해주세요."
    )
