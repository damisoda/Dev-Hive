"""HIVE-49: 추천 확정 시 lazy 가공 + 캐시.

가공(synthesis)은 임베딩/클러스터링/추천 스코어링에 쓰이지 않는 **표시 전용** 산출물이다.
그래서 크롤 적재 때 전량 생성(롱테일 낭비)하지 않고, '추천으로 확정되어 실제 노출될 때'만
생성한다. 한 번 만들면 content.synthesis(JSONB)에 저장해 다음부터 재사용한다(아이템당 1회).

유저 업로드(HIVE-33)는 즉시 피드백이 기여 동기라 upload.py에서 eager 유지 — 여기 적용 대상 아님.
"""
import json
import logging

import anthropic
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.tagging.synthesizer import synthesize

logger = logging.getLogger(__name__)


def ensure_synthesis(
    content_id: int,
    db: Session,
    client: anthropic.Anthropic | None,
    force: bool = False,
) -> dict | None:
    """content의 가공 카드를 반환한다. 없으면 생성·저장(lazy + cache). 실패 시 None(graceful).

    - synthesis가 이미 있으면 그대로 반환(캐시 히트).
    - force=True면 기존 캐시를 무시하고 재생성한다(HIVE-66: title_ko 등 새 필드 채우기 배치용).
    - client(키) 없으면 생성하지 않고 기존 캐시(있으면)/None(추천은 계속).
    - synthesize가 None(미지원 content_type 등)이면 저장하지 않고 None.
    """
    row = db.execute(
        text("SELECT title, body, content_type, synthesis FROM content WHERE id = :cid"),
        {"cid": content_id},
    ).fetchone()
    if row is None:
        return None
    if row.synthesis is not None and not force:
        return row.synthesis  # 캐시 히트 (JSONB → dict)
    if client is None:
        return row.synthesis  # 키 없음 → 생성 불가. 기존 캐시 있으면 그대로, 없으면 None

    item = {"title": row.title, "body": row.body or ""}
    tags = {"content_type": row.content_type}
    try:
        card = synthesize(item, tags, client)
    except Exception:
        logger.exception("lazy 가공 실패 content_id=%s", content_id)
        return None

    if card is not None:
        db.execute(
            text("UPDATE content SET synthesis = (:s)::jsonb WHERE id = :cid"),
            {"s": json.dumps(card, ensure_ascii=False), "cid": content_id},
        )
        db.commit()
    return card
