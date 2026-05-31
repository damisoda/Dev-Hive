"""콘텐츠 피드 - 필터링 가능한 전체 콘텐츠 목록."""

import streamlit as st

from lib.api import list_content, mark_read

st.set_page_config(page_title="피드 · Dev-Hive", layout="wide")
st.title("피드")

if "user_id" not in st.session_state:
    st.warning("프로필을 먼저 생성해주세요 (메인 페이지).")
    st.stop()

SOURCES = ["전체", "reddit", "hn", "github_trending", "huggingface", "velog", "tistory"]
DIFFICULTIES = ["전체", "입문", "중급", "고급"]

col1, col2, col3 = st.columns(3)
with col1:
    src = st.selectbox("출처", SOURCES)
with col2:
    diff = st.selectbox("난이도", DIFFICULTIES)
with col3:
    limit = st.selectbox("표시 개수", [10, 20, 50], index=1)

filters = {"limit": limit}
if src != "전체":
    filters["source"] = src
if diff != "전체":
    filters["difficulty"] = diff

data = list_content(**filters)
if not data or not data.get("items"):
    st.info("표시할 콘텐츠가 없습니다.")
else:
    st.caption(f"총 {data['total']}건 중 {len(data['items'])}건 표시")
    for item in data["items"]:
        with st.container(border=True):
            st.markdown(f"### [{item['title']}]({item.get('url') or '#'})")
            badges = []
            if item.get("source"):
                badges.append(f"`{item['source']}`")
            if item.get("difficulty"):
                badges.append(f"`{item['difficulty']}`")
            if item.get("language"):
                badges.append(f"`{item['language']}`")
            if item.get("quality_score") is not None:
                badges.append(f"품질 {item['quality_score']:.2f}")
            st.markdown(" · ".join(badges))
            if item.get("tags"):
                st.markdown(" ".join(f":blue-background[{t}]" for t in item["tags"]))
            cols = st.columns([1, 1, 4])
            with cols[0]:
                if st.button("읽음 처리", key=f"read_{item['id']}"):
                    if mark_read(st.session_state["user_id"], item["id"]):
                        st.toast("읽음 처리됨")
                        st.rerun()
            with cols[1]:
                if item.get("engagement_likes") is not None:
                    st.caption(
                        f"👍 {item['engagement_likes']} 💬 {item.get('engagement_comments', 0)}"
                    )
