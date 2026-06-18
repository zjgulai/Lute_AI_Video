from __future__ import annotations

import asyncio
import contextlib
import importlib
from datetime import UTC, datetime, timedelta

import httpx
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


class _FakeHttpClient:
    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []

    async def post(self, url: str, **kwargs) -> httpx.Response:
        self.requests.append({"url": url, **kwargs})
        if not self.responses:
            raise AssertionError("unexpected HTTP call")
        return self.responses.pop(0)


def _json_response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request("POST", "https://example.test/metrics"),
    )


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
async def test_default_platform_connector_auth_failure_does_not_save(monkeypatch) -> None:
    from src.tasks.metrics_poller import MetricsPoller

    monkeypatch.delenv("TIKTOK_ACCESS_TOKEN", raising=False)
    repo = _SaveRepo()
    poller = MetricsPoller(repo=repo)

    result = await poller.pull_single(
        {
            "id": "row-real-blocked",
            "video_id": "video-real-blocked",
            "scenario": "S2",
            "platform": "tiktok",
            "tenant_id": "momcozy-marketing",
            "post_id": "tt_real_blocked",
            "published_at": datetime.now(UTC) - timedelta(hours=3),
            "pulled_at": None,
        }
    )

    assert result is False
    assert repo.saved == []


@pytest.mark.asyncio
async def test_not_implemented_platform_error_does_not_save() -> None:
    from src.tasks.metrics_poller import MetricsPoller, PlatformMetricsError

    repo = _SaveRepo()

    async def fetch_tiktok(post_id: str) -> dict:
        raise PlatformMetricsError("not_implemented", f"{post_id} not ready")

    poller = MetricsPoller(repo=repo, platform_fetchers={"tiktok": fetch_tiktok})

    result = await poller.pull_single(
        {
            "id": "row-not-implemented",
            "video_id": "video-not-implemented",
            "scenario": "S2",
            "platform": "tiktok",
            "tenant_id": "momcozy-marketing",
            "post_id": "tt_not_implemented",
            "published_at": datetime.now(UTC) - timedelta(hours=3),
            "pulled_at": None,
        }
    )

    assert result is False
    assert repo.saved == []


@pytest.mark.asyncio
async def test_empty_metrics_payload_does_not_save() -> None:
    from src.tasks.metrics_poller import MetricsPoller

    repo = _SaveRepo()

    async def fetch_tiktok(post_id: str) -> dict:
        return {}

    poller = MetricsPoller(repo=repo, platform_fetchers={"tiktok": fetch_tiktok})

    result = await poller.pull_single(
        {
            "id": "row-empty-payload",
            "video_id": "video-empty-payload",
            "scenario": "S2",
            "platform": "tiktok",
            "tenant_id": "momcozy-marketing",
            "post_id": "tt_empty",
            "published_at": datetime.now(UTC) - timedelta(hours=3),
            "pulled_at": None,
        }
    )

    assert result is False
    assert repo.saved == []


@pytest.mark.asyncio
async def test_unrecognized_metrics_payload_does_not_save() -> None:
    from src.tasks.metrics_poller import MetricsPoller

    repo = _SaveRepo()

    async def fetch_tiktok(post_id: str) -> dict:
        return {"unrecognized": 1}

    poller = MetricsPoller(repo=repo, platform_fetchers={"tiktok": fetch_tiktok})

    result = await poller.pull_single(
        {
            "id": "row-unrecognized-payload",
            "video_id": "video-unrecognized-payload",
            "scenario": "S2",
            "platform": "tiktok",
            "tenant_id": "momcozy-marketing",
            "post_id": "tt_unrecognized",
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


def test_platform_http_status_classification() -> None:
    from src.tasks.metrics_poller import classify_platform_http_status

    assert classify_platform_http_status(401) == "auth"
    assert classify_platform_http_status(403) == "auth"
    assert classify_platform_http_status(429) == "rate_limit"
    assert classify_platform_http_status(404) == "not_found"
    assert classify_platform_http_status(502) == "transient"
    assert classify_platform_http_status(418) == "schema_drift"


@pytest.mark.asyncio
async def test_tiktok_fetch_metrics_maps_official_video_query(monkeypatch) -> None:
    from src.connectors.tiktok_connector import TikTokConnector

    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "test-token")
    fake = _FakeHttpClient(
        _json_response(
            200,
            {
                "data": {
                    "videos": [
                        {
                            "id": "tt_123",
                            "view_count": 1200,
                            "like_count": 80,
                            "comment_count": 12,
                            "share_count": 5,
                        }
                    ]
                },
                "error": {"code": "ok", "message": ""},
            },
        )
    )

    metrics = await TikTokConnector(http_client=fake).fetch_metrics("tt_123")

    assert metrics == {
        "views": 1200,
        "likes": 80,
        "comments": 12,
        "shares": 5,
    }
    assert fake.requests[0]["url"].endswith("/v2/video/query/")
    assert "view_count" in fake.requests[0]["params"]["fields"]
    assert fake.requests[0]["json"] == {"filters": {"video_ids": ["tt_123"]}}


@pytest.mark.asyncio
async def test_tiktok_fetch_metrics_classifies_rate_limit(monkeypatch) -> None:
    from src.connectors.tiktok_connector import TikTokConnector
    from src.tasks.metrics_poller import PlatformMetricsError

    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "test-token")
    fake = _FakeHttpClient(_json_response(429, {"error": {"code": "rate_limit"}}))

    with pytest.raises(PlatformMetricsError) as excinfo:
        await TikTokConnector(http_client=fake).fetch_metrics("tt_123")

    assert excinfo.value.category == "rate_limit"


@pytest.mark.asyncio
async def test_tiktok_fetch_metrics_empty_videos_is_not_found(monkeypatch) -> None:
    from src.connectors.tiktok_connector import TikTokConnector
    from src.tasks.metrics_poller import PlatformMetricsError

    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "test-token")
    fake = _FakeHttpClient(
        _json_response(200, {"data": {"videos": []}, "error": {"code": "ok"}})
    )

    with pytest.raises(PlatformMetricsError) as excinfo:
        await TikTokConnector(http_client=fake).fetch_metrics("tt_missing")

    assert excinfo.value.category == "not_found"


@pytest.mark.asyncio
async def test_tiktok_fetch_metrics_api_error_is_transient(monkeypatch) -> None:
    from src.connectors.tiktok_connector import TikTokConnector
    from src.tasks.metrics_poller import PlatformMetricsError

    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "test-token")
    fake = _FakeHttpClient(
        _json_response(
            200,
            {
                "data": {},
                "error": {"code": "internal_error", "message": "try later"},
            },
        )
    )

    with pytest.raises(PlatformMetricsError) as excinfo:
        await TikTokConnector(http_client=fake).fetch_metrics("tt_123")

    assert excinfo.value.category == "transient"


@pytest.mark.asyncio
async def test_shopify_fetch_metrics_maps_shopifyql_table(monkeypatch) -> None:
    from src.connectors.shopify_connector import ShopifyConnector

    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "shopify-token")
    monkeypatch.setenv("SHOPIFY_STORE_URL", "example.myshopify.com")
    fake = _FakeHttpClient(
        _json_response(
            200,
            {
                "data": {
                    "shopifyqlQuery": {
                        "tableData": {
                            "columns": [
                                {"name": "total_sales"},
                                {"name": "orders"},
                                {"name": "sessions"},
                            ],
                            "rows": [[125.5, 4, 200]],
                        },
                        "parseErrors": [],
                    }
                }
            },
        )
    )

    metrics = await ShopifyConnector(http_client=fake).fetch_metrics("gid://post/1")

    assert metrics == {
        "revenue": 125.5,
        "orders": 4,
        "sales": 4,
        "views": 200,
        "cvr": 0.02,
    }
    assert fake.requests[0]["url"] == (
        "https://example.myshopify.com/admin/api/2024-07/graphql.json"
    )
    assert fake.requests[0]["headers"]["X-Shopify-Access-Token"] == "shopify-token"
    assert "shopifyqlQuery" in fake.requests[0]["json"]["query"]
    assert fake.requests[0]["json"]["variables"]["query"] == (
        "FROM sales SHOW total_sales, orders SINCE -30d"
    )


@pytest.mark.asyncio
async def test_shopify_fetch_metrics_parse_errors_are_schema_drift(monkeypatch) -> None:
    from src.connectors.shopify_connector import ShopifyConnector
    from src.tasks.metrics_poller import PlatformMetricsError

    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "shopify-token")
    monkeypatch.setenv("SHOPIFY_STORE_URL", "example.myshopify.com")
    fake = _FakeHttpClient(
        _json_response(
            200,
            {
                "data": {
                    "shopifyqlQuery": {
                        "tableData": {"columns": [], "rows": []},
                        "parseErrors": [{"message": "Unknown metric"}],
                    }
                }
            },
        )
    )

    with pytest.raises(PlatformMetricsError) as excinfo:
        await ShopifyConnector(http_client=fake).fetch_metrics("shopify-post")

    assert excinfo.value.category == "schema_drift"


@pytest.mark.asyncio
async def test_shopify_fetch_metrics_graphql_access_error_is_auth(monkeypatch) -> None:
    from src.connectors.shopify_connector import ShopifyConnector
    from src.tasks.metrics_poller import PlatformMetricsError

    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "shopify-token")
    monkeypatch.setenv("SHOPIFY_STORE_URL", "example.myshopify.com")
    fake = _FakeHttpClient(
        _json_response(200, {"errors": [{"message": "Access denied for reports"}]})
    )

    with pytest.raises(PlatformMetricsError) as excinfo:
        await ShopifyConnector(http_client=fake).fetch_metrics("shopify-post")

    assert excinfo.value.category == "auth"


@pytest.mark.asyncio
async def test_shopify_fetch_metrics_graphql_not_found(monkeypatch) -> None:
    from src.connectors.shopify_connector import ShopifyConnector
    from src.tasks.metrics_poller import PlatformMetricsError

    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "shopify-token")
    monkeypatch.setenv("SHOPIFY_STORE_URL", "example.myshopify.com")
    fake = _FakeHttpClient(
        _json_response(200, {"errors": [{"message": "Report not found"}]})
    )

    with pytest.raises(PlatformMetricsError) as excinfo:
        await ShopifyConnector(http_client=fake).fetch_metrics("shopify-post")

    assert excinfo.value.category == "not_found"


@pytest.mark.asyncio
async def test_dry_run_due_posts_blocks_when_no_active_posts() -> None:
    from src.tasks.metrics_poller import MetricsPoller

    repo = _SaveRepo(posts=[])
    poller = MetricsPoller(repo=repo, platform_fetchers={"tiktok": lambda _: {}})

    readiness = await poller.dry_run_due_posts()

    assert readiness["readiness"] == "blocked_by_no_active_post"
    assert readiness["active_post_count"] == 0
    assert readiness["due_post_count"] == 0
    assert readiness["candidates"] == []


@pytest.mark.asyncio
async def test_dry_run_due_posts_blocks_when_allowlist_has_no_candidate() -> None:
    from src.tasks.metrics_poller import MetricsPoller

    repo = _SaveRepo(
        posts=[
            {
                "id": "row-due",
                "video_id": "video-due",
                "scenario": "S2",
                "platform": "tiktok",
                "tenant_id": "momcozy-marketing",
                "post_id": "tt_due",
                "published_at": datetime.now(UTC) - timedelta(hours=3),
                "pulled_at": None,
            }
        ]
    )
    poller = MetricsPoller(repo=repo, platform_fetchers={"tiktok": lambda _: {}})

    readiness = await poller.dry_run_due_posts(allowlisted_post_ids={"tt_other"})

    assert readiness["readiness"] == "blocked_by_no_allowlisted_active_post"
    assert readiness["active_post_count"] == 1
    assert readiness["due_post_count"] == 1
    assert readiness["allowlisted_due_post_count"] == 0
    assert readiness["skipped"] == {"not_allowlisted": 1}


@pytest.mark.asyncio
async def test_dry_run_due_posts_returns_allowlisted_candidate() -> None:
    from src.tasks.metrics_poller import MetricsPoller

    repo = _SaveRepo(
        posts=[
            {
                "id": "row-due",
                "video_id": "video-due",
                "scenario": "S2",
                "platform": "tiktok",
                "tenant_id": "momcozy-marketing",
                "post_id": "tt_due",
                "published_at": datetime.now(UTC) - timedelta(hours=3),
                "pulled_at": None,
            }
        ]
    )
    poller = MetricsPoller(repo=repo, platform_fetchers={"tiktok": lambda _: {}})

    readiness = await poller.dry_run_due_posts(allowlisted_post_ids={"tt_due"})

    assert readiness["readiness"] == "ready_for_single_post_pilot"
    assert readiness["allowlisted_due_post_count"] == 1
    assert readiness["candidates"][0]["post_id"] == "tt_due"
    assert readiness["candidates"][0]["_dry_run"]["reason"] == "due"


def test_shopify_access_token_falls_back_to_legacy_api_key(monkeypatch) -> None:
    import src.config as config

    with monkeypatch.context() as m:
        m.delenv("SHOPIFY_ACCESS_TOKEN", raising=False)
        m.setenv("SHOPIFY_API_KEY", "legacy-shopify-key")
        m.setenv("SHOPIFY_STORE_URL", "example.myshopify.com")

        reloaded = importlib.reload(config)

        assert reloaded.SHOPIFY_API_KEY == "legacy-shopify-key"
        assert reloaded.SHOPIFY_ACCESS_TOKEN == "legacy-shopify-key"
        assert reloaded.SHOPIFY_STORE_URL == "example.myshopify.com"

    importlib.reload(config)


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
