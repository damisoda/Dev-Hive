"""데모 시드 콘텐츠에 로컬(무료) 임베딩을 생성하여 적재한다.

OpenAI 키가 없을 때를 위한 폴백. sentence-transformers의 all-MiniLM-L6-v2
(384차원, API 키 불필요)로 임베딩을 만든다.

⚠️ 차원 주의
    content.text_embedding 컬럼은 vector(1536)(= OpenAI text-embedding-3-small
    규격)이다. 본 모델은 384차원이므로 **뒤를 0으로 패딩**하여 1536으로 맞춘다.
    코사인 유사도는 제로패딩에 불변이므로 콘텐츠 간 유사도는 그대로 보존된다.

    👉 따라서 추천 단계(HIVE-13)에서 쿼리 임베딩도 **반드시 동일 모델 + 동일
       패딩**으로 생성해야 한다. OpenAI 임베딩(scripts/embed_seed.py)과 혼용하면
       의미가 깨진다. 실제 키 확보 시 OpenAI 버전으로 재생성하는 것을 권장.

설치(메인 requirements와 분리 — torch가 무거워 일반 의존성엔 포함하지 않음):
    pip install sentence-transformers

실행:
    cd backend
    python scripts/embed_seed_local.py
"""

import sys
from pathlib import Path

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sqlalchemy import create_engine, text

import os

# 레포 루트의 .env를 로드 (DATABASE_URL만 사용, API 키 불필요)
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

db_url = os.getenv("DATABASE_URL")
if not db_url:
    sys.exit("DATABASE_URL 환경변수가 필요합니다.")

MODEL_NAME = "all-MiniLM-L6-v2"
TARGET_DIM = 1536  # content.text_embedding 컬럼 차원 (vector(1536))

engine = create_engine(db_url)


def to_pgvector(embedding: list[float]) -> str:
    """모델 출력(384d)을 TARGET_DIM으로 제로패딩해 pgvector 리터럴 문자열로 변환."""
    if len(embedding) > TARGET_DIM:
        raise ValueError(f"임베딩 차원 {len(embedding)} > 컬럼 차원 {TARGET_DIM}")
    padded = list(embedding) + [0.0] * (TARGET_DIM - len(embedding))
    return "[" + ",".join(repr(x) for x in padded) + "]"


def main() -> None:
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, title, body FROM content WHERE text_embedding IS NULL ORDER BY id")
        ).fetchall()
        if not rows:
            print("임베딩 대상 없음. 모두 채워져 있습니다.")
            return

        print(f"모델 로드: {MODEL_NAME} (384d → {TARGET_DIM}d 제로패딩)")
        model = SentenceTransformer(MODEL_NAME)

        print(f"임베딩 생성 대상: {len(rows)}건")
        for i, row in enumerate(rows, 1):
            text_input = f"{row.title}\n\n{row.body}"
            # normalize: 코사인 유사도 일관성 확보
            embedding = model.encode(text_input, normalize_embeddings=True).tolist()
            conn.execute(
                text("UPDATE content SET text_embedding = (:emb)::vector WHERE id = :id"),
                {"emb": to_pgvector(embedding), "id": row.id},
            )
            print(f"  [{i}/{len(rows)}] id={row.id}: {row.title[:50]}")

        print(f"\n완료. 총 {len(rows)}건 임베딩 적재 (로컬 {MODEL_NAME})")


if __name__ == "__main__":
    main()
