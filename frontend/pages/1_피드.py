"""콘텐츠 피드 - 필터 + 페이지네이션으로 전체 콘텐츠 탐색.

개인화 추천은 ‘커리큘럼’ 페이지. 여기는 ‘둘러보기’.
"""
import math

import streamlit as st

from lib.api import list_content
from lib.components import content_card

st.set_page_config(page_title="피드 · Dev-Hive", layout="wide")
st.title("피드")
st.caption("전체 콘텐츠를 출처·난이도로 탐색하세요. (개인화 추천은 ‘커리큘럼’)")

if "user_id" not in st.session_state:
    st.warning("프로필을 먼저 생성해주세요 (메인 페이지).")
    st.stop()

SOURCES = ["전체", "reddit", "hn", "github_trending", "huggingface", "velog", "tistory", "user"]
DIFFICULTIES = ["전체", "입문", "중급", "고급"]

col1, col2, col3 = st.columns(3)
with col1:
    src = st.selectbox("출처", SOURCES)
with col2:
    diff = st.selectbox("난이도", DIFFICULTIES)
with col3:
    page_size = st.selectbox("표시 개수", [10, 20, 50], index=1)

# 필터가 바뀌면 페이지를 1로 리셋(안 하면 빈 페이지로 점프)
filter_key = (src, diff, page_size)
if st.session_state.get("feed_filter") != filter_key:
    st.session_state["feed_filter"] = filter_key
    st.session_state["feed_page"] = 1

page = st.session_state.get("feed_page", 1)
filters = {"limit": page_size, "offset": (page - 1) * page_size}
if src != "전체":
    filters["source"] = src
if diff != "전체":
    filters["difficulty"] = diff

data = list_content(**filters)
if not data or not data.get("items"):
    st.info("표시할 콘텐츠가 없습니다. 필터를 완화해보세요.")
    st.stop()

total = data.get("total", 0)
pages = max(1, math.ceil(total / page_size))
st.caption(f"총 {total}건 · {page}/{pages} 페이지")

for item in data["items"]:
    content_card(item, st.session_state["user_id"], key_prefix="feed")

nav = st.columns([1, 2, 1])
with nav[0]:
    if st.button("← 이전", disabled=page <= 1, use_container_width=True):
        st.session_state["feed_page"] = page - 1
        st.rerun()
with nav[1]:
    st.markdown(f"<div style='text-align:center'>{page} / {pages}</div>", unsafe_allow_html=True)
with nav[2]:
    if st.button("다음 →", disabled=page >= pages, use_container_width=True):
        st.session_state["feed_page"] = page + 1
        st.rerun()
