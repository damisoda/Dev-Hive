"""콘텐츠 피드 - 필터 + 페이지네이션으로 전체 콘텐츠 탐색.

개인화 추천은 ‘커리큘럼’ 페이지. 여기는 ‘둘러보기’.
"""
import math

import streamlit as st
from lib.ui import call, header, style

from lib.api import list_content, list_feedback
from lib.components import content_card
from lib.viewmodel import source_badge

st.set_page_config(page_title="피드 · Dev-Hive", layout="wide")
style()
header()
st.title("피드")
st.caption("전체 콘텐츠를 출처·난이도로 탐색하세요. (개인화 추천은 ‘커리큘럼’)")

if "user_id" not in st.session_state:
    st.warning("프로필을 먼저 생성하세요 (메인 페이지).")
    st.stop()

SOURCES = ["전체", "reddit", "hn", "github_trending", "huggingface", "velog", "tistory", "user"]
DIFFICULTIES = ["전체", "입문", "중급", "고급"]

# 필터 툴바 — 가로 한 줄 카드
with st.container(border=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        # 값은 원본(source) 그대로, 표시만 이모지+라벨(viewmodel.source_badge)
        src = st.selectbox("출처", SOURCES, key="feed_src",
                           format_func=lambda s: s if s == "전체" else source_badge(s))
    with col2:
        diff = st.selectbox("난이도", DIFFICULTIES, key="feed_diff")
    with col3:
        page_size = st.selectbox("표시 개수", [10, 20, 50], index=1, key="feed_size")

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

data = call(list_content, **filters)
if data is None:          # 연결 실패/오류 — call이 안내와 '다시 시도'를 이미 렌더
    st.stop()

if not data.get("items"):
    # 빈 상태: 필터 조건 결과 0건 — 초기화 안내
    st.info("조건에 맞는 콘텐츠가 없습니다. 필터를 완화하거나 초기화해보세요.")
    if st.button("필터 초기화"):
        for k in ("feed_src", "feed_diff", "feed_size", "feed_filter", "feed_page"):
            st.session_state.pop(k, None)
        st.rerun()
    st.stop()

total = data.get("total", 0)
pages = max(1, math.ceil(total / page_size))
st.caption(f"총 {total}건 · {page}/{pages} 페이지")

feedback_map = list_feedback(st.session_state["user_id"])
for item in data["items"]:
    content_card(item, st.session_state["user_id"], key_prefix="feed", feedback_map=feedback_map)

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
