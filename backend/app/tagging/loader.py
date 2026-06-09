"""
콘텐츠 적재 모듈.
태깅 결과 + 임베딩을 받아 content 테이블에 INSERT하고
relevance >= 0.5인 대주제를 content_node_mapping에 매핑한다.

quality_score < 0.5인 콘텐츠는 적재하지 않는다.
"""
from sqlalchemy import text
from sqlalchemy.engine import Connection

RELEVANCE_THRESHOLD = 0.5
QUALITY_THRESHOLD = 0.5


def load_content(
    item: dict,
    tags: dict,
    embedding: list[float],
    conn: Connection,
    min_quality: float = QUALITY_THRESHOLD,
) -> int | None:
    """
    content 테이블에 INSERT하고 content_node_mapping을 추가한다.

    min_quality: 적재 최소 품질 점수(기본 0.5, 크롤 경로 유지).
                 사용자 업로드(HIVE-33)는 더 낮은 값(예: 0.3)을 넘겨 기준을 완화한다.

    Returns:
        신규 삽입된 content.id. quality_score < min_quality이거나 기존 URL(중복 upsert)이면 None 반환.
    """
    quality_score = tags.get("quality_score", 0.0)
    if quality_score < min_quality:
        return None

    # content INSERT.
    # URL 중복 시 body/text_embedding은 건드리지 않고 engagement만 최신 수치로 갱신한다.
    row = conn.execute(
        text("""
            INSERT INTO content (
                title, body, url, source, author_name,
                language, difficulty, quality_score, content_type,
                text_embedding, engagement_likes, engagement_comments, published_at
            ) VALUES (
                :title, :body, :url, :source, :author_name,
                :language, :difficulty, :quality_score, :content_type,
                (:embedding)::vector, :likes, :comments, :published_at
            )
            ON CONFLICT (url) DO UPDATE SET
                engagement_likes = EXCLUDED.engagement_likes,
                engagement_comments = EXCLUDED.engagement_comments,
                crawled_at = NOW()
            RETURNING id, (xmax = 0) AS inserted
        """),
        {
            "title": item.get("title", ""),
            "body": item.get("body", ""),
            "url": item.get("url"),
            "source": item.get("source", ""),
            "author_name": item.get("author_name"),
            "language": tags.get("language", "en"),
            "difficulty": tags.get("difficulty"),
            "quality_score": quality_score,
            "content_type": tags.get("content_type"),
            "embedding": str(embedding),
            "likes": item.get("engagement", {}).get("likes", 0),
            "comments": item.get("engagement", {}).get("comments", 0),
            "published_at": item.get("published_at"),
        },
    ).fetchone()

    if row is None:
        return None

    if not row.inserted:
        return None  # 기존 콘텐츠는 engagement만 갱신하고 재매핑/본문 재삽입은 하지 않음

    content_id = row.id

    # content_node_mapping INSERT (relevance >= 0.5인 노드만)
    # 대주제 id를 name으로 동적 조회한다 — 하드코딩(1~7) 제거.
    # → Auto-HKG(HIVE-21)가 추가한 새 노드(하위/최상위)에도 매핑되고,
    #   재시드로 id 순서가 바뀌어도 안전하다.
    relevance = tags.get("relevance", {})
    relevant_topics = [
        topic
        for topic, score in relevance.items()
        if isinstance(score, (int, float)) and score >= RELEVANCE_THRESHOLD
    ]
    if not relevant_topics:
        return content_id

    node_rows = conn.execute(
        text("SELECT id, name FROM curriculum_nodes")
    ).fetchall()
    name_to_id = {r.name: r.id for r in node_rows}

    for topic in relevant_topics:
        node_id = name_to_id.get(topic)
        if node_id is None:
            continue  # 아직 그래프에 없는 주제(태거 enum 밖 등) — 스킵
        conn.execute(
            text("""
                INSERT INTO content_node_mapping (content_id, node_id, relevance_score)
                VALUES (:content_id, :node_id, :score)
                ON CONFLICT DO NOTHING
            """),
            {"content_id": content_id, "node_id": node_id, "score": relevance[topic]},
        )

    return content_id
