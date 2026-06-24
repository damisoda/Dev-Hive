"""HIVE-61: 폐기타입(news/paper) 재태깅 마이그레이션.

content_type IN ('news', 'paper') 행을 Haiku로 재태깅해 5타입으로 강제 분류한다.

AC:
  - content_type IN('news','paper') = 0
  - 재분류 100%, 실패/null = 0
  - --dry-run: 무변경 + 예정 건수 출력
  - 2회차 변경 0 (멱등)
  - 전/후 분포표 출력

실행:
    cd backend
    python scripts/migrate_retag_deprecated_types.py --dry-run
    python scripts/migrate_retag_deprecated_types.py
"""
import argparse
import logging
import os
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tagging.tagger import tag_content

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

DEPRECATED_TYPES = ("news", "paper")
VALID_TYPES = frozenset({"experience", "tutorial", "concept", "tool", "discussion"})
MAX_RETRIES = 3


def print_distribution(conn, label: str) -> None:
    rows = conn.execute(
        text(
            "SELECT COALESCE(content_type, 'NULL') AS ct, COUNT(*) AS cnt "
            "FROM content GROUP BY ct ORDER BY cnt DESC"
        )
    ).fetchall()
    print(f"\n[{label} content_type 분포]")
    print(f"{'타입':<15} {'건수':>6}")
    print("-" * 23)
    for r in rows:
        marker = "  ← 폐기" if r.ct in DEPRECATED_TYPES else ""
        print(f"{r.ct:<15} {r.cnt:>6}{marker}")


def retag_with_retry(item: dict, client: anthropic.Anthropic) -> str | None:
    """Haiku로 재태깅. 유효한 content_type이 나올 때까지 MAX_RETRIES번 재시도."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            tags = tag_content(item, client)
            ct = tags.get("content_type")
            if ct in VALID_TYPES:
                return ct
            logger.warning("유효하지 않은 content_type=%r (시도 %d/%d)", ct, attempt, MAX_RETRIES)
        except Exception as exc:
            logger.warning("태깅 예외 (시도 %d/%d): %s", attempt, MAX_RETRIES, exc)
        if attempt < MAX_RETRIES:
            time.sleep(2 ** attempt)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="HIVE-61 폐기타입 재태깅 마이그레이션")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="DB 변경 없이 예정 건수만 출력한다",
    )
    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        sys.exit("DATABASE_URL 환경변수가 필요합니다.")

    client = None
    if not args.dry_run:
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            sys.exit("ANTHROPIC_API_KEY 환경변수가 필요합니다.")
        client = anthropic.Anthropic(api_key=key)

    engine = create_engine(db_url)

    with engine.connect() as conn:
        print_distribution(conn, "이전")

        rows = conn.execute(
            text(
                "SELECT id, title, body, content_type FROM content "
                "WHERE content_type = ANY(:types)"
            ),
            {"types": list(DEPRECATED_TYPES)},
        ).fetchall()

        target = len(rows)
        print(f"\n재태깅 대상: {target}건")

        if args.dry_run:
            print(f"[DRY-RUN] 변경 없음. 예정 건수: {target}건")
            return

        if target == 0:
            print("재태깅 대상 없음 — 이미 완료됐거나 폐기타입 행이 없습니다.")
            return

        success, failed_ids = 0, []
        for row in rows:
            item = {"title": row.title or "", "body": row.body or ""}
            new_type = retag_with_retry(item, client)
            if new_type is None:
                failed_ids.append(row.id)
                logger.error("재태깅 최종 실패 id=%s old=%s", row.id, row.content_type)
                continue
            conn.execute(
                text("UPDATE content SET content_type = :ct WHERE id = :id"),
                {"ct": new_type, "id": row.id},
            )
            logger.info("재태깅 id=%s  %s → %s", row.id, row.content_type, new_type)
            success += 1

        conn.commit()

        print_distribution(conn, "이후")

        remaining = conn.execute(
            text(
                "SELECT COUNT(*) FROM content WHERE content_type = ANY(:types)"
            ),
            {"types": list(DEPRECATED_TYPES)},
        ).scalar()

        print(f"\n--- 결과 ---")
        print(f"성공: {success}건 / 실패: {len(failed_ids)}건 / 잔여 폐기타입: {remaining}건")

        if failed_ids:
            print(f"실패 ID: {failed_ids}")
            sys.exit(1)
        if remaining > 0:
            print("ERROR: 폐기타입이 남아있습니다.")
            sys.exit(1)

        print("완료 — 폐기타입 0건, 재분류 100%")


if __name__ == "__main__":
    main()
