from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ContentSchema(BaseModel):
    title: str
    source: str
    url: str
    published_at: datetime
    body: Optional[str] = None
    author_name: Optional[str] = None
    language: str = "en"
    engagement: dict = Field(default_factory=lambda: {"likes": 0, "comments": 0})

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
