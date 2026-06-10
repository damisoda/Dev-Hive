"""HIVE-38: 지표 시각화 PNG 생성 스크립트.

사용법: python scripts/gen_viz.py
출력: docs/viz/ 디렉터리에 PNG 3종
"""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── 한글 폰트 설정 ──────────────────────────────────────────────
import matplotlib.font_manager as fm

def _setup_korean_font():
    """Windows/Linux 모두에서 한글 폰트 자동 탐색."""
    candidates = [
        "Malgun Gothic", "맑은 고딕",
        "NanumGothic", "NanumBarunGothic",
        "AppleGothic", "Noto Sans KR",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            return name
    # 직접 경로 탐색 (Windows)
    win_fonts = r"C:\Windows\Fonts"
    for fname in ("malgun.ttf", "NanumGothic.ttf"):
        path = os.path.join(win_fonts, fname)
        if os.path.exists(path):
            fm.fontManager.addfont(path)
            prop = fm.FontProperties(fname=path)
            return prop.get_name()
    return None

font_name = _setup_korean_font()
if font_name:
    plt.rcParams["font.family"] = font_name
plt.rcParams["axes.unicode_minus"] = False

# ── 데이터 로드 ──────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(BASE, "backend", "eval_before.json"), encoding="utf-8") as f:
    before = json.load(f)["metrics"]
with open(os.path.join(BASE, "backend", "eval_after.json"), encoding="utf-8") as f:
    after = json.load(f)["metrics"]

OUT_DIR = os.path.join(BASE, "docs", "viz")
os.makedirs(OUT_DIR, exist_ok=True)

DARK_BG   = "#1a1a2e"
BEFORE_C  = "#4fc3f7"   # 하늘
AFTER_C   = "#ef5350"   # 빨강(악화) or 초록(개선)
GOOD_C    = "#66bb6a"
BAD_C     = "#ef5350"
ACCENT    = "#ffd54f"

def save(fig, name):
    path = os.path.join(OUT_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"  saved → {path}")
    plt.close(fig)

# ════════════════════════════════════════════════════════════════
# 1) 핵심 지표 Before / After 막대그래프
# ════════════════════════════════════════════════════════════════
metrics_cfg = [
    # (label, before_val, after_val, higher_is_better)
    ("Modularity",         before["modularity"],       after["modularity"],       True),
    ("Avg Clustering",     before["avg_clustering"],   after["avg_clustering"],   True),
    ("ADC\n(연결 밀도)",    before["adc"],              after["adc"],              True),
    ("Artic. Points\n(단절점)",
                           before["articulation_points"],
                           after["articulation_points"], False),
    ("LCC Ratio\n(연결성)", before["lcc_ratio"],        after["lcc_ratio"],        True),
]

fig, axes = plt.subplots(1, len(metrics_cfg), figsize=(14, 5), facecolor=DARK_BG)
fig.suptitle("Auto-HKG 적용 전후 — 핵심 지표 비교", color="white", fontsize=14, y=1.02)

for ax, (label, bv, av, higher_good) in zip(axes, metrics_cfg):
    ax.set_facecolor(DARK_BG)
    improved = (av > bv) if higher_good else (av < bv)
    after_color = GOOD_C if improved else BAD_C

    bars = ax.bar(["Before", "After"], [bv, av],
                  color=[BEFORE_C, after_color], width=0.5,
                  edgecolor="none")

    # 값 레이블
    for bar, val in zip(bars, [bv, av]):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(bv, av) * 0.03,
                f"{val:.4f}" if val < 10 else f"{int(val)}",
                ha="center", va="bottom", color="white", fontsize=9)

    ax.set_title(label, color="white", fontsize=10, pad=8)
    ax.tick_params(colors="white", labelsize=9)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_ylim(0, max(bv, av) * 1.3 + 1e-9)
    ax.yaxis.set_visible(False)

# 범례
patch_b = mpatches.Patch(color=BEFORE_C, label="Before (924 content)")
patch_g = mpatches.Patch(color=GOOD_C,   label="After — 개선")
patch_r = mpatches.Patch(color=BAD_C,    label="After — 악화")
fig.legend(handles=[patch_b, patch_g, patch_r],
           loc="lower center", ncol=3, framealpha=0,
           labelcolor="white", fontsize=9, bbox_to_anchor=(0.5, -0.08))

plt.tight_layout()
save(fig, "01_metrics_comparison.png")

# ════════════════════════════════════════════════════════════════
# 2) 파편화(Fragmentation) 시각화 — 노드 구성 비교
# ════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(11, 5), facecolor=DARK_BG)
fig.suptitle("Auto-HKG 과파편화(Over-fragmentation) 문제", color="white", fontsize=13, y=1.02)

# Before 파이
ax = axes[0]
ax.set_facecolor(DARK_BG)
sizes_b = [before["kinds"]["topic"], before["kinds"]["content"]]
labels_b = [f"Topic 노드\n({before['kinds']['topic']}개)", f"Content 노드\n({before['kinds']['content']}개)"]
wedges, texts, autotexts = ax.pie(
    sizes_b, labels=labels_b, autopct="%1.0f%%",
    colors=["#7986cb", BEFORE_C],
    textprops={"color": "white", "fontsize": 9},
    wedgeprops={"linewidth": 0},
    startangle=90,
)
for at in autotexts:
    at.set_color("white")
ax.set_title("Before Auto-HKG\n(931 nodes)", color="white", fontsize=11)

# After 파이 — 싱글톤 분리
ax = axes[1]
ax.set_facecolor(DARK_BG)
total_topic_after = after["kinds"]["topic"]   # 832
singleton = 778
real_topic = total_topic_after - singleton    # 54 (7 + 47 multi-content)
sizes_a = [real_topic, singleton, after["kinds"]["content"]]
labels_a = [
    f"Topic 노드(정상)\n({real_topic}개)",
    f"싱글톤 Topic\n(콘텐츠 1건, {singleton}개)",
    f"Content 노드\n({after['kinds']['content']}개)",
]
wedges2, texts2, autotexts2 = ax.pie(
    sizes_a, labels=labels_a, autopct="%1.0f%%",
    colors=["#7986cb", BAD_C, BEFORE_C],
    textprops={"color": "white", "fontsize": 9},
    wedgeprops={"linewidth": 0},
    startangle=90,
)
for at in autotexts2:
    at.set_color("white")
ax.set_title("After Auto-HKG\n(1,756 nodes)", color="white", fontsize=11)

# 화살표 + 텍스트
fig.text(0.5, -0.04,
         f"하위 노드 {total_topic_after}개 중 {singleton}개({singleton/total_topic_after*100:.0f}%)가 싱글톤 → 단절점 0 → {singleton}, 군집계수 {before['avg_clustering']} → {after['avg_clustering']}",
         ha="center", color=ACCENT, fontsize=9)

plt.tight_layout()
save(fig, "02_fragmentation.png")

# ════════════════════════════════════════════════════════════════
# 3) 차수 분포 히스토그램 (Before vs After)
# ════════════════════════════════════════════════════════════════
def hist_from_dict(d: dict) -> tuple[list, list]:
    """{"deg": count, ...} → (degrees, counts) 리스트."""
    items = sorted((int(k), v) for k, v in d.items())
    return [x[0] for x in items], [x[1] for x in items]

deg_b, cnt_b = hist_from_dict(before["degree_dist"]["histogram"])
deg_a, cnt_a = hist_from_dict(after["degree_dist"]["histogram"])

fig, axes = plt.subplots(1, 2, figsize=(13, 5), facecolor=DARK_BG)
fig.suptitle("차수(Degree) 분포 — Before vs After Auto-HKG", color="white", fontsize=13, y=1.02)

for ax, (degs, cnts, label, color, stats) in zip(axes, [
    (deg_b, cnt_b, "Before", BEFORE_C, before["degree_dist"]),
    (deg_a, cnt_a, "After",  BAD_C,    after["degree_dist"]),
]):
    ax.set_facecolor(DARK_BG)

    # 꼬리 노드(>50) 제외 버전으로 메인 히스토그램
    mask = [i for i, d in enumerate(degs) if d <= 50]
    d_plot = [degs[i] for i in mask]
    c_plot = [cnts[i] for i in mask]

    ax.bar(d_plot, c_plot, color=color, alpha=0.8, width=0.8, edgecolor="none")
    ax.set_title(f"{label}\n(min={stats['min']}, max={stats['max']}, mean={stats['mean']})",
                 color="white", fontsize=11)
    ax.set_xlabel("차수 (degree)", color="white", fontsize=9)
    ax.set_ylabel("노드 수", color="white", fontsize=9)
    ax.tick_params(colors="white", labelsize=8)
    for spine in ax.spines.values():
        spine.set_edgecolor("#444")

    # 싱글톤 강조 (After에만)
    if label == "After" and 1 in degs:
        singleton_idx = degs.index(1)
        ax.bar([1], [cnts[singleton_idx]], color=ACCENT, width=0.8, edgecolor="none",
               label=f"싱글톤 ({cnts[singleton_idx]}개)")
        ax.legend(framealpha=0, labelcolor="white", fontsize=9)

    ax.text(0.98, 0.97, "* 차수>50 허브 노드 제외 표시",
            transform=ax.transAxes, ha="right", va="top",
            color="#888", fontsize=7)

plt.tight_layout()
save(fig, "03_degree_distribution.png")

print("\n✅ 시각화 완료: docs/viz/ 에 PNG 3개 저장됨")
