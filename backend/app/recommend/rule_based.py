"""Layer 1 룰베이스 추천 로직.

⚠️ HIVE-13(진하 담당)에서 구현 예정. 아래는 GET /recommend 라우터가 호출할
인터페이스를 고정하기 위한 stub이다. 진하가 본인 작업 시작 시 이 함수 본문을 채운다.
"""

from sqlalchemy.orm import Session


def recommend_next(user_id: int, top_n: int, db: Session) -> list[dict]:
    """다음에 읽을 콘텐츠를 추천한다.

    Layer 1: 룰베이스 (벡터 유사도 + 미독 + 난이도 적합도).

    Returns:
        [{"content_id": int, "title": str, "score": float, "reason": str | None}, ...]
    """
    return []
