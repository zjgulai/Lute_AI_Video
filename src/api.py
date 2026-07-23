"""FastAPI backend — exposes pipeline state and human review endpoints.

Run with: uvicorn src.api:app --reload --port 8001

API keys can be submitted at pipeline start via the api_keys field.
When provided, they are stored in a per-request context (contextvars) so that
concurrent pipelines do not contaminate each other's keys.
If not provided, the server falls back to .env file values (or mock mode).
"""

import asyncio
import json
import logging
import os
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from dotenv import load_dotenv

from src._version import APP_VERSION

load_dotenv()

try:
    from fastapi import Depends, FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    HAS_FASTAPI = True
except ImportError:
    FastAPI = None  # type: ignore[assignment]
    Depends = None  # type: ignore[assignment]
    CORSMiddleware = None  # type: ignore[assignment]
    HAS_FASTAPI = False

try:
    from src.storage import init_db

    HAS_STORAGE = True
except ImportError:
    init_db = None  # type: ignore[assignment]
    HAS_STORAGE = False

# ── FastAPI app ──

if HAS_FASTAPI:
    assert FastAPI is not None
    assert Depends is not None
    assert CORSMiddleware is not None

    async def _run_startup() -> None:
        if HAS_STORAGE:
            assert init_db is not None
            await init_db()
            try:
                from src.storage.db import check_pg_health, is_pg_available

                health = await check_pg_health()
                _log = logging.getLogger("api.startup")
                _log.info(
                    "Persistence backend: %s (status=%s, pg_available=%s)",
                    health.get("backend"),
                    health.get("status"),
                    is_pg_available(),
                )
                if health.get("backend") == "postgresql" and health.get("status") == "tables_missing":
                    _log.error(
                        "PG tables missing - /metrics/* and /admin/* will return "
                        "503 until migrations run. Fix: docker exec ai_video_backend "
                        "alembic upgrade head"
                    )
            except Exception as exc:
                logging.getLogger("api.startup").warning("persistence health check failed: %s", exc)
        # P2-1: Restore active threads from disk (standalone mode only)
        from src.routers._state import _restore_thread_index

        _restore_thread_index()
        # P1-10: Start background thread cache eviction loop
        from src.routers._state import _periodic_cache_eviction
        from src.tasks.bg_registry import register_background_task as _register_background_task

        _register_background_task(
            asyncio.create_task(_periodic_cache_eviction()),
            label="cache_eviction",
        )
        # P0: Production API key sanity check — fail-fast if required keys missing
        from src.config import ENVIRONMENT

        if ENVIRONMENT == "production":
            from src.config import DEEPSEEK_API_KEY, POYO_API_KEY, SEEDANCE_API_KEY, SILICONFLOW_API_KEY

            missing = []
            if not DEEPSEEK_API_KEY:
                missing.append("DEEPSEEK_API_KEY")
            if not POYO_API_KEY and not SEEDANCE_API_KEY:
                missing.append("POYO_API_KEY or SEEDANCE_API_KEY (at least one video backend required)")
            if not SILICONFLOW_API_KEY:
                missing.append("SILICONFLOW_API_KEY")
            if missing:
                raise RuntimeError(
                    f"Production startup failed: missing required API keys: {', '.join(missing)}. "
                    f"Set them in environment variables or switch to development mode."
                )

        # Portfolio: auto-rebuild assets/portfolio/index.json on pipeline.completed
        try:
            from src.tools.portfolio_hook import register_portfolio_hook

            register_portfolio_hook()
        except Exception as _exc:
            logging.getLogger("api.startup").warning("portfolio hook registration failed: %s", _exc)

        # Admin Panel: background tasks (health checks + cleanup)
        try:
            from src.routers.admin import (
                cleanup_expired_sessions,
                cleanup_old_logs,
                run_health_checks,
            )

            async def _admin_health_loop():
                while True:
                    await asyncio.sleep(300)  # 5 minutes
                    try:
                        await run_health_checks()
                    except Exception as exc:
                        logging.getLogger("api.admin").warning("admin health check failed: %s", exc)

            async def _admin_session_cleanup_loop():
                while True:
                    await asyncio.sleep(3600)  # 1 hour
                    try:
                        await cleanup_expired_sessions()
                    except Exception as exc:
                        logging.getLogger("api.admin").warning("admin session cleanup failed: %s", exc)

            async def _admin_log_cleanup_loop():
                while True:
                    await asyncio.sleep(3600)  # 1 hour
                    try:
                        await cleanup_old_logs()
                    except Exception as exc:
                        logging.getLogger("api.admin").warning("admin log cleanup failed: %s", exc)

            _register_background_task(
                asyncio.create_task(_admin_health_loop()),
                label="admin_health",
            )
            _register_background_task(
                asyncio.create_task(_admin_session_cleanup_loop()),
                label="admin_session_cleanup",
            )
            _register_background_task(
                asyncio.create_task(_admin_log_cleanup_loop()),
                label="admin_log_cleanup",
            )
            logging.getLogger("api.startup").info("admin background tasks registered")
        except Exception as _exc:
            logging.getLogger("api.startup").warning("admin background tasks registration failed: %s", _exc)

    @asynccontextmanager
    async def _lifespan(_app: object):
        await _run_startup()
        try:
            yield
        finally:
            from src.services.submission_idempotency import (
                shutdown_submission_idempotency_service_if_initialized,
            )
            from src.tasks.bg_registry import cancel_background_tasks

            try:
                await shutdown_submission_idempotency_service_if_initialized()
            finally:
                await cancel_background_tasks()

    app = FastAPI(title="Short Video Agent API", version=APP_VERSION, lifespan=_lifespan)

    # CORS: allow comma-separated origins via CORS_ORIGINS env var
    _cors_env = os.getenv("CORS_ORIGINS", "")
    _default_origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost",
        "https://lute-ai-video.tcloudbaseapp.com",
    ]
    if _cors_env:
        allow_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
    else:
        allow_origins = _default_origins

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-API-Key",
            "Authorization",
            "X-Client-Trace-Id",
            "Idempotency-Key",
        ],
        allow_credentials=True,  # Admin Panel: HttpOnly cookie auth
    )

    # ── P3-1: Rate limiting middleware (fallback) ──
    # Primary rate limiting is handled by nginx (limit_req_zone, P2-11).
    # This in-memory middleware is kept as a fallback for direct backend access
    # (e.g. local dev without nginx, or health checks from internal tools).
    _rate_window_sec = 60
    _rate_max_requests = 120
    _rate_max_ips = 1000
    _rate_store: OrderedDict[str, list[float]] = OrderedDict()

    @app.middleware("http")
    async def rate_limit_middleware(request, call_next):
        from fastapi.responses import JSONResponse

        # Skip rate limit for health checks and static media serving
        # (portfolio gallery can load 400+ images/videos simultaneously)
        if request.url.path == "/health" or request.url.path.startswith("/api/media/"):
            return await call_next(request)

        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        now = time.time()

        if client_ip in _rate_store:
            _rate_store.move_to_end(client_ip)

        timestamps = _rate_store.get(client_ip, [])
        timestamps = [t for t in timestamps if now - t < _rate_window_sec]

        if len(timestamps) >= _rate_max_requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down.", "retry_after_sec": _rate_window_sec},
            )

        timestamps.append(now)
        _rate_store[client_ip] = timestamps

        while len(_rate_store) > _rate_max_ips:
            _rate_store.popitem(last=False)

        return await call_next(request)

    # ── Request logging middleware ──
    _request_log = logging.getLogger("api.request")

    @app.middleware("http")
    async def request_log_middleware(request, call_next):
        _start = time.perf_counter()
        response = await call_next(request)
        _duration_ms = (time.perf_counter() - _start) * 1000
        _request_log.info(
            "%s %s → %s (%.0fms)",
            request.method,
            request.url.path,
            response.status_code,
            _duration_ms,
        )
        return response

    # ── P-TEST: Unified response wrapper middleware ──
    # Injects _meta {trace_id, duration_ms, version, timestamp} into all JSON
    # responses and echoes X-Client-Trace-Id back as X-Trace-Id header.

    @app.middleware("http")
    async def response_wrapper_middleware(request, call_next):
        from fastapi.responses import JSONResponse
        from starlette.responses import Response

        _start = time.perf_counter()
        client_trace_id = request.headers.get("X-Client-Trace-Id", "")

        response = await call_next(request)

        _duration_ms = round((time.perf_counter() - _start) * 1000, 1)
        server_trace_id = client_trace_id or f"s{int(time.time() * 1000)}{os.urandom(2).hex()}"
        response.headers["X-Trace-Id"] = server_trace_id

        # Skip non-JSON and health endpoint
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response
        if request.url.path == "/health":
            return response
        # Skip streaming responses
        if not hasattr(response, "body_iterator"):
            return response

        # Capture response body
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            # Not valid JSON — return raw (strip content-length so Starlette recalculates)
            raw_headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
            return Response(
                content=body,
                status_code=response.status_code,
                headers=raw_headers,
            )

        # Build _meta
        meta = {
            "trace_id": server_trace_id,
            "duration_ms": _duration_ms,
            "version": APP_VERSION,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }

        if isinstance(data, dict):
            data["_meta"] = meta
        else:
            data = {"data": data, "_meta": meta}

        # Strip content-length so JSONResponse recalculates for the wrapped body
        wrapped_headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        new_response = JSONResponse(
            content=data,
            status_code=response.status_code,
            headers=wrapped_headers,
        )
        # Preserve Set-Cookie headers (e.g. admin_session from login)
        for name, value in response.raw_headers:
            if name.lower() == b"set-cookie":
                new_response.raw_headers.append((name, value))
        return new_response

    _LEGACY_PUBLISH_HEADERS = {
        "Deprecation": "true",
        "Link": '</distribution/publish>; rel="successor-version"',
    }

    @app.middleware("http")
    async def legacy_publish_deprecation_middleware(request, call_next):
        response = await call_next(request)
        parts = request.url.path.split("/")
        is_legacy_publish = request.method == "POST" and len(parts) == 3 and parts[1] == "publish" and bool(parts[2])
        if is_legacy_publish:
            response.headers.update(_LEGACY_PUBLISH_HEADERS)
        return response

    @app.middleware("http")
    async def prometheus_http_middleware(request, call_next):
        from src.telemetry_prometheus import record_http_request

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            route = getattr(request.scope.get("route"), "path", "__unmatched__")
            record_http_request(
                request.method,
                route if isinstance(route, str) else "__unmatched__",
                500,
                time.perf_counter() - started,
            )
            raise
        route = getattr(request.scope.get("route"), "path", "__unmatched__")
        record_http_request(
            request.method,
            route if isinstance(route, str) else "__unmatched__",
            response.status_code,
            time.perf_counter() - started,
        )
        return response

    # ── Mount domain routers (P1-11) ──
    from src.routers import health
    from src.routers._deps import verify_api_key
    from src.services.provider_execution import provider_execution_request_scope

    app.include_router(health.router)

    from src.routers import prometheus

    app.include_router(prometheus.router)

    from src.routers import pipeline

    app.include_router(
        pipeline.router,
        dependencies=[
            Depends(provider_execution_request_scope),
            Depends(verify_api_key),
        ],
    )

    from src.routers import scenario

    app.include_router(
        scenario.router,
        dependencies=[
            Depends(provider_execution_request_scope),
            Depends(verify_api_key),
        ],
    )

    from src.routers import submissions

    app.include_router(submissions.router, dependencies=[Depends(verify_api_key)])

    from src.routers import acceptance_records

    app.include_router(
        acceptance_records.router,
        dependencies=[Depends(verify_api_key)],
    )

    from src.routers import distribution

    app.include_router(distribution.router, dependencies=[Depends(verify_api_key)])

    from src.routers import metrics

    app.include_router(metrics.router, dependencies=[Depends(verify_api_key)])

    from src.routers import assets

    app.include_router(assets.router, dependencies=[Depends(verify_api_key)])

    from src.routers import media

    app.include_router(media.router)

    from src.routers import portfolio

    app.include_router(portfolio.router, dependencies=[Depends(verify_api_key)])

    from src.routers import toolbox

    app.include_router(toolbox.router, dependencies=[Depends(verify_api_key)])

    # Mount legacy asset management endpoints
    try:
        from src import api_assets

        app.include_router(api_assets.router, dependencies=[Depends(verify_api_key)])
    except (ImportError, RuntimeError) as _e:
        logging.warning("api_assets router skipped: %s", _e)

    # Mount telemetry endpoints
    try:
        from src import telemetry_endpoint

        if telemetry_endpoint.router:
            app.include_router(
                telemetry_endpoint.router,
                dependencies=[Depends(verify_api_key)],
            )
    except (ImportError, RuntimeError) as _e:
        logging.warning("telemetry router skipped: %s", _e)

    # Mount admin panel router (session-cookie auth, independent of API key)
    try:
        from src.routers.admin import router as admin_router

        # No prefix — admin.py endpoints already use /api/admin/* full paths
        app.include_router(admin_router)
        logging.getLogger("api.startup").info("admin router mounted at /api/admin/*")
    except (ImportError, RuntimeError) as _e:
        logging.warning("admin router skipped: %s", _e)

    _fastapi_openapi = app.openapi

    def _rewrite_publish_schema_refs(value: Any) -> Any:
        if isinstance(value, dict):
            rewritten: dict[str, Any] = {}
            for key, nested in value.items():
                if isinstance(nested, str) and nested.startswith("#/$defs/"):
                    rewritten[key] = "#/components/schemas/" + nested.removeprefix("#/$defs/")
                else:
                    rewritten[key] = _rewrite_publish_schema_refs(nested)
            return rewritten
        if isinstance(value, list):
            return [_rewrite_publish_schema_refs(item) for item in value]
        return value

    def _openapi_with_exact_publish_request_schema() -> dict[str, Any]:
        schema = _fastapi_openapi()
        publish_request_schema = distribution.PublishAttemptRequest.model_json_schema(mode="validation")
        publish_definitions = publish_request_schema.pop("$defs", {})
        rewritten_publish_definitions = {
            name: _rewrite_publish_schema_refs(definition) for name, definition in publish_definitions.items()
        }
        publish_request_schema = _rewrite_publish_schema_refs(publish_request_schema)

        existing_component_schemas = schema.get("components", {}).get("schemas", {})
        for name, definition in rewritten_publish_definitions.items():
            if name in existing_component_schemas and existing_component_schemas[name] != definition:
                raise RuntimeError(f"OpenAPI component collision: {name}")

        component_schemas = schema.setdefault("components", {}).setdefault("schemas", {})
        for name, definition in rewritten_publish_definitions.items():
            if name not in component_schemas:
                component_schemas[name] = definition
        # FastAPI serializes OpenAPI with exclude_none=True, which strips explicit
        # default: null values from schemas supplied through openapi_extra.
        for path in ("/distribution/publish", "/publish/{video_id}"):
            schema["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"] = deepcopy(
                publish_request_schema
            )
        return schema

    setattr(app, "openapi", _openapi_with_exact_publish_request_schema)
