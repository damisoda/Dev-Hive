"""지식그래프 - Obsidian 스타일 force-directed 시각화.

백엔드 /graph를 받아 pyvis(vis.js)로 인터랙티브 그래프를 그린다.
- topic 노드(대주제 + Auto-HKG 하위노드): 색으로 구분, 크게. Auto-HKG 생성 노드는 금색 강조.
- content 노드: 작게(소속 주제 색 옅게, 호버 시 제목). similar_to 엣지는 기본 off(1200여 개라 빽빽) — 토글.
"""
import streamlit as st
import streamlit.components.v1 as components

from lib.api import get_graph
from lib.graph_viz import build_network

st.set_page_config(page_title="지식그래프 · Dev-Hive", layout="wide")
st.title("지식그래프")
st.caption("커뮤니티 콘텐츠가 대주제로 뭉치고, Auto-HKG가 새 하위노드를 키운다. 노드를 드래그·줌·호버해 보세요.")
st.page_link("pages/5_업로드.py", label="이 그래프에 내 글 더하기 →")


# /graph는 similar_to를 매번 pgvector로 재계산해 느리다 → 캐싱.
# (similar_to 토글은 클라이언트 필터라 데이터 재호출이 필요 없다)
@st.cache_data(ttl=300, show_spinner="그래프 불러오는 중…")
def _load_graph():
    return get_graph()


if st.sidebar.button("새로고침", help="Auto-HKG 실행 후 등 최신 그래프 다시 받기"):
    st.cache_data.clear()
    st.rerun()

# 업로드 직후 진입(5_업로드에서 핸드오프): 캐시를 비워 방금 글의 노드를 즉시 반영 + 배너
_uploaded = st.session_state.pop("just_uploaded", None)
if _uploaded:
    st.cache_data.clear()
    if _uploaded.get("is_new_node"):
        st.success(f"방금 올린 글로 새 주제 '{_uploaded.get('node_name')}'가 생겼어요 — 금색 노드를 찾아보세요.")
    else:
        st.success(f"방금 올린 글이 '{_uploaded.get('node_name')}'에 편입됐어요.")

data = _load_graph()
if not data:
    st.warning("그래프 데이터를 불러오지 못했습니다. 백엔드가 켜져 있는지 확인하세요.")
    st.stop()

stats = data.get("stats", {})
show_similar = st.sidebar.checkbox("similar_to 엣지 표시 (빽빽함)", value=False)
st.sidebar.markdown(
    f"**노드** · topic {stats.get('topics', 0)} / content {stats.get('content', 0)}\n\n"
    f"**엣지** · belongs_to {stats.get('belongs_to', 0)} / "
    f"similar_to {stats.get('similar_to', 0)} / precedes {stats.get('precedes', 0)}"
)
st.sidebar.markdown(
    "---\n**범례**\n\n"
    "- 큰 색 노드 = 대주제 (색마다 다른 주제)\n"
    "- 작은 점 = 콘텐츠 (소속 주제 색 상속)\n"
    "- 금색 = Auto-HKG가 생성한 하위주제"
)

net = build_network(data["nodes"], data["edges"], show_similar)
components.html(net.generate_html(notebook=False), height=780, scrolling=False)
