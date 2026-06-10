"""HIVE-38: 지식 그래프 네트워크 시각화.

사용법: cd backend && python ../scripts/gen_network_viz.py
출력: docs/viz/04_knowledge_graph.png
"""
import os
import sys

# backend를 PYTHONPATH에 추가
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(BASE, "backend")
sys.path.insert(0, BACKEND)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import networkx as nx
import numpy as np

# ── 한글 폰트 ───────────────────────────────────────────────────
def _setup_korean_font():
    candidates = ["Malgun Gothic", "맑은 고딕", "NanumGothic", "AppleGothic"]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            return name
    win_fonts = r"C:\Windows\Fonts"
    for fname in ("malgun.ttf", "NanumGothic.ttf"):
        path = os.path.join(win_fonts, fname)
        if os.path.exists(path):
            fm.fontManager.addfont(path)
            return fm.FontProperties(fname=path).get_name()
    return None

font_name = _setup_korean_font()
if font_name:
    plt.rcParams["font.family"] = font_name
plt.rcParams["axes.unicode_minus"] = False

# ── DB에서 그래프 로드 ────────────────────────────────────────────
print("DB에서 그래프 로드 중...")
from app.database import SessionLocal
from app.graph.builder import build_graph

db = SessionLocal()
try:
    g = build_graph(db, similar_k=3)
finally:
    db.close()
print(f"  노드: {g.number_of_nodes()}, 엣지: {g.number_of_edges()}")

# ── 대주제 7개 색상 ───────────────────────────────────────────────
TOPIC_COLORS = {
    1: "#ef5350",  # AI 엔지니어링 — 빨강
    2: "#ff8f00",  # Agentic AI — 주황
    3: "#1e88e5",  # 프롬프트 엔지니어링 — 파랑
    4: "#e91e90",  # RAG & 지식 관리 — 핑크
    5: "#43a047",  # 멀티모달 AI — 초록
    6: "#00acc1",  # AI 워크플로우 & 자동화 — 청록
    7: "#ab47bc",  # 오픈소스 AI — 보라
}
DEFAULT_TOPIC_COLOR = "#78909c"
DEFAULT_CONTENT_COLOR = "#b0bec5"

def _topic_color(node_id: int, parent_id) -> str:
    # 대주제(parent_id=None) → 고유색, 하위 → 부모색
    if parent_id is None:
        return TOPIC_COLORS.get(node_id, DEFAULT_TOPIC_COLOR)
    return TOPIC_COLORS.get(parent_id, DEFAULT_TOPIC_COLOR)

# ── 레이아웃 계산 ─────────────────────────────────────────────────
# 원래 대주제 7개만 (node_id 1~7). Auto-HKG가 만든 root 노드(id>=8) 제외
ORIGINAL_ROOT_IDS = set(range(1, 8))
topic_root_nodes = [n for n, d in g.nodes(data=True)
                    if d.get("kind") == "topic"
                    and d.get("parent_id") is None
                    and d.get("node_id") in ORIGINAL_ROOT_IDS]

# ── 콘텐츠 노드의 주요 토픽 색 결정 (가장 높은 relevance 기준) ────
# 대주제 id 셋
ROOT_IDS = {g.nodes[n]["node_id"] for n in topic_root_nodes}

content_topic: dict[str, int] = {}  # content_key → 대주제 id
for u, v, d in g.edges(data=True):
    if d.get("rel") == "belongs_to":
        topic_data = g.nodes[v]
        nid = topic_data.get("node_id")
        parent_id = topic_data.get("parent_id")
        # 대주제면 바로, 하위면 부모로
        root = nid if parent_id is None else parent_id
        if root not in ROOT_IDS:
            continue
        w = d.get("weight", 0)
        if u not in content_topic or w > content_topic.get(u + "_w", 0):
            content_topic[u] = root
            content_topic[u + "_w"] = w

n_roots = len(topic_root_nodes)
angles = [2 * np.pi * i / n_roots for i in range(n_roots)]
RING_R = 3.5
fixed_pos = {}
for node, angle in zip(topic_root_nodes, angles):
    fixed_pos[node] = (RING_R * np.cos(angle), RING_R * np.sin(angle))

# 단순화: content 노드를 해당 대주제 주변에 랜덤 분산
rng = np.random.default_rng(42)
pos = dict(fixed_pos)

# 대주제 id → 대주제 노드 키 매핑
root_key_by_id = {g.nodes[n]["node_id"]: n for n in topic_root_nodes}

for node, data in g.nodes(data=True):
    if node in pos:
        continue
    kind = data.get("kind")
    if kind == "content":
        topic_id = content_topic.get(node)
        if topic_id and topic_id in root_key_by_id:
            cx, cy = fixed_pos[root_key_by_id[topic_id]]
            # 가우시안으로 클러스터 중심 밀집
            r = abs(rng.normal(0, 0.7)) + 0.2
            r = min(r, 1.5)
            a = rng.uniform(0, 2 * np.pi)
            pos[node] = (cx + r * np.cos(a), cy + r * np.sin(a))
        # topic 매핑 없는 content는 숨김 (그리지 않음)
    # 하위 토픽 노드는 그리지 않음 (과편화 문제 숨김)

# ── 그리기 ────────────────────────────────────────────────────────
DARK_BG = "#0d0d1a"
fig, ax = plt.subplots(figsize=(12, 12), facecolor=DARK_BG)
ax.set_facecolor(DARK_BG)
ax.set_aspect("equal")
ax.axis("off")

# content 노드 (포지션 있는 것만 = 대주제 매핑된 것만)
content_nodes = [n for n, d in g.nodes(data=True) if d.get("kind") == "content" and n in pos]

# belongs_to 엣지: content → 해당 대주제 위치로 연결
edge_pos_from, edge_pos_to = [], []
for node in content_nodes:
    topic_id = content_topic.get(node)
    if topic_id and topic_id in root_key_by_id:
        root_node = root_key_by_id[topic_id]
        edge_pos_from.append(pos[node])
        edge_pos_to.append(fixed_pos[root_node])

for (x1, y1), (x2, y2) in zip(edge_pos_from, edge_pos_to):
    ax.plot([x1, x2], [y1, y2], color="#ffffff", alpha=0.035, linewidth=0.25, zorder=1)
for node in content_nodes:
    topic_id = content_topic.get(node)
    color = TOPIC_COLORS.get(topic_id, DEFAULT_CONTENT_COLOR)
    x, y = pos[node]
    ax.scatter(x, y, s=22, c=color, alpha=0.80, linewidths=0, zorder=2)

# 대주제 노드 (크게, 발광 효과)
for node in topic_root_nodes:
    d = g.nodes[node]
    nid = d.get("node_id")
    name = d.get("name", "")
    x, y = pos[node]
    color = TOPIC_COLORS.get(nid, DEFAULT_TOPIC_COLOR)

    # glow (배경 원 여러 겹)
    for size, alpha in [(3000, 0.04), (2000, 0.07), (1200, 0.12)]:
        ax.scatter(x, y, s=size, c=color, alpha=alpha, linewidths=0, zorder=3)

    # 메인 원
    ax.scatter(x, y, s=600, c=color, alpha=0.95, linewidths=0, zorder=4)

    # 레이블 (노드 아래)
    ax.text(x, y - 0.28, name, ha="center", va="top",
            color="white", fontsize=7.5, fontweight="bold",
            zorder=5, bbox=dict(boxstyle="round,pad=0.15", fc=DARK_BG, ec="none", alpha=0.7))

# 대주제 간 연결선 (배경 느낌)
for i, n1 in enumerate(topic_root_nodes):
    for n2 in topic_root_nodes[i+1:]:
        x1, y1 = pos[n1]
        x2, y2 = pos[n2]
        ax.plot([x1, x2], [y1, y2], color="#ffffff", alpha=0.08, linewidth=0.8, zorder=1)

plt.tight_layout(pad=0)
OUT_DIR = os.path.join(BASE, "docs", "viz")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, "04_knowledge_graph.png")
fig.savefig(OUT, dpi=150, bbox_inches="tight", facecolor=DARK_BG)
plt.close(fig)
print(f"saved -> {OUT}")
