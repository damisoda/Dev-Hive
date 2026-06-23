# Dev-Hive Web (1차 프런트 프로토타입 · HIVE-67)

Streamlit 프런트(`/frontend`)를 Next.js로 이행하는 첫 슬라이스. **홈 피드 한 화면**을
우리 백엔드(`/content`)에 직접 와이어링한 프로토타입이다. 규원 HIVE-64(Next.js 골격)의
참조 슬라이스로 삼는다.

## 설계 메모
- **서버 컴포넌트에서 백엔드 직접 fetch** → 브라우저 CORS 불필요(백엔드 무수정).
  브라우저 직접 호출이 필요해지면 HIVE-64에서 `CORSMiddleware`로 처리.
- `lib/api.ts`·`lib/viewmodel.ts`는 Streamlit `frontend/lib/{api,viewmodel}.py`의 1:1 TS 이식.
  UI 프레임워크 비의존 층이라 그대로 살아남는다.
- 디자인 토큰: 라이트 · 무채색 zinc · Pretendard · 앰버 액센트(`app/globals.css`).

## 실행
```bash
cd web
cp .env.local.example .env.local   # 필요 시 API_BASE_URL 수정
npm install
npm run dev                        # http://localhost:3000
```
백엔드(`uvicorn`, 기본 :8000)가 떠 있어야 피드가 채워진다. 꺼져 있으면 연결 실패 상태로 안내.

## 범위(현재 슬라이스)
- [x] 홈 피드: `/content` 최신순 렌더, pill(출처·난이도·타입), 메타, 원문 링크
- [x] 빈 상태 / 연결 실패·에러 상태 분기
- [x] 상단 네비(웹사이트형) — 홈만 동작, 디스커버·커리큘럼·프로필은 자리만
- [ ] 개인화 추천(`/recommend`), 페이지네이션·필터, 업로드 — 후속
