"""
태깅 파이프라인 CLI (Anthropic Message Batches 버전).

JSON 콘텐츠를 읽어 → QC 게이트 → Anthropic Message Batches로 일괄 태깅(모든 토큰 50% 할인,
비동기) → quality 사전 필터 → OpenAI 임베딩(건별) → DB 적재(건별 트랜잭션).

코어 로직은 `app.tagging.ingest.ingest_items`로 분리되어 있고, 이 스크립트는 얇은 CLI 래퍼다.
(스케줄 크롤 파이프라인도 같은 `ingest_items`를 import해 적재한다 — 자가복제 일관성.)

설계 메모:
- 태깅만 배치로 보낸다(비싼 단계). 임베딩/적재는 배치 결과 수거 후 건별 동기 처리.
- 배치는 비동기라 보통 1시간 내(최대 24h) 완료될 때까지 폴링한다.
- 적재는 **항목별 트랜잭션**으로 분리한다. 한 건이 실패해도 배치 전체가 롤백되지 않는다.
- 폴링/수거 중 일시적 연결오류(네트워크 블립)는 재시도한다. 한 번 끊겨도 전체가 죽지 않는다.
- 중간에 끊겼다면 --batch-id로 같은 배치에 재접속해 재태깅 없이 이어서 수거/적재한다.
  (이때 json_path는 제출 때와 동일해야 한다. custom_id=item-<index>가 items[index]에 대응하기 때문.)
- 실시간(업로드 즉시) 태깅이 필요하면 app.tagging.tagger.tag_content()를 직접 쓴다.

실행:
    cd backend
    python scripts/run_tagging_pipeline.py ../../data/huggingface_20260531.json
    python scripts/run_tagging_pipeline.py <json> --limit 50
    # 끊긴 배치 이어받기 (재태깅 없음):
    python scripts/run_tagging_pipeline.py <json> --batch-id msgbatch_xxx
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tagging.ingest import ingest_items

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", help="입력 JSON 파일 경로 (제출 때와 동일해야 함)")
    parser.add_argument("--limit", type=int, default=None, help="처리할 최대 건수")
    parser.add_argument(
        "--batch-id",
        default=None,
        help="기존 배치 ID로 재접속(재태깅 없이 수거/적재만). 끊긴 작업 이어받기용.",
    )
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
    if not items:
        sys.exit("입력 항목이 없습니다.")

    anthropic_client = anthropic.Anthropic(api_key=anthropic_key)
    openai_client = OpenAI(api_key=openai_key)
    engine = create_engine(db_url)

    # QC 게이트는 ingest_items 안에서 동일하게 적용된다(결정적 → --batch-id 정렬 보존).
    # limit은 이미 위에서 잘라 넘기므로 ingest_items에는 전달하지 않는다(이중 적용 방지).
    stats = ingest_items(
        items,
        anthropic_client,
        openai_client,
        engine,
        batch_id=args.batch_id,
    )

    if stats["qc_passed"] == 0:
        sys.exit("QC 게이트 통과 항목이 없습니다.")

    print(
        f"\n--- 완료 ---\n"
        f"적재: {stats['inserted']}건 / quality 필터: {stats['skipped_quality']}건 / "
        f"URL 중복: {stats['skipped_dup']}건 / "
        f"태깅 실패: {stats['tag_failed']}건 / 적재 오류: {stats['load_failed']}건"
    )


if __name__ == "__main__":
    main()
