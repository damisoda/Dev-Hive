"""지식그래프 pyvis 네트워크 빌더 (Obsidian 스타일 force-directed).

스트림릿 비의존 — 페이지(pages/4_그래프.py)와 렌더 검증 스크립트가 공용으로 쓴다.
대주제는 색으로 구분, 콘텐츠는 소속 주제 색을 옅게 상속(클러스터가 색으로 읽히게),
Auto-HKG 생성 노드는 금색 강조.
"""
import json

from pyvis.network import Network

# 대주제별 색 팔레트 (어두운 배경에서 구분, 금색과 겹치지 않게). 토픽 순서대로 배정.
_PALETTE = ["#7c9cff", "#ff9c6b", "#5fd3a6", "#e87cc4", "#b29cff", "#5fc8e8", "#ff7c9c"]
AUTO_COLOR = "#ffd166"        # Auto-HKG 생성 노드 강조 (금색)
_EDGE_COLOR = {
    "belongs_to": "rgba(140,160,210,0.16)",
    "similar_to": "rgba(120,120,150,0.09)",
    "precedes": "#ff8c69",
}
_BG = (26, 26, 29)            # #1a1a1d

# vis.js 옵션: 조밀한 force 레이아웃 + 줌아웃돼도 토픽 라벨 보이게(drawThreshold↓) + 드래그 성능.
_OPTIONS = {
    "nodes": {
        "scaling": {"label": {"drawThreshold": 2}},   # 줌아웃 시 라벨 숨김 방지
        "font": {"face": "Pretendard, Apple SD Gothic Neo, sans-serif"},
    },
    "edges": {"smooth": {"type": "continuous"}},
    "physics": {
        "solver": "barnesHut",
        "barnesHut": {
            "gravitationalConstant": -4200,
            "centralGravity": 0.45,        # 적당히 모아 fit 줌이 라벨 읽을 만큼 커지게
            "springLength": 85,
            "springConstant": 0.05,
            "avoidOverlap": 0.18,
        },
        "minVelocity": 0.75,
        "stabilization": {"iterations": 700},
    },
    "interaction": {"hover": True, "hideEdgesOnDrag": True, "tooltipDelay": 120},
}


def _mute(hex_color: str) -> str:
    """주제 색을 배경 쪽으로 끌어당겨 콘텐츠용으로 옅게(틴트 유지)."""
    h = hex_color.lstrip("#")
    rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    out = tuple(int(c * 0.5 + bg * 0.5) for c, bg in zip(rgb, _BG))
    return "#%02x%02x%02x" % out


def build_network(nodes, edges, show_similar: bool = False) -> Network:
    """/graph 응답(nodes/edges)을 Obsidian 스타일 force-directed pyvis Network로."""
    net = Network(height="760px", width="100%", bgcolor="#1a1a1d",
                  font_color="#e0e0e0", directed=False, cdn_resources="remote")
    net.set_options(json.dumps(_OPTIONS))

    # 토픽별 색 배정 + 콘텐츠 소속 토픽(belongs_to 첫 번째) → 색 상속
    topic_color, i = {}, 0
    for n in nodes:
        if n["kind"] == "topic":
            topic_color[n["id"]] = AUTO_COLOR if n.get("auto") else _PALETTE[i % len(_PALETTE)]
            i += 1
    content_topic = {}
    for e in edges:
        if e["rel"] == "belongs_to" and e["source"] not in content_topic:
            content_topic[e["source"]] = e["target"]

    # 표시할 엣지 + 거기 등장하는 노드만. 고립 콘텐츠는 viz에서 제외.
    shown_edges = [e for e in edges if not (e["rel"] == "similar_to" and not show_similar)]
    linked = {ep for e in shown_edges for ep in (e["source"], e["target"])}

    added = set()
    for n in nodes:
        nid = n["id"]
        if n["kind"] == "topic":
            col = topic_color.get(nid, _PALETTE[0])
            net.add_node(
                nid, label=n["label"], shape="dot",
                size=32 if n.get("auto") else 26,
                color={"background": col, "border": col},   # 흰 테두리 제거(자연스러운 글로우)
                title=("[Auto-HKG] " if n.get("auto") else "") + n["label"],
                font={"size": 24, "color": "#ffffff", "strokeWidth": 5, "strokeColor": "#141418"},
            )
            added.add(nid)
        elif nid in linked:   # 콘텐츠는 엣지 있는 것만(고립 제외) + 소속 주제 색 옅게
            # label=" "(공백): 빈 문자열을 주면 vis.js가 노드 id를 라벨로 폴백하므로 공백으로 억제.
            base = topic_color.get(content_topic.get(nid), "#5a6080")
            net.add_node(nid, label=" ", title=n.get("label", ""),
                         size=8, shape="dot", color=_mute(base))
            added.add(nid)

    for e in shown_edges:
        if e["source"] in added and e["target"] in added:   # 양 끝 노드 있을 때만(가드)
            net.add_edge(e["source"], e["target"],
                         color=_EDGE_COLOR.get(e["rel"], "#444"),
                         width=2 if e["rel"] == "precedes" else 1)
    return net
