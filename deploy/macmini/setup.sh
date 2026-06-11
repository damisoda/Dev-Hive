#!/bin/bash
# HIVE-52: 맥미니 원클릭 셋업 — Docker 스택 기동 + DB 복원 + 자동 시작.
#
# 맥미니에서 실행:
#   1) git clone https://github.com/damisoda/Dev-Hive.git && cd Dev-Hive/deploy/macmini
#   2) cp .env.example .env && vi .env   (비밀번호/API 키 입력)
#   3) ./setup.sh [dump.sql 경로]        (dump 경로 주면 DB 복원까지)
#
# idempotent — 재실행 안전. 터널(외부 노출)은 setup 후 README의 터널 섹션 참고.
set -euo pipefail
cd "$(dirname "$0")"

DUMP="${1:-}"

echo "── [1/4] Docker 확인 ──"
if ! command -v docker >/dev/null; then
  if ! command -v brew >/dev/null; then
    echo "Homebrew가 없습니다: https://brew.sh 설치 후 재실행" >&2; exit 1
  fi
  echo "docker가 없어 colima+docker를 설치합니다 (가벼운 무료 런타임)"
  brew install colima docker docker-compose
fi
if ! docker info >/dev/null 2>&1; then
  echo "docker 데몬 기동 (colima)"
  colima start --cpu 2 --memory 4
fi

echo "── [2/4] 환경 파일 확인 ──"
if [ ! -f .env ]; then
  echo ".env가 없습니다: cp .env.example .env 후 값을 채우세요" >&2; exit 1
fi

echo "── [3/4] 스택 기동 (pgvector + backend) ──"
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps

if [ -n "$DUMP" ]; then
  echo "── [3.5] DB 복원: $DUMP ──"
  # dump가 깨끗한 신규 볼륨에 들어간다는 가정(중복 적재 주의). 기존 데이터 있으면 중단.
  ROWS=$(docker compose -f docker-compose.prod.yml exec -T db \
    psql -U devhive -d devhive -tAc \
    "SELECT coalesce((SELECT count(*) FROM content), 0)" 2>/dev/null || echo 0)
  if [ "${ROWS:-0}" -gt 0 ]; then
    echo "content ${ROWS}건이 이미 있어 복원을 건너뜁니다 (강제 복원은 볼륨 삭제 후)" >&2
  else
    docker compose -f docker-compose.prod.yml exec -T db \
      psql -U devhive -d devhive < "$DUMP"
    echo "복원 완료"
  fi
fi

echo "── [4/4] 로그인 시 자동 시작 (launchd) ──"
PLIST=~/Library/LaunchAgents/com.devhive.stack.plist
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.devhive.stack</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string><string>-lc</string>
    <string>cd $(pwd) && (colima start || true) && docker compose -f docker-compose.prod.yml up -d</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>/tmp/devhive-stack.log</string>
  <key>StandardErrorPath</key><string>/tmp/devhive-stack.log</string>
</dict></plist>
EOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo
echo "완료. 헬스체크:"
curl -s http://localhost:8000/health && echo
echo "외부 노출(터널)은 README.md의 '터널' 섹션을 따르세요."
