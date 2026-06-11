"""적재(ingest) 코어 — QC 게이트 → 배치 태깅 → 가공(synthesis) → 임베딩 → 건별 트랜잭션 적재.

`scripts/run_tagging_pipeline.py`(CLI)와 스케줄 크롤 파이프라인(`run_crawler.run_pipeline`)이
공유하는 재사용 가능한 진입점이다. CLI는 `--batch-id` 재접속(끊긴 배치 이어받기)까지 지원하지만,
스케줄 호출은 happy path(제출→대기→수거→임베딩→적재)만 쓴다.

설계 메모(기존 파이프라인 그대로):
- 태깅만 배치로 보낸다(비싼 단계). 임베딩/적재는 배치 결과 수거 후 건별 동기 처리.
- QC 게이트는 결정적(pure)이라 --batch-id 재접속 때도 동일 결과
  → custom_id=item-<index> 정렬 유지(items[index] ↔ tags_by_idx[index]).
- 적재는 **항목별 트랜잭션**으로 분리한다. 한 건 실패가 배치 전체를 롤백하지 않는다.
- 폴링/수거 중 일시적 연결오류(네트워크 블립)는 재시도한다.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import anthropic
from openai import OpenAI
from sqlalchemy.engine import Engine

from app.crawler.qc_gate import qc_gate
from app.tagging.embedder import embed_content
from app.tagging.loader import QUALITY_THRESHOLD, load_content
from app.tagging.tagger import MODEL, _SYSTEM_PROMPT

logger = logging.getLogger(__name__)

POLL_INTERVAL = 30  # 배치 상태 폴링 간격(초)
TRANSIENT = (anthropic.APIConnectionError, anthropic.APIStatusError)  # 재시도 대상 일시 오류
COLLECT_RETRIES = 5  # 결과 수거 재시도 횟수
# 배치 대기 상한(초). Anthropic 배치 SLA가 24h라 기본 26h로 약간 여유를 둔다.
# 초과 시 TimeoutError → 스케줄 경로는 _maybe_ingest의 except가 삼켜 크롤을 유지하고,
# CLI는 트레이스백으로 운영자에게 노출된다(무한 폴링으로 잡 스레드가 영구 점유되는 것 방지).
MAX_WAIT_SECONDS = int(os.getenv("BATCH_MAX_WAIT_SECONDS", str(26 * 3600)))


def _parse_tags(text: str) -> dict:
    """Haiku 응답 텍스트에서 코드블록을 제거하고 JSON으로 파싱한다."""
    raw = re.sub(r"^```json\s*", "", text.strip())
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def submit_batch(client: anthropic.Anthropic, items: list[dict]) -> str:
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
    logger.info("배치 제출 완료: %s (%s건) — 50%% 할인 적용", batch.id, len(requests))
    return batch.id


def wait_for_batch(client: anthropic.Anthropic, batch_id: str) -> None:
    """배치가 끝날 때까지(ended) 폴링한다. 일시적 연결오류는 재시도한다.

    MAX_WAIT_SECONDS를 넘으면 TimeoutError를 던져 무한 폴링을 막는다(잡 스레드 영구 점유 방지).
    """
    start = time.monotonic()

    def _check_timeout() -> None:
        if time.monotonic() - start > MAX_WAIT_SECONDS:
            raise TimeoutError(f"배치 대기 한도 초과({MAX_WAIT_SECONDS}s): {batch_id}")

    while True:
        try:
            batch = client.beta.messages.batches.retrieve(batch_id)
        except TRANSIENT as e:
            logger.info("  폴링 일시 오류(%s) — %ss 후 재시도", type(e).__name__, POLL_INTERVAL)
            _check_timeout()
            time.sleep(POLL_INTERVAL)
            continue
        c = batch.request_counts
        logger.info(
            "  상태=%s (처리중 %s / 성공 %s / 오류 %s / 취소 %s / 만료 %s)",
            batch.processing_status, c.processing, c.succeeded, c.errored, c.canceled, c.expired,
        )
        if batch.processing_status == "ended":
            return
        _check_timeout()
        time.sleep(POLL_INTERVAL)


def collect_tags(client: anthropic.Anthropic, batch_id: str) -> tuple[dict[int, dict], int]:
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
                        logger.info("[%03d] 태그 파싱 실패: %s", idx, e)
                        failed += 1
                else:
                    logger.info("[%03d] 태깅 실패: %s", idx, result.result.type)
                    failed += 1
            return tags_by_idx, failed
        except TRANSIENT as e:
            logger.info("  결과 수거 일시 오류(%s) — 재시도 %s/%s", type(e).__name__, attempt, COLLECT_RETRIES)
            time.sleep(POLL_INTERVAL)
    raise RuntimeError("결과 수거 실패: 일시 오류 재시도 한도 초과")


def ingest_items(
    items: list[dict],
    anthropic_client: anthropic.Anthropic,
    openai_client: OpenAI,
    engine: Engine,
    *,
    limit: int | None = None,
    batch_id: str | None = None,
) -> dict[str, Any]:
    """QC 게이트 → 배치 태깅 → 임베딩 → 건별 트랜잭션 적재.

    Args:
        items: 정규화된 dict 리스트(`ContentSchema.to_dict` 형태).
        anthropic_client / openai_client: 태깅·임베딩 클라이언트.
        engine: SQLAlchemy 엔진(건별 트랜잭션용).
        limit: 처리할 최대 건수(None=전체).
        batch_id: 지정 시 기존 배치 재접속(재태깅 없이 수거/적재만). 끊긴 작업 이어받기용.
                  None이면 신규 배치 제출(스케줄 호출의 happy path).

    Returns:
        통계 dict:
          {
            "total", "qc_passed", "inserted", "skipped_quality",
            "skipped_dup", "tag_failed", "load_failed", "qc_report"
          }

    중요: items와 tags_by_idx 정렬을 유지하려면 QC 게이트 적용 **후**의 items를 인덱싱한다.
          QC는 결정적이므로 --batch-id 재접속 때도 동일하게 줄어들어 정렬이 보존된다.
    """
    if limit:
        items = items[:limit]

    # QC 게이트 — 정규화 후·태깅 전. 명백한 junk를 LLM 비용 들기 전에 컷(무료 휴리스틱).
    items, qc_report = qc_gate(items)
    logger.info("QC 게이트: %s", json.dumps(qc_report, ensure_ascii=False))

    stats: dict[str, Any] = {
        "total": qc_report["total"],
        "qc_passed": len(items),
        "inserted": 0,
        "skipped_quality": 0,
        "skipped_dup": 0,
        "tag_failed": 0,
        "load_failed": 0,
        "qc_report": qc_report,
    }
    if not items:
        logger.info("QC 게이트 통과 항목이 없습니다.")
        return stats

    # 1. 태깅 배치 — 신규 제출 또는 기존 배치 재접속
    if batch_id:
        logger.info("기존 배치 재접속: %s (대상 %s건, 재태깅 없음)", batch_id, len(items))
    else:
        logger.info("처리 대상: %s건 (Message Batches, 50%% 할인)", len(items))
        batch_id = submit_batch(anthropic_client, items)

    wait_for_batch(anthropic_client, batch_id)

    # 2. 결과 수거 (index -> tags)
    tags_by_idx, tag_failed = collect_tags(anthropic_client, batch_id)
    stats["tag_failed"] = tag_failed

    # 3. 임베딩 + 적재 (건별 트랜잭션 — 한 건 실패가 배치 전체를 롤백하지 않음)
    for i, item in enumerate(items):
        title = str(item.get("title", ""))[:60]
        tags = tags_by_idx.get(i)
        if tags is None:
            continue  # 태깅 실패분은 collect_tags에서 카운트됨

        try:
            quality = tags.get("quality_score", 0.0)
            if not isinstance(quality, (int, float)) or quality < QUALITY_THRESHOLD:
                logger.info("[%03d] SKIP(quality)  %s", i, title)
                stats["skipped_quality"] += 1
                continue

            # 가공(synthesis)은 적재 시 하지 않는다(HIVE-49 lazy). 표시 전용이라 롱테일까지
            # 미리 만들 필요가 없고, '추천으로 확정되어 노출될 때' lazy 생성·캐시한다.
            # 임베딩은 원문 고정.
            embedding = embed_content(item, openai_client)

            with engine.begin() as conn:
                content_id = load_content(item, tags, embedding, conn)

            if content_id is None:
                logger.info("[%03d] SKIP(dup url)  %s", i, title)
                stats["skipped_dup"] += 1
            else:
                logger.info("[%03d] OK  id=%s  q=%.2f  %s", i, content_id, quality, title)
                stats["inserted"] += 1

        except Exception as e:
            logger.info("[%03d] ERROR  %s\n      %s", i, title, e)
            stats["load_failed"] += 1

    logger.info(
        "--- 적재 완료 --- 적재:%s건 / quality:%s건 / URL중복:%s건 / 태깅실패:%s건 / 적재오류:%s건",
        stats["inserted"], stats["skipped_quality"], stats["skipped_dup"],
        stats["tag_failed"], stats["load_failed"],
    )
    return stats
