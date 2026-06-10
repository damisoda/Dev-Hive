"""HIVE-43 run_crawler 단위 테스트.

- load_existing_urls_from_db: 가짜 엔진에서 URL 조회 / DB 부재·쿼리 실패 시 빈 집합(no raise).
- run_pipeline: 로컬 raw + DB URL 합집합으로 거름 / 키 부재 시 적재 스킵(no crash).
네트워크·실DB 없음(가짜/모킹).
"""
import app.crawler.run_crawler as rc


def _item(url, **kw):
    base = {"url": url, "title": "t", "body": "b", "source": "velog"}
    base.update(kw)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# load_existing_urls_from_db
# ─────────────────────────────────────────────────────────────────────────────


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **kw):
        class _R:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

        return _R(self._rows)


class _FakeEngine:
    """sqlalchemy.engine.Engine로 isinstance 통과시키기 위해 동적으로 클래스를 바꾼다."""

    def __init__(self, rows, raise_on_connect=False):
        self._rows = rows
        self._raise = raise_on_connect

    def connect(self):
        if self._raise:
            raise RuntimeError("boom")
        return _FakeConn(self._rows)


def _engine_with(rows, raise_on_connect=False):
    # isinstance(engine_or_url, Engine) 분기를 타도록 Engine 등록.
    from sqlalchemy.engine import Engine

    eng = _FakeEngine(rows, raise_on_connect)
    eng.__class__ = type("FakeEngine", (_FakeEngine, Engine), {})
    return eng


def test_load_existing_urls_from_db_returns_urls():
    eng = _engine_with([("https://a.com",), ("https://b.com",), (None,)])
    urls = rc.load_existing_urls_from_db(eng)
    assert urls == {"https://a.com", "https://b.com"}


def test_load_existing_urls_from_db_empty_when_no_db_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert rc.load_existing_urls_from_db(None) == set()


def test_load_existing_urls_from_db_empty_on_query_failure():
    eng = _engine_with([], raise_on_connect=True)
    # 쿼리 실패해도 raise하지 않고 빈 집합.
    assert rc.load_existing_urls_from_db(eng) == set()


# ─────────────────────────────────────────────────────────────────────────────
# URL 정규화 dedup (트레일링 슬래시/대소문자/fragment 변형 = 같은 URL → 재태깅 비용 누수 방지)
# ─────────────────────────────────────────────────────────────────────────────


def test_normalize_url_variants_collapse():
    base = rc._normalize_url("https://a.com/post")
    assert rc._normalize_url("https://A.com/post/") == base       # 대소문자 + 끝 슬래시
    assert rc._normalize_url("https://a.com/post#section") == base  # fragment
    assert rc._normalize_url("HTTPS://a.com/post") == base          # 스킴 대문자
    # 쿼리는 보존(서로 다른 페이지일 수 있음)
    assert rc._normalize_url("https://a.com/post?id=2") != base


def test_filter_existing_urls_treats_variants_as_duplicate():
    existing = {rc._normalize_url("https://a.com/post")}
    crawled = [_item("https://A.com/post/"), _item("https://b.com/new")]
    kept = rc.filter_existing_urls(crawled, existing)
    assert {i["url"] for i in kept} == {"https://b.com/new"}  # 변형은 걸러짐


# ─────────────────────────────────────────────────────────────────────────────
# run_pipeline 필터링
# ─────────────────────────────────────────────────────────────────────────────


def test_run_pipeline_filters_db_and_raw_urls(monkeypatch, tmp_path):
    crawled = [
        _item("https://new.com"),
        _item("https://in-db.com"),
        _item("https://in-raw.com"),
        _item("https://new.com"),  # 배치 내 중복
    ]
    monkeypatch.setattr(rc, "load_existing_urls", lambda *a, **k: {"https://in-raw.com"})
    monkeypatch.setattr(rc, "load_existing_urls_from_db", lambda *a, **k: {"https://in-db.com"})

    saved = {}

    def fake_save_json(items, *a, **k):
        saved["items"] = items
        p = tmp_path / "_x.json"
        p.write_text("[]")
        return p

    monkeypatch.setattr(rc, "save_json", fake_save_json)
    monkeypatch.setattr(rc, "upload_to_drive", lambda p: None)
    monkeypatch.setattr(rc, "_maybe_ingest", lambda items: None)

    rc.run_pipeline(crawl_func=lambda: crawled)

    urls = {i["url"] for i in saved["items"]}
    assert urls == {"https://new.com"}
    assert len(saved["items"]) == 1  # 중복 제거됨


def test_run_pipeline_returns_none_when_all_filtered(monkeypatch):
    crawled = [_item("https://dup.com")]
    monkeypatch.setattr(rc, "load_existing_urls", lambda *a, **k: set())
    monkeypatch.setattr(rc, "load_existing_urls_from_db", lambda *a, **k: {"https://dup.com"})
    called = {"save": False, "ingest": False}
    monkeypatch.setattr(rc, "save_json", lambda *a, **k: called.__setitem__("save", True))
    monkeypatch.setattr(rc, "_maybe_ingest", lambda items: called.__setitem__("ingest", True))

    assert rc.run_pipeline(crawl_func=lambda: crawled) is None
    assert called == {"save": False, "ingest": False}


# ─────────────────────────────────────────────────────────────────────────────
# 적재 게이팅(_maybe_ingest)
# ─────────────────────────────────────────────────────────────────────────────


def test_maybe_ingest_skips_when_keys_absent(monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("INGEST_AFTER_CRAWL", raising=False)
    # 키 부재 → ingest_items가 절대 호출되면 안 되고, 예외도 없어야 한다.
    rc._maybe_ingest([_item("https://x.com")])  # no raise


def test_maybe_ingest_skips_when_flag_off(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("INGEST_AFTER_CRAWL", "off")
    import app.tagging.ingest as ing

    called = {"n": 0}
    monkeypatch.setattr(ing, "ingest_items", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    rc._maybe_ingest([_item("https://x.com")])
    assert called["n"] == 0


def test_run_pipeline_does_not_crash_when_ingest_keys_absent(monkeypatch, tmp_path):
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("INGEST_AFTER_CRAWL", raising=False)
    monkeypatch.setattr(rc, "load_existing_urls", lambda *a, **k: set())
    monkeypatch.setattr(rc, "load_existing_urls_from_db", lambda *a, **k: set())

    def fake_save_json(items, *a, **k):
        p = tmp_path / "_x.json"
        p.write_text("[]")
        return p

    monkeypatch.setattr(rc, "save_json", fake_save_json)
    monkeypatch.setattr(rc, "upload_to_drive", lambda p: None)

    # 실제 _maybe_ingest 경로를 타되 키가 없어 스킵 → crash 없음.
    out = rc.run_pipeline(crawl_func=lambda: [_item("https://x.com")])
    assert out is not None


class _DisposableEngine:
    """create_engine 대체용 가짜 엔진 — dispose() 호출 여부를 추적한다(풀 누수 수정 검증)."""

    def __init__(self):
        self.disposed = False

    def dispose(self):
        self.disposed = True


def test_maybe_ingest_default_on_when_flag_unset(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.delenv("INGEST_AFTER_CRAWL", raising=False)

    import app.tagging.ingest as ing

    calls = {"n": 0}

    def fake_ingest(items, ac, oc, eng, **kw):
        calls["n"] += 1
        return {"inserted": 1, "skipped_quality": 0, "skipped_dup": 0,
                "tag_failed": 0, "load_failed": 0, "qc_report": {}}

    monkeypatch.setattr(ing, "ingest_items", fake_ingest)
    # anthropic/openai/create_engine 생성도 가짜로(네트워크 없음).
    import anthropic
    import openai
    import sqlalchemy
    eng = _DisposableEngine()
    monkeypatch.setattr(anthropic, "Anthropic", lambda **k: object())
    monkeypatch.setattr(openai, "OpenAI", lambda **k: object())
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda url: eng)

    rc._maybe_ingest([_item("https://x.com")])
    assert calls["n"] == 1
    assert eng.disposed is True  # 정상 경로에서도 엔진 정리


def test_maybe_ingest_never_crashes_on_ingest_failure(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.delenv("INGEST_AFTER_CRAWL", raising=False)

    import app.tagging.ingest as ing

    def boom(*a, **k):
        raise RuntimeError("ingest exploded")

    monkeypatch.setattr(ing, "ingest_items", boom)
    import anthropic
    import openai
    import sqlalchemy
    eng = _DisposableEngine()
    monkeypatch.setattr(anthropic, "Anthropic", lambda **k: object())
    monkeypatch.setattr(openai, "OpenAI", lambda **k: object())
    monkeypatch.setattr(sqlalchemy, "create_engine", lambda url: eng)

    # 적재가 터져도 _maybe_ingest는 삼키고 끝난다.
    rc._maybe_ingest([_item("https://x.com")])  # no raise
    assert eng.disposed is True  # 실패 경로에서도 엔진 정리(누수 방지)
