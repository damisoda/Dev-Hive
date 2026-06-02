"""HIVE-18 데이터 연결(connectivity) 점검 — 읽기 전용.

실제 적재된 DB가 API까지 제대로 연결돼 있는지 검증한다. 적재는 파이프라인의 책임이며,
이 스크립트는 DB를 변경하지 않는다(SELECT + GET만 사용. 프로필 생성/읽음 처리 등 쓰기 없음).

검증 계층:
1) DB 데이터 무결성 — content / 임베딩 / content_node_mapping / curriculum_nodes 적재·연결
2) API ↔ DB — /content가 DB 행을 그대로 서빙, /recommend가 DB에 실재하는 콘텐츠를 추천
3) 데이터 간 연결 — 추천된 콘텐츠가 임베딩·대주제 매핑까지 이어져 있는가

사전조건: docker compose up -d (DB) + uvicorn 백엔드 기동.
실행: cd backend && python scripts/e2e_check.py
종료코드: 전부 통과 0, 하나라도 실패 1.
"""
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings  # noqa: E402

BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
_results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> bool:
    _results.append((name, bool(cond), detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return bool(cond)


def summary_and_exit() -> None:
    passed = sum(1 for _, c, _ in _results if c)
    total = len(_results)
    print(f"\n=== 연결 점검: {passed}/{total} PASS ===")
    sys.exit(0 if passed == total else 1)


def main() -> None:
    engine = create_engine(settings.database_url)

    # ---- 1) DB 데이터 무결성 (읽기 전용) ----
    try:
        with engine.connect() as conn:
            content_total = conn.execute(text("SELECT count(*) FROM content")).scalar()
            embedded = conn.execute(
                text("SELECT count(*) FROM content WHERE text_embedding IS NOT NULL")
            ).scalar()
            nodes = conn.execute(text("SELECT count(*) FROM curriculum_nodes")).scalar()
            mappings = conn.execute(text("SELECT count(*) FROM content_node_mapping")).scalar()
            orphan_map = conn.execute(
                text(
                    "SELECT count(*) FROM content_node_mapping m "
                    "WHERE NOT EXISTS (SELECT 1 FROM curriculum_nodes n WHERE n.id = m.node_id)"
                )
            ).scalar()
            sources = conn.execute(text("SELECT count(DISTINCT source) FROM content")).scalar()
    except Exception as e:
        check("DB 연결", False, str(e)[:90])
        summary_and_exit()

    check("DB 연결 + content 적재", content_total > 0, f"content={content_total}건, source {sources}종")
    check("커리큘럼 노드 적재", nodes == 7, f"nodes={nodes} (대주제 7개 기대)")
    check("content↔임베딩 연결", embedded == content_total, f"{embedded}/{content_total} 임베딩 보유")
    check("content↔노드 매핑 존재", mappings > 0, f"매핑 {mappings}건")
    check("매핑 무결성(orphan 없음)", orphan_map == 0, f"orphan={orphan_map}")

    # ---- 2) API ↔ DB ----
    try:
        h = requests.get(f"{BASE}/health", timeout=5)
        if not check("health 200", h.status_code == 200, f"status={h.status_code}"):
            summary_and_exit()
    except requests.RequestException as e:
        check("health 200", False, f"백엔드 미응답: {str(e)[:70]}")
        summary_and_exit()

    c = requests.get(f"{BASE}/content", params={"limit": 5}, timeout=10)
    body = c.json() if c.ok else {}
    items = body.get("items", [])
    check("API /content 서빙", len(items) > 0, f"{len(items)}건 반환")
    check("API total ↔ DB count 일치", body.get("total") == content_total, f"api={body.get('total')} / db={content_total}")

    # ---- 3) 추천 ↔ DB 연결 (읽기 전용 GET, 기존 유저 사용) ----
    with engine.connect() as conn:
        existing_uid = conn.execute(text("SELECT id FROM users ORDER BY id LIMIT 1")).scalar()
        all_ids = {r[0] for r in conn.execute(text("SELECT id FROM content"))}

    if existing_uid is None:
        check("추천 검증용 유저 존재", False, "users 테이블 비어 있음 (온보딩 유저 필요)")
        summary_and_exit()

    rec = requests.get(f"{BASE}/recommend", params={"user_id": existing_uid, "top_n": 5}, timeout=15)
    recs = rec.json().get("recommendations", []) if rec.ok else []
    rec_ids = [r["content_id"] for r in recs]
    check("API /recommend 반환", len(recs) > 0, f"user={existing_uid}, {len(recs)}건")
    check("추천 콘텐츠가 DB에 실재", all(cid in all_ids for cid in rec_ids), f"추천 cid={rec_ids}")

    # 추천 1순위가 임베딩·노드 매핑까지 연결돼 있는가
    if rec_ids:
        top = rec_ids[0]
        with engine.connect() as conn:
            has_emb = conn.execute(
                text("SELECT text_embedding IS NOT NULL FROM content WHERE id=:i"), {"i": top}
            ).scalar()
            map_cnt = conn.execute(
                text("SELECT count(*) FROM content_node_mapping WHERE content_id=:i"), {"i": top}
            ).scalar()
        check("추천 콘텐츠 임베딩 보유", bool(has_emb), f"content_id={top}")
        check("추천 콘텐츠 대주제 매핑 보유", map_cnt > 0, f"content_id={top}, 매핑 {map_cnt}건")

    summary_and_exit()


if __name__ == "__main__":
    main()
