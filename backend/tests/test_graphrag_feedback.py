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
        precedes=None,
        current_level="입문",
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
        # precedes 엣지: [(source_node_id, target_node_id, weight)]. 기본 빈 → path 중립.
        self._precedes = precedes or []
        self._current_level = current_level

    def execute(self, clause, params=None):
        sql = str(clause)
        params = params or {}
        if "profile_vector::text AS pv" in sql:
            return _Result(rows=[SimpleNamespace(pv=self._profile, current_level=self._current_level)])
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
                    published_at=None,  # 테스트 기본값: recency 중립(0.5)
                )
                for cid, title, diff, q, emb, nid in self._candidates
            ])
        if "FROM node_links" in sql:
            return _Result(rows=[
                SimpleNamespace(source_node_id=s, target_node_id=t, weight=w)
                for s, t, w in self._precedes
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


# ── HIVE-60: node_id=None 다양성 페널티 버그 ──────────────────────────

def test_node_id_none_no_mutual_diversity_penalty(monkeypatch):
    """node_id=None 콘텐츠 2건이 서로 다양성 페널티를 주지 않는다.

    버그 시: A 선택 후 node_count[None]=1 → B div=0.5, C(node_id=10) div=1.0 → C가 B보다 먼저 선택.
    수정 후: A 선택 후 B div=1.0, C div=1.0 → 동점, 입력 순서 유지 → B가 C보다 먼저 선택.
    """
    _no_llm(monkeypatch)
    cands = [
        (1, "A", "입문", 0.9, "[0.0,0.0]", None),
        (2, "B", "입문", 0.9, "[0.0,0.0]", None),
        (3, "C", "입문", 0.9, "[0.0,0.0]", 10),
    ]
    out = recommend_next(
        1, 3,
        _Session(profile=None, candidates=cands, centroid="[0.0,0.0]"),
    )
    ids = _ids(out)
    assert ids[0] == 1           # A는 항상 1위
    assert ids[1] == 2           # 버그 시 C(3)가 나옴 — 수정 후 B(2)


def test_node_id_none_does_not_affect_node_id_diversity(monkeypatch):
    """node_id 보유 콘텐츠의 다양성 페널티 로직은 영향받지 않는다."""
    _no_llm(monkeypatch)
    # 노드 10에서 2건: 두 번째 선택 시 div=0.5 페널티 정상 적용 확인.
    cands = [
        (1, "X", "입문", 0.9, "[0.0,0.0]", 10),
        (2, "Y", "입문", 0.9, "[0.0,0.0]", 10),
        (3, "Z", "입문", 0.9, "[0.0,0.0]", 20),
    ]
    out = recommend_next(
        1, 3,
        _Session(profile=None, candidates=cands, centroid="[0.0,0.0]"),
    )
    ids = _ids(out)
    assert ids[0] == 1           # X 먼저
    # X 선택 후 node_count[10]=1 → Y div=0.5, Z div=1.0 → Z가 Y보다 우선(다양성 의도)
    assert ids[1] == 3           # 다른 노드(Z)가 같은 노드(Y)보다 앞


# ── HIVE-87: precedes 경로 점수가 추천 순서를 바꾼다 ──────────────────

def test_precedes_unlearned_prereq_flips_ranking(monkeypatch):
    """선행 미학습 시 후보의 경로점수가 떨어져 추천 순서가 뒤집힌다.

    A=node1(루트,선행없음→path 0.5), B=node2(선행=node1). mastery 전부 0.
    precedes 없을 때: 품질 우위로 B가 1위([2,1]).
    precedes=[node1→node2] 추가: node1 미학습 → B path 0.0 → B 점수 하락 → A가 1위([1,2]).
    경로 성분이 실제 랭킹에 반영됨을 증명(빈 데이터면 기존 동작 보존은 다른 테스트가 커버).
    """
    _no_llm(monkeypatch)
    nodes = [(1, "프롬프트"), (2, "Agentic")]
    cands = [
        (1, "A", None, 0.50, "[0.0,0.0]", 1),   # 루트 노드
        (2, "B", None, 0.55, "[0.0,0.0]", 2),   # 품질 약간 우위
    ]
    base = dict(profile=None, candidates=cands, centroid="[0.0,0.0]", nodes=nodes)

    out_no = recommend_next(1, 2, _Session(**base))
    out_pre = recommend_next(1, 2, _Session(**base, precedes=[(1, 2, 1.0)]))

    assert _ids(out_no) == [2, 1]    # precedes 없으면 품질 우위 B 먼저
    assert _ids(out_pre) == [1, 2]   # 선행 미학습으로 B 강등 → A 먼저 (순서 역전)


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


# ── HIVE-106: 레벨별 신선도 가중치 ────────────────────────────────────────

def test_recency_boosts_intermediate_not_beginner(monkeypatch):
    """중급 유저는 최신 글에 가중치, 초급 유저는 가중치 없음."""
    _no_llm(monkeypatch)
    from datetime import datetime, timezone, timedelta
    import app.recommend.graphrag as gr_mod

    recent = datetime.now(timezone.utc) - timedelta(days=1)   # 어제 발행 → 신선도 높음
    old    = datetime.now(timezone.utc) - timedelta(days=365)  # 1년 전 발행 → 신선도 낮음

    # A(최신, quality 낮음) vs B(오래됨, quality 높음).
    # 초급: recency 없음 → quality 우위 B(id=2) 먼저.
    # 중급: recency 보너스 → 최신 A(id=1)가 quality 격차를 뒤집고 먼저.
    cands_ns = [
        SimpleNamespace(id=1, title="최신글", difficulty="중급", quality_score=0.45,
                        emb="[0.0,0.0]", node_id=10, published_at=recent),
        SimpleNamespace(id=2, title="구글",   difficulty="중급", quality_score=0.55,
                        emb="[0.0,0.0]", node_id=10, published_at=old),
    ]

    class _PatchedSession(_Session):
        def execute(self, clause, params=None):
            sql = str(clause)
            if "ORDER BY m.relevance_score DESC LIMIT 1) AS node_id" in sql and "FROM content c" in sql:
                return _Result(rows=cands_ns)
            return super().execute(clause, params)

    # profile=None: rel_real=False → rel=quality_score 폴백. quality 차이가 선명하게 드러남.
    base = dict(profile=None, centroid="[0.0,0.0]", nodes=[(10, "토픽A")])

    out_mid   = recommend_next(1, 2, _PatchedSession(**base, current_level="중급"))
    out_begin = recommend_next(1, 2, _PatchedSession(**base, current_level="입문"))

    assert _ids(out_mid)[0] == 1,   "중급: recency 보너스로 최신 글이 quality 격차 역전"
    assert _ids(out_begin)[0] == 2, "초급: recency 없으므로 quality 우위 구글이 먼저"
