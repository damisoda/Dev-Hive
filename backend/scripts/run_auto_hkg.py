"""HIVE-21 Auto-HKG 배치 실행 — 콘텐츠를 그래프에 편입(새 노드 자동 생성).

실행:
    cd backend
    python scripts/run_auto_hkg.py             # 전체
    python scripts/run_auto_hkg.py --limit 30  # 일부만
    python scripts/run_auto_hkg.py --dry-run   # 적용하지 않고 롤백(미리보기)

필요 환경변수: ANTHROPIC_API_KEY, DATABASE_URL
"""
import argparse
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.graph.auto_hkg import expand_graph


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="처리할 최대 콘텐츠 수")
    parser.add_argument("--dry-run", action="store_true", help="적용하지 않고 롤백(미리보기)")
    args = parser.parse_args()

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    db_url = os.getenv("DATABASE_URL")
    if not anthropic_key:
        sys.exit("ANTHROPIC_API_KEY 환경변수가 필요합니다.")
    if not db_url:
        sys.exit("DATABASE_URL 환경변수가 필요합니다.")

    client = anthropic.Anthropic(api_key=anthropic_key)
    engine = create_engine(db_url)

    print(f"Auto-HKG 실행 (limit={args.limit}, dry_run={args.dry_run})\n")
    conn = engine.connect()
    trans = conn.begin()
    try:
        stats = expand_graph(conn, client, limit=args.limit)
        if args.dry_run:
            trans.rollback()
        else:
            trans.commit()
    except Exception:
        trans.rollback()
        raise
    finally:
        conn.close()

    note = "  (dry-run — 롤백됨)" if args.dry_run else ""
    print(
        f"\n--- 완료{note} ---\n"
        f"처리: {stats['total']}건 / LLM 호출: {stats['llm_calls']}건\n"
        f"기존 매칭: {stats['existing']} / 새 하위노드: {stats['new_sub']} / 새 최상위: {stats['new_top']} / 스킵: {stats['skipped']}"
    )


if __name__ == "__main__":
    main()
