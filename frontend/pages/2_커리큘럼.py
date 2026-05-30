"""개인화 커리큘럼 - 추천 엔진이 선정한 다음 콘텐츠."""

import streamlit as st

from lib.api import recommend, mark_read

st.set_page_config(page_title="커리큘럼 · Dev-Hive", layout="wide")
st.title("내 커리큘럼")
st.caption("당신에게 맞는 다음 콘텐츠 5건")

if "user_id" not in st.session_state:
    st.warning("프로필을 먼저 생성해주세요 (메인 페이지).")
    st.stop()

top_n = st.slider("추천 개수", 3, 10, 5)
data = recommend(st.session_state["user_id"], top_n=top_n)

if not data or not data.get("recommendations"):
    st.info(
        "아직 추천할 콘텐츠가 충분하지 않습니다. "
        "피드에서 몇 개를 읽으면 추천이 시작됩니다."
    )
else:
    for i, rec in enumerate(data["recommendations"], 1):
        with st.container(border=True):
            cols = st.columns([1, 9])
            with cols[0]:
                st.markdown(f"# {i}")
            with cols[1]:
                st.markdown(f"### {rec['title']}")
                if rec.get("score") is not None:
                    st.caption(f"점수 {rec['score']:.2f}")
                if rec.get("reason"):
                    st.markdown(f"> {rec['reason']}")
                else:
                    st.caption("추천 근거는 Layer 2(GraphRAG)에서 자연어로 생성됩니다.")
                if st.button("읽음 처리", key=f"recread_{rec['content_id']}"):
                    if mark_read(st.session_state["user_id"], rec["content_id"]):
                        st.toast("읽음 처리됨. 다음 추천을 갱신합니다.")
                        st.rerun()
