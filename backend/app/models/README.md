# models — DB 모델

SQLAlchemy 모델 정의. `db/schema.sql`과 1:1 대응한다.

## 테이블 6종
- `user.py` — User
- `content.py` — Content
- `curriculum.py` — CurriculumNode, NodeLink
- `mapping.py` — ContentNodeMapping
- `event.py` — UserReadEvent

스키마 원본은 `db/schema.sql`이며, 모델은 그것을 ORM으로 표현한 것이다.
스키마 변경 시 `db/schema.sql`을 먼저 수정하고 모델을 맞춘다.
