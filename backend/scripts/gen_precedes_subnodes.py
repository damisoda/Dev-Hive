"""대주제별 하위노드 간 precedes(선행관계) 후보를 LLM으로 생성한다 (HIVE-56 확장).

기존 gen_precedes_candidates.py는 7 대주제끼리만 봤다. 진짜 선후구조는 "대주제 안 하위노드들"
(기초→심화) 사이에 있으므로, 대주제마다 그 하위노드들(이름+난이도+글수)을 LLM에 묶어 넣고
선행관계를 제안받는다. 무관쌍이 안 섞이도록 대주제 단위로 끊는다.

LLM: 로컬/원격 ollama(기본 맥미니 GPU를 SSH 터널 localhost:11435로). 출력은 사람이 approved를
검수한 뒤 로더가 node_links로 적재한다. ID는 리셋에 약하니 name도 함께 저장(로더가 name→id 재매핑).

실행:
    ssh -f -N -L 11435:localhost:11434 damisoda@<macmini>   # 터널 먼저
    python scripts/gen_precedes_subnodes.py --url http://localhost:11435 --model gemma4:e4b
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path("/Users/damisoda/code/Dev-Hive")
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import text
from app.database import SessionLocal

SYS = "너는 학습 커리큘럼 설계자다. 개념 간 선행관계(A를 이해해야 B를 학습 가능)를 JSON으로만 답한다."


def _ask(url: str, model: str, topic: str, subs: list[dict]) -> list[dict]:
    lst = "\n".join(f'- "{s["name"]}" (난이도 {s["diff"]}, 글 {s["n"]}개)' for s in subs)
    user = (
        f'다음은 "{topic}" 주제의 하위 개념들이다:\n{lst}\n\n'
        "개념 쌍 중 명확한 선행관계가 있는 것만 골라라(무관하거나 애매하면 제외). "
        "보통 더 쉬운/기초 개념이 선행한다. 같은 난이도면 더 일반적·기반이 되는 쪽이 선행.\n"
        '형식: {"edges":[{"source":"개념명","target":"개념명","reason":"한 문장"}]}'
    )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": SYS}, {"role": "user", "content": user}],
        "stream": False, "format": "json",
        "options": {"temperature": 0.2, "num_ctx": 4096},
    }).encode()
    req = urllib.request.Request(f"{url}/api/chat", data=body, headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=180))
    try:
        return json.loads(r["message"]["content"]).get("edges", [])
    except Exception:
        return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:11435")  # 맥미니 GPU(SSH 터널)
    ap.add_argument("--model", default="gemma4:e4b")
    ap.add_argument("--out", default=str(ROOT / "precedes_subnode_candidates.json"))
    ap.add_argument("--min-content", type=int, default=3)  # 노이즈 클러스터(글 적음) 제외
    args = ap.parse_args()

    db = SessionLocal()
    topics = db.execute(text(
        "SELECT id, name FROM curriculum_nodes WHERE parent_id IS NULL ORDER BY id"
    )).fetchall()

    candidates = []
    for t in topics:
        rows = db.execute(text("""
            SELECT c.id, c.name,
                   mode() WITHIN GROUP (ORDER BY ct.difficulty) AS diff,
                   count(*) AS n
            FROM curriculum_nodes c
            JOIN content_node_mapping m ON m.node_id = c.id
            JOIN content ct ON ct.id = m.content_id
            WHERE c.parent_id = :tid
            GROUP BY c.id, c.name
            HAVING count(*) >= :minc
            ORDER BY count(*) DESC
        """), {"tid": t.id, "minc": args.min_content}).fetchall()
        if len(rows) < 2:
            print(f"  [{t.name}] 하위노드 {len(rows)}개 — 스킵", flush=True)
            continue
        subs = [{"id": r.id, "name": r.name, "diff": r.diff, "n": r.n} for r in rows]
        by_name = {s["name"]: s["id"] for s in subs}
        edges = _ask(args.url, args.model, t.name, subs)
        kept = 0
        for e in edges:
            sid, tid = by_name.get(e.get("source")), by_name.get(e.get("target"))
            if sid and tid and sid != tid:
                candidates.append({
                    "topic": t.name, "source_id": sid, "source_name": e["source"],
                    "target_id": tid, "target_name": e["target"],
                    "reason": e.get("reason", ""), "approved": False,
                })
                kept += 1
        print(f"  [{t.name}] 하위 {len(subs)} → 후보 {kept}", flush=True)

    db.close()
    Path(args.out).write_text(json.dumps(candidates, ensure_ascii=False, indent=2))
    print(f"\n총 후보 {len(candidates)}개 → {args.out} (approved 검수 후 로드)", flush=True)


if __name__ == "__main__":
    main()
