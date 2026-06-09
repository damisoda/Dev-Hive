"""
Claude Haiku 태깅 모듈.
크롤링된 콘텐츠 아이템을 받아 태그 JSON을 반환한다.
"""
import json
import re
import sys
from pathlib import Path

import anthropic

# haiku_tagging_prompt.md 로드
_PROMPT_PATH = Path(__file__).parent / "haiku_tagging_prompt.md"
_PROMPT_MD = _PROMPT_PATH.read_text(encoding="utf-8")

# 프롬프트에서 출력 형식 이후 부분(검증 예시)을 시스템 지시로 변환
_SYSTEM_PROMPT = (
    "You are a content tagging assistant. "
    "Read the reference document below and tag the user-supplied content exactly as instructed.\n\n"
    + _PROMPT_MD
)

MODEL = "claude-haiku-4-5-20251001"


def tag_content(item: dict, client: anthropic.Anthropic) -> dict:
    """단일 콘텐츠 아이템을 태깅하여 dict 반환."""
    user_msg = json.dumps(item, ensure_ascii=False)

    message = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = message.content[0].text.strip()
    # 혹시 코드블록이 포함된 경우 제거
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)


def run_validation(data_path: str, n: int = 10) -> None:
    """data_path JSON에서 n건을 뽑아 태깅 결과를 출력한다."""
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 사용

    items = json.loads(Path(data_path).read_text(encoding="utf-8"))
    samples = items[:n]

    print(f"=== Haiku 태깅 검증 | {Path(data_path).name} 앞 {len(samples)}건 ===\n")

    passed = 0
    failed = 0
    for i, item in enumerate(samples, 1):
        title = item.get("title", "")[:60]
        try:
            result = tag_content(item, client)
            _validate_schema(result)
            top_topic = max(result["relevance"], key=result["relevance"].get)
            print(
                f"[{i:02d}] ✅  {title}\n"
                f"      difficulty={result['difficulty']}  "
                f"quality={result['quality_score']:.2f}  "
                f"type={result['content_type']}  "
                f"lang={result['language']}\n"
                f"      top_relevance={top_topic} ({result['relevance'][top_topic]:.2f})\n"
            )
            passed += 1
        except Exception as e:
            print(f"[{i:02d}] ❌  {title}\n      ERROR: {e}\n")
            failed += 1

    print(f"--- 결과: {passed}건 통과 / {failed}건 실패 ---")


def _validate_schema(result: dict) -> None:
    """출력 스키마 검증. 문제가 있으면 ValueError를 발생시킨다."""
    expected_topics = {
        "프롬프트 엔지니어링", "Agentic AI", "멀티모달 AI",
        "RAG & 지식 관리", "오픈소스 AI", "AI 워크플로우 & 자동화", "AI 엔지니어링",
    }
    valid_difficulties = {"입문", "중급", "고급"}
    valid_types = {"experience", "tutorial", "concept", "tool", "discussion"}
    valid_langs = {"ko", "en"}

    if set(result.get("relevance", {}).keys()) != expected_topics:
        raise ValueError(f"relevance 키 불일치: {set(result.get('relevance', {}).keys())}")
    for k, v in result["relevance"].items():
        if not (isinstance(v, (int, float)) and 0.0 <= v <= 1.0):
            raise ValueError(f"relevance[{k}] 범위 오류: {v}")
    if result.get("difficulty") not in valid_difficulties:
        raise ValueError(f"difficulty 값 오류: {result.get('difficulty')}")
    if not (isinstance(result.get("quality_score"), (int, float)) and 0.0 <= result["quality_score"] <= 1.0):
        raise ValueError(f"quality_score 범위 오류: {result.get('quality_score')}")
    if result.get("content_type") not in valid_types:
        raise ValueError(f"content_type 값 오류: {result.get('content_type')}")
    if result.get("language") not in valid_langs:
        raise ValueError(f"language 값 오류: {result.get('language')}")


if __name__ == "__main__":
    # 사용법: python tagger.py <json_path> [n]
    # 예:    python tagger.py ../../../../data/huggingface_20260531.json 10
    path = sys.argv[1] if len(sys.argv) > 1 else "../../../../data/huggingface_20260531.json"
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    run_validation(path, count)
