# 맥미니 운영 배포 (HIVE-52)

공개 API: **https://macmini.tail67859f.ts.net** (Tailscale Funnel → 127.0.0.1:8000)

## 구성

- 맥미니 M4 (tailnet: `macmini`, 100.73.27.46) — colima(vz) + docker 정적 바이너리 (sudo·brew 불필요)
- `docker-compose.prod.yml`: pgvector(pg16, 내부망 전용) + FastAPI 백엔드(127.0.0.1:8000 바인딩 — 외부 노출은 Funnel로만)
- `ENABLE_SCHEDULER=false` — 재크롤은 수동 트리거(비용 통제)
- 자동시작: `~/Library/LaunchAgents/com.devhive.stack.plist` (로그인 시 colima→compose 기동)
- 데이터: 통합본 994건 + text/graph 임베딩 전체 (2026-06-11 기준)

## 자주 쓰는 명령 (맥북에서)

```bash
ssh damisoda@100.73.27.46                          # 접속 (tailnet 안에서)
# 상태/로그
ssh damisoda@100.73.27.46 'export PATH=$HOME/bin:$PATH; cd ~/Dev-Hive/deploy/macmini && docker compose -f docker-compose.prod.yml ps && docker compose -f docker-compose.prod.yml logs --tail 50 backend'
# 코드 반영(재배포)
rsync -az --exclude .git --exclude '*venv*' --exclude __pycache__ ~/code/Dev-Hive/ damisoda@100.73.27.46:~/Dev-Hive/
ssh damisoda@100.73.27.46 'export PATH=$HOME/bin:$PATH; cd ~/Dev-Hive/deploy/macmini && docker compose -f docker-compose.prod.yml up -d --build backend'
```

## 처음부터 다시 세우는 경우

1. `setup.sh` 참고(brew 경로) — 이번 구축은 sudo 없이 정적 바이너리로 했다:
   colima(GitHub release 단일 바이너리) + lima(tarball→`~/.local`) + docker CLI(정적) +
   compose 플러그인(`~/.docker/cli-plugins/`), PATH는 `~/.zprofile`.
2. `cp .env.example .env` 후 값 입력 → `docker compose -f docker-compose.prod.yml up -d --build`
3. DB 복원: `docker compose -f docker-compose.prod.yml exec -T db psql -U devhive -d devhive < dump.sql`
4. graph_embedding 백필: 로컬 학습(`backend/scripts/train_graphsage_local.py`) 후
   `docker cp embeddings.npz macmini-backend-1:/tmp/ && docker exec macmini-backend-1 python -m app.graph.sage_export --in /tmp/embeddings.npz`

## Tailscale Funnel

- 켜기: `/Applications/Tailscale.app/Contents/MacOS/Tailscale funnel --bg 8000`
- 끄기: `... funnel --https=443 off` / 상태: `... funnel status`
- 전제(1회, 관리콘솔): Serve/Funnel 노드 승인 + DNS 설정에서 HTTPS Certificates 활성화
- Funnel은 재부팅 후에도 유지된다(serve 설정 영속). 안 살아 있으면 위 켜기 명령 재실행.

## 프런트 (Next.js, HIVE-71)

공개 프런트는 compose의 **`web` 서비스(Next.js standalone, 127.0.0.1:3000)**. 서버 컴포넌트와
BFF(`/api/auth/profile`, `/api/feedback`)가 `http://backend:8000`을 **내부망으로** 호출하므로
**브라우저 CORS가 발생하지 않는다**(backend는 외부 미노출 유지). 세션 쿠키(`dh_uid`)는 web과
같은 오리진에서 set/read → 별도 도메인 설정 불필요.

### 배포(맥북에서, 코드 반영 + web 추가)

```bash
# 1) 코드 동기화(develop 기준)
rsync -az --exclude .git --exclude '*venv*' --exclude __pycache__ \
  --exclude 'web/node_modules' --exclude 'web/.next' \
  ~/code/Dev-Hive/ damisoda@100.73.27.46:~/Dev-Hive/
# 2) backend + web 재빌드·기동 (DB/볼륨은 유지)
ssh damisoda@100.73.27.46 'export PATH=$HOME/bin:$PATH; cd ~/Dev-Hive/deploy/macmini && \
  docker compose -f docker-compose.prod.yml up -d --build backend web'
# 3) Funnel을 web(3000)으로 전환 (기존 8000/8501 Funnel은 끄고)
ssh damisoda@100.73.27.46 '/Applications/Tailscale.app/Contents/MacOS/Tailscale funnel --bg 3000'
```

### 데이터 위생(선택, 한 번)

새 프런트의 피드/타입 칩이 깔끔해지려면 폐기타입(paper) 재태깅:
```bash
ssh ... 'cd ~/Dev-Hive/backend && python scripts/migrate_retag_deprecated_types.py --dry-run'  # 먼저 예정 확인
# 이상 없으면 --dry-run 빼고 실행 (ANTHROPIC_API_KEY 필요)
```

### 검증

- `https://macmini.tail67859f.ts.net/` → 새 RocketPunch 홈(Streamlit 아님)
- `/onboarding` 가입 → 홈 피드백 4종·커리큘럼·`/graph` 동작
- Streamlit(`frontend`, 8501)은 레거시로 남겨둠 — 안정화 후 compose에서 제거
