"""HIVE-38 평가·발표 산출물 스크립트.

Auto-HKG/GraphRAG가 '작동한다(thesis)'를 정량 지표로 보인다.

산출:
1. 그래프 자기조직화 지표 (metrics.compute_metrics) — modularity/ADC/허브/브릿지/LCC
2. 추천 근거 품질 샘플 — 유저별 top-N 추천 + 근거 + 적절성 참고치(레벨/mastery)
3. before/after 비교 (Auto-HKG 전후 스냅샷 JSON)

사용:
    cd backend
    # 1) Auto-HKG 전 스냅샷 저장
    python scripts/run_eval.py --out eval_before.json
    # 2) Auto-HKG 실행
    python scripts/run_auto_hkg.py
    # 3) Auto-HKG 후 스냅샷 저장
    python scripts/run_eval.py --out eval_after.json
    # 4) 전후 비교표 출력
    python scripts/run_eval.py --compare eval_before.json eval_after.json
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

# 추천 근거(GraphRAG Haiku) 생성에 API 키가 필요 — root .env 로드.
# 키 없으면 graphrag가 템플릿 근거로 폴백하므로 실행 자체는 문제없다.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.graph.builder import build_graph
from app.graph.metrics import compute_metrics


def _recommendation_samples(db, n_users: int = 3, top_n: int = 5) -> list[dict]:
    """profile_vector 있는 유저를 골라 추천 + 근거 + 적절성 참고치를 수집한다."""
    from app.recommend.graphrag import recommend_next
    from app.services.knowledge_tracing import estimate_mastery

    rows = db.execute(
        text(
            "SELECT id, display_name, current_level FROM users "
            "WHERE profile_vector IS NOT NULL ORDER BY id LIMIT :n"
        ),
        {"n": n_users},
    ).fetchall()

    samples = []
    for u in rows:
        recs = recommend_next(u.id, top_n, db)
        mastery = estimate_mastery(u.id, db)
        avg_m = round(sum(mastery.values()) / len(mastery), 3) if mastery else 0.0
        samples.append({
            "user_id": u.id,
            "display_name": u.display_name,
            "level": u.current_level,
            "avg_mastery": avg_m,
            "recommendations": [
                # score는 float로 명시 캐스팅 (numpy/Decimal이면 JSON 직렬화 실패 방지)
                {"title": r["title"], "score": float(r["score"]), "reason": r.get("reason")}
                for r in recs
            ],
        })
    if not samples:
        print("⚠️  profile_vector 있는 유저가 없어 추천 샘플이 비었습니다 "
              "(데모 유저 생성 후 다시 실행).")
    return samples


def _semantic_metrics(db) -> dict:
    """auto 토픽 클러스터의 임베딩 품질(cohesion/separation/silhouette) + coverage.

    그래프만으로는 못 보는 '의미 품질'을 임베딩으로 잰다 — 파라미터 튜닝 목적함수·회귀 게이트용.
    """
    import numpy as np

    from app.graph.metrics import cluster_quality

    rows = db.execute(
        text(
            """
            SELECT m.node_id AS tid, c.text_embedding AS emb
            FROM content_node_mapping m
            JOIN curriculum_nodes n ON n.id = m.node_id
            JOIN content c ON c.id = m.content_id
            WHERE n.is_auto_generated = TRUE AND c.text_embedding IS NOT NULL
            """
        )
    ).fetchall()
    topic_embeddings: dict = {}
    for r in rows:
        topic_embeddings.setdefault(r.tid, []).append(
            np.array(str(r.emb).strip()[1:-1].split(","), dtype=float)
        )
    quality = cluster_quality(topic_embeddings)

    # coverage: 세분(auto) 토픽에 매핑된 콘텐츠 비율(나머지는 7대주제로만 흡수).
    total = db.execute(
        text("SELECT count(*) FROM content WHERE text_embedding IS NOT NULL")
    ).scalar() or 0
    in_auto = db.execute(
        text(
            "SELECT count(DISTINCT m.content_id) FROM content_node_mapping m "
            "JOIN curriculum_nodes n ON n.id = m.node_id WHERE n.is_auto_generated = TRUE"
        )
    ).scalar() or 0
    return {
        **quality,
        "coverage_ratio": round(in_auto / total, 4) if total else 0.0,
        "content_in_auto_topics": in_auto,
        "content_total": total,
    }


def _snapshot(out_path: str) -> None:
    db = SessionLocal()
    try:
        g = build_graph(db)
        metrics = compute_metrics(g)
        # 노드/엣지 성장 추이용 카운트
        node_growth = {
            "total_nodes": metrics["nodes"],
            "topics": metrics["kinds"].get("topic", 0),
            "content": metrics["kinds"].get("content", 0),
            "edges": metrics["edges"],
        }
        semantic = _semantic_metrics(db)
        samples = _recommendation_samples(db)
    finally:
        db.close()

    snapshot = {"metrics": metrics, "growth": node_growth,
                "semantic": semantic, "rec_samples": samples}
    # default=str: 혹시 남은 비직렬화 타입(numpy/Decimal 등)도 죽지 않게 방어
    Path(out_path).write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    _print_report(snapshot)
    print(f"\n저장됨: {out_path}")


def _print_report(s: dict) -> None:
    m = s["metrics"]
    print("=" * 60)
    print("그래프 자기조직화 지표")
    print("=" * 60)
    print(f"노드 {m['nodes']} (topic {m['kinds'].get('topic',0)} / content {m['kinds'].get('content',0)}) · 엣지 {m['edges']}")
    print(f"modularity      : {m['modularity']}  (커뮤니티 {m['num_communities']}개)")
    print(f"ADC(연결밀도)   : {m['adc']}")
    print(f"허브(최대차수)  : {m['max_degree']}  — {m['hub']}")
    print(f"차수분포        : min {m['degree_dist']['min']} / mean {m['degree_dist']['mean']} / max {m['degree_dist']['max']}")
    print(f"브릿지(단절점)  : {m['articulation_points']}개")
    print(f"LCC             : {m['lcc_size']} ({m['lcc_ratio']*100:.1f}%) · 성분 {m['num_components']}개")
    print(f"평균 군집계수   : {m['avg_clustering']}")
    # HIVE-46 과파편화 지표
    cpt = m.get("content_per_auto_topic", {})
    print(f"고아노드비율    : {m.get('orphan_ratio')}  (auto토픽 {m.get('auto_topics')}개 중 콘텐츠≤1)")
    print(f"토픽최대깊이    : {m.get('max_topic_depth')}  (눈덩이 중첩 지표)")
    print(f"auto토픽당콘텐츠: mean {cpt.get('mean')} / median {cpt.get('median')} / max {cpt.get('max')}")
    sem = s.get("semantic", {})
    if sem:
        print(f"클러스터품질    : cohesion {sem.get('cohesion')} / separation {sem.get('separation')} / silhouette {sem.get('silhouette')}")
        print(f"coverage        : {sem.get('coverage_ratio')} ({sem.get('content_in_auto_topics')}/{sem.get('content_total')}) · 클러스터 {sem.get('n_clusters')}개")
    print("\n매개중심성 상위(브릿지 역할):")
    for b in m["top_betweenness"]:
        print(f"  - {b['node']}  ({b['score']})")
    print("\n" + "=" * 60)
    print("추천 근거 품질 샘플")
    print("=" * 60)
    for u in s["rec_samples"]:
        print(f"\n[{u['display_name']}] 레벨 {u['level']} · 평균mastery {u['avg_mastery']}")
        for i, r in enumerate(u["recommendations"], 1):
            print(f"  {i}. {r['title'][:50]}  (적합도 {r['score']})")
            if r.get("reason"):
                print(f"     근거: {r['reason']}")


def _compare(before_path: str, after_path: str) -> None:
    b = json.loads(Path(before_path).read_text(encoding="utf-8"))["metrics"]
    a = json.loads(Path(after_path).read_text(encoding="utf-8"))["metrics"]

    def row(label, key, fmt="{}"):
        bv, av = b.get(key), a.get(key)
        print(f"{label:18} {fmt.format(bv):>14} → {fmt.format(av):>14}")

    print("=" * 60)
    print("Auto-HKG 전후 비교 (before → after)")
    print("=" * 60)
    row("노드 수", "nodes")
    print(f"{'  topic':18} {b['kinds'].get('topic',0):>14} → {a['kinds'].get('topic',0):>14}")
    print(f"{'  content':18} {b['kinds'].get('content',0):>14} → {a['kinds'].get('content',0):>14}")
    row("엣지 수", "edges")
    row("modularity", "modularity")
    row("커뮤니티 수", "num_communities")
    row("ADC", "adc")
    row("최대차수(허브)", "max_degree")
    row("브릿지(단절점)", "articulation_points")
    row("LCC 비율", "lcc_ratio")
    row("평균군집계수", "avg_clustering")
    # HIVE-46 과파편화 지표(health 축 — modularity와 달리 직접적)
    row("고아노드비율", "orphan_ratio")
    row("토픽최대깊이", "max_topic_depth")

    # 의미 품질(semantic) 비교
    bf = json.loads(Path(before_path).read_text(encoding="utf-8")).get("semantic", {})
    af = json.loads(Path(after_path).read_text(encoding="utf-8")).get("semantic", {})
    if bf or af:
        print("\n[클러스터 의미 품질]")
        for label, key in (("cohesion", "cohesion"), ("separation", "separation"),
                           ("silhouette", "silhouette"), ("coverage", "coverage_ratio")):
            print(f"{label:18} {str(bf.get(key)):>14} → {str(af.get(key)):>14}")
    print("\n해석: 과파편화는 modularity가 아니라 orphan_ratio↓·articulation↓·max_depth↓로 본다.")
    print("      클러스터 품질은 silhouette↑/cohesion↑로 '잘 묶였나'를 정량화(파라미터 튜닝 기준).")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", help="스냅샷 JSON 저장 경로")
    p.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"), help="두 스냅샷 비교")
    args = p.parse_args()

    if args.compare:
        _compare(*args.compare)
    elif args.out:
        _snapshot(args.out)
    else:
        p.error("--out 또는 --compare 중 하나가 필요합니다.")


if __name__ == "__main__":
    main()
