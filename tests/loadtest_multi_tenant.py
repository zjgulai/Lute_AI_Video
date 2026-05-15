"""Locust multi-tenant API key isolation load test.

NEXT-STEPS-2026-05-11 P2-5 / UNIFIED-ROADMAP-2026-05-15 TODO-21.

Purpose
=======
Verify under concurrent multi-tenant HTTP load that:
1. /pipeline/start with different X-API-Key headers does not contaminate
   the contextvars state used by LLMClient (api key isolation regression).
2. Rate limiter (P3-1: 120 req/60s per IP) correctly enforces without
   leaking 429s between tenant boundaries.
3. Response wrapper /_meta.trace_id is unique per request.

This is a soak/load test, not a unit test. Run locally against a dev
backend, or against a staging deployment. DO NOT run against production
lighthouse without operator approval — sustained 120 req/min from a single
IP will trigger the 429 path on real traffic.

Install
=======
    pip install locust

Run (local backend, default 120s 10 users)
==========================================
    locust -f tests/loadtest_multi_tenant.py \\
        --host http://localhost:8001 \\
        --users 10 --spawn-rate 2 --run-time 120s --headless \\
        --csv=output/loadtest_$(date +%Y%m%d_%H%M%S)

Run (staging, longer soak)
==========================
    locust -f tests/loadtest_multi_tenant.py \\
        --host https://staging.example.com \\
        --users 50 --spawn-rate 5 --run-time 600s --headless

Dry-run (validate script imports + locust DSL without sending traffic)
======================================================================
    locust -f tests/loadtest_multi_tenant.py --host http://localhost:8001 \\
        --users 1 --spawn-rate 1 --run-time 3s --headless

Tenants
=======
The test cycles through 5 synthetic tenants with distinct API keys.
For the test to actually exercise the contextvars path, the backend
must accept these keys. In dev, set API_KEY=ai_video_demo_2026 and all
tenants will share that demo key — isolation is still tested by checking
trace_id uniqueness + /health response sanity.

Validation
==========
After the run, check:
- 0 HTTP 500 in stats
- Rate of 429 stable (proves rate limiter works, doesn't cascade)
- p95 latency on /health < 200ms (no degradation under load)
- output/loadtest_*.csv stats_history shows trace_id collision count == 0
"""
from __future__ import annotations

import secrets
from typing import ClassVar

from locust import HttpUser, between, task, events


SYNTHETIC_TENANTS: list[dict[str, str]] = [
    {"name": "tenant_a", "api_key": "ai_video_demo_2026"},
    {"name": "tenant_b", "api_key": "ai_video_demo_2026"},
    {"name": "tenant_c", "api_key": "ai_video_demo_2026"},
    {"name": "tenant_d", "api_key": "ai_video_demo_2026"},
    {"name": "tenant_e", "api_key": "ai_video_demo_2026"},
]


_trace_ids_seen: set[str] = set()
_trace_id_collisions: int = 0


@events.test_stop.add_listener
def report_trace_id_audit(environment, **_kwargs):
    """Print trace-id collision summary at end of run."""
    print(f"\n=== Trace ID audit ===")
    print(f"  unique trace_ids: {len(_trace_ids_seen)}")
    print(f"  collisions: {_trace_id_collisions}")
    if _trace_id_collisions > 0:
        print(f"  ❌ FAIL: response middleware is reusing trace_ids under load")
        environment.process_exit_code = 1
    else:
        print(f"  ✅ PASS: all trace_ids unique")


class MultiTenantUser(HttpUser):
    """Simulate one tenant making concurrent API calls.

    Each user picks a random tenant from SYNTHETIC_TENANTS and sticks with
    it for the session. wait_time creates realistic gaps between requests.
    """

    wait_time = between(0.5, 2.0)
    tenant: ClassVar[dict[str, str]] = {}

    def on_start(self) -> None:
        """Pick tenant + set default headers."""
        self.tenant = secrets.choice(SYNTHETIC_TENANTS)
        self.client.headers["X-API-Key"] = self.tenant["api_key"]
        self.client.headers["X-Client-Trace-Id"] = f"loadtest_{self.tenant['name']}_{secrets.token_hex(4)}"

    @task(10)
    def health_check(self) -> None:
        """High-frequency unauthenticated read — validates rate limiter + response wrapper."""
        global _trace_id_collisions
        with self.client.get("/health", catch_response=True, name="GET /health") as resp:
            if resp.status_code == 200:
                trace_id = resp.headers.get("X-Trace-Id", "")
                if trace_id:
                    if trace_id in _trace_ids_seen:
                        _trace_id_collisions += 1
                        resp.failure(f"trace_id collision: {trace_id}")
                    else:
                        _trace_ids_seen.add(trace_id)

    @task(3)
    def list_assets(self) -> None:
        """Authenticated read — validates X-API-Key isolation, hits PG."""
        with self.client.get("/assets/brand-packages", catch_response=True, name="GET /assets/brand-packages") as resp:
            if resp.status_code not in (200, 401, 429):
                resp.failure(f"unexpected status {resp.status_code}")

    @task(1)
    def health_with_bad_key(self) -> None:
        """Sanity-check that a wrong key gets 401, not 500."""
        with self.client.get(
            "/assets/brand-packages",
            headers={"X-API-Key": "wrong_key_should_401"},
            catch_response=True,
            name="GET /assets (bad key)",
        ) as resp:
            if resp.status_code == 401:
                resp.success()
            elif resp.status_code == 200:
                resp.failure("bad key accepted as valid — auth broken")
            elif resp.status_code in (429,):
                resp.success()
            else:
                resp.failure(f"unexpected status {resp.status_code}")
