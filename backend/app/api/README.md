# api — FastAPI 엔드포인트 (백엔드 파이프라인 4)

## 엔드포인트 (Layer 1)
- `user.py` — 프로필 선택 세션, 온보딩(직군 + 3문항)
- `content.py` — 콘텐츠 목록 조회, 상세 조회
- `recommend.py` — 다음 콘텐츠 추천, 진도(읽음) 업데이트

## API 계약 (초안)
| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | /auth/profile | 데모 프로필 선택 |
| POST | /onboarding | 직군 + 자가평가 → user_state 초기화 |
| GET | /content | 콘텐츠 목록 (필터: source, node, difficulty) |
| GET | /recommend?user_id= | 다음 콘텐츠 추천 |
| PATCH | /progress | 콘텐츠 읽음 처리 |
| GET | /curriculum?user_id= | 유저 커리큘럼 조회 |

각 라우터는 `app/main.py`에서 include한다.
