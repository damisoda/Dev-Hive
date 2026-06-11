# frontend — Streamlit

Dev-Hive UI. Streamlit은 임시 셸이며, Next.js(React) 이행을 전제로 3층으로 분리되어 있다.

## 실행
```bash
cd frontend
pip install -r requirements.txt
streamlit run app.py
```
백엔드(FastAPI, 기본 `http://localhost:8000`)가 먼저 떠 있어야 한다. 주소는 `API_BASE_URL` 환경변수로 주입.

## 아키텍처 — 3층 분리 (HIVE-51)

| 층 | 파일 | 역할 | streamlit 의존 |
|---|---|---|---|
| API 클라이언트 | `lib/api.py` | 순수 HTTP 클라이언트. 실패는 전부 `ApiError`(한국어 메시지) raise. 연결 실패는 `is_connection=True` | 없음 |
| 뷰모델 | `lib/viewmodel.py` | 데이터 → 표시용 구조(배지 목록, 피드백 버튼 정의, mastery 라벨, 추천 카드 필드, source 라벨) | 없음 |
| 렌더 | `lib/ui.py` `lib/components.py` `app.py` `pages/*` | st.* 렌더만. `ui.call(fn, ...)`이 `ApiError`를 잡아 친화적 에러 + '다시 시도' 버튼으로 렌더 | 있음 |

- `lib/graph_viz.py`: pyvis + networkx spring 레이아웃(streamlit 비의존이지만 이행 시 폐기, 아래 참조).
- 호출 패턴: 페이지는 `call(api_fn, ...)`로 감싸 호출. 실패 시 `call`이 안내를 렌더하고 `None` 반환 → 페이지는 `if data is None: st.stop()`.
- 조용한(quiet) API: `get_mastery` `get_user_state` `list_feedback` `get_stats`는 신규 유저 정상 경로라 오류 시 배너 없이 `None`/`{}` 반환.

## 마이그레이션 맵 (Streamlit → Next.js)

| 현재 (Streamlit) | 이행 후 (Next.js/React) |
|---|---|
| `app.py` (온보딩) | `/` 라우트 + 온보딩 폼 컴포넌트 |
| `pages/1_피드.py` | `/feed` |
| `pages/2_커리큘럼.py` | `/curriculum` |
| `pages/3_프로필.py` | `/profile` |
| `pages/4_그래프.py` | `/graph` |
| `pages/5_업로드.py` | `/upload` |
| `lib/api.py` 함수 1개 | TS fetch 훅 1개로 1:1 변환 (`ApiError` → 커스텀 Error 클래스) |
| `lib/viewmodel.py` | 로직 그대로 TS 유틸로 이식 (표시 구조 계산은 프레임워크 무관) |
| `lib/components.py::content_card` | `<ContentCard />` |
| `lib/components.py::recommendation_card` | `<RecommendationCard />` |
| `lib/components.py::render_contribution_heatmap` | `<ContributionHeatmap />` |
| `lib/ui.py::call` | fetch 훅의 에러 바운더리/토스트 |
| `lib/graph_viz.py` (pyvis + spring) | **폐기 예정** — `react-force-graph`로 대체 (서버 측 레이아웃 계산 불필요) |
| `st.session_state["user_id"]` | 세션/쿠키 기반 인증 상태 |

## 백엔드 API 계약 요약

베이스: `API_BASE_URL` (기본 `http://localhost:8000`). 오류는 `{"detail": "..."}`.

| 메서드 · 경로 | 파라미터 | 응답 핵심 필드 |
|---|---|---|
| `POST /auth/profile` | body: `display_name`, `persona`, `onboarding_answers` | `user_id`, `display_name`, `persona`, `current_level` |
| `GET /auth/profile/{user_id}` | path: `user_id` | 위와 동일 |
| `GET /content` | query: `source?`, `node_id?`, `difficulty?`, `limit`, `offset` | `items[]`(`id`,`title`,`url`,`source`,`author_name`,`difficulty`,`content_type`,`quality_score`,`tags`,`engagement_*`), `total` |
| `POST /content` (업로드) | body: `title`, `body`, `url?`, `user_id?` | `content_id`, `node_name`, `is_new_node`, `difficulty`, `content_type` |
| `GET /recommend` | query: `user_id`, `top_n` | `recommendations[]`(`content_id`,`title`,`url`,`score`,`reason`,`difficulty`,`content_type`,`summary`) — **`summary`는 백그라운드 lazy 가공이라 첫 응답에 `null`일 수 있음(HIVE-49)** |
| `GET /recommend/mastery` | query: `user_id` | `mastery`: `{node_id(str): 0~1}` |
| `GET /recommend/user-state` | query: `user_id` | `user_state`(자연어) |
| `PATCH /progress` (읽음) | body: `user_id`, `content_id` | `status`, `leveled_up`, `new_level`, `influence_score` |
| `PUT /feedback` | body: `user_id`, `content_id`, `feedback` | `status`, `feedback` |
| `DELETE /feedback` | body: `user_id`, `content_id` | `status` |
| `GET /feedback` | query: `user_id` | `{content_id: feedback}` |
| `GET /graph` | — | `nodes[]`(`id`,`kind`,`label`,`auto`), `edges[]`(`source`,`target`,`rel`,`weight`), `stats` |
| `GET /stats` | query: `user_id`, `days?` | `influence_score`, `streak`, `heatmap`(`{YYYY-MM-DD: count}`) |

피드백 타입 4종(고정): `understood` / `too_hard` / `want_more` / `not_interested`.
edge `rel`: `belongs_to` / `similar_to` / `precedes`. node `kind`: `topic` / `content`.

## 배포 현황 (2026-06-11)
맥미니 M4 셀프호스팅(docker compose)으로 **임시 Streamlit 공개** 중 — Next.js 전환 전까지의 운영 셸.

- 공개 사이트: https://macmini.tail67859f.ts.net (Streamlit)
- 백엔드 API: https://macmini.tail67859f.ts.net:8443 (Tailscale Funnel)

백엔드 API 주소는 `API_BASE_URL` 환경변수로 주입. 상세 구성은 `deploy/macmini/README.md` 참조.
