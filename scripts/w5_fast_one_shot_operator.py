#!/usr/bin/env python3
"""Operate one explicitly authorized W5 Fast submit through the backend only."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

if (Path.cwd() / "src").is_dir() and str(Path.cwd()) not in sys.path:
    sys.path.insert(0, str(Path.cwd()))

from pydantic import ValidationError

from src.operations.w5_fast_one_shot import (
    BackendResponse,
    EvidenceStore,
    OperatorBlocked,
    TransportAmbiguous,
    assert_backend_route_contract,
    execute_submit_once,
    poll_status,
    safe_ledger_projection,
)

BACKEND_BASE_URL = "http://127.0.0.1:8001"
OPENAPI_PATH = "/openapi.json"
SUBMIT_PATH = "/fast/submit"
STATUS_OPENAPI_PATH = "/fast/status/{task_id}"
EXECUTE_ENV = "AI_VIDEO_W5_FAST_EXECUTE"
EVIDENCE_PATH_ENV = "W5_FAST_EVIDENCE_PATH"

_OPENAPI_LIMIT = 4 * 1024 * 1024
_POLL_LIMIT = 150
_POLL_INTERVAL_SECONDS = 4.0
_RETRY_FIELD = "_".join(("provider", "max", "retries"))


class LoopbackBackendGateway:
    """No-proxy, no-retry adapter for the canonical backend-direct routes."""

    @staticmethod
    def _httpx() -> Any:
        return importlib.import_module("httpx")

    @classmethod
    def _client(cls, *, timeout: float) -> Any:
        return cls._httpx().Client(
            base_url=BACKEND_BASE_URL,
            timeout=timeout,
            trust_env=False,
        )

    @staticmethod
    def _mapping_response(response: Any) -> BackendResponse:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if type(payload) is not dict:
            payload = {}
        return BackendResponse(response.status_code, payload)

    def contract_paths(self) -> Mapping[str, Any]:
        try:
            with self._client(timeout=10.0) as client:
                response = client.get(OPENAPI_PATH)
        except self._httpx().TransportError:
            raise OperatorBlocked("backend_route_contract_unavailable") from None
        if response.status_code != 200 or len(response.content) > _OPENAPI_LIMIT:
            raise OperatorBlocked("backend_route_contract_unavailable")
        try:
            document = response.json()
        except ValueError:
            raise OperatorBlocked("backend_route_contract_invalid") from None
        if type(document) is not dict or type(document.get("paths")) is not dict:
            raise OperatorBlocked("backend_route_contract_invalid")
        return document["paths"]

    def submit(self, *, payload: bytes, raw_key: str, api_key: str) -> BackendResponse:
        headers = {
            "X-API-Key": api_key,
            "Idempotency-Key": raw_key,
            "Content-Type": "application/json",
        }
        try:
            with self._client(timeout=30.0) as client:
                response = client.post(SUBMIT_PATH, headers=headers, content=payload)
        except self._httpx().TransportError:
            raise TransportAmbiguous("backend transport outcome unavailable") from None
        return self._mapping_response(response)

    def status(self, *, task_id: str, api_key: str) -> BackendResponse:
        try:
            with self._client(timeout=20.0) as client:
                response = client.get(
                    f"/fast/status/{task_id}",
                    headers={"X-API-Key": api_key},
                )
        except self._httpx().TransportError:
            raise TransportAmbiguous("backend status transport unavailable") from None
        return self._mapping_response(response)


def _strict_object(raw: str, *, code: str) -> dict[str, Any]:
    def reject_constant(_value: str) -> None:
        raise ValueError("non-finite JSON")

    def pairs_to_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw,
            object_pairs_hook=pairs_to_object,
            parse_constant=reject_constant,
        )
    except (RecursionError, TypeError, ValueError, json.JSONDecodeError):
        raise OperatorBlocked(code) from None
    if type(value) is not dict:
        raise OperatorBlocked(code)
    return value


def _runtime_paths() -> tuple[Path, Path, Path]:
    loader: Any = importlib.import_module("src.pipeline.w5_fast_runtime_loader")
    try:
        paths = loader.configured_w5_fast_runtime_paths()
    except loader.W5FastRuntimeLoadError as exc:
        raise OperatorBlocked(exc.code) from None
    if paths is None:
        raise OperatorBlocked("w5_fast_binding_unavailable")
    return paths


def _private_directory(paths: tuple[Path, Path, Path]) -> Path:
    parents = {path.parent for path in paths}
    if len(parents) != 1:
        raise OperatorBlocked("w5_fast_private_directory_mismatch")
    return next(iter(parents))


def _evidence_store(paths: tuple[Path, Path, Path]) -> EvidenceStore:
    raw = os.environ.get(EVIDENCE_PATH_ENV, "")
    if not raw or not Path(raw).is_absolute():
        raise OperatorBlocked("w5_fast_evidence_path_unavailable")
    evidence = Path(raw)
    private = _private_directory(paths)
    if evidence == Path("/") or evidence == private or private in evidence.parents:
        raise OperatorBlocked("w5_fast_evidence_path_invalid")
    return EvidenceStore(evidence)


def _read_raw_key() -> str:
    raw = sys.stdin.read(66)
    if raw.endswith("\n"):
        raw = raw[:-1]
    if len(raw) != 64:
        raise OperatorBlocked("w5_fast_transient_key_invalid")
    value = raw
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise OperatorBlocked("w5_fast_transient_key_invalid")
    return value


def _load_request(private_directory: Path) -> tuple[dict[str, Any], Any]:
    activation_module: Any = importlib.import_module("src.pipeline.w5_fast_activation")
    state_module: Any = importlib.import_module("src.routers._state")
    raw = activation_module.read_w5_private_json(
        private_directory / "request.json",
        name="W5 request",
    )
    payload = _strict_object(raw, code="w5_fast_request_invalid")
    try:
        request = state_module.FastModeRequest.model_validate(payload)
    except ValidationError:
        raise OperatorBlocked("w5_fast_request_invalid") from None
    return payload, request


def _load_authority(raw_key: str) -> tuple[dict[str, Any], Any, Any]:
    activation_module: Any = importlib.import_module("src.pipeline.w5_fast_activation")
    harness: Any = importlib.import_module("src.pipeline.w5_acceptance_harness")
    policy_module: Any = importlib.import_module("src.pipeline.generation_policy")
    loader: Any = importlib.import_module("src.pipeline.w5_fast_runtime_loader")
    paths = _runtime_paths()
    private_directory = _private_directory(paths)
    payload, request = _load_request(private_directory)
    try:
        plan = harness.validate_w5_plan_draft_json(
            activation_module.read_w5_private_json(paths[0], name="W5 plan")
        )
        policy = policy_module.EffectiveGenerationPolicy.model_validate(
            {
                "tenant_id": plan.tenant_id,
                "scenario": "fast",
                "enable_media_synthesis": request.enable_media_synthesis,
                "artifact_disposition": request.artifact_disposition,
                _RETRY_FIELD: 0,
                "c2pa_signing_mode": os.environ.get(
                    "AI_VIDEO_C2PA_SIGNING_MODE",
                    "local_draft",
                ),
            }
        )
        authority = loader.load_w5_fast_runtime_authority(
            paths=paths,
            validated_request=request,
            effective_policy=policy,
            raw_idempotency_key=raw_key,
            require_active=True,
        )
    except loader.W5FastRuntimeLoadError as exc:
        raise OperatorBlocked(exc.code) from None
    except (OSError, TypeError, ValueError, ValidationError):
        raise OperatorBlocked("w5_fast_authority_invalid") from None
    return payload, request, authority


def _safe_authority(authority: Any) -> dict[str, Any]:
    return {
        "activation_id": authority.activation.activation_id,
        "binding_id": authority.binding.binding_id,
        "tenant_id": authority.plan.tenant_id,
        "submission_cap": authority.plan.submission_cap,
        "automatic_retry_cap": authority.plan.automatic_retry_cap,
        _RETRY_FIELD: 0,
        "artifact_disposition": authority.plan.artifact_disposition,
        "publish_allowed": authority.activation.publish_allowed,
        "delivery_accepted": authority.activation.delivery_accepted,
    }


def _assert_contract(gateway: LoopbackBackendGateway) -> None:
    assert_backend_route_contract(gateway.contract_paths())


def _require_api_key() -> str:
    api_key = os.environ.get("API_KEY", "")
    if not api_key:
        raise OperatorBlocked("w5_fast_api_key_unavailable")
    return api_key


def contract() -> int:
    _assert_contract(LoopbackBackendGateway())
    print(json.dumps({"backend_route_contract": "pass"}, sort_keys=True))
    return 0


def preflight() -> int:
    _require_api_key()
    raw_key = _read_raw_key()
    _payload, request, authority = _load_authority(raw_key)
    _assert_contract(LoopbackBackendGateway())
    report = {
        "status": "ready",
        "activation_id": authority.activation.activation_id,
        "binding_id": authority.binding.binding_id,
        "tenant_id": authority.plan.tenant_id,
        "duration_seconds": request.duration,
        "enable_tts": request.enable_tts,
        "budget_limit_usd_nanos": authority.plan.budget_limit_usd_nanos,
        "provider_job_caps": dict(authority.plan.provider_job_caps),
        "llm_model": authority.binding.expected_llm_model,
        "video_model": authority.binding.expected_video_model,
        "video_resolution": authority.binding.expected_video_resolution,
        "automatic_retry_cap": authority.plan.automatic_retry_cap,
        "artifact_disposition": authority.plan.artifact_disposition,
        "publish_allowed": authority.activation.publish_allowed,
        "delivery_accepted": authority.activation.delivery_accepted,
        "execution_performed": False,
    }
    print(json.dumps(report, sort_keys=True))
    return 0


def submit() -> int:
    if os.environ.get(EXECUTE_ENV) != "1":
        raise OperatorBlocked("w5_fast_execute_gate_disabled")
    api_key = _require_api_key()
    raw_key = _read_raw_key()
    payload, _request, authority = _load_authority(raw_key)
    gateway = LoopbackBackendGateway()
    _assert_contract(gateway)
    store = _evidence_store(_runtime_paths())
    outcome = execute_submit_once(
        store=store,
        gateway=gateway,
        raw_key=raw_key,
        api_key=api_key,
        request_payload=payload,
        authority=_safe_authority(authority),
        invoked_at_unix=int(time.time()),
    )
    print(json.dumps(outcome, sort_keys=True))
    if outcome["submit_state"] == "accepted":
        return 0
    if outcome["submit_state"] in {"transport_ambiguous", "response_ambiguous"}:
        return 3
    return 2


def poll() -> int:
    api_key = _require_api_key()
    gateway = LoopbackBackendGateway()
    _assert_contract(gateway)
    store = _evidence_store(_runtime_paths())
    terminal = poll_status(
        store=store,
        gateway=gateway,
        api_key=api_key,
        max_polls=_POLL_LIMIT,
        sleep=time.sleep,
        poll_interval_seconds=_POLL_INTERVAL_SECONDS,
    )
    print(json.dumps(terminal, sort_keys=True))
    return 0 if terminal.get("status") == "done" else 5


async def _read_ledger_snapshot() -> dict[str, Any]:
    asyncpg: Any = importlib.import_module("asyncpg")
    activation_module: Any = importlib.import_module("src.pipeline.w5_fast_activation")
    harness: Any = importlib.import_module("src.pipeline.w5_acceptance_harness")

    paths = _runtime_paths()
    plan = harness.validate_w5_plan_draft_json(
        activation_module.read_w5_private_json(paths[0], name="W5 plan")
    )
    activation = _strict_object(
        activation_module.read_w5_private_json(paths[1], name="W5 activation"),
        code="w5_fast_activation_invalid",
    )
    activation_id = activation.get("activation_id")
    if not isinstance(activation_id, str):
        raise OperatorBlocked("w5_fast_activation_invalid")
    submit_outcome = _evidence_store(paths).load_object(
        "submit-outcome.json"
    )
    task_id = submit_outcome.get("task_id")
    dsn = os.environ.get("DATABASE_URL", "").replace(
        "postgresql+asyncpg://",
        "postgresql://",
        1,
    )
    if not dsn.startswith(("postgresql://", "postgres://")):
        raise OperatorBlocked("operator_ledger_unavailable")
    try:
        connection = await asyncpg.connect(dsn, timeout=10.0, command_timeout=10.0)
        try:
            async with connection.transaction(readonly=True):
                idempotency = await connection.fetchrow(
                    """
                    SELECT resource_id, record_status, stage,
                           trusted_authorization_ref, safe_error_code
                    FROM idempotency_records
                    WHERE tenant_id = $1 AND trusted_authorization_ref = $2
                    """,
                    plan.tenant_id,
                    activation_id,
                )
                account = None
                attempts: list[dict[str, Any]] = []
                if isinstance(task_id, str):
                    account = await connection.fetchrow(
                        """
                        SELECT account_id, job_id, cap_usd_nanos,
                               reserved_usd_nanos, settled_usd_nanos
                        FROM job_budget_accounts
                        WHERE tenant_id = $1 AND job_kind = 'canonical' AND job_id = $2
                        """,
                        plan.tenant_id,
                        task_id,
                    )
                if account is not None:
                    rows = await connection.fetch(
                        """
                        SELECT logical_operation, ordinal, provider,
                               canonical_model, state, external_task_id,
                               reserved_usd_nanos, settled_usd_nanos, safe_error_code
                        FROM provider_cost_attempts
                        WHERE tenant_id = $1 AND account_id = $2
                        ORDER BY logical_operation, ordinal
                        """,
                        plan.tenant_id,
                        account["account_id"],
                    )
                    attempts = [dict(row) for row in rows]
        finally:
            await connection.close()
    except OperatorBlocked:
        raise
    except Exception:
        raise OperatorBlocked("operator_ledger_unavailable") from None
    return safe_ledger_projection(
        {
            "idempotency": dict(idempotency) if idempotency is not None else None,
            "account": dict(account) if account is not None else None,
            "attempts": attempts,
        }
    )


def ledger() -> int:
    snapshot = asyncio.run(_read_ledger_snapshot())
    store = _evidence_store(_runtime_paths())
    store.create_json("ledger-outcome.json", snapshot)
    print(json.dumps(snapshot, sort_keys=True))
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        raise OperatorBlocked("operator_command_invalid")
    handlers = {
        "contract": contract,
        "preflight": preflight,
        "submit": submit,
        "poll": poll,
        "ledger": ledger,
    }
    handler = handlers.get(sys.argv[1])
    if handler is None:
        raise OperatorBlocked("operator_command_invalid")
    return handler()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OperatorBlocked as exc:
        print(json.dumps({"status": "blocked", "safe_error_code": exc.code}), file=sys.stderr)
        raise SystemExit(2) from None
    except Exception:
        print(
            json.dumps(
                {"status": "blocked", "safe_error_code": "operator_unexpected_failure"}
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
