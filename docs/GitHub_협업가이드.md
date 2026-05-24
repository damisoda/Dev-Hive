# GitHub 협업 가이드

본 문서는 협업이 처음인 팀원을 위한 GitHub 사용 가이드이다. 본 프로젝트는 GitHub Flow에 약간의 변형(main과 develop의 분리)을 적용한다. 모든 코드 변경은 PR을 통해서만 main 또는 develop에 반영된다.

---

## 1. 브랜치 전략

세 단계로 브랜치를 운영한다.

| 브랜치 | 용도 | 직접 push 허용 |
|--------|------|---------|
| `main` | 배포 가능 상태. 데모/발표 시점의 안정 버전 | 금지 |
| `develop` | 통합 개발 브랜치. 모든 작업의 base | 금지 |
| `feature/*`, `fix/*` 등 | 개별 작업 브랜치 | 허용 |

main과 develop에 변경을 반영할 때는 반드시 PR과 리뷰를 거친다.

---

## 2. 브랜치 네이밍 컨벤션

형식: `{타입}/{Jira키}-{짧은-설명-영문}`

| 타입 | 용도 | 예시 |
|------|------|------|
| `feature` | 신규 기능 | `feature/HIVE-12-reddit-crawler` |
| `fix` | 버그 수정 | `fix/HIVE-23-auth-token-expiry` |
| `chore` | 빌드/설정/패키지 | `chore/HIVE-31-eslint-config` |
| `refactor` | 리팩터링 | `refactor/HIVE-42-extract-tagger` |
| `docs` | 문서 변경 | `docs/HIVE-50-update-readme` |
| `test` | 테스트 추가/수정 | `test/HIVE-55-pipeline-unit-test` |

### 규칙
- 전부 소문자로 작성하고, 단어 구분은 하이픈(`-`)으로 한다.
- Jira 이슈 키는 필수이다. 이슈가 없는 작업이라면 먼저 Jira에서 카드를 생성한다.
- 설명은 영문으로 짧게 작성한다. 한글은 일부 환경에서 깨질 수 있다.

---

## 3. 작업 시작 절차

```bash
# 1) 최신 develop을 받아온다
git checkout develop
git pull origin develop

# 2) 새 브랜치를 생성한다
git checkout -b feature/HIVE-12-reddit-crawler

# 3) 작업하며 커밋한다
git add <변경한 파일>
git commit -m "HIVE-12 feat: Reddit PRAW 크롤러 v0 구현"

# 4) 원격 저장소로 푸시한다
git push -u origin feature/HIVE-12-reddit-crawler

# 5) GitHub 웹에서 PR을 생성한다
#    base: develop  ←  compare: feature/HIVE-12-reddit-crawler
```

`-u` 옵션은 처음 push 시 원격 브랜치와 로컬 브랜치를 연결한다. 이후에는 `git push`만으로 푸시된다.

---

## 4. 커밋 메시지 컨벤션

Conventional Commits 규칙과 Jira 키를 조합한다.

### 기본 형식

```
{Jira키} {타입}: {본문 요약 (한 줄, 50자 이내 권고)}

{선택: 빈 줄을 두고 상세 본문}

{선택: 빈 줄을 두고 푸터 (Co-Authored-By, BREAKING CHANGE 등)}
```

### 타입 종류

| 타입 | 의미 | 사용 예 |
|------|------|------|
| `feat` | 신규 기능 추가 | 새 API 엔드포인트, 새 컴포넌트 |
| `fix` | 버그 수정 | 인증 토큰 만료 오류 수정 |
| `docs` | 문서만 변경 | README 업데이트 |
| `style` | 코드 스타일 (기능 변경 없음) | 들여쓰기, 세미콜론 |
| `refactor` | 리팩터링 (기능 변경 없음) | 함수 분리, 변수명 변경 |
| `test` | 테스트 추가/수정 | 단위 테스트 작성 |
| `chore` | 빌드/패키지/설정 | 의존성 업그레이드 |

### 좋은 예시

```
HIVE-12 feat: Reddit PRAW 크롤러 v0 구현

r/ClaudeAI 서브레딧에서 글 10건을 수집하여 raw_contents 테이블에 적재.
좋아요 수, 작성자, 작성일 메타데이터를 함께 저장.
```

```
HIVE-23 fix: JWT 토큰 만료 시 401 응답 누락 수정
```

```
HIVE-50 docs: README의 비용 추정 섹션을 v3 기준으로 갱신
```

### 나쁜 예시

| 메시지 | 문제점 |
|--------|------|
| `fix bug` | Jira 키 없음, 어떤 버그인지 모름 |
| `HIVE-12 작업함` | 타입 없음, 본문이 모호함 |
| `update` | 정보가 전혀 없음 |
| `WIP` | 머지되면 안 되는 미완성 코드의 표지로만 사용 |

---

## 5. 커밋 단위 권고

- 하나의 커밋은 하나의 논리적 변경을 담는다. 여러 기능을 한 커밋에 섞지 않는다.
- 작업 중간에도 자주 커밋한다. PR 마무리 시 squash 옵션으로 합칠 수 있다.
- 작동하지 않는 코드는 커밋하지 않는다. 작업 도중 저장 목적이라면 로컬에만 두거나 Draft PR로 올린다.

---

## 6. .gitignore 기본 규칙

다음 파일은 절대 커밋하지 않는다.

```
# 환경 변수 및 비밀
.env
.env.local
*.env

# API 키 / 자격증명
secrets/
credentials.json
service-account.json

# 의존성 디렉토리
node_modules/
__pycache__/
*.pyc
venv/
.venv/

# 빌드 산출물
dist/
build/
.next/

# IDE 설정
.vscode/
.idea/
*.swp

# OS 파일
.DS_Store
Thumbs.db

# 로컬 데이터
*.db
*.sqlite
data/raw/
data/cache/
```

API 키와 환경 변수는 `.env.example` 파일에 키 이름만 적어 공유하고, 실제 값은 각 팀원이 로컬에서 입력한다.

---

## 7. 충돌 해결 기초

PR 머지 직전에 충돌이 발생한 경우 다음 절차로 처리한다.

```bash
# 1) develop을 최신화한다
git checkout develop
git pull origin develop

# 2) 작업 브랜치로 돌아가서 develop을 merge한다
git checkout feature/HIVE-12-reddit-crawler
git merge develop

# 3) 충돌 파일을 직접 열어 수정한다
#    <<<<<<< HEAD
#    ... 본인 코드 ...
#    =======
#    ... develop 코드 ...
#    >>>>>>> develop
#    위 마커 영역을 정리한다.

# 4) 충돌 해결을 커밋하고 푸시한다
git add <충돌_해결_파일>
git commit
git push
```

충돌 해결이 어려우면 머지하지 않고 반드시 팀에 공유한다. 본인 판단으로 다른 사람의 코드를 임의로 지우지 않는다.

---

## 8. 절대 하지 말아야 할 것

- `main` 또는 `develop` 브랜치에 직접 push
- `git push --force` 사용 (다른 사람의 작업이 사라질 수 있음)
- 리뷰 없이 본인 PR 머지
- `.env` 등 비밀 파일 커밋
- 변경 파일 30개를 초과하는 거대한 PR (분할을 검토한다)

---

## 9. 자주 쓰는 git 명령어 요약

```bash
git status                          # 현재 변경 사항 확인
git diff                            # 아직 add 안 한 변경 보기
git diff --staged                   # add한 변경 보기
git log --oneline -10               # 최근 커밋 10개 확인
git branch                          # 로컬 브랜치 목록
git branch -a                       # 원격 포함 모든 브랜치
git checkout <브랜치>                # 브랜치 이동
git checkout -b <새 브랜치>          # 새 브랜치 생성하며 이동
git fetch --all                     # 원격 변경 가져오기 (적용은 안 함)
git pull                            # 가져오고 현재 브랜치에 적용
git reset HEAD~1                    # 마지막 커밋 취소 (변경은 유지)
```
