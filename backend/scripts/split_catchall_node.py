"""HIVE-88 catch-all 노드 분할 — 과흡수 skeleton 노드의 콘텐츠를 재클러스터링.

'AI 엔지니어링' 등 단일 노드가 전체 콘텐츠의 대다수를 흡수하는 문제를 해결한다.
해당 노드에 매핑된 콘텐츠를 꺼내 2패스 클러스터링으로 하위 노드를 자동 생성하고
콘텐츠를 그 하위 노드로 재매핑한다. 원래 매핑(부모 노드)은 유지한다.

실행:
    cd backend
    python scripts/split_catchall_node.py                   # degree>50인 모든 skeleton 노드 처리
    python scripts/split_catchall_node.py --node-id 3       # 특정 노드 ID
    python scripts/split_catchall_node.py --node-name "AI 엔지니어링"
    python scripts/split_catchall_node.py --min-degree 30   # 임계값 조정
    python scripts/split_catchall_node.py --dry-run         # 미리보기 (롤백)

필요 환경변수: ANTHROPIC_API_KEY, DATABASE_URL
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.graph.auto_hkg import (
    CATCHALL_MIN_DEGREE,
    GROUP_THRESHOLD,
    MIN_CLUSTER_SIZE,
    _cluster_residuals,
    _partition_residuals,
    _create_node,
    _map,
    _name_cluster,
    _parse_emb,
    _unit,
    find_catchall_nodes,
    get_node_contents,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def split_node(
    conn,
    client: anthropic.Anthropic,
    node: dict,
    *,
    group_threshold: float = GROUP_THRESHOLD,
    min_cluster_size: int = MIN_CLUSTER_SIZE,
    dry_run: bool = False,
) -> dict:
    """단일 catch-all 노드를 분할한다. 통계 dict 반환."""
    nid = node["id"]
    name = node["name"]
    contents = get_node_contents(conn, nid, exclude_auto_children=True)
    logger.info("  노드 '%s'(id=%d): 잔여 콘텐츠 %d건 재클러스터링", name, nid, len(contents))

    if not contents:
        logger.info("  → 콘텐츠 없음, 스킵")
        return {"node": name, "contents": 0, "new_nodes": 0, "remapped": 0}

    residuals = [(c["id"], _unit(_parse_emb(c["emb"]))) for c in contents]
    title_by_id = {c["id"]: c["title"] for c in contents}

    clusters, orphans = _partition_residuals(residuals, min_size=min_cluster_size)
    logger.info("  → k-means 클러스터 %d개 / 고아 %d건", len(clusters), len(orphans))

    stats = {"node": name, "contents": len(contents), "new_nodes": 0, "remapped": 0, "llm_calls": 0}

    for members in clusters:
        # 부모는 현재 분할 대상 노드로 고정 (하위 노드로 생성)
        parent_id = nid

        titles = [title_by_id.get(cid, "") for cid in members]
        sub_name, sub_desc = _name_cluster(titles, client)
        stats["llm_calls"] += 1
        logger.info("    클러스터(%d건) → '%s'", len(members), sub_name)

        new_id = _create_node(conn, sub_name, sub_desc, parent_id)
        stats["new_nodes"] += 1
        for cid in members:
            _map(conn, cid, new_id, 1.0)
            stats["remapped"] += 1

    # 고아는 그대로 부모(catch-all) 노드에 두고 재매핑하지 않음
    logger.info(
        "  완료: 신규하위노드=%d / 재매핑=%d건 / 고아=%d건(유지)",
        stats["new_nodes"], stats["remapped"], len(orphans),
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="catch-all 노드 분할")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--node-id", type=int, help="분할할 노드 ID")
    group.add_argument("--node-name", type=str, help="분할할 노드 이름 (부분 일치)")
    parser.add_argument("--min-degree", type=int, default=CATCHALL_MIN_DEGREE,
                        help=f"자동 탐지 임계값 (기본 {CATCHALL_MIN_DEGREE})")
    parser.add_argument("--min-cluster-size", type=int, default=MIN_CLUSTER_SIZE,
                        help=f"클러스터 승격 최소 크기 (기본 {MIN_CLUSTER_SIZE})")
    parser.add_argument("--group-threshold", type=float, default=GROUP_THRESHOLD,
                        help=f"클러스터링 코사인 임계 (기본 {GROUP_THRESHOLD})")
    parser.add_argument("--dry-run", action="store_true", help="미리보기 후 롤백")
    args = parser.parse_args()

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    db_url = os.getenv("DATABASE_URL")
    if not anthropic_key:
        sys.exit("ANTHROPIC_API_KEY 환경변수가 필요합니다.")
    if not db_url:
        sys.exit("DATABASE_URL 환경변수가 필요합니다.")

    client = anthropic.Anthropic(api_key=anthropic_key)
    engine = create_engine(db_url)

    conn = engine.connect()
    trans = conn.begin()
    try:
        # 대상 노드 결정
        if args.node_id:
            row = conn.execute(
                text("SELECT id, name, (SELECT COUNT(*) FROM content_node_mapping WHERE node_id=n.id) AS degree FROM curriculum_nodes n WHERE id=:id"),
                {"id": args.node_id},
            ).fetchone()
            if not row:
                trans.rollback()
                sys.exit(f"노드 id={args.node_id} 없음")
            target_nodes = [{"id": row.id, "name": row.name, "degree": row.degree}]
        elif args.node_name:
            rows = conn.execute(
                text("SELECT id, name, (SELECT COUNT(*) FROM content_node_mapping WHERE node_id=n.id) AS degree FROM curriculum_nodes n WHERE name ILIKE :pat AND is_auto_generated=FALSE"),
                {"pat": f"%{args.node_name}%"},
            ).fetchall()
            if not rows:
                trans.rollback()
                sys.exit(f"노드명 '{args.node_name}' 없음")
            target_nodes = [{"id": r.id, "name": r.name, "degree": r.degree} for r in rows]
        else:
            target_nodes = find_catchall_nodes(conn, args.min_degree)
            if not target_nodes:
                print(f"degree >= {args.min_degree} 인 skeleton 노드 없음")
                trans.rollback()
                return

        print(f"\n대상 노드 {len(target_nodes)}개{'  (dry-run)' if args.dry_run else ''}:")
        for n in target_nodes:
            print(f"  id={n['id']}  degree={n['degree']}  '{n['name']}'")
        print()

        all_stats = []
        for node in target_nodes:
            s = split_node(
                conn, client, node,
                group_threshold=args.group_threshold,
                min_cluster_size=args.min_cluster_size,
                dry_run=args.dry_run,
            )
            all_stats.append(s)

        if args.dry_run:
            trans.rollback()
            print("\n--- dry-run 완료 (롤백됨) ---")
        else:
            trans.commit()
            print("\n--- 완료 ---")

        for s in all_stats:
            print(
                f"  '{s['node']}': 콘텐츠={s['contents']}건 / "
                f"신규하위노드={s['new_nodes']}개 / 재매핑={s['remapped']}건 / LLM={s.get('llm_calls', 0)}회"
            )

    except Exception:
        trans.rollback()
        logger.exception("분할 실패 — 롤백")
        sys.exit(1)
    finally:
        conn.close()
        engine.dispose()


if __name__ == "__main__":
    main()
