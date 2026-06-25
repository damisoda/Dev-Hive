"""HIVE-80: synthesis NULL 항목 일괄 warm.

재태깅 후 synthesis가 NULL인 콘텐츠를 Haiku로 일괄 생성·캐시한다.
기본 대상: synthesis IS NULL (--all 없으면 재태깅분 우선).

실행:
    cd backend
    python scripts/warm_synthesis.py --dry-run   # 대상 건수 확인
    python scripts/warm_synthesis.py             # 실행
    python scripts/warm_synthesis.py --all       # synthesis=NULL 전체 (재태깅 외 포함)
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
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import anthropic
from sqlalchemy import create_engine, text

from app.services.lazy_synthesis import ensure_synthesis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SLEEP = float(os.getenv("WARM_SYNTHESIS_SLEEP", "0.5"))


def main() -> None:
    parser = argparse.ArgumentParser(description="HIVE-80 synthesis warm")
    parser.add_argument("--dry-run", action="store_true", help="대상 건수만 출력, DB 변경 없음")
    parser.add_argument("--all", action="store_true", help="synthesis=NULL 전체 대상 (기본: 재태깅분만)")
    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        sys.exit("DATABASE_URL 환경변수가 필요합니다.")

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_key and not args.dry_run:
        sys.exit("ANTHROPIC_API_KEY 환경변수가 필요합니다.")

    engine = create_engine(db_url)

    with engine.connect() as conn:
        # 재태깅분: content_type이 유효 5타입이고 synthesis NULL
        # --all: synthesis NULL 전체
        if args.all:
            rows = conn.execute(
                text(
                    "SELECT id, content_type FROM content "
                    "WHERE synthesis IS NULL "
                    "ORDER BY id"
                )
            ).fetchall()
        else:
            rows = conn.execute(
                text(
                    "SELECT id, content_type FROM content "
                    "WHERE synthesis IS NULL "
                    "  AND content_type IN ('experience','tutorial','concept','tool','discussion') "
                    "ORDER BY id"
                )
            ).fetchall()

    total = len(rows)
    print(f"\n대상: {total}건")

    if args.dry_run:
        print(f"[DRY-RUN] 변경 없음.")
        return

    if total == 0:
        print("warm 대상 없음 — 완료.")
        return

    client = anthropic.Anthropic(api_key=anthropic_key)
    success, failed = 0, []

    from sqlalchemy.orm import Session
    with Session(engine) as db:
        for i, row in enumerate(rows, 1):
            try:
                card = ensure_synthesis(row.id, db, client)
                if card is not None:
                    success += 1
                    logger.info("[%d/%d] id=%s type=%s → 완료", i, total, row.id, row.content_type)
                else:
                    failed.append(row.id)
                    logger.warning("[%d/%d] id=%s type=%s → None (미지원 타입 또는 생성 실패)", i, total, row.id, row.content_type)
            except Exception:
                failed.append(row.id)
                logger.exception("[%d/%d] id=%s → 예외", i, total, row.id)
            time.sleep(BATCH_SLEEP)

    print(f"\n--- 결과 ---")
    print(f"성공: {success}건 / 실패·스킵: {len(failed)}건")
    if failed:
        print(f"실패 ID: {failed}")
        sys.exit(1)
    print("완료.")


if __name__ == "__main__":
    main()
