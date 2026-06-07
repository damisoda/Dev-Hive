"""백엔드 API 호출 헬퍼."""

import os

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def _handle(response: requests.Response):
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail") or response.text
        except Exception:
            detail = response.text
        st.error(detail)   # FastAPI detail을 그대로(친화적 메시지), raw JSON/상태코드 노출 방지
        return None
    return response.json()


def create_profile(display_name: str, persona: str = "개발자", onboarding_answers: dict | None = None):
    return _handle(requests.post(
        f"{API_BASE_URL}/auth/profile",
        json={
            "display_name": display_name,
            "persona": persona,
            "onboarding_answers": onboarding_answers or {},
        },
        timeout=10,
    ))


def get_profile(user_id: int):
    return _handle(requests.get(f"{API_BASE_URL}/auth/profile/{user_id}", timeout=10))


def list_content(source=None, node_id=None, difficulty=None, limit=20, offset=0):
    params = {"limit": limit, "offset": offset}
    if source:
        params["source"] = source
    if node_id is not None:
        params["node_id"] = node_id
    if difficulty:
        params["difficulty"] = difficulty
    return _handle(requests.get(f"{API_BASE_URL}/content", params=params, timeout=10))


def recommend(user_id: int, top_n: int = 5):
    return _handle(requests.get(
        f"{API_BASE_URL}/recommend",
        params={"user_id": user_id, "top_n": top_n},
        timeout=15,
    ))


def mark_read(user_id: int, content_id: int):
    return _handle(requests.patch(
        f"{API_BASE_URL}/progress",
        json={"user_id": user_id, "content_id": content_id},
        timeout=10,
    ))


def get_graph():
    # /graph는 similar_to를 매 호출마다 계산해 다소 느릴 수 있어 넉넉한 타임아웃.
    try:
        return _handle(requests.get(f"{API_BASE_URL}/graph", timeout=30))
    except requests.RequestException as e:
        st.error(f"그래프 API 연결 실패 (백엔드가 켜져 있나요?): {e}")
        return None


def upload_content(title: str, body: str, url: str | None = None, user_id: int | None = None):
    # 태깅+임베딩+Auto-HKG(LLM 호출 포함)라 넉넉한 타임아웃.
    try:
        return _handle(requests.post(
            f"{API_BASE_URL}/content",
            json={"title": title, "body": body, "url": url, "user_id": user_id},
            timeout=60,
        ))
    except requests.RequestException as e:
        st.error(f"업로드 실패 (백엔드가 켜져 있나요?): {e}")
        return None
