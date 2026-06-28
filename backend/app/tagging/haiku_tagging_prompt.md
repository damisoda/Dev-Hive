# Haiku 태깅 프롬프트 v0

## 목적

크롤링되거나 업로드된 AI 관련 콘텐츠를 읽고, 커리큘럼 추천에 필요한 태그 정보를 JSON으로 생성한다.

## 입력 콘텐츠

```json
{
  "title": "{{title}}",
  "body": "{{body}}",
  "source": "{{source}}",
  "author_name": "{{author_name}}",
  "url": "{{url}}",
  "published_at": "{{published_at}}",
  "language": "{{language}}",
  "engagement": {
    "likes": {{likes}},
    "comments": {{comments}}
  }
}
```

## 대주제 7개

아래 7개 대주제 각각에 대해 콘텐츠 관련도를 0.0부터 1.0 사이 숫자로 평가한다.

| 대주제 | 판단 기준 |
| --- | --- |
| 프롬프트 엔지니어링 | 프롬프트 작성법, 출력 형식 제어, few-shot, CoT, 시스템 프롬프트 |
| Agentic AI | AI 에이전트, MCP, 도구 호출, 멀티 에이전트, 자동화 에이전트, Claude Code/Codex 활용 |
| 멀티모달 AI | 이미지, 비디오, 오디오, 비전 모델, 생성형 미디어, VLM/VLA |
| RAG & 지식 관리 | 임베딩, 벡터 DB, 검색 증강 생성, 지식 베이스, 문서 검색, Obsidian/Notion 지식 관리 |
| 오픈소스 AI | Hugging Face, 오픈 모델, Ollama, vLLM, 로컬 추론, fine-tuning |
| AI 워크플로우 & 자동화 | n8n, Make, Zapier, 업무 자동화, 반복 작업 자동화, AI 도구 조합 |
| AI 엔지니어링 | AI API 개발, 배포, MLOps, 풀스택 구현, 성능/비용 최적화, 프로덕션 운영 |

## difficulty 기준

반드시 아래 셋 중 하나만 사용한다.

| 값 | 기준 |
| --- | --- |
| 입문 | 비전공자·초보자도 따라 할 수 있는 기본 개념, 쉬운 튜토리얼, 도구 첫 사용법, AI가 처음인 사람 대상 글 |
| 중급 | 기본 사용 경험이 있는 사람이 workflow를 개선하거나 여러 도구를 조합하는 내용. API 연동, 에이전트·자동화 도구 활용(MCP·n8n·LangChain 등 사용 경험), 간단한 서비스 배포, 프롬프트 엔지니어링 심화 |
| 고급 | 모델 학습·파인튜닝, 복잡한 에이전트 시스템 설계(멀티에이전트 아키텍처·오케스트레이션), 프로덕션 규모 운영·성능 최적화, 논문·벤치마크 수준의 기술 분석 |

## quality_score 기준

0.0부터 1.0 사이 숫자로 평가한다.

| 점수대 | 기준 |
| --- | --- |
| 0.8-1.0 | 실제 경험, 구체적 절차, 수치, 코드, 비교, 시행착오가 있어 학습 가치가 높음 |
| 0.5-0.79 | 주제는 유용하지만 설명이 다소 일반적이거나 검증 근거가 부족함 |
| 0.0-0.49 | 광고성, 단순 뉴스 공유, 정보 부족, 낚시성 제목, 학습 자료로 쓰기 어려움, 학습 정보 없는 감상문/감성 후기 |

## content_type 기준

반드시 아래 다섯 가지 중 하나만 사용한다.

| 값 | 기준 |
| --- | --- |
| concept | 개념 정리, 입문 설명, "무엇인지"를 알려주는 글 (정의·원리·용어 풀이) |
| tutorial | 단계별 사용법, 가이드, 따라 하기 |
| experience | 개인/팀의 실제 사용 후기, 시행착오, 사례 공유 (직접 경험한 내용) |
| tool | 도구/라이브러리/서비스 소개·큐레이션, "이런 도구가 있다" |
| discussion | 비교, 의견, 토론, 문제 제기, 타인 사례 분석/비판 |

## language 기준

본문 언어를 기준으로 `en` 또는 `ko` 중 하나를 사용한다.

## 출력 규칙

- 반드시 JSON 객체만 출력한다.
- Markdown 코드블록을 쓰지 않는다.
- 설명 문장을 JSON 밖에 쓰지 않는다.
- 모든 숫자는 문자열이 아니라 숫자로 출력한다.
- relevance에는 7개 대주제를 모두 포함한다.
- 잘 모르겠는 경우에도 가장 가까운 값을 추정한다.
- off_topic: 이 글이 **AI 7대주제와 무관**하면 true, 실제로 AI 주제를 다루면 false.

## off_topic 기준

이 커리큘럼은 **AI(LLM·에이전트·RAG·멀티모달·오픈소스·AI워크플로우·AI엔지니어링)** 전용이다.
다음은 off_topic=true로 판정한다 (relevance는 높게 나와도 무관):
- AI와 무관한 **일반 소프트웨어 개발**(웹/모바일/DB/인프라 일반), 개발 문화·철학·회고 에세이
- 비-기술(취미·일상·홍보), 단순 뉴스/이벤트 공지
- 핵심: "개발 인접"만으로는 false가 아니다. 글이 **실제로 AI 주제를 가르치거나 논의**해야 false.
예) "조선시대 사극 문체로 쓴 개발 성장 에세이" → AI 무관 → **off_topic=true**.
예) "MCP 서버로 코드리뷰 봇 만들기" → 에이전트/도구 → off_topic=false.

## 출력 형식

```json
{
  "relevance": {
    "프롬프트 엔지니어링": 0.0,
    "Agentic AI": 0.0,
    "멀티모달 AI": 0.0,
    "RAG & 지식 관리": 0.0,
    "오픈소스 AI": 0.0,
    "AI 워크플로우 & 자동화": 0.0,
    "AI 엔지니어링": 0.0
  },
  "difficulty": "입문",
  "quality_score": 0.0,
  "content_type": "tutorial",
  "language": "ko",
  "off_topic": false
}
```

## 검증용 예시

### 예시 입력

```json
{
  "title": "MCP 서버 5개 연동해서 풀자동 코드리뷰 봇 만들어봤다",
  "body": "GitHub MCP + Linear MCP + Slack MCP + Filesystem MCP + Custom DB MCP를 Claude Code Agent에 물려서 PR 자동 리뷰, Linear 이슈 생성, Slack 알림까지 한 번에 처리했다. 핵심 인사이트는 MCP 5개 동시 사용 시 컨텍스트 윈도우가 빨리 차서 toolset 동적 로딩이 필요하다는 점이다.",
  "source": "reddit",
  "author_name": "agent_builder",
  "url": "https://example.com/mcp-code-review-bot",
  "published_at": "2026-05-26T11:30:00+09:00",
  "language": "ko",
  "engagement": {
    "likes": 512,
    "comments": 134
  }
}
```

### 예시 출력

```json
{
  "relevance": {
    "프롬프트 엔지니어링": 0.2,
    "Agentic AI": 0.95,
    "멀티모달 AI": 0.0,
    "RAG & 지식 관리": 0.1,
    "오픈소스 AI": 0.1,
    "AI 워크플로우 & 자동화": 0.8,
    "AI 엔지니어링": 0.7
  },
  "difficulty": "고급",
  "quality_score": 0.92,
  "content_type": "experience",
  "language": "ko"
}
```

### 예시 입력 (concept)

```json
{
  "title": "RAG가 정확히 뭔가요? 임베딩부터 검색까지 한 번에 정리",
  "body": "RAG(Retrieval-Augmented Generation)는 LLM이 답을 생성하기 전에 외부 지식 베이스에서 관련 문서를 검색해 컨텍스트로 넣어주는 구조다. 핵심은 임베딩으로 문서를 벡터화해 벡터 DB에 저장하고, 질문도 같은 임베딩 공간으로 변환해 코사인 유사도로 가까운 문서를 찾는 것. 파인튜닝과 달리 모델 가중치를 건드리지 않고 지식만 갈아끼울 수 있다는 게 차이점이다.",
  "source": "velog",
  "author_name": "study_note",
  "url": "https://example.com/what-is-rag",
  "published_at": "2026-05-20T09:00:00+09:00",
  "language": "ko",
  "engagement": {
    "likes": 88,
    "comments": 12
  }
}
```

### 예시 출력 (concept)

```json
{
  "relevance": {
    "프롬프트 엔지니어링": 0.1,
    "Agentic AI": 0.0,
    "멀티모달 AI": 0.0,
    "RAG & 지식 관리": 0.95,
    "오픈소스 AI": 0.0,
    "AI 워크플로우 & 자동화": 0.0,
    "AI 엔지니어링": 0.3
  },
  "difficulty": "입문",
  "quality_score": 0.78,
  "content_type": "concept",
  "language": "ko"
}
```

### 예시 입력 (tool)

```json
{
  "title": "로컬에서 LLM 돌릴 때 쓰는 도구 7개 정리 (Ollama, vLLM, LM Studio...)",
  "body": "로컬 추론 환경을 꾸릴 때 자주 쓰는 도구들을 모았다. Ollama는 설치가 가장 쉽고 CLI 한 줄로 모델을 받아 실행할 수 있어 입문용으로 좋다. vLLM은 PagedAttention으로 처리량이 높아 서빙용. LM Studio는 GUI라 비개발자도 접근하기 쉽다. 각 도구의 장단점과 추천 상황을 표로 비교했다.",
  "source": "reddit",
  "author_name": "local_llm_fan",
  "url": "https://example.com/local-llm-tools",
  "published_at": "2026-05-22T14:00:00+09:00",
  "language": "ko",
  "engagement": {
    "likes": 230,
    "comments": 41
  }
}
```

### 예시 출력 (tool)

```json
{
  "relevance": {
    "프롬프트 엔지니어링": 0.0,
    "Agentic AI": 0.0,
    "멀티모달 AI": 0.0,
    "RAG & 지식 관리": 0.0,
    "오픈소스 AI": 0.9,
    "AI 워크플로우 & 자동화": 0.2,
    "AI 엔지니어링": 0.5
  },
  "difficulty": "입문",
  "quality_score": 0.7,
  "content_type": "tool",
  "language": "ko"
}
```
