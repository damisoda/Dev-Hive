"""
콘텐츠 적재 모듈.
태깅 결과 + 임베딩을 받아 content 테이블에 INSERT하고
relevance >= 0.5인 대주제를 content_node_mapping에 매핑한다.

quality_score < 0.5인 콘텐츠는 적재하지 않는다.
"""
from sqlalchemy import text
from sqlalchemy.engine import Connection

# demo_seed.sql 기준 node_id 고정 매핑
# curriculum_nodes 시드: id 1~7이 대주제 순서대로 들어가 있음
NODE_ID_MAP: dict[str, int] = {
    "프롬프트 엔지니어링": 1,
    "Agentic AI": 2,
    "멀티모달 AI": 3,
    "RAG & 지식 관리": 4,
    "오픈소스 AI": 5,
    "AI 워크플로우 & 자동화": 6,
    "AI 엔지니어링": 7,
}

RELEVANCE_THRESHOLD = 0.5
QUALITY_THRESHOLD = 0.5


def load_content(
    item: dict,
    tags: dict,
    embedding: list[float],
    conn: Connection,
) -> int | None:
    """
    content 테이블에 INSERT하고 content_node_mapping을 추가한다.

    Returns:
        신규 삽입된 content.id. quality_score < 0.5이거나 기존 URL upsert이면 None 반환.
    """
    quality_score = tags.get("quality_score", 0.0)
    if quality_score < QUALITY_THRESHOLD:
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
    relevance = tags.get("relevance", {})
    for topic, score in relevance.items():
        if score >= RELEVANCE_THRESHOLD:
            node_id = NODE_ID_MAP.get(topic)
            if node_id is None:
                continue
            conn.execute(
                text("""
                    INSERT INTO content_node_mapping (content_id, node_id, relevance_score)
                    VALUES (:content_id, :node_id, :score)
                    ON CONFLICT DO NOTHING
                """),
                {"content_id": content_id, "node_id": node_id, "score": score},
            )

    return content_id
