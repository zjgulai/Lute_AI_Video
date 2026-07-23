#!/usr/bin/env python3
"""Build one private hash-only W5 Fast runtime binding without execution."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pipeline.w5_acceptance_harness import (  # noqa: E402
    validate_w5_plan_draft_json,
)
from src.pipeline.w5_fast_activation import (  # noqa: E402
    read_w5_private_json,
    validate_w5_fast_activation_json,
)
from src.pipeline.w5_fast_runtime import (  # noqa: E402
    build_w5_fast_runtime_binding,
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--activation", required=True, type=Path)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--idempotency-key-sha256", required=True)
    parser.add_argument(
        "--c2pa-signing-mode",
        required=True,
        choices=("local_draft", "required"),
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(token: str) -> object:
    raise ValueError(f"non-finite JSON number is forbidden: {token}")


def _reject_float(token: str) -> object:
    raise ValueError(f"floating JSON number is forbidden: {token}")


def _request_from_private_file(path: Path) -> dict[str, Any]:
    raw = read_w5_private_json(path, name="W5 Fast request")
    try:
        payload = json.loads(
            raw,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (json.JSONDecodeError, RecursionError, TypeError, ValueError) as exc:
        raise ValueError("W5 Fast request must be strict JSON") from exc
    if type(payload) is not dict:
        raise ValueError("W5 Fast request must be a JSON object")
    expected_keys = {
        "user_prompt",
        "duration",
        "enable_tts",
        "api_keys",
        "enable_media_synthesis",
        "artifact_disposition",
        "provider_max_retries",
    }
    if set(payload) != expected_keys:
        raise ValueError("W5 Fast request fields are incomplete or unknown")
    if not isinstance(payload["user_prompt"], str) or not payload[
        "user_prompt"
    ]:
        raise ValueError("W5 Fast prompt must be a non-empty string")
    if type(payload["duration"]) is not int:
        raise ValueError("W5 Fast duration must be an integer")
    if type(payload["enable_tts"]) is not bool:
        raise ValueError("W5 Fast TTS choice must be boolean")
    if type(payload["enable_media_synthesis"]) is not bool:
        raise ValueError("W5 Fast media choice must be boolean")
    if payload["artifact_disposition"] != "pending_review":
        raise ValueError("W5 Fast disposition must be pending_review")
    if (
        type(payload["provider_max_retries"]) is not int
        or payload["provider_max_retries"] != 0
    ):
        raise ValueError("W5 Fast provider retry cap must be zero")
    if type(payload["api_keys"]) is not dict or payload["api_keys"]:
        raise ValueError("W5 Fast request file must not contain provider keys")
    return payload


def _private_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    repo_tmp = (REPO_ROOT / "tmp").resolve()
    if resolved.is_relative_to(REPO_ROOT) and not resolved.is_relative_to(
        repo_tmp
    ):
        raise ValueError("runtime binding output must be under tmp or outside repository")
    if resolved.exists():
        raise ValueError("runtime binding output already exists")
    return resolved


def main() -> int:
    args = _parse_args()
    try:
        now = datetime.now(UTC)
        plan = validate_w5_plan_draft_json(
            read_w5_private_json(args.plan, name="W5 plan")
        )
        activation = validate_w5_fast_activation_json(
            read_w5_private_json(args.activation, name="W5 activation"),
            plan=plan,
            now=now,
        )
        request = _request_from_private_file(args.request)
        if _SHA256_RE.fullmatch(args.idempotency_key_sha256) is None:
            raise ValueError("idempotency key digest must be lowercase SHA-256")
        policy = {
            "version": "generation-safety.v2",
            "tenant_id": plan.tenant_id,
            "scenario": "fast",
            "provider_submit_allowed": True,
            "enable_media_synthesis": request["enable_media_synthesis"],
            "artifact_disposition": request["artifact_disposition"],
            "provider_max_retries": request["provider_max_retries"],
            "c2pa_signing_mode": args.c2pa_signing_mode,
        }
        binding = build_w5_fast_runtime_binding(
            plan=plan,
            activation=activation,
            validated_request=request,
            effective_policy=policy,
            idempotency_key_sha256=args.idempotency_key_sha256,
            now=now,
        )
        output = _private_output(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(binding.model_dump_json(indent=2) + "\n")
    except (OSError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print("Wrote private W5 Fast runtime binding")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
