"""HIVE-56: 승인된 precedes 후보를 node_links에 적재(전수검수 로더).

gen_precedes_candidates.py가 만든 JSON에서 approved=true인 것만 적재한다.
가드: 자기참조 제거, 기존+승인 합쳐 **DAG 유지(사이클 거부)**, PK(source,target) ON CONFLICT로 멱등.

node_links = topic→topic precedes 엣지 테이블(별도 rel 컬럼 없음). weight=confidence.

실행:
    cd backend
    python scripts/load_precedes.py [--in precedes_candidates.json] [--dry-run]
"""
import argparse
import json
import os
import sys
from pathlib import Path

import networkx as nx
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def select_loadable(candidates, existing):
    """순수 함수(테스트용). candidates·existing = (source, target) 튜플 모음.

    자기참조/중복 제거 + 사이클 생성 엣지 거부. 반환 (to_insert, skipped[(s,t,reason)]).
    """
    g = nx.DiGraph()
    g.add_edges_from(existing)
    existing_set = set(existing)
    to_insert, skipped = [], []
    for s, t in candidates:
        if s == t:
            skipped.append((s, t, "self"))
            continue
        if (s, t) in existing_set or g.has_edge(s, t):
            skipped.append((s, t, "dup"))
            continue
        # t→s 경로가 이미 있으면 s→t 추가는 사이클
        if g.has_node(s) and g.has_node(t) and nx.has_path(g, t, s):
            skipped.append((s, t, "cycle"))
            continue
        g.add_edge(s, t)
        to_insert.append((s, t))
    return to_insert, skipped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=str(ROOT / "precedes_candidates.json"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        sys.exit("DATABASE_URL 필요")

    cands = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    approved = [c for c in cands if c.get("approved")]
    conf = {(c["source"], c["target"]): float(c.get("confidence") or 0.5) for c in approved}
    print(f"승인 후보: {len(approved)}건")

    engine = create_engine(db_url)
    with engine.connect() as conn:
        existing = [
            (r.source_node_id, r.target_node_id)
            for r in conn.execute(text("SELECT source_node_id, target_node_id FROM node_links")).fetchall()
        ]
        to_insert, skipped = select_loadable([(c["source"], c["target"]) for c in approved], existing)

        for s, t, why in skipped:
            print(f"  SKIP({why}) {s}→{t}")
        print(f"적재 대상: {len(to_insert)}건 / 스킵 {len(skipped)}건")

        if args.dry_run:
            print("[DRY-RUN] 변경 없음")
            return

        for s, t in to_insert:
            conn.execute(
                text(
                    "INSERT INTO node_links (source_node_id, target_node_id, weight) "
                    "VALUES (:s, :t, :w) ON CONFLICT (source_node_id, target_node_id) DO NOTHING"
                ),
                {"s": s, "t": t, "w": conf.get((s, t), 0.5)},
            )
        conn.commit()

        total = conn.execute(text("SELECT count(*) FROM node_links")).scalar()
        print(f"적재 완료. node_links(precedes) 총 {total}건")


if __name__ == "__main__":
    main()
