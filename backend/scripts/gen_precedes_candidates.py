"""HIVE-56: topic→topic precedes 후보 생성 (사람검수 전 단계).

curriculum_nodes의 최상위(대주제) 노드 간 선행관계(prerequisite)를 LLM이 후보로 제안한다.
출력은 JSON 파일(기본 precedes_candidates.json) — 사람이 approved 플래그를 검수한 뒤
load_precedes.py가 승인분만 node_links에 적재한다(완전자동 아님, 전수검수 v1).

DLELP(arXiv:2506.22303)의 concept-level prerequisite 설계를 따른다 — 난이도는 엣지에
넣지 않고 추천 단에서 별도 축으로 결합한다.

실행:
    cd backend
    python scripts/gen_precedes_candidates.py [--out precedes_candidates.json]
"""
import argparse
import json
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

MODEL = "claude-haiku-4-5-20251001"

PROMPT = """다음은 한 AI 기술 커뮤니티의 학습 대주제 목록이다. 각 주제는 id와 이름, 보유 글 수를 가진다.

{topics}

이 주제들 사이의 **선행관계(prerequisite)**를 판단하라. "A precedes B" = A를 어느 정도 이해해야 B를 학습할 준비가 된다는 뜻이다.

규칙:
- 방향성 있는 DAG. **자기참조 금지, 사이클 금지.**
- **보수적으로** — 명확한 선행만. 애매하면 넣지 마라(유사/병렬 관계는 precedes 아님).
- 난이도는 고려하지 마라(그건 별도 축이다). 오직 개념적 선행만.

JSON 배열만 출력하라(설명 문장 금지):
[{{"source": <id>, "target": <id>, "source_name": "..", "target_name": "..", "rationale": "왜 선행인지 한 문장", "confidence": 0.0~1.0}}]
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "precedes_candidates.json"))
    args = ap.parse_args()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        sys.exit("DATABASE_URL 필요")
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY 필요")

    engine = create_engine(db_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT n.id, n.name, "
                "(SELECT count(*) FROM content_node_mapping m WHERE m.node_id = n.id) AS c "
                "FROM curriculum_nodes n WHERE n.parent_id IS NULL ORDER BY n.id"
            )
        ).fetchall()
    if len(rows) < 2:
        sys.exit("대주제가 2개 미만 — 후보 생성 불가")

    topics_txt = "\n".join(f"- id={r.id}: {r.name} (글 {r.c}개)" for r in rows)
    valid_ids = {r.id for r in rows}

    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": PROMPT.format(topics=topics_txt)}],
    )
    raw = msg.content[0].text.strip()
    # JSON 배열만 추출(코드펜스 등 방어)
    start, end = raw.find("["), raw.rfind("]")
    cands = json.loads(raw[start : end + 1]) if start >= 0 else []

    # 후처리: 유효 id·자기참조 제거
    clean = []
    for c in cands:
        s, t = c.get("source"), c.get("target")
        if s in valid_ids and t in valid_ids and s != t:
            c["approved"] = False  # 사람이 검수해 true로 바꿈
            clean.append(c)

    Path(args.out).write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"후보 {len(clean)}건 → {args.out}\n")
    for c in clean:
        print(f"  [{c['source']}] {c['source_name']} → [{c['target']}] {c['target_name']}"
              f"  (conf {c.get('confidence')})\n      {c.get('rationale')}")


if __name__ == "__main__":
    main()
