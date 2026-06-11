"""백엔드 API 순수 HTTP 클라이언트 (HIVE-51).

스트림릿 비의존 — UI 프레임워크를 몰라야 한다. 실패는 전부 `ApiError`(한국어 메시지)로
올리고, 렌더(st.error 등)는 lib/ui.call 어댑터가 담당한다.
(Next.js 이행 시 이 파일을 TS fetch 클라이언트로 1:1 변환하는 것이 목표)
"""

import os

import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


class ApiError(Exception):
    """백엔드 API 오류 — 사용자에게 그대로 보여줄 한국어 메시지를 담는다.

    is_connection=True면 백엔드 프로세스 자체에 연결 실패(서버 꺼짐 등).
    """

    def __init__(self, message: str, *, is_connection: bool = False, status_code: int | None = None):
        super().__init__(message)
        self.is_connection = is_connection
        self.status_code = status_code


def _handle(response: requests.Response):
    """4xx/5xx → FastAPI detail을 메시지로 ApiError raise (raw JSON/상태코드 노출 방지)."""
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail") or response.text
        except Exception:
            detail = response.text
        raise ApiError(str(detail), status_code=response.status_code)
    return response.json()


def _request(method: str, path: str, **kwargs):
    """공통 요청 래퍼 — 연결/타임아웃 예외를 한국어 ApiError로 변환."""
    try:
        response = requests.request(method, f"{API_BASE_URL}{path}", **kwargs)
    except requests.ConnectionError as e:
        raise ApiError("백엔드 서버에 연결할 수 없습니다.", is_connection=True) from e
    except requests.Timeout as e:
        raise ApiError("백엔드 응답이 늦어지고 있습니다. 잠시 후 다시 시도하세요.") from e
    except requests.RequestException as e:
        raise ApiError(f"요청에 실패했습니다: {e}") from e
    return _handle(response)


def create_profile(display_name: str, persona: str = "개발자", onboarding_answers: dict | None = None):
    return _request("POST", "/auth/profile", json={
        "display_name": display_name,
        "persona": persona,
        "onboarding_answers": onboarding_answers or {},
    }, timeout=10)


def get_profile(user_id: int):
    return _request("GET", f"/auth/profile/{user_id}", timeout=10)


def list_content(source=None, node_id=None, difficulty=None, limit=20, offset=0):
    params = {"limit": limit, "offset": offset}
    if source:
        params["source"] = source
    if node_id is not None:
        params["node_id"] = node_id
    if difficulty:
        params["difficulty"] = difficulty
    return _request("GET", "/content", params=params, timeout=10)


def recommend(user_id: int, top_n: int = 5):
    # GraphRAG(LLM rerank+근거)라 실측 ~12s — 타임아웃 여유 필수(커리큘럼 페이지는 세션 캐싱).
    return _request("GET", "/recommend", params={"user_id": user_id, "top_n": top_n}, timeout=60)


def mark_read(user_id: int, content_id: int):
    return _request("PATCH", "/progress", json={"user_id": user_id, "content_id": content_id}, timeout=10)


def get_graph():
    # /graph는 similar_to를 매 호출마다 계산해 다소 느릴 수 있어 넉넉한 타임아웃.
    return _request("GET", "/graph", timeout=30)


def upload_content(title: str, body: str, url: str | None = None, user_id: int | None = None):
    # 태깅+임베딩+Auto-HKG(LLM 호출 포함)라 넉넉한 타임아웃.
    return _request("POST", "/content", json={
        "title": title, "body": body, "url": url, "user_id": user_id,
    }, timeout=60)


def get_mastery(user_id: int):
    """노드별 mastery(0~1) dict — 응답 `{user_id, mastery}`에서 mastery만 언랩 반환.

    데이터 없음(404 등)/오류면 None(빨간 배너 없이 조용히 — 신규 유저 정상 경로).
    """
    try:
        data = _request("GET", "/recommend/mastery", params={"user_id": user_id}, timeout=15)
    except ApiError:
        return None
    return (data or {}).get("mastery") or {}


def get_user_state(user_id: int):
    """유저 상태 `{user_id, user_state}` — 프로필 학습 현황용. 없음/오류면 None(조용히)."""
    try:
        return _request("GET", "/recommend/user-state", params={"user_id": user_id}, timeout=15)
    except ApiError:
        return None


# ── 피드백 / 통계 (HIVE-37) ──────────────────────────────────────────

def set_feedback(user_id: int, content_id: int, feedback: str):
    """콘텐츠 피드백 저장/갱신 (understood/too_hard/want_more/not_interested)."""
    return _request("PUT", "/feedback", json={
        "user_id": user_id, "content_id": content_id, "feedback": feedback,
    }, timeout=10)


def clear_feedback(user_id: int, content_id: int):
    """콘텐츠 피드백 해제 (토글 off)."""
    return _request("DELETE", "/feedback", json={
        "user_id": user_id, "content_id": content_id,
    }, timeout=10)


def list_feedback(user_id: int) -> dict:
    """유저 피드백 `{content_id: feedback}`. 없음/오류면 빈 dict(조용히)."""
    try:
        data = _request("GET", "/feedback", params={"user_id": user_id}, timeout=10)
    except ApiError:
        return {}
    # JSON 객체 키는 문자열 → int로 정규화
    return {int(k): v for k, v in (data or {}).items()}


def get_stats(user_id: int):
    """influence_score / streak / heatmap. 없음/오류면 None(조용히)."""
    try:
        return _request("GET", "/stats", params={"user_id": user_id}, timeout=15)
    except ApiError:
        return None
