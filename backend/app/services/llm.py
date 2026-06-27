"""LLM 백엔드 토글 — anthropic(클라우드 Haiku) | ollama(로컬 EXAONE).

크레딧 의존을 끊기 위한 추상화. `.messages.create(model, max_tokens, system, messages)` 인터페이스를
anthropic SDK와 동일하게 맞춰, 호출부(synthesizer·tagger·auto_hkg 네이밍·rationale)를 수정 없이
둔 채 백엔드만 바꾼다.

환경변수:
- LLM_BACKEND = anthropic(기본) | ollama
- OLLAMA_URL   = http://localhost:11434 (맥미니 자체 호스팅 시 동일)
- OLLAMA_MODEL = 기본 EXAONE-3.5-7.8B(한국어 특화, synthesis가 한국어라 적합)

설계 메모: synthesis/tagging/네이밍은 JSON 출력, rationale는 자유 문장이다. ollama format='json'은
JSON 강제라 rationale를 망가뜨리므로, system 프롬프트에 'JSON'이 있을 때만 format='json'을 켠다.
"""
import json
import os
import urllib.request
from types import SimpleNamespace

import anthropic


def _backend() -> str:
    return os.getenv("LLM_BACKEND", "anthropic").strip().lower()


def is_local() -> bool:
    return _backend() == "ollama"


def llm_available() -> bool:
    """가공/태깅/네이밍 LLM을 쓸 수 있는가. ollama 백엔드면 API 키가 필요 없다."""
    return is_local() or bool(os.getenv("ANTHROPIC_API_KEY"))


_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
_OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL", "hf.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct-GGUF:Q4_K_M"
)


class _OllamaMessages:
    """anthropic client.messages.create 시그니처를 흉내내 ollama /api/chat을 호출한다."""

    def create(self, model=None, max_tokens=512, system="", messages=None, **kw):
        msgs = [{"role": "system", "content": system}]
        for m in messages or []:
            c = m.get("content", "")
            msgs.append({
                "role": m.get("role", "user"),
                "content": c if isinstance(c, str) else json.dumps(c, ensure_ascii=False),
            })
        options = {"temperature": 0.2, "num_ctx": 8192, "num_predict": int(max_tokens)}
        payload = {"model": _OLLAMA_MODEL, "messages": msgs, "stream": False, "options": options}
        if "JSON" in (system or ""):  # synthesis/tagging/네이밍만 JSON 강제(rationale 제외)
            payload["format"] = "json"
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{_OLLAMA_URL}/api/chat", data=body, headers={"Content-Type": "application/json"}
        )
        r = json.load(urllib.request.urlopen(req, timeout=300))
        text = r["message"]["content"]
        return SimpleNamespace(content=[SimpleNamespace(text=text)], stop_reason="end_turn")


class OllamaClient:
    """anthropic.Anthropic 드롭인 대체(messages.create만). 배치(beta.messages.batches)는 미지원."""

    def __init__(self) -> None:
        self.messages = _OllamaMessages()


def get_llm_client(api_key: str | None = None):
    """백엔드에 맞는 LLM 클라이언트를 돌려준다. ollama면 OllamaClient(키 무시)."""
    if is_local():
        return OllamaClient()
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
