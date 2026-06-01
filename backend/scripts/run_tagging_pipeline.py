"""
태깅 파이프라인 실행 스크립트.
JSON 파일에서 콘텐츠를 읽어 태깅 → 임베딩 → DB 적재를 순서대로 수행한다.

실행:
    cd backend
    python scripts/run_tagging_pipeline.py ../../data/huggingface_20260531.json
    python scripts/run_tagging_pipeline.py ../../data/hackernews_20260531.json --limit 50
"""
import argparse
import json
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine

import os

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tagging.tagger import tag_content
from app.tagging.embedder import embed_content
from app.tagging.loader import load_content, QUALITY_THRESHOLD


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", help="입력 JSON 파일 경로")
    parser.add_argument("--limit", type=int, default=None, help="처리할 최대 건수")
    args = parser.parse_args()

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    db_url = os.getenv("DATABASE_URL")

    if not anthropic_key:
        sys.exit("ANTHROPIC_API_KEY 환경변수가 필요합니다.")
    if not openai_key:
        sys.exit("OPENAI_API_KEY 환경변수가 필요합니다.")
    if not db_url:
        sys.exit("DATABASE_URL 환경변수가 필요합니다.")

    items = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    if args.limit:
        items = items[: args.limit]

    anthropic_client = anthropic.Anthropic(api_key=anthropic_key)
    openai_client = OpenAI(api_key=openai_key)
    engine = create_engine(db_url)

    inserted = skipped_quality = skipped_dup = failed = 0

    print(f"처리 대상: {len(items)}건\n")

    with engine.begin() as conn:
        for i, item in enumerate(items, 1):
            title = item.get("title", "")[:60]
            try:
                # 1. 태깅
                tags = tag_content(item, anthropic_client)

                # 2. quality_score 사전 필터
                if tags.get("quality_score", 0.0) < QUALITY_THRESHOLD:
                    print(f"[{i:03d}] SKIP(quality)  {title}")
                    skipped_quality += 1
                    continue

                # 3. 임베딩
                embedding = embed_content(item, openai_client)

                # 4. DB 적재
                content_id = load_content(item, tags, embedding, conn)
                if content_id is None:
                    print(f"[{i:03d}] SKIP(dup url)  {title}")
                    skipped_dup += 1
                else:
                    print(f"[{i:03d}] OK  id={content_id}  q={tags['quality_score']:.2f}  {title}")
                    inserted += 1

            except Exception as e:
                print(f"[{i:03d}] ERROR  {title}\n      {e}")
                failed += 1

    print(
        f"\n--- 완료 ---\n"
        f"적재: {inserted}건 / quality 필터: {skipped_quality}건 / "
        f"URL 중복: {skipped_dup}건 / 오류: {failed}건"
    )


if __name__ == "__main__":
    main()
