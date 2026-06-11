"""프로필 - 본인 정보 + 학습 현황(user-state 자연어)."""
import streamlit as st
from lib.ui import call, header, style

from lib.api import get_profile, get_stats, get_user_state
from lib.components import render_contribution_heatmap

st.set_page_config(page_title="프로필 · Dev-Hive", layout="wide")
style()
header()
st.title("프로필")

if "user_id" not in st.session_state:
    st.warning("프로필을 먼저 생성하세요 (메인 페이지).")
    st.stop()

uid = st.session_state["user_id"]
profile = call(get_profile, uid)
if profile is None:       # 연결 실패/오류 — call이 안내와 '다시 시도'를 이미 렌더
    st.stop()
stats = get_stats(uid)
inf = stats.get("influence_score", 0) if stats else 0
streak = stats.get("streak", 0) if stats else 0
# 읽은 글 수 = /stats heatmap(최근 1년, {날짜: 읽은 수}) 합 — 별도 지표 발명 없이 API 데이터만
read_total = sum((stats.get("heatmap") or {}).values()) if stats else 0
if profile:
    st.caption(f"{profile.get('display_name', '-')} · {profile.get('persona', '개발자')}")
    cols = st.columns(4)
    stat_cards = [
        ("현재 레벨", profile.get("current_level") or "입문"),
        ("영향력 점수", inf),
        ("읽은 글 (최근 1년)", read_total),
        ("연속 학습", f"{streak}일"),
    ]
    for col, (label, value) in zip(cols, stat_cards):
        with col, st.container(border=True):
            st.metric(label, value)

st.divider()
st.subheader("학습 잔디")
with st.container(border=True):
    if stats and stats.get("heatmap"):
        render_contribution_heatmap(stats["heatmap"])
    else:
        st.caption("콘텐츠를 읽으면 여기에 학습 기록(잔디)이 채워집니다.")

st.divider()
st.subheader("내 학습 현황")
state = get_user_state(uid)
if state and state.get("user_state"):
    # 현재 레벨 · 관심 분야 · 노드별 읽음 이력(자연어). 줄바꿈 보존 위해 text.
    st.text(state["user_state"])
else:
    st.caption("콘텐츠를 읽으면 여기에 레벨·관심 분야·읽음 이력이 표시됩니다.")

st.divider()
st.page_link("pages/2_커리큘럼.py", label="내 커리큘럼으로 →")
