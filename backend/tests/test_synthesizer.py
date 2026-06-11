"""HIVE-41 가공(synthesizer) 단위 테스트.

Anthropic 클라이언트를 mock(가짜 카드 JSON 반환)으로 대체해 LLM 없이:
- content_type별 분기 + 카드 구조(공통헤더 + 타입별 바디) 파싱
- 키 없음 / LLM 실패 / 응답 헛출력 → None (graceful)
- 알 수 없는 content_type → None
- 환각 방지 계약: 누락 키는 빈 배열/None으로 보정
을 검증한다. 적재(loader)는 synthesis가 None이어도 계속되므로 None 경로가 중요.
"""
import json
from types import SimpleNamespace

import pytest

from app.tagging.synthesizer import _BODY_KEYS, _HEADER_KEYS, synthesize


class _FakeMessage:
    """client.messages.create() 반환을 흉내낸다: .content[0].text + .stop_reason."""

    def __init__(self, text: str, stop_reason: str = "end_turn"):
        self.content = [SimpleNamespace(text=text)]
        self.stop_reason = stop_reason


class _FakeAnthropic:
    """가짜 카드 JSON 문자열을 그대로 돌려주는 mock 클라이언트.

    raise_exc=True면 create()에서 예외를 던져 LLM 실패를 시뮬레이션한다.
    stop_reason으로 출력 잘림(max_tokens)을 시뮬레이션한다.
    호출된 system/max_tokens를 captured_*에 저장해 검증에 쓴다.
    """

    def __init__(self, reply_text: str = "{}", raise_exc: bool = False,
                 stop_reason: str = "end_turn"):
        self._reply_text = reply_text
        self._raise_exc = raise_exc
        self._stop_reason = stop_reason
        self.captured_system = None
        self.captured_max_tokens = None
        self.call_count = 0

        outer = self

        class _Messages:
            def create(self, *, model, max_tokens, system, messages):
                outer.call_count += 1
                outer.captured_system = system
                outer.captured_max_tokens = max_tokens
                if outer._raise_exc:
                    raise RuntimeError("simulated LLM failure")
                return _FakeMessage(outer._reply_text, stop_reason=outer._stop_reason)

        self.messages = _Messages()


def _client_returning(card: dict, **kw) -> _FakeAnthropic:
    return _FakeAnthropic(reply_text=json.dumps(card, ensure_ascii=False), **kw)


# --- HIVE-45: 출력 토큰 상한 + 잘림 로깅 -----------------------------------

def test_synthesize_uses_3072_max_tokens():
    from app.tagging import synthesizer
    client = _FakeAnthropic(reply_text="{}")
    synthesize(_ITEM, {"content_type": "experience"}, client)
    assert client.captured_max_tokens == 3072 == synthesizer.MAX_OUTPUT_TOKENS


def test_truncation_logs_warning(caplog):
    import logging
    # stop_reason=max_tokens면(출력 잘림) 조용한 None이 되지 않게 경고를 남긴다.
    client = _FakeAnthropic(reply_text="{}", stop_reason="max_tokens")
    with caplog.at_level(logging.WARNING, logger="app.tagging.synthesizer"):
        synthesize(_ITEM, {"content_type": "experience"}, client)
    assert any("max_tokens" in r.getMessage() for r in caplog.records)


_ITEM = {"title": "제목", "body": "본문 내용이 충분히 있다."}


# --- content_type별 분기 + 카드 구조 파싱 ---------------------------------

def test_experience_card_structure():
    card = {
        "one_liner": "vLLM으로 처리량 3배 올린 경험",
        "key_takeaways": ["PagedAttention이 핵심", "배치 크기 튜닝 필요"],
        "context": "프로덕션 서빙 비용 절감 과제",
        "findings": ["throughput 3배", "VRAM 사용 안정"],
        "pitfalls": ["초기 OOM"],
        "numbers": ["3x throughput", "p99 120ms"],
        "verdict": "서빙엔 vLLM 추천",
    }
    client = _client_returning(card)
    out = synthesize(_ITEM, {"content_type": "experience"}, client)

    assert out is not None
    assert out["content_type"] == "experience"
    # 공통 헤더
    assert out["one_liner"] == card["one_liner"]
    assert out["key_takeaways"] == card["key_takeaways"]
    # 타입별 바디 키가 모두 존재
    for key in _BODY_KEYS["experience"]:
        assert key in out
    assert out["numbers"] == ["3x throughput", "p99 120ms"]
    # 분기 검증: experience 시스템 프롬프트가 쓰였다
    assert "content_type='experience'" in client.captured_system


def test_form_violation_coerced_not_stringified():
    # 단일값 키에 리스트 / 배열 키에 dict·number 요소 → 형식위반은 떨군다(stringify 아님).
    bad = {
        "one_liner": "ok",
        "verdict": ["a", "b"],              # 단일값 키에 리스트
        "findings": ["good", {"x": 1}, 5],  # 배열에 str 아닌 요소
    }
    out = synthesize(_ITEM, {"content_type": "experience"}, _client_returning(bad))
    assert out["verdict"] is None           # 리스트 → None (str화 아님)
    assert out["findings"] == ["good"]       # dict/number 요소 드롭


def test_tool_card_structure_and_branch():
    card = {
        "one_liner": "로컬 LLM 도구 3종",
        "key_takeaways": ["Ollama 입문용"],
        "what": "로컬 추론 런타임 모음",
        "when_to_use": "오프라인/비용 절감",
        "how": ["설치", "모델 pull", "실행"],
        "requirements": "GPU 권장",
        "gotchas": ["VRAM 한계"],
    }
    client = _client_returning(card)
    out = synthesize(_ITEM, {"content_type": "tool"}, client)

    assert out["content_type"] == "tool"
    assert out["how"] == ["설치", "모델 pull", "실행"]
    assert out["requirements"] == "GPU 권장"
    assert set(_BODY_KEYS["tool"]).issubset(out.keys())
    assert "content_type='tool'" in client.captured_system


def test_concept_card_structure():
    card = {
        "one_liner": "RAG 한 줄 정의",
        "key_takeaways": ["검색+생성"],
        "definition": "외부 지식 검색 후 생성",
        "mechanism": ["임베딩", "벡터 검색", "컨텍스트 주입"],
        "comparisons": ["파인튜닝 vs RAG"],
        "when_matters": "최신 지식 필요할 때",
    }
    out = synthesize(_ITEM, {"content_type": "concept"}, _client_returning(card))
    assert out["content_type"] == "concept"
    assert out["mechanism"] == ["임베딩", "벡터 검색", "컨텍스트 주입"]
    assert set(_BODY_KEYS["concept"]).issubset(out.keys())


def test_tutorial_card_structure():
    card = {
        "one_liner": "Ollama 5분 셋업",
        "key_takeaways": ["CLI 한 줄"],
        "goal": "로컬에서 모델 실행",
        "steps": ["설치", "pull", "run"],
        "result": "프롬프트 응답 확인",
        "notes": ["디스크 공간 확인"],
    }
    out = synthesize(_ITEM, {"content_type": "tutorial"}, _client_returning(card))
    assert out["content_type"] == "tutorial"
    assert out["steps"] == ["설치", "pull", "run"]
    assert set(_BODY_KEYS["tutorial"]).issubset(out.keys())


def test_discussion_card_structure():
    card = {
        "one_liner": "RAG vs 파인튜닝 논쟁",
        "key_takeaways": ["상황에 따라 다름"],
        "claim": "대부분 RAG가 낫다",
        "arguments": ["갱신 용이", "비용 저렴"],
        "counterpoints": ["지연 증가"],
        "conclusion": "혼용이 현실적",
    }
    out = synthesize(_ITEM, {"content_type": "discussion"}, _client_returning(card))
    assert out["content_type"] == "discussion"
    assert out["arguments"] == ["갱신 용이", "비용 저렴"]
    assert set(_BODY_KEYS["discussion"]).issubset(out.keys())


# --- 환각 방지 / 보정 계약 -------------------------------------------------

def test_missing_body_keys_filled_as_empty():
    # 모델이 헤더만 주고 바디 일부를 빠뜨려도 빈 배열/None으로 보정(환각 대신 빈칸)
    card = {"one_liner": "한 줄", "key_takeaways": ["a"]}
    out = synthesize(_ITEM, {"content_type": "experience"}, _client_returning(card))
    assert out is not None
    assert out["findings"] == []   # 배열 키 → []
    assert out["pitfalls"] == []
    assert out["numbers"] == []
    assert out["context"] is None  # 단일 키 → None
    assert out["verdict"] is None


def test_unknown_keys_dropped():
    # 명세 밖 키(hallucinated_extra)는 카드에서 제거된다
    card = {
        "one_liner": "x",
        "key_takeaways": [],
        "definition": "d",
        "mechanism": [],
        "comparisons": [],
        "when_matters": "w",
        "hallucinated_extra": "버려져야 함",
    }
    out = synthesize(_ITEM, {"content_type": "concept"}, _client_returning(card))
    assert "hallucinated_extra" not in out
    allowed = {"content_type", *_HEADER_KEYS, *_BODY_KEYS["concept"]}
    assert set(out.keys()) == allowed


# --- graceful None 경로 ----------------------------------------------------

def test_missing_content_type_returns_none():
    client = _client_returning({"one_liner": "x"})
    assert synthesize(_ITEM, {}, client) is None
    assert client.call_count == 0  # LLM 호출조차 안 함(비용 절약)


def test_unknown_content_type_returns_none():
    client = _client_returning({"one_liner": "x"})
    assert synthesize(_ITEM, {"content_type": "news"}, client) is None  # 폐기된 타입
    assert synthesize(_ITEM, {"content_type": "paper"}, client) is None
    assert client.call_count == 0


def test_llm_failure_returns_none():
    client = _FakeAnthropic(raise_exc=True)
    assert synthesize(_ITEM, {"content_type": "experience"}, client) is None


def test_invalid_json_returns_none():
    client = _FakeAnthropic(reply_text="이건 JSON이 아니야")
    assert synthesize(_ITEM, {"content_type": "tool"}, client) is None


def test_empty_header_response_returns_none():
    # 헤더 키가 통째로 없는 헛출력 → 가공 실패로 None
    client = _client_returning({"random": "노이즈"})
    assert synthesize(_ITEM, {"content_type": "concept"}, client) is None


def test_empty_item_returns_none():
    # 가공할 원문(title/body)이 전혀 없으면 호출 없이 None
    client = _client_returning({"one_liner": "x"})
    assert synthesize({"title": "", "body": ""}, {"content_type": "tutorial"}, client) is None
    assert client.call_count == 0


def test_code_fence_stripped():
    # Haiku가 ```json 코드블록으로 감싸도 파싱된다(tagger와 동일 처리)
    card = {
        "one_liner": "x", "key_takeaways": [],
        "claim": "c", "arguments": [], "counterpoints": [], "conclusion": "z",
    }
    fenced = "```json\n" + json.dumps(card, ensure_ascii=False) + "\n```"
    client = _FakeAnthropic(reply_text=fenced)
    out = synthesize(_ITEM, {"content_type": "discussion"}, client)
    assert out is not None
    assert out["claim"] == "c"
