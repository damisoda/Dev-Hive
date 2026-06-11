# models — DB 모델

SQLAlchemy 모델 정의. `db/schema.sql`과 대응한다.

## 모델 파일
- `base.py` — declarative Base
- `user.py` — User (`users`)
- `content.py` — Content (`content` — synthesis JSONB, text_embedding 1536, graph_embedding 256 포함)
- `mapping.py` — ContentNodeMapping (`content_node_mapping`)
- `event.py` — UserReadEvent (`user_read_events`)
- `feedback.py` — UserContentFeedback (`user_content_feedback`, HIVE-37)

## 스키마 테이블 7종
`users`, `content`, `curriculum_nodes`, `content_node_mapping`, `user_read_events`,
`user_content_feedback`, `node_links`

이 중 `curriculum_nodes`와 `node_links`는 ORM 모델 없이 raw SQL(`sqlalchemy.text`)로 접근한다
(graph/builder.py, auto_hkg.py 등).

스키마 원본은 `db/schema.sql`이며, 모델은 그것을 ORM으로 표현한 것이다.
스키마 변경 시 `db/schema.sql`을 먼저 수정하고 모델을 맞춘다.
