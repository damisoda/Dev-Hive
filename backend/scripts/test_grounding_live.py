"""HIVE-90 grounding 회귀 검증 — 실제 Haiku 호출.

환각이 보고된 content_type별 샘플로 synthesize()를 실행하고
grounding 필터 후 환각 항목이 남아 있지 않은지 확인한다.

실행: cd backend && python scripts/test_grounding_live.py
전제: ANTHROPIC_API_KEY가 .env 또는 환경변수에 설정돼 있어야 한다.
"""
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from dotenv import load_dotenv
load_dotenv(BACKEND_ROOT / ".env")

import anthropic
from app.tagging.synthesizer import _content_tokens, _is_grounded, synthesize

# ── 환각이 보고된 케이스 재현용 샘플 ────────────────────────────────────────
# 원문이 짧고 절차가 없는 tutorial → 예전에는 steps를 발명했음(HIVE-90 이슈)
SAMPLES = [
    {
        "label": "tutorial — 절차 없는 원문 (환각 발생 원형)",
        "item": {
            "title": "Redis 캐싱으로 API 응답 속도 개선",
            "body": (
                "우리 팀은 Redis를 도입해 자주 조회되는 데이터를 캐싱했다. "
                "그 결과 평균 응답 시간이 200ms에서 20ms로 줄었다. "
                "Redis는 인메모리 저장소라 빠르다."
            ),
        },
        "tags": {"content_type": "tutorial"},
    },
    {
        "label": "experience — 수치 없는 원문 (numbers 발명 위험)",
        "item": {
            "title": "GraphRAG 도입 후기",
            "body": (
                "GraphRAG를 프로덕션에 적용해봤다. "
                "일반 RAG보다 복잡한 질의에 더 나은 답변을 줬고, "
                "특히 엔티티 간 관계를 묻는 질문에서 차이가 컸다. "
                "단점은 그래프 구축 비용이 높다는 점이다."
            ),
        },
        "tags": {"content_type": "experience"},
    },
    {
        "label": "concept — 비교 대상 없는 원문 (comparisons 발명 위험)",
        "item": {
            "title": "MCP(Model Context Protocol) 이해하기",
            "body": (
                "MCP는 LLM 애플리케이션과 외부 도구를 연결하는 표준 프로토콜이다. "
                "호스트, 클라이언트, 서버 세 가지 컴포넌트로 구성된다. "
                "Anthropic이 제안했고 여러 AI 회사가 채택 중이다."
            ),
        },
        "tags": {"content_type": "concept"},
    },
]


def _check_grounding(card: dict, body: str) -> list[str]:
    """카드 배열 항목 중 body에 근거 없는 항목을 반환한다."""
    from app.tagging.synthesizer import _ARRAY_BODY_KEYS, _content_tokens
    import re

    body_lower = body.lower()
    body_en_words = set(re.findall(r"[a-z]+", body_lower))
    violations = []

    content_type = card.get("content_type", "")
    array_keys = _ARRAY_BODY_KEYS.get(content_type, set()) | {"key_takeaways"}

    for key in array_keys:
        items = card.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, str):
                continue
            if not _is_grounded(item, body_lower):
                violations.append(f"[{key}] {item!r}")

    return violations


def main() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    total_violations = 0
    results = []

    for sample in SAMPLES:
        label = sample["label"]
        item = sample["item"]
        tags = sample["tags"]
        body = item["body"]

        print(f"\n{'='*60}")
        print(f"▶ {label}")
        print(f"  body: {body[:80]}...")

        card = synthesize(item, tags, client)

        if card is None:
            print("  결과: synthesize() → None (graceful)")
            results.append({"label": label, "status": "NONE", "violations": []})
            continue

        violations = _check_grounding(card, body)
        status = "PASS" if not violations else "FAIL"
        total_violations += len(violations)

        print(f"  결과: {status} (violations={len(violations)})")
        print(f"  카드:\n{json.dumps(card, ensure_ascii=False, indent=4)}")
        if violations:
            print(f"  ⚠️  grounding 위반 항목:")
            for v in violations:
                print(f"     - {v}")

        results.append({"label": label, "status": status, "violations": violations})

    print(f"\n{'='*60}")
    passed = sum(1 for r in results if r["status"] in ("PASS", "NONE"))
    print(f"최종: {passed}/{len(results)} PASS  |  grounding 위반 총 {total_violations}건")
    sys.exit(0 if total_violations == 0 else 1)


if __name__ == "__main__":
    main()
