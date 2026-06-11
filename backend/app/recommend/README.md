# recommend — 추천 엔진 (백엔드 파이프라인 3)

유저 상태를 추적하고 다음 콘텐츠를 추천한다.

## 구성
- `graphrag.py` — **메인 (HIVE-22)**. 추천 '결정'은 알고리즘 4성분 점수로 내린다 (LLM 아님):
  - 관련성 0.3 — profile_vector ↔ content 임베딩 **mean-centering** 코사인 (anisotropy 보정)
  - 난이도 0.4 — estimate_mastery(node) ↔ content.difficulty 적합도
  - 경로 0.2 — 선행(precedes) 일관성 (precedes 데이터가 채워지면 활성화, 현재 중립값)
  - 다양성 0.1 — 같은 노드 편중 방지 (그리디 재정렬, MMR 변형)

  피드백 신호(HIVE-48)가 즉시 반영된다: understood/not_interested 제외, want_more 센트로이드 보너스, too_hard 난이도 하향.
  Haiku는 top-1의 자연어 근거 1회 생성에만 사용 — 키 부재·실패 시 템플릿 폴백.
- `rule_based.py` — **폴백**. 벡터 유사도 + 미독/피드백/난이도 필터. profile_vector NULL이면 quality_score 내림차순. GraphRAG 예외 시 `api/recommend.py`가 자동 폴백한다.

LLM Knowledge Tracing(user_state 직렬화·mastery 추정)은 `app/services/knowledge_tracing.py`에 있다.
추천 확정 콘텐츠의 가공 카드는 `app/services/lazy_synthesis.py`가 BackgroundTasks로 생성·캐시한다(HIVE-49).

## 추천 응답 포맷
```json
{
  "recommendations": [
    {"content_id": 42, "title": "...", "url": "...", "score": 0.9,
     "reason": "...", "difficulty": "중급", "content_type": "experience",
     "summary": null}
  ]
}
```
`summary`(가공 카드)는 백그라운드 lazy 가공이라 첫 응답에 `null`일 수 있다.
