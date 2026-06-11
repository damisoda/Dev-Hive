# 자가복제형 기술 커뮤니티 (Self-Evolving Dev Community)

> 커뮤니티의 경험이 곧 다른 사람의 학습이 되는 플랫폼.
> AI 트렌드처럼 빠르게 변하는 도메인에서 커뮤니티 자체가 살아있는 교과서가 된다.

본 저장소는 서강대학교 INSIGHT 2차 인콘 프로젝트의 구현체이다.

---

## 현황 (2026-06-11, Layer 2 완료)

- **배포**: 맥미니 M4 셀프호스팅 — 공개 사이트 https://macmini.tail67859f.ts.net (Streamlit 임시), API https://macmini.tail67859f.ts.net:8443 (Tailscale Funnel). 상세는 [`deploy/macmini/README.md`](deploy/macmini/README.md)
- **데이터**: 통합본 994건 (velog 311 / github_trending 300 / huggingface 221 / reddit 91 / x 64 / 기타)
- **그래프**: Auto-HKG v2(2패스)로 자동노드 26개 · orphan 0, GraphSAGE 256차원 임베딩 994/994건 적재 (val link-AUC 0.768)
- **평가 실측**: modularity 0.512 / tag_purity_topic 0.7745 (baseline 0.4143) / V-measure_topic 0.4238 (baseline 0.1481) / coverage 0.214 / e2e 연결점검 11/12

---

## 1. 문제 의식

AI 기술의 발전 속도가 너무 빠르다. 개인이 혼자 이 흐름을 따라가기는 벅차다.

- Claude Code의 새 기능, 매일 올라오는 AI 패치노트
- GPT 이미지 생성, Crew AI의 멀티 에이전트 피드백 루프
- Obsidian × Claude 연동, GitHub 플러그인 생태계
- 그리고 이 모든 것이 6개월이면 낡아버린다

기존 플랫폼은 이 속도를 따라가지 못한다.

| 서비스 | 한계 |
|--------|------|
| 인프런 / Udemy | 강의 하나당 유료, 6개월이면 낡은 콘텐츠 |
| Reddit / X | 정보는 넘치지만 구조화 없음 |
| Dev.to / Hashnode | 글 공유는 되지만 개인화된 커리큘럼 불가 |

생산자가 멈추면 함께 멈추는 플랫폼이 아니라, 유저가 경험을 올릴수록 스스로 진화하는 플랫폼이 필요하다.

---

## 2. 솔루션 개요

주니어 개발자들이 AI 툴을 써보고 공유하면, AI가 그 경험을 학습 콘텐츠로 변환하여 커리큘럼에 자동 삽입한다.

```
유저 업로드 / 멀티소스 크롤링 (velog · tistory · reddit · github_trending · huggingface · x)
    ↓
QC 게이트 (소스 허용목록 · star/서브레딧 큐레이션 · NSFW · 중복 — LLM 비용 전 휴리스틱)
    ↓
AI 태깅 (Claude Haiku — 토픽 / 난이도 / 퀄리티 / content_type / 언어)
    ↓
가공 synthesis (content_type 5종 카드 — 임베딩은 원문 고정, 가공본은 별도 JSONB)
    ↓
임베딩 (OpenAI text-embedding-3-small 1536d)
    ↓
Auto-HKG v2 (그래프 자기조직화 — 2패스 흡수·클러스터링으로 노드 자동 생성 및 편입)
    ↓
GraphSAGE 임베딩 (256d) + LLM Knowledge Tracing
    ↓
GraphRAG 추천 (mean-centering 벡터 검색 + 4성분 스코어링 + Haiku 자연어 근거)
    ↓
개인화된 학습 경로 + 피드백 루프 + 레벨업 + 영향력 점수
```

콘텐츠 생산자가 멈춰도 커뮤니티 그래프는 계속 진화한다. 이는 *Agentic Deep Graph Reasoning Yields Self-Organizing Knowledge Networks* (arXiv:2502.13025)의 자기조직화 명제와 일치한다.

---

## 3. 타겟 페르소나

본 프로젝트는 단계적으로 페르소나를 확장한다.

| 단계 | 페르소나 | 시점 |
|------|---------|------|
| Core MVP | 개발자형 (부트캠프 수료, 취업 준비, AI 툴 입문) | 2차 데모 (6/6) |
| Expansion | 마케터형, 기획자형 | 3차 데모 (6/28) |

대상 사용자의 공통 특성은 다음과 같다.

- AI 툴에 관심은 있으나 학습 진입점을 모름
- Reddit, X 등에서 정보 수집은 하지만 적용으로 이어지지 못함
- 자신의 현재 수준에 맞는 콘텐츠를 식별하기 어려움

---

## 4. 시스템 아키텍처

```
┌────────────────────────────────────────────────────┐
│ Presentation Layer   (Streamlit 임시 — Next.js 전환  │
│   예정. api/viewmodel/렌더 3층 분리 완료)             │
├────────────────────────────────────────────────────┤
│ API Layer            (FastAPI / 맥미니 docker)       │
├────────────────────────────────────────────────────┤
│ Business Logic Layer                                │
│   온보딩 · 진도 추적 · 레벨업 · 영향력 점수 · 피드백   │
├────────────────────────────────────────────────────┤
│ AI / ML Layer                                       │
│   1. Auto-HKG v2       (2패스 + LLM 네이밍)          │
│   2. LLM Knowledge Tracing (mastery 추정)            │
│   3. GraphRAG Recommendation (4성분 + LLM 근거)      │
│   4. GraphSAGE 노드 임베딩 (자기지도학습 산출물)       │
│   5. 가공 synthesis    (content_type 5종 카드)       │
├────────────────────────────────────────────────────┤
│ Training Pipeline (off-line 배치, 로컬 CPU 학습)     │
├────────────────────────────────────────────────────┤
│ Data Layer                                          │
│   Postgres + pgvector                               │
├────────────────────────────────────────────────────┤
│ Ingestion Layer  (적재 전 QC 게이트 통과)             │
│   자동: Velog/Tistory · Reddit · GitHub Trending ·  │
│         HuggingFace   일회성: X (Apify, 시드유저)    │
└────────────────────────────────────────────────────┘
```

상세 설계는 [`docs/파이프라인.md`](docs/파이프라인.md)를 참조한다.

---

## 5. 멀티소스 구성

총 6개 소스에서 콘텐츠를 수집한다. 적재 전 QC 게이트(`backend/app/crawler/qc_gate.py`)를 통과해야 한다.

| 소스 | 접근 방법 | 언어 | 운영 방식 | 적재량 (994건 기준) |
|------|---------|------|---------|---------|
| Velog (+Tistory) | Velog GraphQL 검색 | 한국어 | 자동 (지속) | 311건 |
| GitHub Trending | GitHub Search API + README 보강 | 영문 | 자동 (지속) | 300건 |
| HuggingFace | daily papers API | 영문 | 자동 (지속) | 221건 |
| Reddit | PRAW / Arctic Shift 아카이브 | 영문 | 자동 (지속) | 91건 |
| X (Twitter) | Apify 스크레이퍼 — 시드유저 14인 전문가 계정 | 영문/한국어 | 일회성 | 64건 |
| 기타 (유저 업로드 등) | — | — | — | 잔여 |

Hacker News는 데이터 품질 미달로 폐기했고(QC 게이트가 자동 거부), Threads는 수집하지 않는다.
X 자동 파이프라인은 future work로 명시한다.

---

## 6. 핵심 기술 요소

### 6.1 Auto-HKG v2 (Automatic Hierarchical Knowledge Graph)

수작업 스켈레톤(대주제 7개) 위에 그래프가 스스로 자란다. 콘텐츠 1건씩 그리디 매칭하던 v1이 고아노드를 양산하여(825개 중 94% 고아) 2패스 구조로 재설계했다:
1패스 — 대주제 centroid 코사인 ≥ 0.70이면 기존 노드로 흡수, 2패스 — 잔여 콘텐츠를 유사도 그래프(≥ 0.65)의 연결요소로 클러스터링(최소 3건)한 뒤 승격 클러스터만 LLM이 네이밍.
실측(994건): 자동노드 26개 · orphan 0.

### 6.2 LLM Knowledge Tracing

유저의 읽음 이력과 자가평가 답변으로 노드별 mastery를 추정(BKT-lite)하고, 자연어 user_state 텍스트로 직렬화하여 추천 근거 생성의 컨텍스트로 주입한다.

### 6.3 GraphRAG Recommendation

추천 결정은 알고리즘 4성분 점수(관련성 0.3 · 난이도 0.4 · 경로 0.2 · 다양성 0.1)로 내린다.

- Stage A — Retrieval: profile_vector ↔ 콘텐츠 임베딩 **mean-centering** 코사인 (anisotropy 보정, 실측 분별력 0.031→0.922)
- Stage B — Reasoning: Haiku 1회 호출로 1순위 자연어 근거 생성 (결정엔 미관여, 실패 시 템플릿 폴백)

피드백 4종(understood / too_hard / want_more / not_interested)이 다음 추천에 즉시 반영되고, GraphRAG 실패 시 rule_based로 자동 폴백한다. 추천 확정 콘텐츠의 가공 카드는 BackgroundTasks로 lazy 생성·캐시한다.

### 6.4 GraphSAGE 자기지도학습

topic(커리큘럼 노드)–content 이종 그래프에서 링크 예측 자기지도학습을 수행한다. 타깃은 구조 신호(belongs_to + precedes)만 사용하고 similar_to는 텍스트 파생이라 순환 방지를 위해 제외한다. 학습은 로컬 스크립트(`backend/scripts/train_graphsage_local.py`)로 CPU 약 7초에 끝나며(val link-AUC 0.768), 256차원 임베딩이 994/994건 적재되어 있다. Colab 노트북(`training/`)은 GPU용으로 유지한다.

---

## 7. 기술 스택

| 레이어 | 선택 |
|--------|------|
| 크롤러 (자동) | Python — PRAW, requests (Velog GraphQL, GitHub API, HuggingFace API, Arctic Shift) |
| 크롤러 (일회성) | Apify Actor (X 시드유저 14인) |
| 임베딩 (텍스트) | OpenAI text-embedding-3-small (1536차원) |
| 임베딩 (그래프) | GraphSAGE (PyTorch Geometric, 256차원) |
| 벡터 저장소 | pgvector (Postgres 확장) |
| 태깅·가공·추천 LLM | Anthropic Claude Haiku 4.5 |
| 백엔드 | FastAPI (Python) |
| 프론트엔드 | Streamlit (임시 — api/viewmodel/렌더 3층 분리, Next.js 마이그레이션 준비 완료) |
| 그래프 시각화 | pyvis + networkx (Next.js 이행 시 react-force-graph로 대체 예정) |
| 학습 환경 | 로컬 CPU (`backend/scripts/train_graphsage_local.py`, 약 7초) — Colab 노트북 보조 |
| 인프라 | 맥미니 M4 셀프호스팅 (docker compose: pgvector + backend + frontend, Tailscale Funnel 공개) |

---

## 8. 차별점 요약

| 항목 | 기존 교육 플랫폼 | 본 플랫폼 |
|------|---------------|----------|
| 콘텐츠 생산 | 전문가 / 강사 | 커뮤니티 유저 + 멀티소스 크롤링 |
| 업데이트 주기 | 수개월 ~ 수년 | 실시간 (그래프 자기조직화) |
| 개인화 | 없음 또는 수동 | LLM Knowledge Tracing 기반 자동화 |
| 추천 근거 제시 | 없음 | 자연어 설명 동반 |
| 트렌드 반영 | 느림 | 즉시 (Auto-HKG로 신규 노드 자동 편입) |

---

## 9. 프로젝트 로드맵 (레이어 구조)

| Layer | 기간 | 산출물 | 상태 |
|-------|------|--------|------|
| Layer 1 — Walking Skeleton | 5/25 – 5/31 | 단일 소스 기반 데이터 흐름 검증 | **완료** (1차 데모 5/31) |
| Layer 2 — Core MVP | 6/1 – 6/6 | 멀티소스 + GraphRAG + LLM KT + GraphSAGE, 개발자 페르소나 | **완료** (2차 데모 6/6) |
| Layer 2 보강 | 6/7 – 6/15 | 자가복제(Auto-HKG v2 + 업로드) + QC 게이트 + 가공 + 피드백 루프 + 그래프 시각화 + 맥미니 배포 | **완료** (6/11) |
| 시험 휴회 | 6/16 – 6/22 | 폴리시, 평가, 문서 한정 | 예정 |
| Layer 3 — Expansion | 6/23 – 6/28 | precedes 엣지 · quality_score 랭킹 연결 · Next.js 전환 · 직군 확장(마케터·기획자) | 예정 (3차 데모 6/28) |
| 최종 발표 | 6/29 | — | 발표 심사 |

상세 일정은 [`docs/로드맵.md`](docs/로드맵.md)를 참조한다.

---

## 10. 학술적 근거

본 프로젝트의 핵심 아이디어는 다음 연구에 기반한다.

### 자가복제 명제
- [Agentic Deep Graph Reasoning Yields Self-Organizing Knowledge Networks (arXiv:2502.13025, Feb 2025)](https://arxiv.org/abs/2502.13025)

### Generative GraphRAG / Auto-HKG
- [Beyond Static Question Banks: Dynamic Knowledge Expansion via LLM-Automated Graph Construction (arXiv:2602.00020)](https://arxiv.org/pdf/2602.00020)
- [LLM-Powered Construction of Course Knowledge-Competency Graphs (ACM 2025)](https://dl.acm.org/doi/10.1145/3766557.3766569)
- [Generative GraphRAG for Education (MDPI 2025)](https://www.mdpi.com/2076-3417/15/14/7655)
- [LLM-Assisted Knowledge Graph Completion for Curriculum and Domain Modelling (arXiv:2501.12300)](https://arxiv.org/pdf/2501.12300)

### Graph Neural Networks
- Hamilton, W. L., Ying, R., & Leskovec, J. (2017). *Inductive Representation Learning on Large Graphs* (GraphSAGE), NeurIPS 2017
- Kipf, T. N., & Welling, M. (2017). *Semi-Supervised Classification with Graph Convolutional Networks*, ICLR 2017

### LLM Knowledge Tracing
- [Next Token Knowledge Tracing (arXiv:2511.02599, Nov 2025)](https://arxiv.org/abs/2511.02599)
- [LLM-KT: Aligning LLMs with Knowledge Tracing (arXiv:2502.02945)](https://arxiv.org/html/2502.02945v1)
- [LPReKL: KT + LLM Learning Path Recommendation (MDPI 2025)](https://www.mdpi.com/2079-9292/14/22/4385)

### 학습 경로 추천
- [Multi-Agent Learning Path Planning via LLMs (arXiv:2601.17346, Jan 2026)](https://www.arxiv.org/pdf/2601.17346)
- [Educational Personalized Learning Path Planning with LLMs (arXiv:2407.11773)](https://arxiv.org/pdf/2407.11773)
- [EduLoop-Agent: Closed-Loop Personalized Learning Agent (arXiv:2510.22559, Oct 2025)](https://arxiv.org/pdf/2510.22559)

### Cold-Start Recommendation
- [Cold-Start Recommendation towards the Era of LLMs: A Survey (arXiv:2501.01945, 2025)](https://arxiv.org/abs/2501.01945)
- [Cold-Start Recommendation with Knowledge-Guided RAG (arXiv:2505.20773)](https://arxiv.org/html/2505.20773v2)

추가 참고 문헌은 [`docs/파이프라인.md`](docs/파이프라인.md)의 9절을 참조한다.

---

## 11. 비용 추정

MVP 전체 운영 비용은 미화 35달러 이내로 추정한다 (기획 시점 추정 — Threads는 폐기, 인프라는 맥미니 셀프호스팅으로 전환되어 실비용은 더 낮다).

| 항목 | 비용 |
|------|------|
| Apify 스크레이퍼 (X 시드유저 크롤) | 약 $15 이내 |
| LLM 태깅·가공 및 Auto-HKG (Haiku, 배치 50% 할인) | 약 $1 |
| 텍스트 임베딩 (text-embedding-3-small) | $0.02 |
| GraphSAGE 학습 (로컬 CPU 약 7초) | $0 |
| 추천 호출 (Haiku 근거 생성 1회) | 호출당 약 $0.0005 |
| 인프라 (맥미니 셀프호스팅 + Tailscale Funnel) | $0 |
| 개발 및 디버깅 버퍼 | 약 $5 |

---

## 12. 레포 구조

```
.
├── README.md
├── .gitignore
├── .env.example                       # 환경변수 템플릿 (키 이름만)
├── docker-compose.yml                 # 로컬 PostgreSQL + pgvector
├── railway.json                       # Railway 배포 설정 (현재 운영은 맥미니)
├── .github/
│   └── PULL_REQUEST_TEMPLATE.md
├── docs/                              # 기획 + 협업 문서
│   ├── 프로젝트_제안서.md
│   ├── 로드맵.md
│   ├── 파이프라인.md
│   ├── GitHub_협업가이드.md
│   ├── PR_가이드.md / PR_템플릿.md
│   └── Jira_가이드.md / Jira-GitHub_연동가이드.md
├── db/                               # DB 스키마
│   ├── schema.sql                     # 테이블 7종 + pgvector
│   └── seed.sql                       # 대주제 7개 시드
├── deploy/
│   └── macmini/                       # 맥미니 운영 배포 (compose.prod + setup)
├── backend/                          # FastAPI 백엔드
│   ├── app/
│   │   ├── main.py                    # 엔트리포인트 (ENABLE_SCHEDULER opt-in)
│   │   ├── config.py                  # 환경변수 로딩
│   │   ├── database.py                # DB 연결
│   │   ├── models/                    # SQLAlchemy 모델
│   │   ├── api/                       # 엔드포인트 (auth/content/recommend/progress/feedback/graph/stats)
│   │   ├── crawler/                   # 크롤링 (6개 소스) + QC 게이트 + 스케줄러
│   │   ├── tagging/                   # 태깅 + 가공(synthesis) + 임베딩 + 적재
│   │   ├── graph/                     # 그래프 빌더 + Auto-HKG v2 + GraphSAGE export/적재 + 지표
│   │   ├── recommend/                 # GraphRAG (메인) + rule_based (폴백)
│   │   └── services/                  # KT·레벨업·영향력·profile_vector·업로드·피드백 신호·lazy synthesis
│   ├── scripts/                       # 파이프라인 CLI (태깅·Auto-HKG·GraphSAGE 학습·평가·e2e)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                         # Streamlit (api/viewmodel/렌더 3층 분리)
│   ├── app.py
│   ├── lib/                           # api.py · viewmodel.py · ui.py · components.py · graph_viz.py
│   ├── pages/                         # 피드 · 커리큘럼 · 프로필 · 그래프 · 업로드
│   └── requirements.txt
└── training/                         # GraphSAGE 학습 (Colab 노트북 — 기본 경로는 backend/scripts/train_graphsage_local.py)
    └── graphsage_train.ipynb
```

---

## 13. 설치 및 실행

### 사전 준비
```bash
cp .env.example .env
# .env에 API 키 입력 (Anthropic, OpenAI, Reddit 등)
```

### 1. 데이터베이스 (Docker)
```bash
docker compose up -d
# PostgreSQL + pgvector 기동, schema.sql + seed.sql 자동 적용
```

### 2. 백엔드
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
# http://localhost:8000/health 로 확인
```

### 3. 프론트엔드
```bash
cd frontend
pip install -r requirements.txt
streamlit run app.py
```

### 배포 (2026-06-11 운영 중)
맥미니 M4 셀프호스팅 — docker compose(pgvector + backend + frontend), `ENABLE_SCHEDULER=false`(재크롤 수동 트리거), launchd 자동시작.

- 공개 사이트: https://macmini.tail67859f.ts.net (Streamlit 임시)
- API: https://macmini.tail67859f.ts.net:8443 (Tailscale Funnel)

상세 절차는 [`deploy/macmini/README.md`](deploy/macmini/README.md) 참조. (`railway.json`은 이전 배포 경로 잔재.)

---

## 14. 기여 가이드

본 프로젝트는 커뮤니티가 스스로 진화하는 것을 철학으로 삼는다. 아이디어, 피드백, 코드 기여 모두 환영한다.

1. 저장소 Fork
2. 브랜치 생성: `git checkout -b feature/your-idea`
3. 커밋: `git commit -m "feat: 설명"`
4. PR 생성

브랜치 전략은 main / dev / feature 3단계를 사용한다. 작업 분배는 Jira에서 관리한다.

---

## 15. 향후 확장 (Layer 3 / 백로그)

- precedes 엣지 생성 (선행 학습 연결) — GraphRAG 경로 성분 활성화
- quality_score → 추천 랭킹 연결
- Next.js / Vercel 프론트엔드 전환 (3층 분리로 마이그레이션 준비 완료)
- X 재적재 (likes 정상화 반영)
- 직군 확장 (마케터·기획자 페르소나)
- 유저 상호작용 데이터 누적 시 GraphSAGE 임베딩의 supervised fine-tuning
- Generative Recommendation (TIGER, Semantic IDs) 로의 확장
- LLM 태깅을 소형 로컬 모델로 distillation 하여 추론 비용 절감
