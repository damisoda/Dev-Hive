"""HIVE-22: GraphRAG 추천 (구조 우선).

추천 '결정'은 알고리즘 4성분 점수로 내린다 (LLM 아님):
  관련성 0.3 — profile_vector ↔ content 임베딩 mean-centering 코사인
  난이도 0.4 — estimate_mastery(node) ↔ content.difficulty 적합도
              (약한 개념 → 쉬운/선행, 강한 개념 → 어려운/심화)
  경로   0.2 — 선후(prerequisite) 일관성. 후보 토픽의 선행토픽 mastery 가중평균
              (precedes 엣지 = node_links). 선행을 익혔으면↑(배울 준비됨), 안 익혔으면↓(이름).
              선행이 없거나 precedes 데이터가 비면 _NEUTRAL_PATH로 폴백(순위 무영향).
  다양성 0.1 — 같은 노드 편중 방지(그리디 다양성 재정렬, MMR 변형).

LLM(Haiku)은 top-1의 '왜 이 순서' 근거 1회 생성에만 쓴다 — 결정엔 미관여,
키가 없거나 실패하면 템플릿으로 폴백.

참고: CG-RAG(2602.00020)의 mastery 기반 커리큘럼 검색 방향. 4성분 가중치/centering은
도메인 적응(튜닝 대상)이며 논문 수치 그대로가 아님.
rule_based.recommend_next와 동일 시그니처 — 드롭인 교체.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.services.constants import (
    LEVEL_MASTERY_FLOOR,
    ONBOARDING_MASTERY_CEILING,
)
from app.services.constants import (
    FEEDBACK_WANT_MORE_GRAPHRAG_WEIGHT as W_FB,
    LEVEL_ORDER,
    MASTERY_TOO_HARD_DELTA,
    MASTERY_UNDERSTOOD_ALPHA,
    RECENCY_GRAPHRAG_WEIGHT as W_RECENCY,
    QUALITY_GRAPHRAG_WEIGHT as W_QUALITY,
    RECENCY_HALF_LIFE_DAYS,
)
from app.services.feedback_signals import (
    feedback_excluded_ids,
    too_hard_topics,
    understood_topics,
    want_more_centroid,
)
from app.services.knowledge_tracing import build_user_state, estimate_mastery

logger = logging.getLogger(__name__)

W_REL, W_DIFF, W_PATH, W_DIV = 0.3, 0.4, 0.2, 0.1
# 중급 이상 전용 신선도 보너스(LEVEL_ORDER[1:]에서 파생 — 레벨 추가 시 자동 반영).
_RECENCY_LEVELS = frozenset(LEVEL_ORDER[1:])

_DIFFICULTY_NORM = {"입문": 0.0, "중급": 0.5, "고급": 1.0}
_NEUTRAL_PATH = 0.5          # prerequisite 데이터 부재 시 중립(순위 무영향)
_HAIKU_MODEL = "claude-haiku-4-5-20251001"


def _recency_score(published_at: datetime | None, created_at: datetime | None = None) -> float:
    """시간 감쇠 점수(0~1). 반감기 RECENCY_HALF_LIFE_DAYS일.
    홈 피드 정렬(HIVE-107)과 동일하게 COALESCE(published_at, created_at) 기준.
    둘 다 없으면 0.0(recency 항 비가산). 미래 발행일 → 0.0(보너스 없음).
    """
    effective = published_at or created_at
    if effective is None:
        return 0.0
    if effective.tzinfo is None:
        effective = effective.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - effective).total_seconds() / 86400
    if days < 0:
        return 0.0  # 미래 발행일(임베고/예정 콘텐츠) → recency 보너스 없음
    return math.exp(-math.log(2) * days / RECENCY_HALF_LIFE_DAYS)


def _div_key(c: dict) -> object:
    """다양성 카운트 키. node_id=None이면 content_id로 독립 처리.

    node_id=None 콘텐츠가 단일 키(None)를 공유하면 서로 다양성 페널티를 누적시킨다.
    content_id는 콘텐츠마다 고유하므로 None인 경우 각자 독립 카운트된다.
    """
    nid = c["node_id"]
    return nid if nid is not None else ("_", c["content_id"])


def _parse_vec(raw) -> np.ndarray | None:
    """pgvector 반환(str "[...]" 또는 list)을 np.ndarray로."""
    if raw is None:
        return None
    if isinstance(raw, str):
        vals = [v for v in raw.strip("[]").split(",") if v.strip()]
        if not vals:                      # "[]"/"" 같은 빈 임베딩 방어
            return None
        return np.array([float(x) for x in vals], dtype=float)
    return np.array([float(x) for x in raw], dtype=float)


def _global_centroid(db: Session) -> np.ndarray | None:
    """전체 콘텐츠 임베딩 평균(anisotropy 보정용 중심). 데이터 늘면 변하므로 호출 시점 계산."""
    row = db.execute(
        text("SELECT AVG(text_embedding)::text FROM content WHERE text_embedding IS NOT NULL")
    ).scalar()
    return _parse_vec(row)


def _load_prereq_map(db: Session) -> dict[int, list[tuple[int, float]]]:
    """precedes 엣지(node_links)를 {target_node: [(선행 source, weight), ...]}로 적재.

    (source, target) = source가 target의 선행(prerequisite). 후보 토픽 T의 선행을
    O(1)로 찾도록 target 기준으로 묶는다. node_links는 작아 호출당 1쿼리로 충분하다.
    node_links가 비면 {} → 전 후보 path가 _NEUTRAL_PATH(기존 동작과 동일).
    """
    rows = db.execute(
        text("SELECT source_node_id, target_node_id, weight FROM node_links")
    ).fetchall()
    prereq_map: dict[int, list[tuple[int, float]]] = {}
    for r in rows:
        w = float(r.weight) if r.weight is not None else 0.5
        prereq_map.setdefault(int(r.target_node_id), []).append(
            (int(r.source_node_id), w)
        )
    return prereq_map


def _topic_of(db: Session) -> dict[int, int]:
    """노드 → 소속 대주제 id. precedes는 7대주제 간에만 있으므로, 콘텐츠 대표노드가 auto
    하위노드면 부모 대주제로 해소해 _path_score가 선행 신호를 받게 한다(catch-all 분할 이후
    대표노드가 대부분 하위노드라 path가 전부 중립이던 문제 해소). 대주제는 자기 자신."""
    rows = db.execute(text("SELECT id, parent_id FROM curriculum_nodes")).fetchall()
    return {int(r.id): (int(r.parent_id) if r.parent_id is not None else int(r.id)) for r in rows}


def _difficulty_fit(content_difficulty: str | None, mastery: float) -> float:
    """이상 난이도 ≈ 현재 mastery → 적합도 = 1 - |난이도 - mastery| (0~1)."""
    d = _DIFFICULTY_NORM.get(content_difficulty, 0.5)
    return 1.0 - abs(d - mastery)


def _difficulty_target(node_mastery: float, level_floor: float) -> float:
    """난이도 매칭 기준치(HIVE-95). 미학습(온보딩만, ≤상한) 토픽은 선언 레벨 floor로 올려
    onboarding mastery(≤0.2) 때문에 중·고급 유저가 입문 콘텐츠로 쏠리던 편향을 해소한다.
    읽음으로 학습한(상한 초과) 토픽은 실제 node mastery를 그대로 써 적응을 유지한다."""
    return node_mastery if node_mastery > ONBOARDING_MASTERY_CEILING else max(node_mastery, level_floor)


def _path_score(
    node_id: int | None,
    prereq_map: dict[int, list[tuple[int, float]]],
    mastery: dict[int, float],
) -> float:
    """선행 충족도(0~1): 후보 토픽의 선행토픽 mastery 가중평균.

    선행을 이미 익혔으면 1.0에 가까움(지금 배울 준비됨), 안 익혔으면 0.0(아직 이름).
    선행이 없거나(루트 토픽) precedes 데이터가 비면 _NEUTRAL_PATH → 순위 무영향.
    weight는 precedes 신뢰도(load_precedes) — 신뢰 높은 선행일수록 비중이 크다.
    mastery에 없는 선행 노드는 0.0(미학습)으로 본다(KeyError 방지).
    """
    if node_id is None:
        return _NEUTRAL_PATH
    prereqs = prereq_map.get(node_id)
    if not prereqs:
        return _NEUTRAL_PATH
    den = sum(w for _, w in prereqs)
    if den <= 0:
        return _NEUTRAL_PATH
    num = sum(w * mastery.get(src, 0.0) for src, w in prereqs)
    return num / den


def _template_reason(c: dict) -> str:
    # profile_vector 기반 관련성이 실제로 계산됐을 때만 '관심 적합' 표기(quality 폴백을 관심으로 오표기 방지)
    reason = f"난이도 적합 {c['diff']:.0%}"
    if c.get("rel_real"):
        reason += f" · 관심 적합 {c['rel']:.0%}"
    return reason


def _rationale(user_state: str, item: dict) -> str | None:
    """top-1 근거 한 문장(Haiku). 키 없거나 실패 시 None → 템플릿 폴백."""
    try:
        from app.services.llm import get_llm_client, llm_available
        if not llm_available():
            return None
        client = get_llm_client(settings.anthropic_api_key)
        msg = client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=200,
            system=(
                "학습 추천 이유를 한국어 한 문장으로 설명한다. 유저 상태와 콘텐츠를 보고 "
                "'왜 지금 이걸 봐야 하는지'를 과장 없이 간결하게."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"[유저 상태]\n{user_state}\n\n"
                    f"[추천 콘텐츠]\n제목: {item['title']}\n난이도: {item.get('difficulty')}"
                ),
            }],
        )
        return msg.content[0].text.strip()
    except Exception as exc:  # 키 부재/네트워크/응답 형식 등 — 결정엔 영향 없으므로 폴백
        logger.warning("rationale 생성 실패(템플릿 폴백): %s", exc)
        return None


def recommend_next(user_id: int, top_n: int, db: Session) -> list[dict]:
    """4성분 알고리즘으로 미독 콘텐츠를 정렬해 top_n 추천. (rule_based 드롭인 교체)"""
    urow = db.execute(
        text("SELECT profile_vector::text AS pv, current_level FROM users WHERE id = :uid"),
        {"uid": user_id},
    ).fetchone()
    if urow is None:
        return []

    profile = _parse_vec(urow.pv)
    use_recency = (urow.current_level or "입문") in _RECENCY_LEVELS
    level_floor = LEVEL_MASTERY_FLOOR.get(urow.current_level or "입문", 0.0)  # HIVE-95 콜드스타트 정렬
    mastery = estimate_mastery(user_id, db)  # {node_id: 0~1}

    # 피드백 → 토픽별 mastery 조정(HIVE-48). 전역 난이도 감점 대신 대표 토픽 단위로 정교하게.
    #   too_hard 토픽 → mastery 하향 → difficulty_fit이 더 쉬운/선행 콘텐츠를 선호
    #   understood 토픽 → mastery 상향 → 더 어려운/심화 콘텐츠를 선호(역량 신호)
    # 두 신호가 같은 토픽에 동시에 오면 두 조정이 합쳐져 상쇄된다(자연스러운 절충).
    for node in too_hard_topics(user_id, db):
        mastery[node] = max(0.0, mastery.get(node, 0.0) - MASTERY_TOO_HARD_DELTA)
    for node in understood_topics(user_id, db):
        mastery[node] = min(1.0, mastery.get(node, 0.0) + MASTERY_UNDERSTOOD_ALPHA)

    # want_more 중심(HIVE-48): profile_vector를 오염시키지 않고 점수 단계에서 보너스로만 더한다.
    # 관련성과 동일하게 global centroid로 centering한 코사인(0~1)에 W_FB를 곱한다.
    wm_centroid = _parse_vec(want_more_centroid(user_id, db))

    # 피드백 제외(HIVE-37): understood/not_interested 콘텐츠는 추천에서 뺀다.
    # 공용 헬퍼(feedback_signals)로 rule_based와 동일 신호를 공유한다.
    excluded = feedback_excluded_ids(user_id, db)
    params: dict = {"uid": user_id}
    excl_clause = ""
    if excluded:
        params["excluded"] = list(excluded)
        excl_clause = "AND c.id <> ALL(:excluded)"

    # 후보: 미독 + 임베딩 보유 + 대표 노드(최고 relevance_score)
    rows = db.execute(
        text(
            f"""
            SELECT c.id, c.title, c.difficulty, c.quality_score,
                   c.published_at,
                   c.created_at,
                   c.text_embedding::text AS emb,
                   (SELECT m.node_id FROM content_node_mapping m
                    WHERE m.content_id = c.id
                    ORDER BY m.relevance_score DESC LIMIT 1) AS node_id
            FROM content c
            WHERE c.text_embedding IS NOT NULL
              AND c.content_type NOT IN ('paper', 'news')
              AND c.id NOT IN (
                  SELECT content_id FROM user_read_events WHERE user_id = :uid
              )
              {excl_clause}
            ORDER BY c.id
            """
        ),
        params,
    ).fetchall()
    if not rows:
        return []

    g = _global_centroid(db)
    # precedes 선행맵: 피드백 반영(too_hard/understood) 후의 mastery로 채점하도록 여기서 1회 적재.
    prereq_map = _load_prereq_map(db)
    topic_of = _topic_of(db)  # 하위노드 대표 → 대주제 해소(precedes 신호 활성화)
    pc = (profile - g) if (profile is not None and g is not None) else None
    # want_more 중심도 관련성과 동일 기준으로 centering(global centroid 필요).
    wmc = (wm_centroid - g) if (wm_centroid is not None and g is not None) else None

    cands: list[dict] = []
    for r in rows:
        emb = _parse_vec(r.emb)
        ec = (emb - g) if (emb is not None and g is not None) else None
        # 관련성: centered 코사인 → 0~1. profile_vector(또는 centroid) 없으면 quality로 대체(콜드스타트).
        rel_real = pc is not None and ec is not None
        if rel_real:
            denom = float(np.linalg.norm(pc) * np.linalg.norm(ec)) or 1.0
            rel = (float(np.dot(pc, ec) / denom) + 1.0) / 2.0
        else:
            rel = float(r.quality_score) if r.quality_score is not None else 0.5
        diff = _difficulty_fit(r.difficulty, _difficulty_target(mastery.get(r.node_id, 0.0), level_floor))
        # want_more 보너스: 별도 항(4성분과 무관). centered 코사인(0~1) × W_FB. 신호 없으면 0.
        if wmc is not None and ec is not None:
            wm_denom = float(np.linalg.norm(wmc) * np.linalg.norm(ec)) or 1.0
            wm_sim = (float(np.dot(wmc, ec) / wm_denom) + 1.0) / 2.0
        else:
            wm_sim = 0.0
        path = _path_score(topic_of.get(r.node_id, r.node_id), prereq_map, mastery)
        recency = W_RECENCY * _recency_score(r.published_at, r.created_at) if use_recency else 0.0
        # 품질 보너스: 프로필 유저만(콜드스타트는 rel=quality라 중복 방지). 저가치 콘텐츠 demote.
        q = float(r.quality_score) if r.quality_score is not None else 0.5
        qbonus = W_QUALITY * q if rel_real else 0.0
        base = W_REL * rel + W_DIFF * diff + W_PATH * path + W_FB * wm_sim + recency + qbonus
        cands.append({
            "content_id": r.id, "title": r.title, "difficulty": r.difficulty,
            "node_id": r.node_id, "rel": rel, "rel_real": rel_real,
            "diff": diff, "path": path, "recency": recency, "base": base,
        })

    # 그리디 선택: 매 단계 base + 다양성(같은 노드 누적 penalty) 최대를 뽑는다.
    selected: list[dict] = []
    node_count: dict = {}
    while cands and len(selected) < top_n:
        best, best_score = None, -1.0
        for c in cands:
            div = 1.0 / (1.0 + node_count.get(_div_key(c), 0))
            s = c["base"] + W_DIV * div
            if s > best_score:
                best, best_score = c, s
        selected.append({**best, "score": round(best_score, 4)})
        node_count[_div_key(best)] = node_count.get(_div_key(best), 0) + 1
        cands.remove(best)

    # top-1만 LLM 근거(1회), 나머지는 템플릿
    user_state = build_user_state(user_id, db)
    out: list[dict] = []
    for i, c in enumerate(selected):
        reason = (_rationale(user_state, c) or _template_reason(c)) if i == 0 else _template_reason(c)
        out.append({
            "content_id": c["content_id"], "title": c["title"],
            "score": c["score"], "reason": reason,
        })
    return out
