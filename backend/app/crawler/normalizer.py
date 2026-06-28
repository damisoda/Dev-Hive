import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


def clean_body(text: str) -> str:
    """마크다운 아티팩트 제거 — 임베딩·태깅 품질 향상용."""
    if not text:
        return ""
    # 이미지 제거
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    # 마크다운 링크 → 텍스트만 유지
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    # 코드 블록 fence 제거 (내용은 유지)
    text = re.sub(r'```[^\n]*\n?', '', text)
    # 인라인 코드 백틱 제거
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # 헤더 기호 제거
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # 볼드·이탤릭 마커 제거
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    # 블록인용 마커 제거
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)
    # 마크다운 테이블 — 구분선 제거 후 셀 텍스트만 추출
    text = re.sub(r'^\|[-:| ]+\|$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\|(.+)\|$', lambda m: '  '.join(c.strip() for c in m.group(1).split('|') if c.strip()), text, flags=re.MULTILINE)
    # HTML 태그 제거
    text = re.sub(r'<[^>]+>', '', text)
    # 수평선 제거
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # 연속 줄바꿈 압축
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 각 줄 앞뒤 공백 정리
    text = '\n'.join(line.strip() for line in text.splitlines())
    return text.strip()


class ContentSchema(BaseModel):
    title: str
    source: str
    url: str
    published_at: datetime
    body: Optional[str] = None
    author_name: Optional[str] = None
    language: str = "en"
    engagement: dict = Field(default_factory=lambda: {"likes": 0, "comments": 0, "retweets": 0, "views": 0})

    def to_dict(self) -> dict:
        return {
            **self.model_dump(),
            "published_at": self.published_at.isoformat(),
            "body": self.body if self.body is not None else "",
        }


def normalize(
    title: str,
    source: str,
    url: str,
    published_at: datetime,
    body: Optional[str] = None,
    author_name: Optional[str] = None,
    language: str = "en",
    likes: int = 0,
    comments: int = 0,
) -> ContentSchema:
    return ContentSchema(
        title=title,
        source=source,
        url=url,
        published_at=published_at,
        body=body,
        author_name=author_name,
        language=language,
        engagement={"likes": likes, "comments": comments},
    )
