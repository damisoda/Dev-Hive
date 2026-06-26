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

from app.tagging.synthesizer import (
    _BODY_KEYS, _HEADER_KEYS, _apply_grounding, _is_grounded, _is_phantom, synthesize,
)


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


# --- HIVE-62: 시스템 프롬프트 한국어 출력 단언 --------------------------------

def test_system_prompt_instructs_korean_output():
    client = _client_returning({"one_liner": "x", "key_takeaways": []})
    synthesize(_ITEM, {"content_type": "experience"}, client)
    assert "한국어" in client.captured_system


def test_phantom_text_coerced_to_null():
    """HIVE-104: LLM이 null 대신 '원문에서 명시되지 않음' 텍스트를 쓰면 null/[]로 보정된다."""
    card_with_phantom = {
        "one_liner": "x",
        # 첫 항목은 _ITEM body에 실제로 있는 내용(grounding 통과), 두 번째는 위장 텍스트
        "key_takeaways": ["vLLM throughput 3배 향상", "원문에서 명시되지 않음"],
        "context": "원문에서 명시적으로 설명되지 않음",
        "findings": ["vLLM PagedAttention으로 VRAM 효율 향상"],
        "pitfalls": [],
        "numbers": [],
        "verdict": "not mentioned in the source",
    }
    out = synthesize(
        _ITEM,
        {"content_type": "experience"},
        _client_returning(card_with_phantom),
    )
    assert out is not None
    assert len(out["key_takeaways"]) == 1   # 위장 텍스트 1개 제거됨
    assert out["context"] is None           # 위장 텍스트 → null
    assert out["verdict"] is None           # 영문 패턴도 감지


def test_is_phantom_detects_korean_patterns():
    assert _is_phantom("원문에서 명시되지 않음") is True
    assert _is_phantom("원문에서 언급되지 않음") is True
    assert _is_phantom("원문에서 설명되지 않음") is True
    assert _is_phantom("실제 내용이 있는 문장") is False


def test_is_phantom_no_false_positive_on_positive_form():
    # "원문에서 언급된 X" 양성형은 정상 내용 — phantom 아님
    assert _is_phantom("원문에서 언급된 세 가지 핵심 원칙이 있다") is False
    assert _is_phantom("원문에서 설명한 작동 원리") is False


def test_is_phantom_no_false_positive_on_technical_negation():
    # "명시되지 않은 기본값" 등 기술적 관형절은 phantom 아님 (원문에서 prefix 없음)
    assert _is_phantom("명시되지 않은 기본값이 보안 취약점을 유발한다") is False
    assert _is_phantom("설명되지 않는 예외 케이스가 있음") is False


def test_is_phantom_detects_english_patterns():
    assert _is_phantom("not mentioned in source") is True
    assert _is_phantom("not specified in the original") is True
    assert _is_phantom("normal gotcha text") is False


def test_system_prompt_forbids_external_reference_expansion():
    """HIVE-104: 인용 트윗·URL 등 외부 콘텐츠 추론 금지 지시가 프롬프트에 포함된다."""
    client = _client_returning({"one_liner": "x", "key_takeaways": []})
    synthesize(_ITEM, {"content_type": "discussion"}, client)
    assert "인용 트윗" in client.captured_system


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


_ITEM = {
    "title": "개발 테스트 항목",
    "body": (
        "vLLM은 PagedAttention 기법으로 VRAM 효율을 높이고 throughput을 3x 개선했다. "
        "초기 OOM 문제를 배치 크기 튜닝으로 해결했으며 서빙에는 vLLM을 추천한다. "
        "p99 지연은 120ms까지 낮아졌다. VRAM 사용이 안정됐다. "
        "Ollama는 로컬에서 LLM 모델을 CLI 한 줄로 실행할 수 있는 추론 런타임 모음이다. "
        "GPU 권장 환경이며 VRAM 한계가 있다. 설치 후 모델 pull과 run이 필요하다. "
        "오프라인 비용 절감 목적에 적합하다. 로컬 LLM 도구 3종을 비교했다. "
        "RAG는 외부 지식을 임베딩으로 벡터 검색해 컨텍스트로 주입하는 검색 기반 생성 기법이다. "
        "파인튜닝과 비교하면 갱신이 용이하고 비용이 저렴하나 지연이 증가하는 트레이드오프가 있다. "
        "대부분의 경우 RAG가 낫다는 주장이 있으나 상황에 따라 다르며 혼용이 현실적이다. "
        "최신 지식이 필요할 때 특히 유용하다. 프롬프트 응답을 확인할 수 있다. "
        "디스크 공간 확인이 필요하다. good practice를 따르는 것이 중요하다."
    ),
}


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
        "one_liner": "RAG 개념",
        "key_takeaways": ["외부 지식을 벡터 검색해 생성에 활용"],
        "definition": "외부 지식 임베딩 벡터 검색 기반 생성",
        "mechanism": ["임베딩 벡터 검색", "컨텍스트 주입"],
        "comparisons": [],
        "when_matters": "최신 지식 필요할 때",
        "hallucinated_extra": "버려져야 함",
    }
    out = synthesize(_ITEM, {"content_type": "concept"}, _client_returning(card))
    assert out is not None
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


# --- HIVE-90: grounding 필터 -----------------------------------------------

def test_grounding_removes_hallucinated_steps():
    # tutorial.steps에 원문에 없는 절차가 포함되면 제거된다
    body = "vLLM을 pip install vllm 으로 설치한 뒤 서버를 실행한다."
    card = {
        "one_liner": "vLLM 설치",
        "key_takeaways": ["pip install vllm 으로 설치"],
        "goal": "로컬 추론 서버 실행",
        "steps": [
            "pip install vllm 으로 설치한다",          # ← 원문에 있음 → 통과
            "conda create -n llm python=3.11 실행",    # ← 원문에 없음 → 제거
            "Docker 컨테이너 빌드 후 push 한다",        # ← 원문에 없음 → 제거
        ],
        "result": "추론 서버 실행 완료",
        "notes": [],
        "content_type": "tutorial",
    }
    result = _apply_grounding(card, body)
    assert len(result["steps"]) == 1
    assert "pip install" in result["steps"][0]


def test_grounding_passes_grounded_items():
    # 원문에 있는 내용은 제거되지 않는다
    body = "PagedAttention 기법으로 VRAM 효율을 3배 높였다. throughput도 크게 향상됐다."
    card = {
        "one_liner": "vLLM 성능",
        "key_takeaways": ["PagedAttention으로 VRAM 효율 3배 향상", "throughput 향상"],
        "context": "VRAM 최적화",
        "findings": ["PagedAttention 기법 적용", "throughput 대폭 개선"],
        "pitfalls": [],
        "numbers": ["3배"],
        "verdict": "효율적",
        "content_type": "experience",
    }
    result = _apply_grounding(card, body)
    assert len(result["key_takeaways"]) == 2
    assert len(result["findings"]) == 2


def test_grounding_skips_filter_when_body_empty():
    # body가 없으면 필터를 적용하지 않는다(제거 없음)
    card = {
        "one_liner": "x",
        "key_takeaways": ["완전히 발명된 내용"],
        "steps": ["존재하지 않는 절차 A", "존재하지 않는 절차 B"],
        "goal": "g", "result": "r", "notes": [],
        "content_type": "tutorial",
    }
    result = _apply_grounding(card, "")
    assert result["steps"] == card["steps"]
    assert result["key_takeaways"] == card["key_takeaways"]


def test_grounding_integrated_with_synthesize():
    # synthesize()가 grounding 필터를 거쳐 환각 항목을 제거한다
    body = "Redis를 캐시로 사용하면 응답 속도가 빨라진다."
    item = {"title": "Redis 캐시 활용", "body": body}
    card = {
        "one_liner": "Redis 캐시 활용",
        "key_takeaways": [
            "Redis 캐시로 응답 속도 향상",    # ← 원문 근거 있음 → 통과
            "Kubernetes 클러스터 구성 필수",  # ← 원문에 없음 → 제거
        ],
        "goal": "캐시 설정",
        "steps": ["Redis 설치", "캐시 적용"],
        "result": "속도 개선",
        "notes": [],
    }
    out = synthesize(item, {"content_type": "tutorial"}, _client_returning(card))
    assert out is not None
    assert len(out["key_takeaways"]) == 1
    assert "Redis" in out["key_takeaways"][0]


def test_is_grounded_returns_true_for_matching_tokens():
    body = "vllm 설치 후 서버를 실행하면 throughput이 향상됩니다"
    assert _is_grounded("vllm 설치 방법", body) is True


def test_is_grounded_returns_false_for_no_match():
    body = "Redis를 캐시로 사용한다"
    assert _is_grounded("Kubernetes 클러스터 구성 및 Docker 빌드", body) is False


def test_is_grounded_empty_statement_passes():
    assert _is_grounded("", "아무 본문") is True


def test_grounding_catches_quoted_tweet_hallucination():
    """HIVE-104: 인용 트윗 없이 외부 문구만 있는 짧은 트윗에서 환각 항목을 제거한다."""
    body = "Karpathy의 새 영상 정말 인상적이에요."
    card = {
        "one_liner": "Karpathy LLM 지식 베이스 시리즈",
        "key_takeaways": [
            "Karpathy 영상 인상적",            # 원문 근거 있음 → 통과
            "LLM Knowledge Bases 3단계 구성",  # 원문에 없음 → 제거
            "Vector DB와 RAG 결합 방법론",     # 원문에 없음 → 제거
        ],
        "claim": "LLM Knowledge Bases 구축이 핵심 기술",  # 원문에 없음 → None
        "arguments": ["Vector DB 활용", "RAG 파이프라인"], # 원문에 없음 → 제거
        "counterpoints": [],
        "conclusion": "Karpathy 영상 참고 권장",  # 원문 근거 있음 → 통과
        "content_type": "discussion",
    }
    result = _apply_grounding(card, body)
    assert len(result["key_takeaways"]) == 1
    assert "Karpathy" in result["key_takeaways"][0]
    assert result["arguments"] == []
    assert result["claim"] is None
    assert result["conclusion"] is not None


def test_code_fence_stripped():
    # Haiku가 ```json 코드블록으로 감싸도 파싱된다(tagger와 동일 처리)
    card = {
        "one_liner": "x", "key_takeaways": ["RAG 활용"],
        "claim": "c", "arguments": ["갱신 용이"], "counterpoints": [], "conclusion": "z",
    }
    fenced = "```json\n" + json.dumps(card, ensure_ascii=False) + "\n```"
    client = _FakeAnthropic(reply_text=fenced)
    out = synthesize(_ITEM, {"content_type": "discussion"}, client)
    assert out is not None
    assert out["claim"] == "c"


def test_bare_code_fence_stripped():
    # ```json 태그 없는 bare ``` 펜스도 파싱된다 (DOTALL 버그 회귀 방지)
    card = {
        "one_liner": "x", "key_takeaways": ["RAG 활용"],
        "claim": "c", "arguments": ["갱신 용이"], "counterpoints": [], "conclusion": "z",
    }
    fenced = "```\n" + json.dumps(card, ensure_ascii=False) + "\n```"
    client = _FakeAnthropic(reply_text=fenced)
    out = synthesize(_ITEM, {"content_type": "discussion"}, client)
    assert out is not None
    assert out["claim"] == "c"


def test_backtick_in_json_value_not_eaten():
    # JSON 값 내부에 백틱이 있어도 파싱이 깨지지 않는다 (DOTALL 버그 회귀 방지)
    card = {
        "one_liner": "x",
        "key_takeaways": ["RAG 활용"],
        "goal": "로컬에서 모델 실행",
        "steps": ["pip install vllm 으로 설치한다", "use ```bash``` shell for execution"],
        "result": "추론 서버 실행 완료",
        "notes": [],
    }
    client = _FakeAnthropic(reply_text=json.dumps(card, ensure_ascii=False))
    out = synthesize(_ITEM, {"content_type": "tutorial"}, client)
    assert out is not None


def test_trailing_comment_after_json_parsed():
    # JSON 닫는 중괄호 뒤에 설명 텍스트가 있어도 첫 번째 객체만 추출해 파싱한다
    card = {
        "one_liner": "x", "key_takeaways": ["RAG 활용"],
        "claim": "c", "arguments": ["갱신 용이"], "counterpoints": [], "conclusion": "z",
    }
    with_trailing = json.dumps(card, ensure_ascii=False) + "\n\n여기는 설명 텍스트입니다."
    client = _FakeAnthropic(reply_text=with_trailing)
    out = synthesize(_ITEM, {"content_type": "discussion"}, client)
    assert out is not None
    assert out["claim"] == "c"
