"""개인화 커리큘럼 - 학습 경로(mastery 진척) + 다음 추천(GraphRAG).

A. 내 학습 경로: 노드별 mastery를 약한 것부터(다음에 배울 것) 진척 막대로.
B. 다음에 읽을 추천: GraphRAG 추천 + 자연어 근거(reason) 강조.
"""
import streamlit as st
from lib.ui import style

from lib.api import get_graph, get_mastery, list_feedback, recommend
from lib.components import recommendation_card

st.set_page_config(page_title="커리큘럼 · Dev-Hive", layout="wide")
style()
st.title("내 커리큘럼")
st.caption("내 숙련도 기반 학습 경로와, 다음에 읽을 개인화 추천")

if "user_id" not in st.session_state:
    st.warning("프로필을 먼저 생성해주세요 (메인 페이지).")
    st.stop()

uid = st.session_state["user_id"]


@st.cache_data(ttl=300, show_spinner=False)
def _topic_nodes():
    # 노드 이름 조회용(무거운 /graph는 캐싱). mastery는 매번 신선하게 따로 조회.
    return [n for n in (get_graph() or {}).get("nodes", []) if n.get("kind") == "topic"]


def _mastery_label(m: float) -> str:
    return "미학습" if m < 0.3 else ("학습중" if m < 0.7 else "숙련")


# ── A. 내 학습 경로 ───────────────────────────────────────────────
st.subheader("내 학습 경로")
st.caption("약한 개념이 위 — 다음에 배우면 좋아요")
mastery = get_mastery(uid) or {}
topics = _topic_nodes()
if not topics:
    st.caption("그래프가 비어 있어 경로를 표시할 수 없습니다.")
else:
    rows = []
    for n in topics:
        if n.get("auto"):
            continue   # Auto-HKG 하위노드는 학습 경로에서 제외 — 대주제 7개만(잡음 방지)
        try:
            nid = int(str(n["id"]).split(":")[1])
        except (IndexError, ValueError):
            continue
        rows.append({
            "name": n.get("label") or "?",
            "m": float(mastery.get(str(nid), 0.0)),
        })
    rows.sort(key=lambda r: r["m"])   # 약한 개념 먼저
    for r in rows:
        st.progress(r["m"], text=f"{r['name']} · {_mastery_label(r['m'])} {r['m']:.0%}")

st.divider()

# ── B. 다음에 읽을 추천 ───────────────────────────────────────────
st.subheader("다음에 읽을 추천")
top_n = st.slider("추천 개수", 3, 10, 5)
data = recommend(uid, top_n=top_n)
if not data or not data.get("recommendations"):
    st.info("아직 추천이 충분하지 않습니다. 피드에서 몇 개를 읽으면 추천이 시작됩니다.")
    st.page_link("pages/1_피드.py", label="피드에서 콘텐츠 둘러보기 →")
else:
    feedback_map = list_feedback(uid)   # 추천 카드에 피드백 버튼(HIVE-49) — want_more/too_hard가 추천에 반영
    for i, rec in enumerate(data["recommendations"], 1):
        recommendation_card(rec, uid, i, feedback_map=feedback_map)
