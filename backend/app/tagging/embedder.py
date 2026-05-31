"""
OpenAI text-embedding-3-small 임베딩 생성 모듈.
콘텐츠 아이템의 title + body를 받아 1536차원 벡터를 반환한다.
"""
from openai import OpenAI

EMBED_MODEL = "text-embedding-3-small"


def embed_content(item: dict, client: OpenAI) -> list[float]:
    """title + body를 이어붙여 임베딩을 생성하고 1536차원 벡터를 반환한다."""
    text_input = f"{item.get('title', '')}\n\n{item.get('body', '')}"
    response = client.embeddings.create(model=EMBED_MODEL, input=text_input)
    return response.data[0].embedding
