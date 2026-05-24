# 자가복제형 기술 커뮤니티 (Self-Evolving Dev Community)

> 커뮤니티의 경험이 곧 다른 사람의 학습이 되는 플랫폼.
> AI 트렌드처럼 빠르게 변하는 도메인에서 커뮤니티 자체가 살아있는 교과서가 된다.

본 저장소는 서강대학교 INSIGHT 2차 인콘 프로젝트의 구현체이다.

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
유저 업로드 / 멀티소스 크롤링
    ↓
AI 태깅 (토픽 / 난이도 / 직군 / 퀄리티 / 언어)
    ↓
Auto-HKG (그래프 자기조직화 — 노드 자동 생성 및 편입)
    ↓
GraphSAGE 임베딩 + LLM Knowledge Tracing
    ↓
GraphRAG 추천 (벡터 검색 + LLM rerank + 자연어 근거 생성)
    ↓
개인화된 학습 경로 + 작성자 영향력 점수
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
│ Presentation Layer            (Next.js / Vercel)    │
├────────────────────────────────────────────────────┤
│ API Layer                     (FastAPI / Railway)   │
├────────────────────────────────────────────────────┤
│ Business Logic Layer                                │
│   온보딩 · 진도 추적 · 영향력 점수                    │
├────────────────────────────────────────────────────┤
│ AI / ML Layer                                       │
│   1. Auto-HKG          (LLM 프롬프트)                │
│   2. LLM Knowledge Tracing (LLM 프롬프트)            │
│   3. GraphRAG Recommendation (LLM 프롬프트)          │
│   4. GraphSAGE 노드 임베딩 (자기지도학습 산출물)       │
├────────────────────────────────────────────────────┤
│ Training Pipeline (off-line 배치, Google Colab)     │
├────────────────────────────────────────────────────┤
│ Data Layer                                          │
│   Postgres + pgvector                               │
├────────────────────────────────────────────────────┤
│ Ingestion Layer                                     │
│   자동: Reddit · GitHub Trending · HN · RSS         │
│   일회성: X · Threads (Apify)                       │
└────────────────────────────────────────────────────┘
```

상세 설계는 [`파이프라인.md`](파이프라인.md)를 참조한다.

---

## 5. 멀티소스 구성

총 6개 소스에서 콘텐츠를 수집한다.

| 소스 | 접근 방법 | 언어 | 운영 방식 | 목표 수집량 |
|------|---------|------|---------|---------|
| Reddit | PRAW | 영문 | 자동 (지속) | 600건 |
| GitHub Trending | 공식 API | 영문 | 자동 (지속) | 300건 |
| Hacker News | Algolia API | 영문 | 자동 (지속) | 300건 |
| Velog / Tistory | RSS | 한국어 | 자동 (지속) | 300건 |
| X (Twitter) | Apify 스크레이퍼 | 영문/한국어 | 일회성 | 500건 |
| Threads | Apify 스크레이퍼 + 공식 API | 영문/한국어 | 일회성 | 200건 |

총 시드 약 2200건. X와 Threads의 자동 파이프라인은 future work로 명시한다.

---

## 6. 핵심 기술 요소

### 6.1 Auto-HKG (Automatic Hierarchical Knowledge Graph)

LLM이 새 콘텐츠의 그래프 적합도를 판단하여, 기존 CurriculumNode에 매칭하거나 새 하위 노드를 자동 생성한다. 수작업 스켈레톤 위에 AI가 그래프를 키워나가는 구조이다.

### 6.2 LLM Knowledge Tracing

유저의 읽음 이력과 자가평가 답변을 자연어 텍스트로 직렬화하여 추천 프롬프트의 컨텍스트로 주입한다. 별도 학습 없이 LLM이 직접 mastery 상태를 해석한다.

### 6.3 GraphRAG Recommendation

두 단계로 작동한다.

- Stage A — Retrieval: pgvector 기반 결합 임베딩(텍스트 + GraphSAGE) 코사인 유사도로 후보 10건 추출 및 룰 필터링
- Stage B — Reasoning: Haiku 1회 호출로 상위 3건 재정렬 및 1순위 자연어 근거 생성

### 6.4 GraphSAGE 자기지도학습

Content–Author–Tag–CurriculumNode–Source 이종 그래프에서 자기지도학습을 수행한다. 학습 산출물인 노드 임베딩은 텍스트 임베딩과 결합하여 retrieval에 활용된다. Google Colab 무료 티어에서 PyTorch Geometric으로 구현한다.

---

## 7. 기술 스택

| 레이어 | 선택 |
|--------|------|
| 크롤러 (자동) | Python — PRAW, requests, feedparser |
| 크롤러 (일회성) | Apify Actor (Twitter Scraper, Threads Scraper) |
| 임베딩 (텍스트) | OpenAI text-embedding-3-small |
| 임베딩 (그래프) | GraphSAGE (PyTorch Geometric) |
| 벡터 저장소 | pgvector (Postgres 확장) |
| 태깅 및 추천 LLM | Anthropic Claude Haiku 4.5 |
| 백엔드 | FastAPI (Python) |
| 프론트엔드 | Next.js + Tailwind CSS |
| 그래프 시각화 | react-force-graph |
| 학습 환경 | Google Colab 무료 티어 (T4 GPU) |
| 인프라 | Railway (BE + DB) + Vercel (FE) |

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

| Layer | 기간 | 산출물 | 데모 |
|-------|------|--------|------|
| Layer 1 — Walking Skeleton | 5/25 – 5/31 | Reddit 단일 소스 기반 데이터 흐름 검증 | 1차 데모 5/31 |
| Layer 2 — Core MVP | 6/1 – 6/6 | 6개 소스 + GraphRAG + LLM KT + GraphSAGE, 개발자 페르소나 | 2차 데모 6/6 |
| Layer 2 보강 | 6/7 – 6/15 | 자가복제 (Auto-HKG + 업로드) + 그래프 시각화 + 정식 배포 | — |
| 시험 휴회 | 6/16 – 6/22 | 폴리시, 평가, 문서 한정 | — |
| Layer 3 — Expansion | 6/23 – 6/28 | 마케터·기획자 페르소나 추가 | 3차 데모 6/28 |
| 최종 발표 | 6/29 | — | 발표 심사 |

상세 일정은 [`로드맵.md`](로드맵.md)를 참조한다.

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

추가 참고 문헌은 [`파이프라인.md`](파이프라인.md)의 9절을 참조한다.

---

## 11. 비용 추정

MVP 전체 운영 비용은 미화 35달러 이내로 추정한다.

| 항목 | 비용 |
|------|------|
| Apify 스크레이퍼 (X 500건 + Threads 200건) | 약 $15 |
| LLM 태깅 및 Auto-HKG (Haiku × 2200건) | 약 $1 |
| 텍스트 임베딩 (text-embedding-3-small × 2200건) | $0.02 |
| GraphSAGE 학습 (Colab 무료 티어) | $0 |
| 추천 호출 (Haiku rerank + 근거 생성) | 호출당 약 $0.0005 |
| 인프라 (Railway + Vercel, 2개월) | 약 $10 |
| 개발 및 디버깅 버퍼 | 약 $5 |

---

## 12. 프로젝트 문서 구조

```
.
├── README.md                  # 본 문서
├── 프로젝트_제안서.md           # 제안 단계 문서
├── 로드맵.md                   # 레이어 기반 실행 로드맵
└── 파이프라인.md                # 시스템 파이프라인 상세 설계
```

---

## 13. 설치 및 실행

> 구현 진행 중. Layer 1 (5/31) 완료 시점부터 실행 가능한 형태로 갱신될 예정이다.

예정 구조:

```
backend/        FastAPI 서비스 (크롤러, AI 파이프라인, API)
frontend/       Next.js 애플리케이션
training/       GraphSAGE 학습 노트북 (Google Colab 호환)
docs/           아키텍처 다이어그램 및 의사결정 기록
```

---

## 14. 기여 가이드

본 프로젝트는 커뮤니티가 스스로 진화하는 것을 철학으로 삼는다. 아이디어, 피드백, 코드 기여 모두 환영한다.

1. 저장소 Fork
2. 브랜치 생성: `git checkout -b feature/your-idea`
3. 커밋: `git commit -m "feat: 설명"`
4. PR 생성

브랜치 전략은 main / dev / feature 3단계를 사용한다. 작업 분배는 Jira에서 관리한다.

---

## 15. 향후 확장 (Future Work)

- 유저 상호작용 데이터 누적 시 GraphSAGE 임베딩의 supervised fine-tuning
- X / Threads의 자동 파이프라인 확장 (X API Basic 구독 또는 우회 경로)
- Generative Recommendation (TIGER, Semantic IDs) 로의 확장
- LLM 태깅을 KoBERT 등 소형 모델로 distillation 하여 추론 비용 절감
- 추가 페르소나 (디자이너, 데이터 분석가 등) 지원
