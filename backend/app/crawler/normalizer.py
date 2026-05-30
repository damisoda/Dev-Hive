from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ContentSchema:
    title: str
    body: str
    source: str
    author_name: str
    url: str
    published_at: datetime
    language: str
    engagement: dict = field(default_factory=lambda: {"likes": 0, "comments": 0})

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "body": self.body,
            "source": self.source,
            "author_name": self.author_name,
            "url": self.url,
            "published_at": self.published_at.isoformat(),
            "language": self.language,
            "engagement": self.engagement,
        }


def normalize(
    title: str,
    body: str,
    source: str,
    author_name: str,
    url: str,
    published_at: datetime,
    language: str = "en",
    likes: int = 0,
    comments: int = 0,
) -> ContentSchema:
    return ContentSchema(
        title=title,
        body=body,
        source=source,
        author_name=author_name,
        url=url,
        published_at=published_at,
        language=language,
        engagement={"likes": likes, "comments": comments},
    )
