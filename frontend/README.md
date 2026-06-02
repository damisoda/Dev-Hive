# frontend — Streamlit

추천 결과와 커리큘럼을 보여주는 데모용 UI.

## 실행
```bash
cd frontend
pip install -r requirements.txt
streamlit run app.py
```

## 페이지 구성
- `app.py` — 진입점
- `pages/1_피드.py` — 콘텐츠 피드 (태그/난이도 필터)
- `pages/2_커리큘럼.py` — 내 학습 경로
- `pages/3_프로필.py` — 읽은 이력 + 영향력 점수

## 배포
Streamlit Community Cloud 또는 Railway. 백엔드 API 주소는 `API_BASE_URL` 환경변수로 주입.
