"""HIVE-43 스케줄러 단위 테스트.

apscheduler 실제 가동 없이, start_scheduler가 github/reddit/velog 잡을
idempotent 패턴(get_job 가드 + max_instances/coalesce/replace_existing)으로
등록하는지 가짜 스케줄러로 검증한다.
"""
import app.crawler.scheduler as scheduler


class _FakeScheduler:
    """add_job 호출을 캡처하는 가짜 BackgroundScheduler."""

    def __init__(self, *args, **kwargs):
        self.jobs: dict[str, dict] = {}
        self.running = False
        self.started = False

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def add_job(self, func, *, trigger, id, **kwargs):
        self.jobs[id] = {"func": func, "trigger": trigger, **kwargs}

    def start(self):
        self.running = True
        self.started = True


def _patch_fake(monkeypatch):
    """apscheduler.import + 모듈 전역 _scheduler를 가짜로 교체."""
    import apscheduler.schedulers.background as bg

    monkeypatch.setattr(bg, "BackgroundScheduler", _FakeScheduler)
    monkeypatch.setattr(scheduler, "_scheduler", None)


def test_start_scheduler_registers_all_three_jobs(monkeypatch):
    _patch_fake(monkeypatch)
    sch = scheduler.start_scheduler()

    assert set(sch.jobs) == {"github_12h", "reddit_24h", "velog_24h"}
    assert sch.started is True


def test_velog_job_registered_with_idempotent_pattern(monkeypatch):
    _patch_fake(monkeypatch)
    sch = scheduler.start_scheduler()

    velog = sch.jobs["velog_24h"]
    assert velog["func"] is scheduler.run_velog_job
    assert velog["trigger"] == "interval"
    assert velog["hours"] == 24
    assert velog["max_instances"] == 1
    assert velog["coalesce"] is True
    assert velog["replace_existing"] is True


def test_start_scheduler_idempotent_no_duplicate_jobs(monkeypatch):
    _patch_fake(monkeypatch)
    sch1 = scheduler.start_scheduler()
    # 두 번째 호출은 같은 스케줄러를 재사용하고 잡을 중복 등록하지 않는다.
    sch2 = scheduler.start_scheduler()

    assert sch1 is sch2
    assert set(sch2.jobs) == {"github_12h", "reddit_24h", "velog_24h"}


def test_run_velog_job_runs_pipeline_with_crawl_velog(monkeypatch):
    captured = {}

    def fake_run_pipeline(crawl_func):
        captured["crawl_func"] = crawl_func
        return "saved.json"

    monkeypatch.setattr(scheduler, "run_pipeline", fake_run_pipeline)
    scheduler.run_velog_job()

    assert captured["crawl_func"] is scheduler.crawl_velog
