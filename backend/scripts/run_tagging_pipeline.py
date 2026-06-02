"""
태깅 파이프라인 (Anthropic Message Batches 버전).

JSON 콘텐츠를 읽어 → Anthropic Message Batches로 일괄 태깅(모든 토큰 50% 할인, 비동기)
→ quality 사전 필터 → OpenAI 임베딩(건별) → DB 적재(건별 트랜잭션).

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
import os
import re
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tagging.tagger import MODEL, _SYSTEM_PROMPT
from app.tagging.embedder import embed_content
from app.tagging.loader import load_content, QUALITY_THRESHOLD

POLL_INTERVAL = 30  # 배치 상태 폴링 간격(초)
TRANSIENT = (anthropic.APIConnectionError, anthropic.APIStatusError)  # 재시도 대상 일시 오류
COLLECT_RETRIES = 5  # 결과 수거 재시도 횟수


def _parse_tags(text: str) -> dict:
    """Haiku 응답 텍스트에서 코드블록을 제거하고 JSON으로 파싱한다."""
    raw = re.sub(r"^```json\s*", "", text.strip())
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _submit_batch(client: anthropic.Anthropic, items: list[dict]):
    """items를 태깅 요청 배치로 제출한다. custom_id는 'item-<index>'."""
    requests = [
        {
            "custom_id": f"item-{i}",
            "params": {
                "model": MODEL,
                "max_tokens": 512,
                "system": _SYSTEM_PROMPT,
                "messages": [
                    {"role": "user", "content": json.dumps(item, ensure_ascii=False)}
                ],
            },
        }
        for i, item in enumerate(items)
    ]
    batch = client.beta.messages.batches.create(requests=requests)
    print(f"배치 제출 완료: {batch.id} ({len(requests)}건) — 50% 할인 적용")
    return batch.id


def _wait_for_batch(client: anthropic.Anthropic, batch_id: str) -> None:
    """배치가 끝날 때까지(ended) 폴링한다. 일시적 연결오류는 재시도한다."""
    while True:
        try:
            batch = client.beta.messages.batches.retrieve(batch_id)
        except TRANSIENT as e:
            print(f"  폴링 일시 오류({type(e).__name__}) — {POLL_INTERVAL}s 후 재시도")
            time.sleep(POLL_INTERVAL)
            continue
        c = batch.request_counts
        print(
            f"  상태={batch.processing_status} "
            f"(처리중 {c.processing} / 성공 {c.succeeded} / 오류 {c.errored} / 취소 {c.canceled} / 만료 {c.expired})"
        )
        if batch.processing_status == "ended":
            return
        time.sleep(POLL_INTERVAL)


def _collect_tags(client: anthropic.Anthropic, batch_id: str) -> tuple[dict[int, dict], int]:
    """배치 결과에서 custom_id별 태그 dict를 수거한다. 일시 오류 시 전체 재시도."""
    for attempt in range(1, COLLECT_RETRIES + 1):
        tags_by_idx: dict[int, dict] = {}
        failed = 0
        try:
            for result in client.beta.messages.batches.results(batch_id):
                try:
                    idx = int(result.custom_id.split("-", 1)[1])
                except (ValueError, IndexError):
                    failed += 1
                    continue
                if result.result.type == "succeeded":
                    try:
                        text = result.result.message.content[0].text
                        tags_by_idx[idx] = _parse_tags(text)
                    except Exception as e:
                        print(f"[{idx:03d}] 태그 파싱 실패: {e}")
                        failed += 1
                else:
                    print(f"[{idx:03d}] 태깅 실패: {result.result.type}")
                    failed += 1
            return tags_by_idx, failed
        except TRANSIENT as e:
            print(f"  결과 수거 일시 오류({type(e).__name__}) — 재시도 {attempt}/{COLLECT_RETRIES}")
            time.sleep(POLL_INTERVAL)
    raise RuntimeError("결과 수거 실패: 일시 오류 재시도 한도 초과")


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

    # 1. 태깅 배치 — 신규 제출 또는 기존 배치 재접속
    if args.batch_id:
        batch_id = args.batch_id
        print(f"기존 배치 재접속: {batch_id} (대상 {len(items)}건, 재태깅 없음)\n")
    else:
        print(f"처리 대상: {len(items)}건 (Message Batches, 50% 할인)\n")
        batch_id = _submit_batch(anthropic_client, items)

    _wait_for_batch(anthropic_client, batch_id)

    # 2. 결과 수거 (index -> tags)
    tags_by_idx, tag_failed = _collect_tags(anthropic_client, batch_id)

    # 3. 임베딩 + 적재 (건별 트랜잭션 — 한 건 실패가 배치 전체를 롤백하지 않음)
    inserted = skipped_quality = skipped_dup = load_failed = 0
    for i, item in enumerate(items):
        title = str(item.get("title", ""))[:60]
        tags = tags_by_idx.get(i)
        if tags is None:
            continue  # 태깅 실패분은 _collect_tags에서 카운트됨

        try:
            quality = tags.get("quality_score", 0.0)
            if not isinstance(quality, (int, float)) or quality < QUALITY_THRESHOLD:
                print(f"[{i:03d}] SKIP(quality)  {title}")
                skipped_quality += 1
                continue

            embedding = embed_content(item, openai_client)

            with engine.begin() as conn:
                content_id = load_content(item, tags, embedding, conn)

            if content_id is None:
                print(f"[{i:03d}] SKIP(dup url)  {title}")
                skipped_dup += 1
            else:
                print(f"[{i:03d}] OK  id={content_id}  q={quality:.2f}  {title}")
                inserted += 1

        except Exception as e:
            print(f"[{i:03d}] ERROR  {title}\n      {e}")
            load_failed += 1

    print(
        f"\n--- 완료 ---\n"
        f"적재: {inserted}건 / quality 필터: {skipped_quality}건 / URL 중복: {skipped_dup}건 / "
        f"태깅 실패: {tag_failed}건 / 적재 오류: {load_failed}건"
    )


if __name__ == "__main__":
    main()
