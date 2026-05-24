# Pull Request 템플릿

본 파일은 GitHub의 PR 템플릿 원본이다. PR 작성 시 자동으로 본문에 채워지도록 하려면 다음 위치에 동일한 내용으로 저장해야 한다.

```
{레포 루트}/.github/PULL_REQUEST_TEMPLATE.md
```

GitHub은 위 경로의 파일을 인식하여 PR 본문 기본값으로 사용한다.

---

## 템플릿 원본 (아래 영역을 그대로 복사)

```markdown
## 관련 Jira 이슈

Closes HIVE-{이슈번호}

## 변경 사항 요약

<!-- 무엇이 어떻게 바뀌었는지 3~5줄로 작성한다 -->

- 

## 테스트 방법

<!-- 리뷰어가 이 변경을 어떻게 검증할 수 있는지 단계별로 작성한다 -->

1. 
2. 

## 스크린샷 또는 결과 로그

<!-- UI 변경 시 스크린샷 첨부, BE/AI 변경 시 실행 결과 로그 첨부 -->

## 셀프 체크리스트

- [ ] 로컬에서 동작 확인 완료
- [ ] 다른 모듈 회귀 영향 검토
- [ ] .env / 비밀 정보 커밋 여부 확인
- [ ] 불필요한 console.log / print 제거
- [ ] 코드 컨벤션 준수
- [ ] 관련 Jira 이슈 키를 PR 제목과 본문에 포함

## 추가 컨텍스트

<!-- 리뷰 전 알아두면 좋을 배경, 결정 사유, 알려진 한계 등 -->
```

---

## 설치 방법

본 템플릿이 GitHub에서 실제로 작동하려면 다음 절차를 따른다.

1. 로컬 레포지토리 루트에서 `.github/` 폴더를 생성한다.
2. 그 안에 `PULL_REQUEST_TEMPLATE.md` 파일을 만든다.
3. 위 "템플릿 원본"의 코드 블록 내용을 그대로 붙여넣는다.
4. develop 브랜치에 PR로 머지한다.

```bash
mkdir -p .github
# .github/PULL_REQUEST_TEMPLATE.md 파일 생성 후 내용 붙여넣기
git checkout -b chore/HIVE-XX-add-pr-template
git add .github/PULL_REQUEST_TEMPLATE.md
git commit -m "HIVE-XX chore: PR 템플릿 추가"
git push -u origin chore/HIVE-XX-add-pr-template
# GitHub에서 PR 생성
```

머지 이후 새 PR을 만들 때 본문이 자동으로 위 템플릿으로 채워진다.

---

## 작성 시 주의 사항

- `Closes HIVE-{이슈번호}`는 PR 머지 시 Jira 이슈를 자동으로 Done 상태로 이동시킨다. 이슈 키는 반드시 정확하게 적는다.
- HTML 주석(`<!-- ... -->`)은 PR이 게시되어도 보이지 않는다. 작성자만 보이는 안내문이다.
- 셀프 체크리스트는 PR 제출 전에 본인이 확인하는 항목이다. 모두 체크되지 않은 상태로 머지하지 않는다.
- "관련 Jira 이슈"가 없는 PR은 원칙적으로 만들지 않는다. Jira에서 카드를 먼저 생성한다.
