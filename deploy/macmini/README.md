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

## 프런트 (예정)

Next.js → Vercel. API는 위 Funnel URL 사용. CORS 허용 도메인에 Vercel 도메인 추가 필요
(`backend/app/main.py` CORS 설정 확인).
