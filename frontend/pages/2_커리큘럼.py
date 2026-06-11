"""개인화 커리큘럼 - 학습 경로(mastery 진척) + 다음 추천(GraphRAG).

A. 내 학습 경로: 노드별 mastery를 약한 것부터(다음에 배울 것) 진척 막대로.
B. 다음에 읽을 추천: GraphRAG 추천 + 자연어 근거(reason) 강조.
"""
import streamlit as st
from lib.ui import call, style

from lib.api import get_graph, get_mastery, list_feedback, recommend
from lib.components import recommendation_card
from lib.viewmodel import curriculum_rows

st.set_page_config(page_title="커리큘럼 · Dev-Hive", layout="wide")
style()
st.title("내 커리큘럼")
st.caption("내 숙련도 기반 학습 경로와, 다음에 읽을 개인화 추천")

if "user_id" not in st.session_state:
    st.warning("프로필을 먼저 생성하세요 (메인 페이지).")
    st.stop()

uid = st.session_state["user_id"]


@st.cache_data(ttl=300, show_spinner=False)
def _topic_nodes():
    # 노드 이름 조회용(무거운 /graph는 캐싱). mastery는 매번 신선하게 따로 조회.
    # 실패(ApiError)는 캐싱되지 않고 호출부의 call()까지 전파된다.
    return [n for n in get_graph().get("nodes", []) if n.get("kind") == "topic"]


# ── A. 내 학습 경로 ───────────────────────────────────────────────
st.subheader("내 학습 경로")
st.caption("약한 개념이 위 — 다음에 배우면 좋아요")
topics = call(_topic_nodes, retry_key="curri_graph")
if topics is None:        # 연결 실패/오류 — call이 안내와 '다시 시도'를 이미 렌더
    st.stop()
mastery = get_mastery(uid) or {}
if not topics:
    st.caption("그래프가 비어 있어 경로를 표시할 수 없습니다.")
else:
    for r in curriculum_rows(topics, mastery):   # 약한 개념 먼저 (viewmodel)
        st.progress(r["m"], text=f"{r['name']} · {r['label']} {r['m']:.0%}")

st.divider()

# ── B. 다음에 읽을 추천 ───────────────────────────────────────────
st.subheader("다음에 읽을 추천")
top_n = st.slider("추천 개수", 3, 10, 5)

# GraphRAG 추천은 LLM 경유라 수 초 걸린다(실측 ~12s). 읽음/피드백 클릭의 rerun마다
# 재계산하면 버튼 하나가 십수 초가 되므로, 결과를 세션에 고정하고 '추천 새로고침'
# 버튼으로만 다시 계산한다 — 피드백·읽음 반영과 'AI 요약 준비 중' 채움도 이 시점에.
_rec_key = f"recs_{uid}_{top_n}"
btn_col, hint_col = st.columns([1, 4])
with btn_col:
    if st.button("추천 새로고침", use_container_width=True):
        st.session_state.pop(_rec_key, None)
with hint_col:
    st.caption("읽음·피드백을 반영해 다시 추천받으려면 새로고침하세요.")

if _rec_key not in st.session_state:
    with st.spinner("개인화 추천을 계산하고 있어요… (몇 초 걸립니다)"):
        data = call(recommend, uid, top_n=top_n, retry_key="curri_rec")
    if data is None:
        st.stop()
    st.session_state[_rec_key] = data
data = st.session_state[_rec_key]
if not data.get("recommendations"):
    # 빈 상태: 온보딩/읽음 데이터가 부족하면 추천이 비어 있을 수 있다 — 피드로 유도
    st.info("아직 추천할 데이터가 부족합니다. 피드에서 콘텐츠를 몇 개 읽고 다시 방문하세요.")
    st.page_link("pages/1_피드.py", label="피드에서 콘텐츠 둘러보기 →")
else:
    feedback_map = list_feedback(uid)   # 추천 카드에 피드백 버튼(HIVE-49) — want_more/too_hard가 추천에 반영
    for i, rec in enumerate(data["recommendations"], 1):
        recommendation_card(rec, uid, i, feedback_map=feedback_map)
