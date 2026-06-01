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
| 입문 | 비전공자/초보자도 따라 할 수 있는 기본 개념, 쉬운 튜토리얼, 도구 첫 사용법 |
| 중급 | 기본 사용 경험이 있는 사람이 workflow를 개선하거나 여러 도구를 조합하는 내용 |
| 고급 | 모델 학습, 에이전트 아키텍처, 운영/배포, 성능 최적화, 논문/벤치마크 수준 내용 |

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
| tutorial | 단계별 사용법, 가이드, 따라 하기 |
| experience | 개인/팀의 실제 사용 후기, 시행착오, 사례 공유 (직접 경험한 내용) |
| news | 출시, 업데이트, 이슈, 트렌드 소개 |
| paper | 논문, 모델, 벤치마크, 연구 결과 설명 |
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
  "language": "ko"
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
