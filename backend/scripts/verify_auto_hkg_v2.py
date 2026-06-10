"""HIVE-44: 2-패스 Auto-HKG 비파괴 검증.

하나의 트랜잭션 안에서:
  1) v1 자동노드 + 매핑 롤백 (깨끗한 스켈레톤 상태 재현)
  2) 새 2-패스 expand_graph 실행
  3) 결과 측정 (생성 노드 수 / 고아 비율 / 클러스터 샘플)
  4) 트랜잭션 ROLLBACK — DB 원상 유지

실행: cd backend && python scripts/verify_auto_hkg_v2.py [--limit N]
"""
import argparse
import json
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.graph.auto_hkg import expand_graph
from app.graph.builder import build_graph
from app.graph.metrics import compute_metrics


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--snapshot", metavar="PATH", default=None,
                    help="2-패스 적용 후 그래프 지표를 JSON으로 저장 (HIVE-38 지표)")
    args = ap.parse_args()

    key = os.getenv("ANTHROPIC_API_KEY")
    db_url = os.getenv("DATABASE_URL")
    if not key or not db_url:
        sys.exit("ANTHROPIC_API_KEY / DATABASE_URL 필요")

    client = anthropic.Anthropic(api_key=key)
    engine = create_engine(db_url)
    conn = engine.connect()
    trans = conn.begin()
    try:
        # 1) v1 자동노드 롤백 — 깨끗한 스켈레톤 상태로
        conn.execute(text(
            "DELETE FROM content_node_mapping WHERE node_id IN "
            "(SELECT id FROM curriculum_nodes WHERE is_auto_generated = TRUE)"
        ))
        conn.execute(text("DELETE FROM curriculum_nodes WHERE is_auto_generated = TRUE"))
        before_nodes = conn.execute(text("SELECT COUNT(*) FROM curriculum_nodes")).scalar()
        print(f"[reset] 스켈레톤 노드 수: {before_nodes}")

        # 2) 새 2-패스 실행
        print("[run] 2-패스 Auto-HKG 실행 중...\n")
        stats = expand_graph(conn, client, limit=args.limit)

        # 3) 측정
        new_nodes = conn.execute(text(
            "SELECT COUNT(*) FROM curriculum_nodes WHERE is_auto_generated = TRUE"
        )).scalar()
        # 노드별 멤버 수
        rows = conn.execute(text(
            """
            SELECT n.id, n.name, n.parent_id, COUNT(m.content_id) AS cnt
            FROM curriculum_nodes n
            LEFT JOIN content_node_mapping m ON m.node_id = n.id
            WHERE n.is_auto_generated = TRUE
            GROUP BY n.id, n.name, n.parent_id
            ORDER BY cnt DESC
            """
        )).fetchall()
        singletons = sum(1 for r in rows if r.cnt <= 1)
        sizes = [r.cnt for r in rows]

        print("\n" + "=" * 56)
        print("HIVE-44 2-패스 Auto-HKG 검증 결과")
        print("=" * 56)
        print(f"처리 콘텐츠      : {stats['total']}건")
        print(f"LLM 호출         : {stats['llm_calls']}건 (클러스터 네이밍만)")
        print(f"1패스 흡수        : {stats['absorbed']}건")
        print(f"2패스 클러스터 노드: {stats['new_nodes']}개 (콘텐츠 {stats['clustered']}건)")
        print(f"고아 흡수         : {stats['orphan_mapped']}건")
        print("-" * 56)
        print(f"생성된 자동노드   : {new_nodes}개  (v1: 825개)")
        if rows:
            print(f"싱글톤 노드       : {singletons}개 ({singletons/len(rows)*100:.1f}%)  (v1: 778개 / 94%)")
            print(f"클러스터 크기 상위: {sorted(sizes, reverse=True)[:10]}")
        print("\n[샘플] 상위 10개 클러스터:")
        for r in rows[:10]:
            print(f"  - [{r.cnt:>3}건] {r.name}")

        # 3b) HIVE-38 지표 스냅샷 (선택) — 2-패스 적용 후 그래프
        if args.snapshot:
            print("\n[metrics] 그래프 빌드 + 지표 계산 중...")
            g = build_graph(conn)
            metrics = compute_metrics(g)
            with open(args.snapshot, "w", encoding="utf-8") as f:
                json.dump({"metrics": metrics}, f, ensure_ascii=False, indent=2)
            print(f"  modularity={metrics['modularity']} "
                  f"avg_clustering={metrics['avg_clustering']} "
                  f"articulation_points={metrics['articulation_points']}")
            print(f"  스냅샷 저장 → {args.snapshot}")

        # 4) 롤백 — DB 원상 복구
        trans.rollback()
        print("\n(검증 완료 — 트랜잭션 ROLLBACK, DB 원상 유지)")
    except Exception:
        trans.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
