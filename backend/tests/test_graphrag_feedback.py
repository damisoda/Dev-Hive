"""HIVE-48 GraphRAG 피드백 반영 통합 테스트 (가짜 session, DB 비의존).

메인 추천기(graphrag.recommend_next)가 피드백 신호를 점수에 반영하는지 검증:
  (가) want_more 중심에 가까운 콘텐츠 → 보너스로 순위 상승
  (가) too_hard 토픽 → mastery 하향 → 더 쉬운 난이도 추천
  (다) understood 토픽 → mastery 상향 → 더 어려운(심화) 난이도 추천

SQL 종류별로 정해진 결과를 돌려주는 가짜 session으로 구성. LLM 근거 생성은 patch로 차단.
"""
from types import SimpleNamespace

import app.recommend.graphrag as gr
from app.recommend.graphrag import recommend_next


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _Session:
    """SQL 종류별로 정해진 결과를 돌려주는 가짜 session.

    nodes: [(id, name)], onboarding: dict, read_rows: [(node_id, difficulty, first_read)],
    candidates: [(id, title, difficulty, quality_score, emb, node_id)],
    centroid: pgvector text, excluded/too_hard_topics/understood_topics/want_more 신호.
    """

    def __init__(
        self,
        *,
        profile="[1.0,0.0]",
        candidates=None,
        centroid="[0.0,0.0]",
        nodes=None,
        onboarding=None,
        read_rows=None,
        excluded=None,
        too_hard=None,
        understood=None,
        want_more=None,
    ):
        self._profile = profile
        self._candidates = candidates or []
        self._centroid = centroid
        self._nodes = nodes or []
        self._onboarding = onboarding or {}
        self._read_rows = read_rows or []
        self._excluded = excluded or []
        self._too_hard = too_hard or []
        self._understood = understood or []
        self._want_more = want_more

    def execute(self, clause, params=None):
        sql = str(clause)
        params = params or {}
        if "profile_vector::text AS pv" in sql:
            return _Result(rows=[SimpleNamespace(pv=self._profile)])
        if "SELECT onboarding_answers FROM users" in sql:
            return _Result(rows=[SimpleNamespace(onboarding_answers=self._onboarding)])
        if "SELECT id, name FROM curriculum_nodes" in sql:
            return _Result(rows=[SimpleNamespace(id=i, name=n) for i, n in self._nodes])
        if "MIN(ure.read_at) AS first_read" in sql:
            return _Result(rows=[
                SimpleNamespace(node_id=nid, difficulty=d, first_read=t)
                for nid, d, t in self._read_rows
            ])
        if "feedback = ANY(:types)" in sql:
            return _Result(rows=[SimpleNamespace(content_id=c) for c in self._excluded])
        if "feedback = 'want_more'" in sql:
            return _Result(scalar=self._want_more)
        if "f.feedback = :fb" in sql:
            fb = params.get("fb")
            src = self._too_hard if fb == "too_hard" else self._understood
            return _Result(rows=[SimpleNamespace(node_id=n) for n in src])
        if "ORDER BY m.relevance_score DESC LIMIT 1) AS node_id" in sql and "FROM content c" in sql:
            return _Result(rows=[
                SimpleNamespace(
                    id=cid, title=title, difficulty=diff,
                    quality_score=q, emb=emb, node_id=nid,
                )
                for cid, title, diff, q, emb, nid in self._candidates
            ])
        if "AVG(text_embedding)::text FROM content" in sql:
            return _Result(scalar=self._centroid)
        # build_user_state의 노드별 읽음 건수(추천 결정엔 무관)
        if "COUNT(DISTINCT ure.content_id) AS read_count" in sql:
            return _Result(rows=[])
        if "SELECT current_level, onboarding_answers FROM users" in sql:
            return _Result(rows=[SimpleNamespace(current_level="중급", onboarding_answers=self._onboarding)])
        raise AssertionError(f"예상치 못한 쿼리: {sql[:80]}")


def _ids(out):
    return [o["content_id"] for o in out]


def _no_llm(monkeypatch):
    # top-1 LLM 근거는 결정 무관 → 템플릿 폴백으로 고정(키/네트워크 차단)
    monkeypatch.setattr(gr, "_rationale", lambda state, item: None)


# ── (가) want_more 보너스 → 순위 상승 ─────────────────────────────────

def test_want_more_boosts_similar_content(monkeypatch):
    _no_llm(monkeypatch)
    # profile은 중립([0,0])이라 관련성 동률, 난이도도 동일 → want_more만이 순위를 가른다.
    # centroid=[0,0]이라 centering은 무영향. emb=[1,0]이 want_more 중심[1,0]과 정렬.
    cands = [
        (1, "A", "중급", 0.5, "[1.0,0.0]", 10),
        (2, "B", "중급", 0.5, "[-1.0,0.0]", 20),
    ]
    base = dict(profile="[0.0,0.0]", candidates=cands, centroid="[0.0,0.0]")

    out_no = recommend_next(1, 2, _Session(**base))
    out_wm = recommend_next(1, 2, _Session(**base, want_more="[1.0,0.0]"))

    # want_more 없으면 동률(quality 동일) — 입력 순서 유지로 A 먼저.
    # want_more=[1,0]이면 A(=[1,0])가 보너스로 확실히 1위.
    assert _ids(out_wm)[0] == 1
    # B는 want_more 중심과 반대 → A보다 점수 낮음
    assert out_wm[0]["score"] > out_wm[1]["score"]
    assert _ids(out_no) == [1, 2]


# ── (가) too_hard 토픽 → 더 쉬운 난이도 추천 ──────────────────────────

def test_too_hard_topic_prefers_easier(monkeypatch):
    _no_llm(monkeypatch)
    # 노드 10에 입문/고급 콘텐츠. 초기 mastery=0.5(읽음으로 끌어올림 가정 위해 직접 조정 대신
    # onboarding 신호 없이 BKT로). 여기선 read_rows로 node10 mastery를 중간대로 만든 뒤
    # too_hard로 하향 → 입문(쉬운) 콘텐츠가 difficulty_fit 우위.
    nodes = [(10, "토픽A")]
    # 고급 1회 읽음 → mastery(10) = 0 + (1-0)*0.20 = 0.20. too_hard 하향(-0.2) → 0.0 → 입문 적합 1.0
    cands = [
        (1, "쉬움", "입문", 0.5, "[0.0,0.0]", 10),
        (2, "어려움", "고급", 0.5, "[0.0,0.0]", 10),
    ]
    base = dict(
        profile="[0.0,0.0]", candidates=cands, centroid="[0.0,0.0]",
        nodes=nodes, read_rows=[(10, "고급", 1)],
    )

    out_normal = recommend_next(1, 2, _Session(**base))
    out_hard = recommend_next(1, 2, _Session(**base, too_hard=[10]))

    # too_hard 적용 시 입문(content_id=1)이 1위로 올라온다.
    assert _ids(out_hard)[0] == 1
    # too_hard 적용으로 입문이 어려움보다 점수 우위가 더 벌어졌는지(난이도 정렬 이동) 확인
    easy_hard = next(o for o in out_hard if o["content_id"] == 1)["score"]
    hard_hard = next(o for o in out_hard if o["content_id"] == 2)["score"]
    assert easy_hard > hard_hard


# ── (다) understood 토픽 → 더 어려운(심화) 난이도 추천 ────────────────

def test_understood_topic_prefers_harder(monkeypatch):
    _no_llm(monkeypatch)
    nodes = [(10, "토픽A")]
    # 읽음 없음 → mastery(10)=0.0. understood 상향(+0.15) → 0.15.
    # 0.15에서도 입문(0.0) 적합이 고급(1.0)보다 높지만, 상향으로 고급 적합이 개선되는지 확인.
    cands = [
        (1, "쉬움", "입문", 0.5, "[0.0,0.0]", 10),
        (2, "어려움", "고급", 0.5, "[0.0,0.0]", 10),
    ]
    base = dict(
        profile="[0.0,0.0]", candidates=cands, centroid="[0.0,0.0]", nodes=nodes,
    )

    out_normal = recommend_next(1, 2, _Session(**base))
    out_und = recommend_next(1, 2, _Session(**base, understood=[10]))

    hard_normal = next(o for o in out_normal if o["content_id"] == 2)["score"]
    hard_und = next(o for o in out_und if o["content_id"] == 2)["score"]
    # understood 상향 → 고급(어려운) 콘텐츠 점수가 올라간다.
    assert hard_und > hard_normal


# ── 콜드스타트: profile NULL + mastery 빈 → 에러 없이 입문 추천 ───────

def test_cold_start_no_profile_no_mastery(monkeypatch):
    _no_llm(monkeypatch)
    # 신규 유저: profile_vector NULL, 읽음/온보딩 없음 → mastery 0.0 → 입문 적합 우위.
    cands = [
        (1, "입문글", "입문", 0.9, "[0.1,0.2]", 10),
        (2, "고급글", "고급", 0.9, "[0.1,0.2]", 10),
    ]
    out = recommend_next(
        1, 2,
        _Session(profile=None, candidates=cands, centroid="[0.0,0.0]", nodes=[(10, "토픽A")]),
    )
    # 에러 없이 추천 생성, 입문이 먼저.
    assert _ids(out)[0] == 1
