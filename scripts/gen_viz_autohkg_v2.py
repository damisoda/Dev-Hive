"""HIVE-44: Auto-HKG 2-패스 재설계 효과 시각화.

v0(Auto-HKG 전) / v1(과파편화) / v2(2-패스) 3개 상태의 핵심 지표 비교.

사용법: python scripts/gen_viz_autohkg_v2.py [before.json] [after_v1.json] [after_v2.json]
기본: /tmp/eval_before.json, /tmp/eval_after.json, backend/eval_after2.json
출력: docs/viz/05_autohkg_v1_vs_v2.png
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

def _setup_korean_font():
    available = {f.name for f in fm.fontManager.ttflist}
    for name in ("Malgun Gothic", "맑은 고딕", "NanumGothic", "AppleGothic"):
        if name in available:
            return name
    for fname in ("malgun.ttf", "NanumGothic.ttf"):
        path = os.path.join(r"C:\Windows\Fonts", fname)
        if os.path.exists(path):
            fm.fontManager.addfont(path)
            return fm.FontProperties(fname=path).get_name()
    return None

fn = _setup_korean_font()
if fn:
    plt.rcParams["font.family"] = fn
plt.rcParams["axes.unicode_minus"] = False

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p_before = sys.argv[1] if len(sys.argv) > 1 else "/tmp/eval_before.json"
p_v1 = sys.argv[2] if len(sys.argv) > 2 else "/tmp/eval_after.json"
p_v2 = sys.argv[3] if len(sys.argv) > 3 else os.path.join(BASE, "backend", "eval_after2.json")

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)["metrics"]

m0, m1, m2 = load(p_before), load(p_v1), load(p_v2)

DARK_BG = "#1a1a2e"
C_V0 = "#90a4ae"  # 회색 (Auto-HKG 전 baseline)
C_V1 = "#ef5350"  # 빨강 (과파편화)
C_V2 = "#66bb6a"  # 초록 (2-패스 수정)

# (label, [v0, v1, v2], 정수표시?)
panels = [
    ("Avg Clustering\n(군집계수)", [m0["avg_clustering"], m1["avg_clustering"], m2["avg_clustering"]], False),
    ("단절점 수\n(Articulation Pts)", [m0["articulation_points"], m1["articulation_points"], m2["articulation_points"]], True),
    ("Modularity", [m0["modularity"], m1["modularity"], m2["modularity"]], False),
    ("자동노드 수", [0, 825, m2.get("kinds", {}).get("topic", 31) - 7], True),
]

fig, axes = plt.subplots(1, len(panels), figsize=(15, 5.2), facecolor=DARK_BG)
fig.suptitle("HIVE-44 — Auto-HKG 2-패스 재설계 효과 (v0 → v1 과파편화 → v2 수정)",
             color="white", fontsize=14, y=1.03)

labels = ["v0\n(전)", "v1\n(파편화)", "v2\n(2패스)"]
colors = [C_V0, C_V1, C_V2]

for ax, (title, vals, as_int) in zip(axes, panels):
    ax.set_facecolor(DARK_BG)
    bars = ax.bar(labels, vals, color=colors, width=0.62, edgecolor="none")
    vmax = max(vals) if max(vals) > 0 else 1
    for bar, v in zip(bars, vals):
        txt = f"{int(v)}" if as_int else f"{v:.3f}"
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + vmax * 0.03,
                txt, ha="center", va="bottom", color="white", fontsize=9)
    ax.set_title(title, color="white", fontsize=10.5, pad=8)
    ax.tick_params(colors="white", labelsize=8.5)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_ylim(0, vmax * 1.25 + 1e-9)
    ax.yaxis.set_visible(False)

fig.text(0.5, -0.03,
         "2-패스: 단절점 778→0, 군집계수 0.225→0.474 (v0 기준선 0.463 회복), 자동노드 825→24 (싱글톤 94%→0%)",
         ha="center", color="#ffd54f", fontsize=10)

plt.tight_layout()
OUT_DIR = os.path.join(BASE, "docs", "viz")
os.makedirs(OUT_DIR, exist_ok=True)
OUT = os.path.join(OUT_DIR, "05_autohkg_v1_vs_v2.png")
fig.savefig(OUT, dpi=150, bbox_inches="tight", facecolor=DARK_BG)
plt.close(fig)
print(f"saved -> {OUT}")
