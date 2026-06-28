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
from app.graph.metrics import compute_metrics, compute_objective, precedes_link_metrics

# HIVE-58: J 회귀 게이트 임계 — ΔJ가 이보다 더 떨어지면 회귀로 보고 exit 1.
J_REGRESSION_TOLERANCE = -0.02


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
    """auto 토픽 클러스터의 의미(semantic) 품질.

    PRIMARY = tag_purity: 클러스터링에 쓰이지 않은 **독립 태거 라벨**(content_type·대주제)로
    각 auto 클러스터가 얼마나 단일 라벨로 구성되는지(순도)를 잰다. baseline(랜덤 클러스터 기대)
    대비 높으면 '의미가 있게 묶였다'는 해석 가능 — silhouette보다 직접적이고 비순환적.

    embedding_geometry = cluster_quality(cohesion/separation/silhouette)는 임베딩 기하라
    파라미터 튜닝·회귀 게이트용(튜닝용)으로만 둔다.
    """
    import numpy as np

    from app.graph.metrics import (
        cluster_label_purity,
        cluster_quality,
        label_cluster_agreement,
    )

    # auto 멤버십 + content_type + 임베딩 (한 번에 조회)
    rows = db.execute(
        text(
            """
            SELECT m.node_id AS tid, m.content_id AS cid,
                   c.content_type AS ctype, c.text_embedding AS emb
            FROM content_node_mapping m
            JOIN curriculum_nodes n ON n.id = m.node_id
            JOIN content c ON c.id = m.content_id
            WHERE n.is_auto_generated = TRUE AND c.text_embedding IS NOT NULL
            """
        )
    ).fetchall()

    # 콘텐츠별 우세 대주제(non-auto root, relevance_score argmax)
    dom_rows = db.execute(
        text(
            """
            SELECT m.content_id AS cid, m.node_id AS rid, m.relevance_score AS rel
            FROM content_node_mapping m
            JOIN curriculum_nodes n ON n.id = m.node_id
            WHERE n.is_auto_generated = FALSE AND n.parent_id IS NULL
            """
        )
    ).fetchall()
    dominant_root: dict = {}    # content_id -> root_node_id (relevance 최대)
    best_rel: dict = {}
    for r in dom_rows:
        rel = float(r.rel) if r.rel is not None else 0.0
        if r.cid not in best_rel or rel > best_rel[r.cid]:
            best_rel[r.cid] = rel
            dominant_root[r.cid] = r.rid

    topic_embeddings: dict = {}             # tid -> [embedding] (임베딩 기하용)
    labels_ctype: dict = {}                 # tid -> [content_type] (순도 PRIMARY)
    labels_topic: dict = {}                 # tid -> [dominant_root_id]
    for r in rows:
        topic_embeddings.setdefault(r.tid, []).append(
            np.array(str(r.emb).strip()[1:-1].split(","), dtype=float)
        )
        labels_ctype.setdefault(r.tid, []).append(r.ctype)
        labels_topic.setdefault(r.tid, []).append(dominant_root.get(r.cid))

    geometry = cluster_quality(topic_embeddings)
    tag_purity_ctype = cluster_label_purity(labels_ctype)
    tag_purity_topic = cluster_label_purity(labels_topic)

    # V-measure: 클러스터링 vs 독립 라벨 일치도(purity 편향 보정). 평평한 (true,pred)로.
    flat_true_ct = [l for ls in labels_ctype.values() for l in ls]
    flat_true_tp = [l for ls in labels_topic.values() for l in ls]
    flat_pred = [tid for tid, ls in labels_ctype.items() for _ in ls]
    flat_pred_tp = [tid for tid, ls in labels_topic.items() for _ in ls]
    vmeasure_ctype = label_cluster_agreement(flat_true_ct, flat_pred)
    vmeasure_topic = label_cluster_agreement(flat_true_tp, flat_pred_tp)

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
        "tag_purity_content_type": tag_purity_ctype,
        "tag_purity_topic": tag_purity_topic,
        "v_measure_content_type": vmeasure_ctype,
        "v_measure_topic": vmeasure_topic,
        "embedding_geometry": geometry,       # 튜닝용(headline 아님)
        "coverage_ratio": round(in_auto / total, 4) if total else 0.0,
        "content_in_auto_topics": in_auto,
        "content_total": total,
    }


def _predicted_precedes(db) -> set:
    """node_links 전 행 = precedes(source->target) 예측 집합 (HIVE-58)."""
    rows = db.execute(text("SELECT source_node_id, target_node_id FROM node_links")).fetchall()
    return {(int(r.source_node_id), int(r.target_node_id)) for r in rows}


def load_golden_precedes(path: str) -> set:
    """골든셋 (source_node_id,target_node_id,label) JSON -> label==1 엣지 집합 (HIVE-58 계약).

    포맷: [{"source_node_id":int,"target_node_id":int,"label":0|1}, ...]
    label 누락 시 1로 간주. 0쌍 파일에도 빈 집합 반환(NaN/0div 없이 안전).
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {(int(r["source_node_id"]), int(r["target_node_id"]))
            for r in data if int(r.get("label", 1)) == 1}


def export_precedes(db, path: str) -> int:
    """현재 node_links를 골든셋과 동일 (source_node_id,target_node_id,label) 포맷으로 내보낸다.
    사람이 label(1=참 / 0=오답·역방향)을 검수해 골든셋으로 쓴다 (HIVE-58 export 계약)."""
    rows = [{"source_node_id": s, "target_node_id": t, "label": 1}
            for (s, t) in sorted(_predicted_precedes(db))]
    Path(path).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(rows)


def _snapshot(out_path: str, golden_path: str | None = None) -> None:
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
        golden = load_golden_precedes(golden_path) if golden_path else set()
        precedes_eval = precedes_link_metrics(_predicted_precedes(db), golden)
        samples = _recommendation_samples(db)
    finally:
        db.close()

    snapshot = {"metrics": metrics, "growth": node_growth,
                "semantic": semantic, "precedes_eval": precedes_eval,
                "rec_samples": samples}
    snapshot["objective"] = compute_objective(snapshot)
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
        print("\n" + "-" * 60)
        print("의미(semantic) — auto 클러스터 라벨 순도 (PRIMARY)")
        print("-" * 60)
        ct = sem.get("tag_purity_content_type", {})
        tp = sem.get("tag_purity_topic", {})
        print(f"content_type 순도: mean {ct.get('purity_mean')} / weighted {ct.get('purity_weighted')} / baseline {ct.get('baseline')}  (클러스터 {ct.get('n_clusters')}개)")
        print(f"대주제 순도      : mean {tp.get('purity_mean')} / weighted {tp.get('purity_weighted')} / baseline {tp.get('baseline')}  (클러스터 {tp.get('n_clusters')}개)")
        vc = sem.get("v_measure_content_type", {})
        vt = sem.get("v_measure_topic", {})
        print(f"V-measure        : content_type {vc.get('v_measure')} (homog {vc.get('homogeneity')}/compl {vc.get('completeness')}, 랜덤 {vc.get('baseline')}) / 대주제 {vt.get('v_measure')} (랜덤 {vt.get('baseline')})")
        geo = sem.get("embedding_geometry", {})
        print(f"  (튜닝용) 임베딩기하: silhouette {geo.get('silhouette')} / cohesion {geo.get('cohesion')} / separation {geo.get('separation')}")
        print(f"coverage        : {sem.get('coverage_ratio')} ({sem.get('content_in_auto_topics')}/{sem.get('content_total')})")
    pe = s.get("precedes_eval")
    if pe:
        print("\n" + "-" * 60)
        print("precedes 링크 평가 (HIVE-58)")
        print("-" * 60)
        print(f"예측 {pe['n_pred']} · 골든 {pe['n_golden']} · TP {pe['tp']}")
        print(f"precision {pe['precision']} / recall {pe['recall']} / f1 {pe['f1']} / reversed_rate {pe['reversed_rate']}")
    obj = s.get("objective")
    if obj:
        c = obj["components"]
        print("\n" + "-" * 60)
        print(f"목적함수 J = {obj['J']}  (회귀게이트 기준)")
        print("-" * 60)
        print(f"coverage {c['coverage_ratio']} · purity_w {c['purity_weighted']} · v_measure {c['v_measure']} · orphan {c['orphan_ratio']} · depth {c['max_topic_depth']}(score {c['depth_score']})")
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

    # 의미 품질(semantic) 비교 — semantic은 스냅샷 최상위 키. 구버전 스냅샷 가드.
    bf = json.loads(Path(before_path).read_text(encoding="utf-8")).get("semantic", {})
    af = json.loads(Path(after_path).read_text(encoding="utf-8")).get("semantic", {})
    if bf or af:
        print("\n[의미(semantic) — 클러스터 라벨 순도 (PRIMARY)]")

        def srow(label, top_key, sub_key):
            bv = (bf.get(top_key) or {}).get(sub_key)
            av = (af.get(top_key) or {}).get(sub_key)
            print(f"{label:22} {str(bv):>14} → {str(av):>14}")

        srow("content_type 순도", "tag_purity_content_type", "purity_mean")
        srow("  baseline", "tag_purity_content_type", "baseline")
        srow("대주제 순도", "tag_purity_topic", "purity_mean")
        srow("  baseline", "tag_purity_topic", "baseline")
        srow("V-measure(ctype)", "v_measure_content_type", "v_measure")
        srow("  랜덤 baseline", "v_measure_content_type", "baseline")
        srow("V-measure(대주제)", "v_measure_topic", "v_measure")
        srow("(튜닝)silhouette", "embedding_geometry", "silhouette")
        print(f"{'coverage':22} {str(bf.get('coverage_ratio')):>14} → {str(af.get('coverage_ratio')):>14}")
    print("\n해석: 과파편화는 modularity가 아니라 orphan_ratio↓·articulation↓·max_depth↓로 본다.")
    print("      의미는 tag_purity(순도)가 baseline을 넘는지로 '의미있게 묶였나'를 본다(silhouette은 튜닝용).")

    # precedes 링크 평가 비교 (HIVE-58) — 스냅샷에 있으면.
    bp = json.loads(Path(before_path).read_text(encoding="utf-8")).get("precedes_eval")
    ap = json.loads(Path(after_path).read_text(encoding="utf-8")).get("precedes_eval")
    if bp or ap:
        print("\n[precedes 링크 (f1 / reversed_rate / golden)]")
        print(f"  f1            {str((bp or {}).get('f1')):>10} → {str((ap or {}).get('f1')):>10}")
        print(f"  reversed_rate {str((bp or {}).get('reversed_rate')):>10} → {str((ap or {}).get('reversed_rate')):>10}")
        print(f"  golden 쌍수   {str((bp or {}).get('n_golden')):>10} → {str((ap or {}).get('n_golden')):>10}")

    # HIVE-58: 목적함수 J 회귀 게이트 — ΔJ < J_REGRESSION_TOLERANCE 면 exit 1.
    bs = json.loads(Path(before_path).read_text(encoding="utf-8"))
    as_ = json.loads(Path(after_path).read_text(encoding="utf-8"))
    jb, ja = compute_objective(bs)["J"], compute_objective(as_)["J"]
    dJ = round(ja - jb, 4)
    print("\n" + "=" * 60)
    print(f"목적함수 J: {jb} → {ja}   (ΔJ {dJ:+.4f}, 게이트 {J_REGRESSION_TOLERANCE})")
    print("=" * 60)
    if dJ < J_REGRESSION_TOLERANCE:
        print(f"❌ 회귀 감지: ΔJ {dJ:+.4f} < {J_REGRESSION_TOLERANCE} → 실패")
        sys.exit(1)
    print(f"✅ 통과: ΔJ {dJ:+.4f} ≥ {J_REGRESSION_TOLERANCE}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", help="스냅샷 JSON 저장 경로")
    p.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"), help="두 스냅샷 비교 + J 회귀게이트")
    p.add_argument("--golden", help="precedes 골든셋 JSON 경로(source_node_id,target_node_id,label)")
    p.add_argument("--export-precedes", metavar="PATH", help="현재 node_links를 골든셋 포맷으로 내보내기")
    args = p.parse_args()

    if args.export_precedes:
        db = SessionLocal()
        try:
            n = export_precedes(db, args.export_precedes)
        finally:
            db.close()
        print(f"precedes {n}건 내보냄: {args.export_precedes}")
    elif args.compare:
        _compare(*args.compare)
    elif args.out:
        _snapshot(args.out, args.golden)
    else:
        p.error("--out / --compare / --export-precedes 중 하나가 필요합니다.")


if __name__ == "__main__":
    main()
