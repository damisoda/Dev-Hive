"""HIVE-33: 사용자 업로드 레이어.

사용자가 올린 글(제목/본문, 선택 URL)을 기존 파이프라인으로 흘려보낸다:
  태깅(tagger, Haiku) → 임베딩(embedder, OpenAI) → 적재(loader) → Auto-HKG 편입(HIVE-21)

결과로 '기존 노드 편입' 또는 '새 하위/최상위 노드 생성'을 반환한다 — 올린 글이 그래프에
편입되는 데모 클라이맥스. 진하 파이프라인(tagger/embedder/loader)을 그대로 재사용한다.
"""
import uuid
from datetime import datetime, timezone

import anthropic
from openai import OpenAI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.crawler.qc_gate import qc_gate
from app.graph.auto_hkg import _node_centroids, _node_info, expand_one
from app.tagging.embedder import embed_content
from app.tagging.loader import load_content
from app.tagging.synthesizer import synthesize
from app.tagging.tagger import tag_content


# 사용자 업로드 품질 하한 — 크롤(loader 기본 0.5)보다 완화. 짧은 경험글은 받되 명백한 junk는 거름. (튜닝 가능)
USER_MIN_QUALITY = 0.3


class UploadError(Exception):
    """업로드 처리 실패(키 부재 / 품질 미달 / URL 중복 등) — 엔드포인트에서 422로 변환."""


def upload_user_content(
    title: str,
    body: str,
    url: str | None,
    user_id: int | None,
    db: Session,
) -> dict:
    """업로드 콘텐츠를 파이프라인에 태워 그래프에 편입하고 결과를 반환한다."""
    if not settings.anthropic_api_key:
        raise UploadError("ANTHROPIC_API_KEY 미설정 — 태깅/Auto-HKG 불가")
    if not settings.openai_api_key:
        raise UploadError("OPENAI_API_KEY 미설정 — 임베딩 불가")

    item = {
        "title": title,
        "body": body,
        # 사용자 글은 URL이 없을 수 있어 충돌 없는 합성 URL 부여(loader가 url UNIQUE 사용)
        "url": url or f"user://{user_id or 'anon'}/{uuid.uuid4().hex[:12]}",
        "source": "user",
        "author_name": None,
        "engagement": {"likes": 0, "comments": 0},
        # 크롤 경로와 동일하게 ISO 문자열로 — item은 tagger에서 json.dumps되므로
        # datetime 객체면 직렬화 실패한다. loader는 문자열을 그대로 TIMESTAMP에 적재.
        "published_at": datetime.now(timezone.utc).isoformat(),
    }

    # QC 게이트(태깅·임베딩 비용 전). 유저 경로는 NSFW·빈본문만 적용(소스/별/서브레딧 우회).
    passed, _report = qc_gate([item], expected_source="user")
    if not passed:
        reason = next(iter(_report["by_reason"]), "거부됨")
        raise UploadError(f"업로드가 품질 게이트에서 거부됐어요 (사유: {reason}).")

    anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    openai_client = OpenAI(api_key=settings.openai_api_key)

    tags = tag_content(item, anthropic_client)
    # 가공(태깅 후·적재 전): content_type별 카드 생성. 실패(None)는 비차단 — 가공 없이 적재.
    try:
        synthesis = synthesize(item, tags, anthropic_client)
    except Exception:
        synthesis = None
    # 임베딩은 원문 고정(가공본 임베딩 X). 가공본은 synthesis 컬럼에만 저장.
    embedding = embed_content(item, openai_client)

    conn = db.connection()
    # 사용자 업로드는 크롤(0.5)보다 완화된 품질 하한 적용(HIVE-33)
    content_id = load_content(
        item, tags, embedding, conn, min_quality=USER_MIN_QUALITY, synthesis=synthesis
    )
    if content_id is None:
        q = float(tags.get("quality_score", 0.0))
        if q < USER_MIN_QUALITY:
            raise UploadError(f"품질 점수가 너무 낮아 등록되지 않았어요 ({q:.2f} < {USER_MIN_QUALITY}).")
        raise UploadError("이미 등록된 URL이에요 (중복).")

    # loader가 채우지 않는 uploaded_by 기록(기여 스트림용)
    if user_id is not None:
        conn.execute(
            text("UPDATE content SET uploaded_by = :uid WHERE id = :cid"),
            {"uid": user_id, "cid": content_id},
        )

    # Auto-HKG 편입 — 방금 적재한 행을 DB 형식 그대로 다시 읽어 expand_one에 전달(형식 일치)
    centroids = _node_centroids(conn)
    info = _node_info(conn)
    row = conn.execute(
        text("SELECT id, title, tags, difficulty, text_embedding FROM content WHERE id = :cid"),
        {"cid": content_id},
    ).fetchone()
    res = expand_one(dict(row._mapping), centroids, info, conn, anthropic_client)
    db.commit()

    node_id = res.get("node_id")
    node_name = info.get(node_id, {}).get("name") if node_id is not None else None
    return {
        "content_id": content_id,
        "title": title,
        "action": res["action"],                       # existing / new_sub / new_top / skipped
        "node_id": node_id,
        "node_name": node_name,
        "is_new_node": res["action"] in ("new_sub", "new_top"),
        "difficulty": tags.get("difficulty"),
        "content_type": tags.get("content_type"),
    }
