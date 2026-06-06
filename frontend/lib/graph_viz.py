"""지식그래프 pyvis 네트워크 빌더 (Obsidian 스타일 force-directed).

스트림릿 비의존 — 페이지(pages/4_그래프.py)와 렌더 검증 스크립트가 공용으로 쓴다.
대주제 7개를 원형(ring)에 고정 배치해 전체가 둥근 만다라 형태가 되게 하고,
콘텐츠는 소속 주제 주변에 물리로 뭉쳐 꽃잎(petal) 클러스터를 만든다.
대주제는 색상별 + 글로우, 콘텐츠는 같은 색조로 선명하게, Auto-HKG 노드는 금색 강조.
"""
import json
import math

from pyvis.network import Network

# 대주제별 색 팔레트 (어두운 배경에서 구분, 금색과 겹치지 않게). 토픽 순서대로 배정.
_PALETTE = ["#7c9cff", "#ff9c6b", "#6bd47e", "#e87cc4", "#b29cff", "#5fc8e8", "#ff6b6b"]
AUTO_COLOR = "#ffd166"        # Auto-HKG 생성 노드 강조 (금색)
_EDGE_COLOR = {
    "belongs_to": "rgba(150,165,215,0.17)",   # 옅게 → 색 클러스터가 주인공, 중앙 엉킴↓
    "similar_to": "rgba(120,120,150,0.09)",
    "precedes": "#ff8c69",
}
_RING_R = 470                 # 대주제 원형 배치 반지름(vis.js 좌표계)

# vis.js 옵션: 토픽은 ring에 고정, 콘텐츠만 물리. 약한 중심중력 + 곡선 엣지 + 줌아웃 라벨 표시.
_OPTIONS = {
    "nodes": {
        "scaling": {"label": {"drawThreshold": 2}},
        "font": {"face": "Pretendard, Apple SD Gothic Neo, sans-serif"},
        "shadow": {"enabled": True, "color": "rgba(0,0,0,0.45)", "size": 14, "x": 0, "y": 2},
    },
    "edges": {"smooth": {"enabled": True, "type": "continuous"}},
    "physics": {
        "solver": "barnesHut",
        "barnesHut": {
            "gravitationalConstant": -2800,
            "centralGravity": 0.035,       # 낮게 → ring 구조 지배(중앙 쏠림 방지, 꽃잎 바깥으로)
            "springLength": 80,            # 짧게 → 콘텐츠가 허브에 바짝(꽃잎 조여 둥글게)
            "springConstant": 0.095,       # 콘텐츠를 소속 주제에 단단히 붙임(꽃잎)
            "avoidOverlap": 0.22,
        },
        "minVelocity": 0.75,
        "stabilization": {"iterations": 800},
    },
    "interaction": {"hover": True, "hideEdgesOnDrag": True, "tooltipDelay": 120},
}


def _content_color(hex_color: str) -> str:
    """콘텐츠는 소속 주제와 같은 색조를 살짝 어둡게(허브보다 덜 튀게, 색조는 선명히 유지)."""
    h = hex_color.lstrip("#")
    rgb = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(int(c * 0.78) for c in rgb)


def build_network(nodes, edges, show_similar: bool = False) -> Network:
    """/graph 응답(nodes/edges)을 둥근 만다라형 force-directed pyvis Network로."""
    net = Network(height="780px", width="100%", bgcolor="#16161a",
                  font_color="#e8e8ee", directed=False, cdn_resources="remote")
    net.set_options(json.dumps(_OPTIONS))

    # 대주제: 색 배정 + 원형 좌표(맨 위 12시부터 시계방향) 고정 배치
    topics = [n for n in nodes if n["kind"] == "topic"]
    topic_color, ring_pos = {}, {}
    for i, n in enumerate(topics):
        topic_color[n["id"]] = AUTO_COLOR if n.get("auto") else _PALETTE[i % len(_PALETTE)]
        ang = 2 * math.pi * i / max(len(topics), 1) - math.pi / 2
        ring_pos[n["id"]] = (_RING_R * math.cos(ang), _RING_R * math.sin(ang))

    # 콘텐츠 → 소속 토픽(belongs_to 첫 번째) → 색 상속
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
            x, y = ring_pos[nid]
            net.add_node(
                nid, label=n["label"], shape="dot",
                size=48 if n.get("auto") else 42,   # 콘텐츠(9)와 급 차이 크게(P1)
                x=x, y=y, physics=False, fixed=True,        # ring에 고정 → 전체가 둥글게
                color={"background": col, "border": col},
                shadow={"enabled": True, "color": col, "size": 26, "x": 0, "y": 0},  # 동색 글로우
                title=("[Auto-HKG] " if n.get("auto") else "") + n["label"],
                font={"size": 26, "color": "#ffffff", "strokeWidth": 6, "strokeColor": "#101014",
                      "bold": True},
            )
            added.add(nid)
        elif nid in linked:   # 콘텐츠는 엣지 있는 것만(고립 제외) + 소속 주제 색
            # label=" "(공백): 빈 문자열을 주면 vis.js가 노드 id를 라벨로 폴백하므로 공백으로 억제.
            base = topic_color.get(content_topic.get(nid), "#6b7290")
            net.add_node(nid, label=" ", title=n.get("label", ""),
                         size=9, shape="dot", color=_content_color(base))
            added.add(nid)

    for e in shown_edges:
        if e["source"] in added and e["target"] in added:   # 양 끝 노드 있을 때만(가드)
            net.add_edge(e["source"], e["target"],
                         color=_EDGE_COLOR.get(e["rel"], "#444"),
                         width=2 if e["rel"] == "precedes" else 1)
    return net
