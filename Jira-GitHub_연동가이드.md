# Jira-GitHub 연동 가이드

본 문서는 Jira와 GitHub을 양방향으로 연결하여 사용하는 방법을 정리한다. 정상적으로 연동된 상태에서는 Jira 카드 상태가 GitHub의 커밋·PR·머지에 따라 자동으로 변경된다.

---

## 1. 연동의 작동 방식

GitHub for Jira 앱이 설치되고 저장소가 연결된 상태에서, 커밋 메시지·브랜치명·PR에 Jira 이슈 키(예: `HIVE-12`)가 포함되면 자동으로 다음이 일어난다.

- 커밋이 해당 Jira 이슈 상세 화면에 노출된다.
- PR의 상태(open / review / merged)가 Jira 이슈 카드에 표시된다.
- Smart Commits 명령어로 카드 상태를 자동 전환할 수 있다.
- Automation 룰을 설정하면 PR 생성·머지 시점에 카드 상태가 자동 이동한다.

---

## 2. 브랜치명에 이슈 키 포함

올바른 예시:

```
feature/HIVE-12-reddit-crawler
fix/HIVE-23-auth-token
chore/HIVE-31-eslint-config
```

잘못된 예시:

| 브랜치명 | 문제점 |
|---------|------|
| `my-work` | Jira 이슈 키 없음 |
| `HIVE12-crawler` | 키와 번호 사이 하이픈 누락 |
| `feature/hive-12-...` | 소문자 키는 매칭되지 않음 (대문자 사용) |

---

## 3. 커밋 메시지에 이슈 키 포함

올바른 예시:

```
HIVE-12 feat: Reddit PRAW 크롤러 v0 구현
```

이슈 키는 커밋 메시지의 어디에 들어가도 매칭되지만, 본 프로젝트의 컨벤션은 **맨 앞에 두는 것**이다. 자동화 룰과 검색 모두에서 일관성을 확보할 수 있다.

---

## 4. PR에 이슈 키 포함

PR 제목 또는 본문 어디든 키가 포함되면 자동 연결된다.

권장 위치:

- 제목: `[HIVE-12] feat: ...`
- 본문 첫 줄: `Closes HIVE-12`

`Closes`, `Fixes`, `Resolves` 키워드와 함께 키를 사용하면 PR 머지 시 이슈가 자동으로 Done 상태로 전환된다.

---

## 5. Smart Commits

커밋 메시지 안에서 특별한 문법을 사용하면 Jira 이슈의 상태를 자동으로 전환할 수 있다. 이를 Smart Commits라 한다.

### 기본 문법

```
{이슈키} #{명령어} {추가 인자}
```

### 주요 명령어

| 명령어 | 효과 | 예시 |
|--------|------|------|
| `#comment` | 이슈에 댓글 추가 | `HIVE-12 #comment 1차 PoC 완료` |
| `#time` | 작업 시간 기록 | `HIVE-12 #time 2h Reddit 크롤러 구현` |
| `#in-review` | 상태를 In Review로 이동 | `HIVE-12 #in-review` |
| `#done` | 상태를 Done으로 이동 | `HIVE-12 #done` |

### 복합 사용 예시

```
HIVE-12 #time 3h #comment Reddit PoC 완료, 다음은 GitHub Trending #in-review
```

이 커밋 하나로 다음 세 가지가 동시에 수행된다.

- 작업 시간 3시간이 기록됨
- 댓글이 추가됨
- 상태가 In Review로 이동함

### 주의 사항

- 본인의 GitHub 계정 이메일과 Jira 계정 이메일이 동일해야 동작한다.
- 명령어와 인자는 띄어쓰기로 구분한다.

---

## 6. 자동화 룰 (권장)

다음 룰을 설정하면 수동 명령어 없이도 카드 상태가 자동 전환된다.

| 트리거 | 액션 |
|--------|------|
| PR 생성됨 | 이슈를 In Review로 이동 |
| PR 머지됨 | 이슈를 Done으로 이동 |
| 브랜치 생성됨 | 이슈를 In Progress로 이동 |

### 설정 방법

1. Jira에서 `Dev-Hive` 프로젝트 진입
2. 좌측 사이드바 하단 **Project settings** 클릭
3. **Automation** 메뉴 선택
4. **Create rule** 클릭
5. 템플릿 중 "When PR is created" 등의 시나리오 선택
6. 트리거·조건·액션 확인 후 활성화

본 프로젝트는 최소 다음 두 룰을 권고한다.

- "When PR is created, transition issue to In Review"
- "When PR is merged, transition issue to Done"

---

## 7. 트러블슈팅

### 커밋이 Jira 이슈에 안 보임

- 이슈 키의 대소문자를 확인한다. `HIVE-12`는 가능하지만 `hive-12`는 불가.
- GitHub for Jira 앱이 설치되어 있는지 확인한다 (Jira → Apps → Manage your apps).
- 저장소가 연결되어 있는지 확인한다 (앱 설정 화면).
- 초기 동기화는 5~10분의 지연이 있을 수 있다. 시간을 두고 다시 확인한다.

### Smart Commits이 작동 안 함

- 이슈 키 다음에 공백을 둔 뒤 `#명령어` 형식인지 확인한다.
- GitHub 계정 이메일과 Jira 계정 이메일이 동일한지 확인한다. 다르다면 Jira 프로필에서 이메일을 추가한다.
- 명령어 철자를 확인한다 (`#in-review`이지 `#inreview`가 아님).

### PR이 이슈 카드에 안 보임

- PR 제목 또는 본문에 키가 포함되었는지 확인한다.
- 저장소 연결 상태를 GitHub for Jira 앱 설정에서 확인한다.
- PR을 닫았다가 다시 열어 동기화를 강제할 수 있다.

### 자동화 룰이 작동 안 함

- 룰이 활성화 상태인지 확인한다 (`Project settings → Automation`).
- 트리거 조건을 다시 본다. 예를 들어 "PR created"만 트리거되며 "PR opened"는 별개의 이벤트일 수 있다.
- 실행 로그를 확인한다 (`Automation → Audit log`).

---

## 8. 실전 워크플로우 예시

전형적인 작업 흐름을 시간 순서로 정리한다.

### Step 1. Jira에서 카드 준비

```
HIVE-12 이슈 생성 또는 기존 카드를 In Progress로 이동
```

### Step 2. 로컬에서 브랜치 생성

```bash
git checkout develop
git pull origin develop
git checkout -b feature/HIVE-12-reddit-crawler
```

이 단계에서 Automation 룰 "When branch is created" 가 설정되어 있다면 카드가 자동으로 In Progress로 이동한다.

### Step 3. 작업하며 커밋

```bash
git commit -m "HIVE-12 feat: PRAW 셋업"
git commit -m "HIVE-12 feat: 글 10건 수집 로직"
```

### Step 4. 푸시 후 PR 생성

```bash
git push -u origin feature/HIVE-12-reddit-crawler
```

GitHub 웹에서 PR 생성. 본문에 `Closes HIVE-12`를 포함한다.

### Step 5. 카드 상태 자동 전환

- PR 생성 시점에 Automation 룰이 카드를 In Review로 이동
- 리뷰어 Approve 후 머지
- 머지 시점에 `Closes HIVE-12` 키워드로 카드가 Done으로 이동

### 결과

수동으로 카드를 옮기지 않아도 코드 작업만 하면 카드 상태가 따라온다. Jira와 GitHub 사이를 오갈 필요가 없어진다.

---

## 9. 본 가이드와 함께 보면 좋은 문서

- `GitHub_협업가이드.md` — 브랜치 전략, 커밋 메시지 컨벤션 등
- `PR_가이드.md` — PR 작성·리뷰·머지 절차
- `Jira_가이드.md` — Jira 카드 관리, 보드 사용법
- `PR_템플릿.md` — PR 본문 자동 채움 템플릿
