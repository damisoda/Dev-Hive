# api — FastAPI 엔드포인트 (백엔드 파이프라인 4)

## 라우터 구성 (Layer 2 완료 시점)
- `auth.py` — 프로필 선택 세션, 온보딩(직군 + 3문항 자가평가 → profile_vector 초기화)
- `content.py` — 콘텐츠 목록 조회 + 유저 업로드(`POST /content` → QC 게이트 → 태깅 → 임베딩 → Auto-HKG 편입)
- `recommend.py` — GraphRAG 추천(실패 시 rule_based 폴백), user_state, mastery 조회. 추천 확정 시 `BackgroundTasks`로 lazy synthesis 캐시(HIVE-49)
- `progress.py` — 읽음 처리(레벨업 판정 + influence_score 갱신 포함)
- `feedback.py` — 콘텐츠 피드백 upsert/삭제/조회 (4종: understood / too_hard / want_more / not_interested)
- `graph.py` — 지식그래프 노출(topic·content 노드 + belongs_to / similar_to / precedes 엣지)
- `stats.py` — influence_score, streak, 잔디 히트맵

## API 계약
| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | /auth/profile | 데모 프로필 생성(직군 + 자가평가 → profile_vector 초기화) |
| GET | /auth/profile/{user_id} | 프로필 조회 |
| GET | /content | 콘텐츠 목록 (필터: source, node_id, difficulty) |
| POST | /content | 유저 업로드 → 파이프라인 통과 후 그래프 편입 |
| GET | /recommend?user_id= | 다음 콘텐츠 추천 (GraphRAG, summary는 lazy 가공이라 첫 응답에 null 가능) |
| GET | /recommend/user-state?user_id= | LLM KT가 직렬화한 user_state 텍스트 |
| GET | /recommend/mastery?user_id= | 노드별 mastery 추정치 |
| PATCH | /progress | 콘텐츠 읽음 처리 (leveled_up, influence_score 반환) |
| PUT / DELETE / GET | /feedback | 피드백 등록·취소·조회 |
| GET | /graph | 그래프 시각화용 nodes/edges/stats |
| GET | /stats?user_id= | 영향력 점수 + streak + 히트맵 |

각 라우터는 `app/main.py`에서 include한다. 상세 파라미터·응답 필드는 `frontend/README.md`의 API 계약 요약 참조.
