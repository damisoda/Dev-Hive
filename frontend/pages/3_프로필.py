"""프로필 - 본인 정보 표시. 읽은 이력은 Layer 2에서 별도 엔드포인트 추가."""

import streamlit as st

from lib.api import get_profile

st.set_page_config(page_title="프로필 · Dev-Hive", layout="wide")
st.title("프로필")

if "user_id" not in st.session_state:
    st.warning("프로필을 먼저 생성해주세요 (메인 페이지).")
    st.stop()

profile = get_profile(st.session_state["user_id"])
if profile:
    cols = st.columns(2)
    with cols[0]:
        st.metric("이름", profile.get("display_name", "-"))
        st.metric("직군", profile.get("persona", "-"))
    with cols[1]:
        st.metric("현재 단계", profile.get("current_level", "입문") if "current_level" in profile else "입문")
        st.metric("영향력 점수", profile.get("influence_score", 0) if "influence_score" in profile else 0)

st.divider()
st.subheader("읽은 콘텐츠 이력")
st.info("이력 조회 엔드포인트는 Layer 2(6/7~)에서 추가 예정입니다.")
