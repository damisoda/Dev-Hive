"""지식그래프 - Obsidian 스타일 force-directed 시각화.

백엔드 /graph를 받아 pyvis(vis.js)로 인터랙티브 그래프를 그린다.
- topic 노드(대주제 + Auto-HKG 하위노드): 색으로 구분, 크게. Auto-HKG 생성 노드는 금색 강조.
- content 노드: 작게(소속 주제 색 옅게, 호버 시 제목). similar_to 엣지는 기본 off(1200여 개라 빽빽) — 토글.
"""
import html

import streamlit as st
from lib.ui import call, header, style
import streamlit.components.v1 as components

from lib.api import get_graph
from lib.graph_viz import AUTO_COLOR, PALETTE, build_network

st.set_page_config(page_title="지식그래프 · Dev-Hive", layout="wide")
style()
header()
st.title("지식그래프")
st.caption("커뮤니티 콘텐츠가 대주제로 뭉치고, Auto-HKG가 새 하위노드를 키운다. 노드를 드래그·줌·호버해 보세요.")
st.page_link("pages/5_업로드.py", label="이 그래프에 내 글 더하기 →")


# /graph는 similar_to를 매번 pgvector로 재계산해 느리다 → 캐싱.
# (similar_to 토글은 클라이언트 필터라 데이터 재호출이 필요 없다)
# 실패(ApiError)는 캐싱되지 않고 호출부의 call()까지 전파된다.
@st.cache_data(ttl=300, show_spinner="그래프 불러오는 중…")
def _load_graph():
    return get_graph()


# 사이드바 없음(상단 네비) — 컨트롤은 본문 툴바 행으로
_tb_refresh, _tb_similar, _tb_stats = st.columns([1.1, 2.2, 3.7])
with _tb_refresh:
    if st.button("그래프 새로고침", help="Auto-HKG 실행 후 등 최신 그래프 다시 받기",
                 use_container_width=True):
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

data = call(_load_graph)
if data is None:          # 연결 실패/오류 — call이 안내와 '다시 시도'를 이미 렌더
    st.stop()

if not data.get("nodes"):
    # 빈 상태: 아직 그래프에 노드가 없다 — 첫 글 업로드로 유도
    st.info("아직 그래프에 노드가 없습니다. 첫 글을 올려 지식그래프를 시작하세요.")
    st.page_link("pages/5_업로드.py", label="글 올리러 가기 →")
    st.stop()

stats = data.get("stats", {})
with _tb_similar:
    show_similar = st.checkbox("similar_to 엣지 표시 (빽빽함)", value=False)
with _tb_stats:
    st.caption(
        f"노드 topic {stats.get('topics', 0)} · content {stats.get('content', 0)}  |  "
        f"엣지 belongs_to {stats.get('belongs_to', 0)} · "
        f"similar_to {stats.get('similar_to', 0)} · precedes {stats.get('precedes', 0)}"
    )

# 범례 — 대주제 7개 색 chip + 금색 Auto. 색 배정은 graph_viz와 동일(topic 순서 → PALETTE).
_roots = [n for n in data["nodes"] if n.get("kind") == "topic" and not n.get("auto")]
_legend = [
    f"<span class='dh-legend-chip'><span class='dot' style='background:{PALETTE[i % len(PALETTE)]}'>"
    f"</span>{html.escape(n.get('label') or '?')}</span>"
    for i, n in enumerate(_roots)
] + [
    f"<span class='dh-legend-chip'><span class='dot' style='background:{AUTO_COLOR}'></span>"
    "Auto-HKG 하위주제</span>"
]
st.markdown(f"<div class='dh-legend'>{''.join(_legend)}</div>", unsafe_allow_html=True)


# 레이아웃(spring) 계산이 무거워 HTML을 캐싱 — 데이터/토글이 바뀔 때만 1회 계산, rerun엔 즉시.
@st.cache_data(ttl=300, show_spinner="그래프 그리는 중…")
def _render_graph_html(nodes, edges, show_similar):
    return build_network(nodes, edges, show_similar).generate_html(notebook=False)


# 다크 viz를 라운드 카드 프레임으로 감싼다 (iframe 모서리는 ui.py CSS에서 라운드 처리)
with st.container(border=True):
    components.html(
        _render_graph_html(data["nodes"], data["edges"], show_similar),
        height=780, scrolling=False,
    )
