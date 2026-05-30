"""데모 시드 콘텐츠에 OpenAI 임베딩을 생성하여 적재한다.

text_embedding이 NULL인 콘텐츠를 찾아 text-embedding-3-small로 1536차원 벡터를
생성하고 pgvector 컬럼에 UPDATE한다. 1회성 부트스트랩 스크립트.

실행:
    cd backend
    python scripts/embed_seed.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine, text

# 레포 루트의 .env를 로드
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

api_key = os.getenv("OPENAI_API_KEY")
db_url = os.getenv("DATABASE_URL")
if not api_key or not db_url:
    sys.exit("OPENAI_API_KEY / DATABASE_URL 환경변수가 필요합니다.")

client = OpenAI(api_key=api_key)
engine = create_engine(db_url)

EMBED_MODEL = "text-embedding-3-small"


def main() -> None:
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, title, body FROM content WHERE text_embedding IS NULL ORDER BY id")
        ).fetchall()
        if not rows:
            print("임베딩 대상 없음. 모두 채워져 있습니다.")
            return

        print(f"임베딩 생성 대상: {len(rows)}건")
        for i, row in enumerate(rows, 1):
            text_input = f"{row.title}\n\n{row.body}"
            response = client.embeddings.create(model=EMBED_MODEL, input=text_input)
            embedding = response.data[0].embedding

            # pgvector는 '[v1,v2,...]' 형식의 문자열 INSERT 허용
            conn.execute(
                text("UPDATE content SET text_embedding = (:emb)::vector WHERE id = :id"),
                {"emb": str(embedding), "id": row.id},
            )
            print(f"  [{i}/{len(rows)}] id={row.id}: {row.title[:50]}")

        print(f"\n완료. 총 {len(rows)}건 임베딩 적재")


if __name__ == "__main__":
    main()
