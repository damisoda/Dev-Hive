"""HIVE-21: Auto-HKG — 자동 계층형 지식그래프 확장.

새 콘텐츠를 그래프에 편입한다: 기존 노드에 매칭하거나, 새 노드(하위/최상위)를 생성.
대주제 7개는 닫힌 분류가 아니라 '씨앗' — Auto-HKG로 그래프가 스스로 자란다(self-organizing).

플로우(콘텐츠 1건):
1. 후보 — 노드 centroid(소속 콘텐츠 text_embedding 평균) vs 콘텐츠 임베딩 코사인 top-K
2. 가드레일 단락 — top 유사도 > DEDUP면 LLM 없이 바로 기존 노드(명백히 들어맞음)
3. Haiku 판단 — existing | new_sub(부모) | new_top + 이름/설명
4. 가드레일 — new_top은 top 유사도 < NEW_TOP일 때만(아니면 new_sub 강등). 전 노드 대상이라 멱등
5. 적용 — curriculum_nodes INSERT(parent_id, is_auto_generated) + content_node_mapping

설계 메모: precedes(노드 간 선행 엣지)는 v2(여기선 parent_id hierarchy만). 트리거는 배치
(scripts/run_auto_hkg.py). dedup은 콘텐츠-centroid 유사도로 처리 → 새 임베딩 호출 없음.
"""
from __future__ import annotations

import json
import re

import anthropic
import numpy as np
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.tagging.tagger import MODEL

DEDUP_THRESHOLD = 0.85  # top 후보 유사도 이 이상이면 새 노드 안 만들고 기존으로 (LLM 단락)
NEW_TOP_THRESHOLD = 0.40  # top 후보 유사도 이 미만일 때만 새 최상위 대주제 허용
CANDIDATE_K = 5

_SYSTEM_PROMPT = """You are a curriculum knowledge-graph organizer for an AI-learning community.
Given one piece of content and candidate curriculum nodes (with similarity scores), decide where it belongs.

Return ONLY a JSON object:
{"decision":"existing"|"new_sub"|"new_top","node_id":<int>,"parent_id":<int>,"new_name":"<short Korean name>","new_desc":"<one-line Korean>","reason":"<short>"}

- "existing": fits a candidate node -> set node_id.
- "new_sub": a coherent SUB-topic of a candidate -> set parent_id to that candidate's id, plus new_name/new_desc.
- "new_top": fits NONE of the candidates (a genuinely new major area) -> new_name/new_desc.
- Prefer existing or new_sub. Use new_top only when nothing fits.
- new_name must be concise and must NOT duplicate an existing candidate name."""


def _parse_emb(s: str) -> np.ndarray:
    """pgvector가 문자열('[0.1,0.2,...]')로 돌려준 임베딩을 ndarray로."""
    return np.array(s.strip()[1:-1].split(","), dtype=float)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _node_centroids(conn: Connection) -> dict[int, np.ndarray]:
    """노드별 소속 콘텐츠 text_embedding 평균(centroid). 콘텐츠 없는 노드는 빠진다."""
    rows = conn.execute(
        text(
            """
            SELECT m.node_id AS node_id, c.text_embedding AS emb
            FROM content_node_mapping m
            JOIN content c ON c.id = m.content_id
            WHERE c.text_embedding IS NOT NULL
            """
        )
    ).fetchall()
    acc: dict[int, list[np.ndarray]] = {}
    for r in rows:
        acc.setdefault(r.node_id, []).append(_parse_emb(r.emb))
    return {nid: np.mean(vs, axis=0) for nid, vs in acc.items()}


def _node_info(conn: Connection) -> dict[int, dict]:
    rows = conn.execute(
        text("SELECT id, name, description, parent_id FROM curriculum_nodes")
    ).fetchall()
    return {
        r.id: {"name": r.name, "desc": r.description, "parent_id": r.parent_id}
        for r in rows
    }


def _candidates(emb: np.ndarray, centroids: dict[int, np.ndarray], k: int) -> list[tuple[int, float]]:
    sims = [(nid, _cosine(emb, cen)) for nid, cen in centroids.items()]
    sims.sort(key=lambda x: x[1], reverse=True)
    return sims[:k]


def _judge(content: dict, cands: list[tuple[int, float]], info: dict[int, dict],
           client: anthropic.Anthropic) -> dict:
    """Haiku로 편입 위치를 판단한다. 파싱 실패 시 기존 노드(top)로 폴백."""
    payload = {
        "content": {
            "title": content.get("title", ""),
            "tags": content.get("tags"),
            "difficulty": content.get("difficulty"),
        },
        "candidates": [
            {"node_id": nid, "name": info[nid]["name"],
             "desc": info[nid]["desc"], "similarity": round(sim, 3)}
            for nid, sim in cands if nid in info
        ],
    }
    msg = client.messages.create(
        model=MODEL,
        max_tokens=300,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    )
    try:
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError, IndexError, AttributeError):
        # 빈/비텍스트 응답·잘못된 JSON → 최근접 기존 노드로 폴백
        return {"decision": "existing", "node_id": cands[0][0] if cands else None,
                "reason": "parse-fallback"}


def _create_node(conn: Connection, name: str, desc: str, parent_id: int | None) -> int:
    row = conn.execute(
        text(
            """
            INSERT INTO curriculum_nodes (name, description, parent_id, is_auto_generated)
            VALUES (:name, :desc, :parent_id, TRUE)
            RETURNING id
            """
        ),
        {"name": name, "desc": desc, "parent_id": parent_id},
    ).fetchone()
    return row.id


def _map(conn: Connection, content_id: int, node_id: int, score: float) -> None:
    conn.execute(
        text(
            """
            INSERT INTO content_node_mapping (content_id, node_id, relevance_score)
            VALUES (:cid, :nid, :score)
            ON CONFLICT DO NOTHING
            """
        ),
        {"cid": content_id, "nid": node_id, "score": score},
    )


def _valid_node_id(val, info: dict[int, dict]) -> int | None:
    """LLM이 준 node id를 int로 강제하고 실제 존재하는 노드인지 검증. 아니면 None(환각 방지)."""
    try:
        nid = int(val)
    except (TypeError, ValueError):
        return None
    return nid if nid in info else None


def expand_one(content: dict, centroids: dict[int, np.ndarray], info: dict[int, dict],
               conn: Connection, client: anthropic.Anthropic) -> dict:
    """콘텐츠 1건을 그래프에 편입한다. centroids/info를 in-place로 갱신(새 노드 반영)."""
    emb = _parse_emb(content["text_embedding"])
    cands = _candidates(emb, centroids, CANDIDATE_K)
    top_id, top_sim = (cands[0] if cands else (None, 0.0))

    # 가드레일 단락: 명백히 들어맞으면 LLM 없이 기존 노드
    if top_sim >= DEDUP_THRESHOLD and top_id is not None:
        _map(conn, content["id"], top_id, top_sim)
        return {"action": "existing", "node_id": top_id, "sim": round(top_sim, 3), "llm": False}

    j = _judge(content, cands, info, client)
    decision = j.get("decision", "existing")

    # 가드레일: new_top은 top 유사도 < NEW_TOP일 때만, 아니면 new_sub로 강등(부모=top)
    if decision == "new_top" and top_sim >= NEW_TOP_THRESHOLD:
        decision = "new_sub"
        j["parent_id"] = top_id

    if decision == "new_sub" and j.get("new_name"):
        parent = _valid_node_id(j.get("parent_id"), info)
        if parent is None:
            parent = top_id  # 환각 부모 → 최근접 노드
        name, desc = str(j["new_name"])[:100], str(j.get("new_desc") or "")[:1000]
        nid = _create_node(conn, name, desc, parent)
        centroids[nid] = emb           # 새 노드 centroid = 시드 콘텐츠
        info[nid] = {"name": name, "desc": desc, "parent_id": parent}
        _map(conn, content["id"], nid, 1.0)
        return {"action": "new_sub", "node_id": nid, "parent_id": parent, "name": name, "llm": True}

    if decision == "new_top" and j.get("new_name"):
        name, desc = str(j["new_name"])[:100], str(j.get("new_desc") or "")[:1000]
        nid = _create_node(conn, name, desc, None)
        centroids[nid] = emb
        info[nid] = {"name": name, "desc": desc, "parent_id": None}
        _map(conn, content["id"], nid, 1.0)
        return {"action": "new_top", "node_id": nid, "name": name, "llm": True}

    # existing (또는 폴백). 환각/누락 node_id는 최근접 노드로 보정.
    node_id = _valid_node_id(j.get("node_id"), info)
    if node_id is None:
        node_id = top_id
    if node_id is not None:
        _map(conn, content["id"], node_id, max(top_sim, 0.5))
        return {"action": "existing", "node_id": node_id, "sim": round(top_sim, 3), "llm": True}
    return {"action": "skipped", "node_id": None, "llm": True}  # 빈 그래프 등 — 매핑 대상 없음


def expand_graph(conn: Connection, client: anthropic.Anthropic, limit: int | None = None) -> dict:
    """콘텐츠를 순회하며 그래프를 확장한다. 종류별 카운트를 반환."""
    centroids = _node_centroids(conn)
    info = _node_info(conn)

    # 멱등성: 이미 Auto-HKG 노드(is_auto_generated)에 매핑된 콘텐츠는 재처리하지 않는다.
    sql = """
        SELECT c.id, c.title, c.tags, c.difficulty, c.text_embedding
        FROM content c
        WHERE c.text_embedding IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM content_node_mapping m
              JOIN curriculum_nodes n ON n.id = m.node_id
              WHERE m.content_id = c.id AND n.is_auto_generated = TRUE
          )
        ORDER BY c.id
    """
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    contents = conn.execute(text(sql)).fetchall()

    stats = {"existing": 0, "new_sub": 0, "new_top": 0, "skipped": 0, "llm_calls": 0, "total": 0}
    for c in contents:
        res = expand_one(dict(c._mapping), centroids, info, conn, client)
        stats[res["action"]] += 1
        stats["llm_calls"] += 1 if res.get("llm") else 0
        stats["total"] += 1
    return stats
