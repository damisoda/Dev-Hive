"""HIVE-21 / HIVE-44: Auto-HKG — 자동 계층형 지식그래프 확장 (2-패스 재설계).

새 콘텐츠를 그래프에 편입한다. 대주제 7개는 닫힌 분류가 아니라 '씨앗' — Auto-HKG로
그래프가 스스로 자란다(self-organizing). 단, 콘텐츠 1건마다 전용 노드를 찍어내는
과파편화를 막기 위해 v1의 per-content 그리디 매칭을 버리고 2-패스 구조로 바꾼다.

== 왜 2-패스인가 (HIVE-44, 진단 문서 Auto-HKG_진단_20260610.md 근거) ==
v1은 콘텐츠를 1건씩 보며 "안 맞으면 새 노드"를 만들었다. 그 결과 924건 처리에
자동노드 825개가 생겼고 그중 778개(94%)가 콘텐츠 1건짜리 고아노드였다. 원인:
  (a) DEDUP=0.85가 실제 콘텐츠↔centroid 코사인 분포 최댓값(0.816)을 넘어 흡수 0%.
  (b) 새 노드 centroid=시드 1건 임베딩이라 후보 풀을 오염시켜 눈덩이(snowball).
해결은 임계값 조정이 아니라 아키텍처 변경 — 멤버십을 1건씩 그리디로 정하지 말고
클러스터를 먼저 묶고(2패스) 이름만 붙인다.

== 구조 ==
- 1패스(대주제 흡수): 콘텐츠 vs 안정적 스켈레톤(비-auto 노드) centroid 코사인 top.
  top >= DEDUP(0.70)이면 그 노드로 흡수. 새 노드를 후보 풀에 넣지 않아 오염 없음(B).
- 2패스(잔여 클러스터링): 흡수 안 된 잔여 콘텐츠끼리 임베딩 유사도 그래프(코사인
  >= GROUP)의 연결요소로 묶는다. 크기 >= MIN인 클러스터만 노드 1개로 승격하고
  Haiku는 이름만 붙인다. MIN 미만(고아 후보)은 노드를 만들지 않고 최근접 기존
  노드에 매핑한다 — 고아노드 금지(A).

설계 메모: LLM 호출이 콘텐츠 수(924)가 아니라 클러스터 수(~38)로 줄어 비용도 급감.
트리거는 배치(scripts/run_auto_hkg.py). dedup은 임베딩 코사인으로 처리 → 새 임베딩 호출 없음.
"""
from __future__ import annotations

import json
import re

import threading

import anthropic
import networkx as nx
import numpy as np
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.tagging.tagger import MODEL

# 진단 문서 §5 권장 파라미터
DEDUP_THRESHOLD = 0.70   # 1패스: 스켈레톤 흡수 임계 (top 코사인 이 이상이면 기존 노드로)
GROUP_THRESHOLD = 0.65   # 2패스: 잔여 콘텐츠 간 클러스터링 유사도 임계
MIN_CLUSTER_SIZE = 3     # 2패스: 노드로 승격할 최소 클러스터 크기 (미만은 고아 → 흡수)

# HIVE-57: 동적 흡수임계(opt-in, AUTOHKG_DYNAMIC_DEDUP=1). 고정 0.70은 코퍼스 분포에 종속이라
# 새 글 유입으로 분포가 드리프트하면 흡수 실패→고아 폭증(백테스트 실증: 고정 잔차율 79~89% vs
# 동적 55~76%, orphan_ratio 0.439→0.398). tau_j = max((1-β)분위(음성분포), floor)로 분포를 추종.
DEDUP_BETA = 0.05        # tau_j 분위: 노드 j 음성분포의 (1-β) 분위수
DEDUP_FLOOR = 0.62       # 흡수정밀도 하한 보장(0.62 미만은 정밀도<80%, 진단 실측) — tau 하한

# expand_graph는 동일 DB에 대해 동시에 두 경로(_maybe_ingest + 48h 스케줄)로 호출될 수 있다.
# 락 없이 동시 실행되면 _create_node(UNIQUE 제약 없음)가 중복 노드를 생성한다.
_expand_graph_lock = threading.Lock()

# 단건 업로드 경로(expand_one, HIVE-33)용. 배치 크롤(2패스)과 달리 1건씩 편입하며
# 노드 생성을 허용한다 — 저볼륨 유저 기여라 과파편화 위험이 낮고, "내 글이 그래프에
# 새 토픽으로 편입"되는 자가복제 데모 모먼트가 핵심이기 때문.
NEW_TOP_THRESHOLD = 0.40  # top 후보 유사도 이 미만일 때만 새 최상위 대주제 허용
CANDIDATE_K = 5           # Haiku에 줄 후보 노드 수

_NAMING_SYSTEM = """You name a cluster of related AI-learning content for a curriculum knowledge graph.
Given several content titles that an embedding model grouped together, return ONE short Korean topic label.

Return ONLY a JSON object:
{"new_name":"<concise Korean topic name, no longer than ~20 chars>","new_desc":"<one-line Korean description>"}

- new_name must capture the shared theme (e.g. "MCP 서버 구축", "Claude Code 활용", "로컬 LLM 서빙").
- Do NOT duplicate the parent topic's name. Be specific to what the titles share."""

# 단건 업로드(expand_one)에서 1건의 편입 위치를 판단하는 Haiku 프롬프트.
_JUDGE_SYSTEM = """You are a curriculum knowledge-graph organizer for an AI-learning community.
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


def _unit(v: np.ndarray) -> np.ndarray:
    """L2 정규화. 정규화 후 내적 = 코사인 유사도."""
    n = np.linalg.norm(v)
    return v / n if n else v


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _skeleton_centroids(conn: Connection) -> dict[int, np.ndarray]:
    """안정적 스켈레톤(비-auto 노드)의 centroid. 새 자동노드는 후보에서 제외(풀 미오염, B).

    centroid = 소속 콘텐츠 text_embedding 평균. 콘텐츠 없는 노드는 빠진다.
    """
    rows = conn.execute(
        text(
            """
            SELECT m.node_id AS node_id, c.text_embedding AS emb
            FROM content_node_mapping m
            JOIN content c ON c.id = m.content_id
            JOIN curriculum_nodes n ON n.id = m.node_id
            WHERE c.text_embedding IS NOT NULL
              AND n.is_auto_generated = FALSE
            """
        )
    ).fetchall()
    acc: dict[int, list[np.ndarray]] = {}
    for r in rows:
        acc.setdefault(r.node_id, []).append(_parse_emb(r.emb))
    return {nid: np.mean(vs, axis=0) for nid, vs in acc.items()}


def _root_centroids(conn: Connection) -> dict[int, np.ndarray]:
    """대주제(parent_id IS NULL, 비-auto) centroid. 새 클러스터 노드의 부모 결정용."""
    rows = conn.execute(
        text(
            """
            SELECT m.node_id AS node_id, c.text_embedding AS emb
            FROM content_node_mapping m
            JOIN content c ON c.id = m.content_id
            JOIN curriculum_nodes n ON n.id = m.node_id
            WHERE c.text_embedding IS NOT NULL
              AND n.is_auto_generated = FALSE
              AND n.parent_id IS NULL
            """
        )
    ).fetchall()
    acc: dict[int, list[np.ndarray]] = {}
    for r in rows:
        acc.setdefault(r.node_id, []).append(_parse_emb(r.emb))
    return {nid: np.mean(vs, axis=0) for nid, vs in acc.items()}


def _nearest(emb: np.ndarray, centroids: dict[int, np.ndarray]) -> tuple[int | None, float]:
    """centroids 중 코사인 최댓값 노드와 그 값."""
    best_id, best_sim = None, -1.0
    for nid, cen in centroids.items():
        s = _cosine(emb, cen)
        if s > best_sim:
            best_id, best_sim = nid, s
    return best_id, (best_sim if best_id is not None else 0.0)


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


def _name_cluster(titles: list[str], client: anthropic.Anthropic) -> tuple[str, str]:
    """Haiku로 클러스터에 이름/설명을 붙인다. 실패 시 첫 제목 기반 폴백."""
    sample = titles[:8]
    payload = {"titles": sample}
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=200,
            system=_NAMING_SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        raw = msg.content[0].text.strip()
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        j = json.loads(raw)
        name = str(j.get("new_name") or "").strip()[:100]
        desc = str(j.get("new_desc") or "").strip()[:1000]
        if name:
            return name, desc
    except (json.JSONDecodeError, ValueError, IndexError, AttributeError, anthropic.AnthropicError):
        pass
    # 폴백: 첫 제목 축약
    fallback = (sample[0] if sample else "자동 그룹").strip()[:40]
    return f"자동: {fallback}", "임베딩 클러스터링으로 묶인 콘텐츠 그룹"


def _cluster_residuals(
    residuals: list[tuple[int, np.ndarray]], group_threshold: float, min_size: int
) -> tuple[list[list[int]], list[int]]:
    """잔여 콘텐츠를 임베딩 유사도 그래프의 연결요소로 클러스터링.

    residuals: (content_id, 정규화된 임베딩) 목록.
    반환: (승격 클러스터 목록[크기>=min_size], 고아 content_id 목록[크기<min_size]).
    """
    n = len(residuals)
    g = nx.Graph()
    g.add_nodes_from(range(n))
    # O(n^2) 쌍별 코사인 — 잔여는 보통 수백 건이라 비용 무시 가능. 정규화돼 있어 내적=코사인.
    for i in range(n):
        ei = residuals[i][1]
        for j in range(i + 1, n):
            if float(np.dot(ei, residuals[j][1])) >= group_threshold:
                g.add_edge(i, j)

    clusters: list[list[int]] = []
    orphans: list[int] = []
    for comp in nx.connected_components(g):
        members = [residuals[idx][0] for idx in comp]
        if len(members) >= min_size:
            clusters.append(members)
        else:
            orphans.extend(members)
    # 큰 클러스터 먼저 (로그 가독성 + 안정적 순서)
    clusters.sort(key=len, reverse=True)
    return clusters, orphans


def _adaptive_dedup_thresholds(
    conn: Connection, skeleton: dict[int, np.ndarray], beta: float, floor: float
) -> dict[int, float]:
    """노드별 동적 흡수임계 tau_j = max((1-β)분위(음성분포), floor) (HIVE-57).

    음성분포 = 노드 j 에 속하지 않은(다른 대주제로 매핑된) 콘텐츠와 j centroid의 코사인.
    분포가 드리프트해도 흡수율을 일정하게 유지(고정 절대임계의 고아 폭증 방지). floor로 흡수정밀도 하한.
    """
    rows = conn.execute(text("""
        SELECT (SELECT m.node_id FROM content_node_mapping m
                JOIN curriculum_nodes n ON n.id = m.node_id
                WHERE m.content_id = c.id AND n.is_auto_generated = FALSE
                ORDER BY m.relevance_score DESC LIMIT 1) AS node_id,
               c.text_embedding
        FROM content c WHERE c.text_embedding IS NOT NULL
    """)).fetchall()
    labeled = [(r.node_id, _parse_emb(r.text_embedding)) for r in rows if r.node_id is not None]
    tau: dict[int, float] = {}
    for nid, cen in skeleton.items():
        neg = [_cosine(emb, cen) for lab, emb in labeled if lab != nid]
        if neg:
            tau[nid] = max(float(np.quantile(neg, 1.0 - beta)), floor)
    return tau


def expand_graph(
    conn: Connection,
    client: anthropic.Anthropic,
    limit: int | None = None,
    *,
    dedup_threshold: float = DEDUP_THRESHOLD,
    group_threshold: float = GROUP_THRESHOLD,
    min_cluster_size: int = MIN_CLUSTER_SIZE,
    dynamic_dedup: bool = False,
    dedup_beta: float = DEDUP_BETA,
    dedup_floor: float = DEDUP_FLOOR,
) -> dict:
    """2-패스로 그래프를 확장한다. 종류별 카운트를 반환.

    1패스: 스켈레톤 흡수(top 코사인 >= dedup). 2패스: 잔여 클러스터링 후 노드 승격.
    dynamic_dedup=True(또는 env AUTOHKG_DYNAMIC_DEDUP=1)면 고정 dedup_threshold 대신
    노드별 동적 tau_j 사용(HIVE-57, 드리프트 robust). 기본은 고정(기존 동작 보존).
    """
    import os
    dynamic_dedup = dynamic_dedup or os.getenv("AUTOHKG_DYNAMIC_DEDUP") == "1"
    with _expand_graph_lock:
        return _expand_graph_inner(conn, client, limit,
                                   dedup_threshold=dedup_threshold,
                                   group_threshold=group_threshold,
                                   min_cluster_size=min_cluster_size,
                                   dynamic_dedup=dynamic_dedup,
                                   dedup_beta=dedup_beta,
                                   dedup_floor=dedup_floor)


def _expand_graph_inner(
    conn: Connection,
    client: anthropic.Anthropic,
    limit: int | None = None,
    *,
    dedup_threshold: float = DEDUP_THRESHOLD,
    group_threshold: float = GROUP_THRESHOLD,
    min_cluster_size: int = MIN_CLUSTER_SIZE,
    dynamic_dedup: bool = False,
    dedup_beta: float = DEDUP_BETA,
    dedup_floor: float = DEDUP_FLOOR,
) -> dict:
    skeleton = _skeleton_centroids(conn)
    roots = _root_centroids(conn)
    # HIVE-57: 동적 흡수임계(노드별). off면 None → 고정 dedup_threshold 사용(기존 동작).
    tau_map = (
        _adaptive_dedup_thresholds(conn, skeleton, dedup_beta, dedup_floor)
        if dynamic_dedup and skeleton else None
    )

    # 멱등성: 이미 Auto-HKG 노드에 매핑된 콘텐츠는 재처리하지 않는다.
    sql = """
        SELECT c.id, c.title, c.difficulty, c.text_embedding
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

    stats = {
        "absorbed": 0,      # 1패스 스켈레톤 흡수
        "clustered": 0,     # 2패스 클러스터 노드로 매핑된 콘텐츠
        "orphan_mapped": 0, # 2패스 고아 → 최근접 기존 노드 매핑
        "new_nodes": 0,     # 생성된 클러스터 노드 수
        "skipped": 0,       # 매핑 대상 없음(빈 그래프 등)
        "llm_calls": 0,
        "total": 0,
    }

    # ── 1패스: 대주제(스켈레톤) 흡수 ──────────────────────────────
    residuals: list[tuple[int, np.ndarray]] = []  # (content_id, 정규화 임베딩)
    title_by_id: dict[int, str] = {}
    for c in contents:
        stats["total"] += 1
        cid = c.id
        title_by_id[cid] = c.title or ""
        emb = _parse_emb(c.text_embedding)
        if not skeleton:
            stats["skipped"] += 1
            continue
        top_id, top_sim = _nearest(emb, skeleton)
        thr = tau_map.get(top_id, dedup_threshold) if tau_map else dedup_threshold
        if top_id is not None and top_sim >= thr:
            _map(conn, cid, top_id, top_sim)
            stats["absorbed"] += 1
        else:
            residuals.append((cid, _unit(emb)))

    # ── 2패스: 잔여 클러스터링 → 노드 승격(이름만 LLM) ────────────
    if residuals:
        clusters, orphans = _cluster_residuals(residuals, group_threshold, min_cluster_size)

        for members in clusters:
            # 클러스터 centroid로 부모(대주제) 결정
            members_set = set(members)
            cent = np.mean(
                [r[1] for r in residuals if r[0] in members_set], axis=0
            )
            parent_id, _ = _nearest(cent, roots) if roots else (None, 0.0)

            titles = [title_by_id.get(cid, "") for cid in members]
            name, desc = _name_cluster(titles, client)
            stats["llm_calls"] += 1

            new_id = _create_node(conn, name, desc, parent_id)
            stats["new_nodes"] += 1
            for cid in members:
                _map(conn, cid, new_id, 1.0)
                stats["clustered"] += 1

        # 고아(작은 클러스터): 노드 안 만들고 최근접 스켈레톤 노드로 매핑 (A)
        emb_by_id = {r[0]: r[1] for r in residuals}
        for cid in orphans:
            if not skeleton:
                stats["skipped"] += 1
                continue
            top_id, top_sim = _nearest(emb_by_id[cid], skeleton)
            if top_id is not None:
                _map(conn, cid, top_id, max(top_sim, 0.5))
                stats["orphan_mapped"] += 1
            else:
                stats["skipped"] += 1

    return stats


# ─────────────────────────────────────────────────────────────────────────────
# 단건 편입 경로 (HIVE-33 업로드) — expand_one
#
# 배치 크롤은 expand_graph(2-패스)로 과파편화를 막지만, 유저 업로드는 1건씩 들어오고
# (저볼륨 기여) "내 글이 그래프에 새 토픽으로 편입"되는 자가복제 데모 모먼트가 핵심이라
# per-content 판단 + 노드 생성을 허용한다. _parse_emb/_cosine/_create_node/_map은 위 공용.
# 임계값(DEDUP/NEW_TOP/CANDIDATE_K)은 모듈 상수 — 적응형 임계 레이어가 추후 오버라이드 가능.
# ─────────────────────────────────────────────────────────────────────────────


def _node_centroids(conn: Connection) -> dict[int, np.ndarray]:
    """노드별 소속 콘텐츠 text_embedding 평균(centroid). 콘텐츠 없는 노드는 빠진다.

    업로드 후보군은 auto 노드 포함 전 노드 — 업로드가 기존 auto 토픽에도 붙을 수 있게.
    """
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
        system=_JUDGE_SYSTEM,
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
