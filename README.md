# 자가복제형 기술 커뮤니티 (Self-Evolving Dev Community)

> 커뮤니티의 경험이 곧 다른 사람의 학습이 되는 플랫폼.
> AI 트렌드처럼 빠르게 변하는 도메인에서 커뮤니티 자체가 살아있는 교과서가 된다.

본 저장소는 서강대학교 INSIGHT 인콘 프로젝트의 구현체이다.

---

## 현황 (2026-06-28, Layer 3 진행)

- **배포**: 맥미니 M4 셀프호스팅 — 공개 사이트 https://macmini.tail67859f.ts.net (Next.js/web, Funnel 443→3000). 프런트 BFF는 백엔드를 compose 내부망(`http://backend:8000`)으로 호출해 브라우저 CORS가 없으며, 직접 API는 https://macmini.tail67859f.ts.net:8443 (Funnel 8443→8000, `/docs`)로도 접근 가능하다. 상세는 [`deploy/macmini/README.md`](deploy/macmini/README.md)
- **데이터**: 통합본 1283건 — velog 402 · github_trending 309 · huggingface 158 · github_discussions 145 · reddit 143 · x 122 · user(유저 업로드) 4. 가공(synthesis) 커버리지 1283/1283 (100%)
- **난이도 분포**: 중급 674 · 고급 401 · 입문 208
- **그래프**: 커리큘럼 노드 99개 (대주제 7 + auto 하위 92), precedes(node_links) 88엣지 (로컬모델 후보 생성 + 사람 검수 적재). GraphSAGE는 학습 파이프라인만 구축 — `graph_embedding`은 2026-06-26 재구축 후 미재export로 현재 0/1283(미적재)이고 추천에도 미반영(이전 코퍼스 val link-AUC 0.768)
- **평가 실측(run_eval)**: modularity 0.685 / tag_purity_topic(weighted) 0.595 (baseline 0.48) / tag_purity_content_type(weighted) 0.690 (baseline 0.469) / v_measure_topic 0.16 / v_measure_content_type 0.22 / coverage 0.91 / orphan_ratio 0.033

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
  (velog · github_trending · github_discussions · reddit · huggingface · x)
    ↓
QC 게이트 (소스 허용목록 · star≥100/서브레딧 큐레이션 · NSFW · 빈본문 · 중복 — LLM 비용 전 휴리스틱)
    ↓
AI 태깅 (Claude Haiku — 7대주제 relevance / 난이도 / 퀄리티 / content_type 5종 / 언어 / off_topic)
    ↓
임베딩 (OpenAI text-embedding-3-small — 원문 title+body 고정)
    ↓
Auto-HKG (그래프 자기조직화 — 2패스 흡수·클러스터링 + catch-all 자동분할로 노드 자동 생성·편입)
    ↓
적재 (건별 트랜잭션 · URL UPSERT · quality≥0.5 · relevance≥0.5 노드 매핑)
    ↓
GraphRAG 추천 (mean-centering 벡터 검색 + 4성분 스코어링 + precedes 경로점수 + Haiku 자연어 근거)
    ↓
개인화된 학습 경로 + 피드백 루프 + 레벨업 + 영향력 점수
```

가공(synthesis) 카드는 임베딩과 분리된 별도 JSONB로 저장되며, 적재 시점이 아니라 추천 확정·노출 시점에 lazy 생성·캐시된다(임베딩은 항상 원문 고정).

콘텐츠 생산자가 멈춰도 커뮤니티 그래프는 계속 진화한다. 이는 *Agentic Deep Graph Reasoning Yields Self-Organizing Knowledge Networks* (arXiv:2502.13025)의 자기조직화 명제와 일치한다.

---

## 3. 타겟 페르소나

본 프로젝트의 Core 페르소나는 개발자형(부트캠프 수료, 취업 준비, AI 툴 입문)이다. 마케터·기획자 등 직군 확장은 향후 과제로 둔다(현재 persona 기본값은 단일 '개발자').

대상 사용자의 공통 특성은 다음과 같다.

- AI 툴에 관심은 있으나 학습 진입점을 모름
- Reddit, X 등에서 정보 수집은 하지만 적용으로 이어지지 못함
- 자신의 현재 수준에 맞는 콘텐츠를 식별하기 어려움

---

## 4. 시스템 아키텍처

```
┌────────────────────────────────────────────────────┐
│ Presentation Layer   (Next.js / web — App Router +   │
│   BFF route, 서버사이드 백엔드 호출, JWT httpOnly 세션)│
├────────────────────────────────────────────────────┤
│ API Layer            (FastAPI / 맥미니 docker)       │
│   라우터 7종: auth·content·recommend·progress·       │
│   graph·feedback·stats (JWT Bearer 인증)             │
├────────────────────────────────────────────────────┤
│ Business Logic Layer                                │
│   온보딩 · 진도 추적(BKT-lite) · 레벨업 · 영향력 점수  │
│   · 피드백 신호 · profile_vector 동적 혼합            │
├────────────────────────────────────────────────────┤
│ AI / ML Layer                                       │
│   1. Auto-HKG  (2패스 + catch-all 분할 + LLM 네이밍) │
│   2. Knowledge Tracing (BKT-lite mastery 추정)       │
│   3. GraphRAG Recommendation (4성분 + 보너스 + 근거) │
│   4. GraphSAGE 노드 임베딩 (미적재 · 추천 미반영)     │
│   5. 가공 synthesis (content_type 5종 카드, lazy)    │
├────────────────────────────────────────────────────┤
│ Training Pipeline (off-line 배치, 로컬 학습)         │
├────────────────────────────────────────────────────┤
│ Data Layer                                          │
│   Postgres + pgvector (테이블 8종)                   │
├────────────────────────────────────────────────────┤
│ Ingestion Layer  (적재 전 QC 게이트 통과)             │
│   velog · github_trending · github_discussions ·    │
│   reddit · huggingface · x (Apify)                  │
└────────────────────────────────────────────────────┘
```

상세 설계는 [`docs/파이프라인.md`](docs/파이프라인.md)를 참조한다.

---

## 5. 멀티소스 구성

6종 소스에서 콘텐츠를 수집한다(크롤러 파일은 8개 — velog/reddit은 두 경로가 동일 라벨을 공유). 적재 전 QC 게이트(`backend/app/crawler/qc_gate.py`)를 통과해야 한다.

| 소스 (source 라벨) | 접근 방법 | 언어 | 운영 방식 | 적재량 (1283건 기준) |
|------|---------|------|---------|---------|
| velog | Velog 비공식 GraphQL (일반 + 입문자 변형) | 한국어 | 자동 (지속) | 402건 |
| github_trending | GitHub Search API + README 본문 보강 (star≥100) | 영문 | 자동 (지속) | 309건 |
| huggingface | daily papers API | 영문 | 자동 (지속) | 158건 |
| github_discussions | GitHub GraphQL API (`GITHUB_TOKEN` 필요) | 영문 | 자동 (지속) | 145건 |
| reddit | PRAW + Arctic Shift 공개 아카이브 (서브레딧 큐레이션) | 영문 | 자동 (지속) | 143건 |
| x (Twitter) | Apify 스크레이퍼 — 시드유저 14인 × 키워드 하이브리드 | 영문/한국어 | 자동 (`APIFY_TOKEN` 있으면) | 122건 |
| user (유저 업로드) | 업로드 파이프라인 (QC `expected_source="user"` 우회) | — | — | 4건 |

- **Hacker News(hn)**는 데이터 품질 미달로 완전 폐기했다(크롤러 없음, QC 게이트 허용목록에서도 제외되어 자동 거부).
- **Tistory**는 QC 허용목록에만 남아 있고 실제 수집 크롤러는 없다(현재 수집 경로 없음).
- QC 게이트는 precision 우선 휴리스틱으로 소스 미스라벨 강제정정(`source_mismatch`), 허용목록, NSFW, 빈 본문, github star<100, reddit 서브레딧/무응답 Q&A, X 본문 길이·언어·무참여, 배치 내 중복 URL을 검사한다. 유저 업로드는 NSFW·빈본문·중복만 적용(자가복제 일관성).

---

## 6. 핵심 기술 요소

### 6.1 Auto-HKG (Automatic Hierarchical Knowledge Graph)

수작업 스켈레톤(대주제 7개) 위에 그래프가 스스로 자란다. 콘텐츠 1건씩 그리디 매칭하던 v1이 고아노드를 양산하여(825개 중 94% 고아) 2패스 구조로 재설계했다.

- **1패스 흡수**: 스켈레톤 centroid 코사인 top ≥ `DEDUP_THRESHOLD=0.70`이면 기존 노드로 흡수. (배치 실행은 `dynamic_dedup` opt-in으로 노드별 동적 임계 `tau_j`를 사용한다 — HIVE-57.)
- **2패스 클러스터링**: 1패스에서 흡수되지 않은 잔여를 코사인 유사도 그래프(≥ `GROUP_THRESHOLD=0.65`)의 **연결요소**로 묶고, 최소 `MIN_CLUSTER_SIZE=3` 이상 클러스터만 노드로 승격한다. 승격 클러스터만 LLM(Haiku)이 이름을 붙인다(LLM 호출 = 클러스터 수, 콘텐츠 수 아님).
- **catch-all 자동분할** (HIVE-89): 잔여 매핑이 `CATCHALL_MIN_DEGREE=50` 이상으로 비대해진 노드를 spherical k-means(목표 크기 45)로 쪼개되, 자기군집 centroid 코사인 < `CATCHALL_OUTLIER_SIM=0.45`인 아웃라이어는 신규주제 후보로 보존한다.
- **단건 편입** (`expand_one`, 업로드 경로): 1건씩 편입하며 노드 생성을 허용한다(자가복제 모먼트). top 유사도 < `NEW_TOP_THRESHOLD=0.40`일 때만 새 대주제를 허용하고, 이상이면 하위노드로 강등한다.

실측(1283건): 커리큘럼 노드 99개 (대주제 7 + auto 하위 92), coverage 0.91 · orphan_ratio 0.033.

### 6.2 Knowledge Tracing (BKT-lite)

유저의 읽음 이력으로 노드별 mastery를 추정한다.

- **초기값**: 전 노드 0.0, 온보딩 답변 노드만 점수→mastery(0/0.1/0.2)로 약한 사전확률 부여(별도 퀴즈/자가평가 경로는 없음 — 경험형 콘텐츠엔 퀴즈가 부적합하다는 설계 결정).
- **읽음 갱신**: BKT 학습전이 `p ← p + (1−p)·gain`, 난이도별 gain(입문 0.10 / 중급 0.15 / 고급 0.20). relevance는 GraphRAG 관련성 성분과 이중계산을 피하기 위해 미반영.
- **레벨업 임계**: 입문→중급 0.6, 중급→고급 0.75. 읽음으로 학습한 대주제(mastery>0.2)의 평균으로 판정.

### 6.3 GraphRAG Recommendation

- **Stage A — Retrieval**: profile_vector ↔ 콘텐츠 text_embedding의 **mean-centering** 코사인(anisotropy 보정, 실측 분별력 0.031→0.922). 후보는 미독 + 임베딩 보유 + content_type ∉ {paper, news}.
- **Stage B — Scoring**: 4성분 점수 `관련성 0.3 · 난이도 0.4 · 경로 0.2 · 다양성 0.1`에 더해 3개 보너스 항을 가산한다 — want_more 피드백 보너스(0.15), recency 보너스(0.15, 중급·고급 전용, 반감기 90일), quality 보너스(0.10, 프로필 벡터 보유 유저만). 다양성은 그리디 MMR 재정렬 단계에서 가산된다.
- **경로 성분(precedes)**: `node_links`에 적재된 선행관계로 후보 토픽의 선행 mastery 가중평균을 계산한다(하위노드 자체 선행 우선, 없으면 부모 대주제 폴백). 선행이 없거나 비면 중립값 0.5. **현재 활성·배선 완료**(아래 6.5).
- **Stage C — Reasoning**: Haiku 1회 호출로 1순위 자연어 근거 생성(결정엔 미관여, 실패/키부재 시 템플릿 폴백).
- 콜드스타트 보정: 미학습 토픽은 선언 레벨 floor로 난이도 타깃을 올려 입문 편향을 해소한다(HIVE-95).
- GraphRAG 실패 시 `rule_based`로 자동 폴백한다.

**피드백 4종 즉시 반영**: `user_content_feedback` 테이블의 현재 상태를 매 추천마다 읽어 토글한다(저장된 파생값 없음). understood → 추천 제외 + 대표 토픽 mastery +0.15, too_hard → 대표 토픽 mastery −0.2, want_more → 별도 보너스 항(제외 안 함), not_interested → 제외.

**profile_vector**: OpenAI 호출 없이 기존 콘텐츠 임베딩 평균으로 구성하며, 읽음 건수에 따라 온보딩 벡터와 읽음 벡터를 선형 동적 혼합한다(읽음 0건 온보딩 100% → 20건 이상 온보딩 10%).

### 6.4 영향력 점수

기여를 측정하는 단일 정수 점수다(티어 없음).

```
influence = (read_score + streak·0.5 + contribution) × level_multiplier
```

- `read_score` = Σ(읽은 콘텐츠 × 난이도 가중 입문1/중급2/고급3)
- `streak` = 연속 학습일(KST)
- `contribution` (HIVE-96, "thesis의 심장") = 업로드 수 × 3 + 내 업로드를 남이 읽은 횟수 × 2
- `level_multiplier` = 입문 1.0 / 중급 1.15 / 고급 1.3

### 6.5 precedes (선행 학습 관계)

`node_links(source→target, weight=confidence)` 테이블에 topic 간 선행관계를 DAG로 적재하며, GraphRAG 경로 성분으로 **실제 배선·활성**되어 있다(현재 88엣지). 후보는 두 경로로 생성하고 모두 사람 검수(approved)를 거친다.

- 대주제 7개 간: `gen_precedes_candidates.py` — Anthropic Haiku(클라우드).
- 대주제별 하위노드 간(기초→심화): `gen_precedes_subnodes.py` — 로컬/원격 ollama(gemma, 맥미니 GPU를 SSH 터널로 사용).
- 적재(`load_precedes.py`)는 approved만, 자기참조·중복 제거 + DAG 사이클 거부 + 멱등 UPSERT.

### 6.6 GraphSAGE 자기지도학습 (미적재·미반영, future work)

topic–content 이종 그래프에서 링크 예측 자기지도학습을 수행한다. 타깃은 구조 신호(belongs_to + precedes)만 사용하고 similar_to는 텍스트 임베딩 파생이라 순환 방지를 위해 제외한다. 학습은 로컬 스크립트(`backend/scripts/train_graphsage_local.py`, PyTorch Geometric SAGEConv×2, 256d)로 수행하며 이전 코퍼스에서 val link-AUC 0.768을 얻었다. 산출 임베딩은 `content.graph_embedding`(pgvector 256d) 컬럼에 적재하도록 설계됐으나, **2026-06-26 전체 재구축 이후 재export하지 않아 현재 0/1283으로 비어 있다.** 또한 추천 retrieval은 text_embedding(1536d, mean-centering)만 사용하며 `graph_embedding`을 읽는 코드가 없다 — 즉 **학습 파이프라인만 구축됐고 적재·추천 반영은 모두 향후 과제다.**

---

## 7. 기술 스택

| 레이어 | 선택 |
|--------|------|
| 크롤러 | Python — PRAW, requests, Apify Actor (Velog GraphQL, GitHub Search/GraphQL API, HuggingFace API, Arctic Shift, X) |
| 임베딩 (텍스트) | OpenAI text-embedding-3-small (1536차원) |
| 임베딩 (그래프) | GraphSAGE (PyTorch Geometric, 256차원 — 학습 파이프라인만, 현재 미적재·미반영) |
| 벡터 저장소 | pgvector (Postgres 확장) |
| 태깅·가공·추천 근거 LLM | Anthropic Claude Haiku (`claude-haiku-4-5-20251001`) |
| precedes 후보 생성 LLM | Anthropic Haiku(대주제) + 로컬 ollama gemma/EXAONE(하위노드) |
| LLM 백엔드 토글 | `LLM_BACKEND=anthropic\|ollama` — 클라우드 Haiku ↔ 로컬 EXAONE(맥미니 GPU) 전환, 키 없으면 graceful |
| 백엔드 | FastAPI (Python) — JWT(PyJWT, HS256) Bearer 인증, bcrypt, rate limit |
| 프론트엔드 | Next.js ^15.1.6 (App Router) / React 19 / TypeScript 5.7 — `web/` (BFF route로 백엔드 호출, JWT httpOnly 세션) |
| 그래프 시각화 | react-force-graph-2d ^1.29.1 + d3-force ^3 (`web/components/GraphCanvas.tsx`) |
| 학습 환경 | 로컬 (`backend/scripts/train_graphsage_local.py`) — Colab 노트북 보조 |
| 인프라 | 맥미니 M4 셀프호스팅 (docker compose: pgvector + backend + web, Tailscale Funnel 공개) |

---

## 8. 차별점 요약

| 항목 | 기존 교육 플랫폼 | 본 플랫폼 |
|------|---------------|----------|
| 콘텐츠 생산 | 전문가 / 강사 | 커뮤니티 유저 + 멀티소스 크롤링 |
| 업데이트 주기 | 수개월 ~ 수년 | 실시간 (그래프 자기조직화) |
| 개인화 | 없음 또는 수동 | Knowledge Tracing 기반 자동화 |
| 추천 근거 제시 | 없음 | 자연어 설명 동반 |
| 트렌드 반영 | 느림 | 즉시 (Auto-HKG로 신규 노드 자동 편입) |
| 기여 반영 | 없음 | 업로드·소비 기반 영향력 점수 |

---

## 9. 프로젝트 로드맵 (레이어 구조)

| Layer | 기간 | 산출물 | 상태 |
|-------|------|--------|------|
| Layer 1 — Walking Skeleton | 5/25 – 5/31 | 단일 소스 기반 데이터 흐름 검증 | **완료** (1차 데모 5/31) |
| Layer 2 — Core MVP | 6/1 – 6/6 | 멀티소스 + GraphRAG + KT + GraphSAGE, 개발자 페르소나 | **완료** (2차 데모 6/6) |
| Layer 2 보강 | 6/7 – 6/15 | 자가복제(Auto-HKG 2패스 + 업로드) + QC 게이트 + 가공 + 피드백 루프 + 그래프 시각화 + 맥미니 배포 | **완료** |
| 시험 휴회 | 6/16 – 6/22 | 폴리시, 평가, 문서 한정 | **완료** |
| Layer 3 — Expansion | 6/23 – 6/28 | precedes 엣지 활성 · quality_score 랭킹 연결 · Next.js 일원화 · X 재적재 · JWT 인증 · funnel 계측 | **완료** (3차 데모 6/28) |
| 최종 발표 | 6/29 | — | 발표 심사 |

상세 일정은 [`docs/로드맵.md`](docs/로드맵.md)를 참조한다.

---

## 10. 학술적 근거

본 프로젝트의 핵심 아이디어는 다음 연구에 기반한다(코드 주석에 직접 인용된 4편을 핵심으로 둔다).

### 자기조직화 (자가복제 명제)
- [Agentic Deep Graph Reasoning Yields Self-Organizing Knowledge Networks (arXiv:2502.13025, Feb 2025)](https://arxiv.org/abs/2502.13025) — `graph/metrics.py` 인용

### Auto-HKG / KG 완성 (그래프 자기조직화)
- [LLM-Assisted Knowledge Graph Completion for Curriculum and Domain Modelling (arXiv:2501.12300)](https://arxiv.org/pdf/2501.12300) — `graph/metrics.py` 인용
- [Beyond Static Question Banks: Dynamic Knowledge Expansion via LLM-Automated Graph Construction (arXiv:2602.00020, CG-RAG)](https://arxiv.org/abs/2602.00020) — `recommend/graphrag.py` 인용 (ID/제목 재확인 권장)

### 선행관계 (precedes) 설계
- [GraphRAG-Induced Dual Knowledge Structure Graphs for Personalized Learning Path Recommendation (DLELP, arXiv:2506.22303)](https://arxiv.org/abs/2506.22303) — `scripts/gen_precedes_candidates.py` 인용, precedes 후보 생성의 청사진

### Graph Neural Networks
- Hamilton, W. L., Ying, R., & Leskovec, J. (2017). *Inductive Representation Learning on Large Graphs* (GraphSAGE), NeurIPS 2017
- Kipf, T. N., & Welling, M. (2017). *Semi-Supervised Classification with Graph Convolutional Networks*, ICLR 2017

### LLM Knowledge Tracing (보조)
- [Next Token Knowledge Tracing (arXiv:2511.02599, Nov 2025)](https://arxiv.org/abs/2511.02599)
- [LLM-KT: Aligning LLMs with Knowledge Tracing (arXiv:2502.02945)](https://arxiv.org/html/2502.02945v1)

### 학습 경로 추천 / Cold-Start (보조)
- [Multi-Agent Learning Path Planning via LLMs (arXiv:2601.17346, Jan 2026)](https://www.arxiv.org/pdf/2601.17346)
- [Educational Personalized Learning Path Planning with LLMs (arXiv:2407.11773)](https://arxiv.org/pdf/2407.11773)
- [EduLoop-Agent: Closed-Loop Personalized Learning Agent (arXiv:2510.22559, Oct 2025)](https://arxiv.org/pdf/2510.22559)
- [Cold-Start Recommendation towards the Era of LLMs: A Survey (arXiv:2501.01945, 2025)](https://arxiv.org/abs/2501.01945)
- [Cold-Start Recommendation with Knowledge-Guided RAG (arXiv:2505.20773)](https://arxiv.org/html/2505.20773v2)

추가 참고 문헌은 [`docs/파이프라인.md`](docs/파이프라인.md)의 9절을 참조한다.

---

## 11. 비용 추정

LLM 비용은 Haiku 배치(50% 할인)와 로컬 EXAONE 하이브리드(`LLM_BACKEND` 토글)로 낮게 유지한다. 인프라는 맥미니 셀프호스팅으로 실비용이 거의 없다.

| 항목 | 비용 |
|------|------|
| Apify 스크레이퍼 (X 시드유저 크롤) | 약 $15 이내 |
| LLM 태깅·가공 및 Auto-HKG 네이밍 (Haiku, 배치 50% 할인 / 또는 로컬 EXAONE 무료) | 약 $1 |
| 텍스트 임베딩 (text-embedding-3-small) | $0.02 |
| precedes 후보 생성 (로컬 ollama gemma — 맥미니 GPU) | $0 |
| GraphSAGE 학습 (로컬) | $0 |
| 추천 호출 (Haiku 근거 생성 1회) | 호출당 약 $0.0005 |
| 인프라 (맥미니 셀프호스팅 + Tailscale Funnel) | $0 |

---

## 12. 레포 구조

```
.
├── README.md
├── .gitignore
├── .env.example                       # 환경변수 템플릿 (키 이름만)
├── docker-compose.yml                 # 로컬 PostgreSQL + pgvector
├── railway.json                       # 이전 배포 경로 잔재 (현재 운영은 맥미니)
├── precedes_candidates.json           # 대주제 precedes 후보 (사람검수 approved 플래그)
├── precedes_subnode_candidates.json   # 하위노드 precedes 후보 (untracked)
├── .github/
│   └── PULL_REQUEST_TEMPLATE.md
├── scripts/                           # 시각화 생성 (gen_viz / gen_network_viz / gen_viz_autohkg_v2)
├── docs/                              # 기획 + 협업 문서
│   ├── 프로젝트_제안서.md / 로드맵.md / 파이프라인.md
│   ├── GitHub_협업가이드.md / PR_가이드.md / PR_템플릿.md / Jira_가이드.md
│   └── specs/                         # API_CHANGE_PROCESS.md + openapi-snapshot.json
├── db/                               # DB 스키마
│   ├── schema.sql                     # 테이블 8종 + pgvector + 마이그레이션
│   └── seed.sql                       # 대주제 7개 시드
├── deploy/
│   └── macmini/                       # 맥미니 운영 배포 (docker-compose.prod + setup)
├── backend/                          # FastAPI 백엔드
│   ├── app/
│   │   ├── main.py                    # 엔트리포인트 (ENABLE_SCHEDULER opt-in)
│   │   ├── config.py / database.py
│   │   ├── models/                    # SQLAlchemy 모델 (user/content/event/feedback/mapping)
│   │   ├── api/                       # 라우터 7종 (auth/content/recommend/progress/graph/feedback/stats)
│   │   ├── crawler/                   # 크롤러 8개 + qc_gate + normalizer + scheduler + run_crawler
│   │   ├── tagging/                   # tagger + synthesizer + embedder + ingest + loader
│   │   ├── graph/                     # auto_hkg + builder + export_graph + sage_export + metrics
│   │   ├── recommend/                 # graphrag (메인) + rule_based (폴백)
│   │   └── services/                  # KT·레벨업·영향력·profile_vector·업로드·피드백·lazy synthesis·llm 토글·security·rate_limit
│   ├── scripts/                       # 파이프라인 CLI (태깅·Auto-HKG·GraphSAGE 학습·평가·e2e·precedes 3종·데이터 위생·warm_synthesis)
│   ├── tests/ · data/
│   ├── requirements.txt
│   └── Dockerfile
├── web/                              # Next.js 프런트엔드 (App Router + BFF)
│   ├── app/                           # 페이지 9개(홈·discover·curriculum·graph·onboarding·profile·upload·welcome) + api/ BFF route 7개
│   ├── components/ (22개) · lib/      # ContentCard·GraphCanvas·ReadModal·AuthForm 등 + api·session
│   └── package.json
└── training/                         # GraphSAGE 학습 (Colab 노트북 — 기본 경로는 backend/scripts/train_graphsage_local.py)
    └── graphsage_train.ipynb
```

---

## 13. 설치 및 실행

### 사전 준비
```bash
cp .env.example .env
# .env에 API 키 입력 (Anthropic, OpenAI, Reddit, GitHub, Apify 등) — JWT_SECRET 필수
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

### 3. 프론트엔드 (web / Next.js)
```bash
cd web
npm install
npm run dev
# http://localhost:3000
```

### 배포 (운영 중)
맥미니 M4 셀프호스팅 — docker compose(pgvector + backend + web), `ENABLE_SCHEDULER=false`(재크롤 수동 트리거), launchd 자동시작. web은 `API_BASE_URL=http://backend:8000`으로 같은 compose 네트워크 내부에서 백엔드를 호출하므로 브라우저 CORS가 없다. 외부 공개는 Tailscale Funnel이 web(3000)을 서빙하며, 직접 API는 Funnel 8443→8000(`/docs`)로도 노출돼 있다.

- 공개 사이트: https://macmini.tail67859f.ts.net (Next.js/web)

상세 절차는 [`deploy/macmini/README.md`](deploy/macmini/README.md) 참조. (`railway.json`은 이전 배포 경로 잔재이며 발표 주간 백업용으로만 둔다.)

---

## 14. 인증 및 보안

- **방식**: 아이디·비밀번호 회원가입/로그인. bcrypt 해시 + HS256 JWT(`sub`=user_id, 만료 14일). `JWT_SECRET`이 비면 토큰 발급/검증을 거부한다.
- **IDOR 봉합**: `get_current_user`가 `Authorization: Bearer <jwt>` 서명을 검증한다(위조 가능한 `X-User-Id` 신뢰 방식을 대체).
- **방어 장치**: 로그인 실패 시 401(아이디 존재 여부 비노출) + 더미 bcrypt로 timing 사이드채널 차단, rate limit(login 5/60s, signup 10/3600s), 온보딩 점수 범위 검증.
- **프런트 세션**: BFF가 JWT를 `dh_token`(httpOnly, sameSite=lax, prod에서 secure, maxAge 14일) 쿠키로 저장한다. 표시용 보조 쿠키는 신뢰하지 않으며 인증은 오직 `dh_token` 서명으로 한다.

---

## 15. 기여 가이드

본 프로젝트는 커뮤니티가 스스로 진화하는 것을 철학으로 삼는다. 아이디어, 피드백, 코드 기여 모두 환영한다.

1. 저장소 Fork
2. 브랜치 생성: `git checkout -b feature/HIVE-XX-설명`
3. 커밋: `git commit -m "HIVE-XX feat: 설명"`
4. PR 생성 (`[HIVE-XX] type: 설명` 형식, Closes HIVE-XX)

브랜치 전략은 main / develop / feature 3단계를 사용한다. 작업 분배는 Jira에서 관리하며, 1 PR = 1 카드 = 1 작업을 원칙으로 한다.

---

## 16. 향후 확장 (백로그)

- 기여 기반 영향력 고도화 (현재 업로드·소비 항 구현 — 측정 지표 확장)
- Auto-HKG threshold 자동화 (동적 흡수임계 기본화 + precedes 임계 튜닝)
- GraphSAGE 임베딩 재export + 추천 retrieval 반영 (현재 미적재·미반영)
- 로컬 distill 태거 본배포 (현재 라이브는 Haiku 유지, distill은 relevance 약화로 보류)
- 하위노드 precedes 후보 적재 경로 정비 (로더-후보 스키마 정합 + name→id 재매핑)
- 직군 확장 (마케터·기획자 페르소나)
- GraphSAGE supervised fine-tuning, Generative Recommendation (TIGER, Semantic IDs)
