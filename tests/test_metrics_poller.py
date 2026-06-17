from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

import pytest


class _Repo:
    async def get_active_posts(self) -> list[dict]:
        return [{"id": str(i)} for i in range(6)]


class _SaveRepo:
    def __init__(self, posts: list[dict] | None = None) -> None:
        self.posts = posts or []
        self.saved: list[dict] = []

    async def get_active_posts(self) -> list[dict]:
        return self.posts

    async def save_metrics(self, **kwargs) -> dict:
        self.saved.append(kwargs)
        return kwargs


@pytest.mark.asyncio
async def test_pull_all_uses_bounded_concurrency() -> None:
    from src.tasks.metrics_poller import MetricsPoller

    poller = MetricsPoller(max_concurrency=2)
    poller.repo = _Repo()  # type: ignore[assignment]

    active = 0
    max_active = 0

    async def fake_pull_single(post: dict) -> bool:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return True

    poller.pull_single = fake_pull_single  # type: ignore[method-assign]

    await poller.pull_all()

    assert max_active == 2


@pytest.mark.asyncio
async def test_pull_all_isolates_single_task_failure() -> None:
    from src.tasks.metrics_poller import MetricsPoller

    poller = MetricsPoller(max_concurrency=3)
    poller.repo = _Repo()  # type: ignore[assignment]
    seen: list[str] = []

    async def fake_pull_single(post: dict) -> bool:
        seen.append(post["id"])
        if post["id"] == "2":
            raise RuntimeError("platform error")
        return post["id"] != "3"

    poller.pull_single = fake_pull_single  # type: ignore[method-assign]

    await poller.pull_all()

    assert sorted(seen) == ["0", "1", "2", "3", "4", "5"]


@pytest.mark.asyncio
async def test_pull_single_uses_injected_platform_fetcher_and_saves_metrics() -> None:
    from src.tasks.metrics_poller import MetricsPoller

    repo = _SaveRepo()
    calls: list[str] = []

    async def fetch_tiktok(post_id: str) -> dict:
        calls.append(post_id)
        return {
            "views": 1200,
            "watch_rate": 0.68,
            "ctr": 0.09,
            "cvr": 0.03,
            "followers_gained": 7,
            "sales": 4,
        }

    poller = MetricsPoller(repo=repo, platform_fetchers={"tiktok": fetch_tiktok})

    result = await poller.pull_single(
        {
            "id": "row-1",
            "video_id": "video-1",
            "scenario": "S2",
            "platform": "TikTok",
            "tenant_id": "momcozy-marketing",
            "post_id": "tt_123",
            "post_url": "https://www.tiktok.com/@momcozy/video/tt_123",
            "published_at": datetime.now(UTC) - timedelta(hours=3),
            "pulled_at": None,
        }
    )

    assert result is True
    assert calls == ["tt_123"]
    assert repo.saved == [
        {
            "video_id": "video-1",
            "scenario": "S2",
            "platform": "TikTok",
            "tenant_id": "momcozy-marketing",
            "post_id": "tt_123",
            "post_url": "https://www.tiktok.com/@momcozy/video/tt_123",
            "metrics_dict": {
                "views": 1200,
                "watch_rate": 0.68,
                "ctr": 0.09,
                "cvr": 0.03,
                "followers_gained": 7,
                "sales": 4,
            },
        }
    ]


@pytest.mark.asyncio
async def test_pull_single_skips_unknown_platform_without_saving() -> None:
    from src.tasks.metrics_poller import MetricsPoller

    repo = _SaveRepo()
    poller = MetricsPoller(repo=repo, platform_fetchers={})

    result = await poller.pull_single(
        {
            "id": "row-unknown",
            "video_id": "video-unknown",
            "scenario": "S2",
            "platform": "unknown-platform",
            "tenant_id": "momcozy-marketing",
            "post_id": "unknown_123",
            "published_at": datetime.now(UTC) - timedelta(hours=3),
            "pulled_at": None,
        }
    )

    assert result is False
    assert repo.saved == []


@pytest.mark.asyncio
async def test_pull_single_skips_recent_snapshot_without_fetching() -> None:
    from src.tasks.metrics_poller import MetricsPoller

    repo = _SaveRepo()
    calls = 0

    async def fetch_tiktok(post_id: str) -> dict:
        nonlocal calls
        calls += 1
        return {"views": 1}

    poller = MetricsPoller(repo=repo, platform_fetchers={"tiktok": fetch_tiktok})

    result = await poller.pull_single(
        {
            "id": "row-recent",
            "video_id": "video-recent",
            "scenario": "S2",
            "platform": "tiktok",
            "tenant_id": "momcozy-marketing",
            "post_id": "tt_recent",
            "published_at": datetime.now(UTC) - timedelta(hours=3),
            "pulled_at": datetime.now(UTC) - timedelta(minutes=20),
        }
    )

    assert result is False
    assert calls == 0
    assert repo.saved == []


@pytest.fixture
def isolated_video_metrics_db(tmp_path, monkeypatch):
    from src.storage import db as db_module

    db_path = tmp_path / "metrics.db"
    db_module._sqlite_conn = None

    def _init_at_test_path():
        import sqlite3

        db_module._sqlite_conn = sqlite3.connect(str(db_path))
        db_module._sqlite_conn.row_factory = sqlite3.Row
        db_module._create_sqlite_tables()

    async def _no_pool():
        return None

    monkeypatch.setattr(db_module, "_init_sqlite", _init_at_test_path)
    monkeypatch.setattr(db_module, "get_pool", _no_pool)
    monkeypatch.setattr(db_module, "is_pg_available", lambda: False)

    import src.storage.metrics_repository as mr_module

    monkeypatch.setattr(mr_module, "get_pool", _no_pool)

    _init_at_test_path()
    yield

    if db_module._sqlite_conn is not None:
        with contextlib.suppress(Exception):
            db_module._sqlite_conn.close()
        db_module._sqlite_conn = None


@pytest.mark.asyncio
async def test_pull_all_ingests_fake_platform_metrics_into_dashboard(
    isolated_video_metrics_db,
) -> None:
    from src.storage import db as db_module
    from src.storage.metrics_repository import VideoMetricsRepository
    from src.tasks.metrics_poller import MetricsPoller

    repo = VideoMetricsRepository()
    await repo.save_metrics(
        video_id="video-p2-1l",
        scenario="S2",
        platform="tiktok",
        tenant_id="momcozy-marketing",
        post_id="tt_p2_1l",
        post_url="https://www.tiktok.com/@momcozy/video/tt_p2_1l",
        metrics_dict={"views": 10, "watch_rate": 0.1},
    )

    old_ts = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=3)
    conn = db_module.get_sqlite_conn()
    assert conn is not None
    conn.execute(
        "UPDATE video_metrics SET pulled_at = ?, published_at = ? WHERE video_id = ?",
        (old_ts, old_ts, "video-p2-1l"),
    )
    conn.commit()

    async def fetch_tiktok(post_id: str) -> dict:
        assert post_id == "tt_p2_1l"
        return {
            "title": "S2 bounded metrics fixture",
            "views": 3210,
            "watch_rate": 0.74,
            "ctr": 0.11,
            "cvr": 0.04,
            "followers_gained": 12,
            "sales": 5,
        }

    poller = MetricsPoller(repo=repo, platform_fetchers={"tiktok": fetch_tiktok})
    await poller.pull_all()

    overview = await repo.get_dashboard_overview(tenant_id="momcozy-marketing")
    row = next(item for item in overview if item["video_id"] == "video-p2-1l")
    assert row["metrics"]["views"] == 3210
    assert row["metrics"]["watch_rate"] == 0.74
    assert row["tenant_id"] == "momcozy-marketing"
