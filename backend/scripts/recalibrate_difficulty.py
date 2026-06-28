"""HIVE-82: 기존 콘텐츠 difficulty 일괄 재산정.

94%가 '고급'으로 쏠린 difficulty를 태거 프롬프트 기준으로 재산정한다.
content_type 등 다른 필드는 건드리지 않고 difficulty만 업데이트한다.

실행:
    cd backend
    python scripts/recalibrate_difficulty.py --dry-run   # 현재 분포 확인
    python scripts/recalibrate_difficulty.py             # 전체 재산정
    python scripts/recalibrate_difficulty.py --limit 50  # N건만 테스트
"""
import argparse
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", encoding="utf-8-sig")
sys.path.insert(0, str(ROOT))

import anthropic
from sqlalchemy import create_engine, text

from app.tagging.tagger import tag_content

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

VALID_DIFFICULTIES = ("입문", "중급", "고급")
BATCH_SLEEP = float(os.getenv("RECALIB_SLEEP", "0.3"))


def print_distribution(conn, label: str) -> None:
    rows = conn.execute(
        text(
            "SELECT COALESCE(difficulty, 'NULL') AS d, COUNT(*) AS cnt "
            "FROM content GROUP BY d ORDER BY cnt DESC"
        )
    ).fetchall()
    print(f"\n[{label} difficulty 분포]")
    print(f"{'난이도':<8} {'건수':>6} {'비율':>7}")
    print("-" * 24)
    total = sum(r.cnt for r in rows)
    for r in rows:
        pct = r.cnt / total * 100 if total else 0
        print(f"{r.d:<8} {r.cnt:>6} {pct:>6.1f}%")
    print(f"{'합계':<8} {total:>6}")


def main() -> None:
    parser = argparse.ArgumentParser(description="HIVE-82 difficulty 재산정")
    parser.add_argument("--dry-run", action="store_true", help="현재 분포만 출력, DB 변경 없음")
    parser.add_argument("--limit", type=int, default=0, help="처리 건수 제한 (0=전체)")
    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        sys.exit("DATABASE_URL 환경변수가 필요합니다.")

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_key and not args.dry_run:
        sys.exit("ANTHROPIC_API_KEY 환경변수가 필요합니다.")

    engine = create_engine(db_url)

    with engine.connect() as conn:
        print_distribution(conn, "현재")

        if args.dry_run:
            print("\n[DRY-RUN] 변경 없음.")
            return

        query = (
            "SELECT id, title, body, content_type, difficulty FROM content "
            "WHERE content_type NOT IN ('paper', 'news') "
            "ORDER BY id"
        )
        if args.limit:
            query += f" LIMIT {args.limit}"

        rows = conn.execute(text(query)).fetchall()

    total = len(rows)
    print(f"\n재산정 대상: {total}건")
    if total == 0:
        print("대상 없음.")
        return

    client = anthropic.Anthropic(api_key=anthropic_key)
    changed, failed = 0, []

    from sqlalchemy.orm import Session
    with Session(engine) as db:
        for i, row in enumerate(rows, 1):
            item = {"title": row.title or "", "body": row.body or ""}
            try:
                tags = tag_content(item, client)
                new_diff = tags.get("difficulty")
                if new_diff not in VALID_DIFFICULTIES:
                    logger.warning("[%d/%d] id=%s — 유효하지 않은 difficulty=%r, 스킵", i, total, row.id, new_diff)
                    failed.append(row.id)
                    continue
                if new_diff != row.difficulty:
                    db.execute(
                        text("UPDATE content SET difficulty = :d WHERE id = :id"),
                        {"d": new_diff, "id": row.id},
                    )
                    db.commit()
                    logger.info("[%d/%d] id=%s  %s → %s", i, total, row.id, row.difficulty, new_diff)
                    changed += 1
                else:
                    logger.info("[%d/%d] id=%s  %s (변경 없음)", i, total, row.id, row.difficulty)
            except Exception:
                logger.exception("[%d/%d] id=%s — 예외", i, total, row.id)
                failed.append(row.id)
            time.sleep(BATCH_SLEEP)

    with engine.connect() as conn:
        print_distribution(conn, "재산정 후")

    print(f"\n--- 결과 ---")
    print(f"변경: {changed}건 / 실패: {len(failed)}건")
    if failed:
        print(f"실패 ID: {failed}")
        sys.exit(1)
    print("완료.")


if __name__ == "__main__":
    main()
