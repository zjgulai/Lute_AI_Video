"""Static guard for FastAPI route authentication boundaries."""

from __future__ import annotations

import ast
import builtins
import json
import runpy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
API_PY = REPO_ROOT / "src" / "api.py"
CONTRACT = REPO_ROOT / "configs" / "backend-route-auth-contract.yaml"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "backend-route-auth-contract.md"
ACCEPTANCE_RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "artifact-acceptance-lifecycle.md"
PUBLISH_RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "publish-acceptance-consumption.md"
API_REFERENCE = REPO_ROOT / "docs" / "reference" / "api-endpoints.md"
DOCS_LINK_SCOPE = REPO_ROOT / "configs" / "docs-link-check-scope.txt"
LIVE_PUBLISH_TEST = REPO_ROOT / "tests" / "test_publish_e2e.py"

ROUTER_FILES = {
    "pipeline.router": REPO_ROOT / "src" / "routers" / "pipeline.py",
    "scenario.router": REPO_ROOT / "src" / "routers" / "scenario.py",
    "submissions.router": REPO_ROOT / "src" / "routers" / "submissions.py",
    "acceptance_records.router": REPO_ROOT / "src" / "routers" / "acceptance_records.py",
    "distribution.router": REPO_ROOT / "src" / "routers" / "distribution.py",
    "metrics.router": REPO_ROOT / "src" / "routers" / "metrics.py",
    "assets.router": REPO_ROOT / "src" / "routers" / "assets.py",
    "portfolio.router": REPO_ROOT / "src" / "routers" / "portfolio.py",
    "api_assets.router": REPO_ROOT / "src" / "api_assets.py",
    "telemetry_endpoint.router": REPO_ROOT / "src" / "telemetry_endpoint.py",
}

MIXED_OR_PUBLIC_ROUTER_FILES = (
    REPO_ROOT / "src" / "routers" / "health.py",
    REPO_ROOT / "src" / "routers" / "prometheus.py",
    REPO_ROOT / "src" / "routers" / "media.py",
)

ADMIN_ROUTER_FILES = tuple((REPO_ROOT / "src" / "routers" / "admin").glob("*.py"))
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

EXPECTED_PUBLISH_ERROR_ROWS = {
    "acceptance_not_found": ("`404`", "`false`", "`false`"),
    "acceptance_expired": ("`409`", "`false`", "`false`"),
    "acceptance_not_available": ("`409`", "`false`", "`false`"),
    "acceptance_artifact_integrity_mismatch": (
        "`409`",
        "`false`",
        "`false`",
    ),
    "acceptance_store_unavailable": ("`503`", "`false`", "`true`"),
    "publish_connector_not_ready": ("`503`", "`false`", "`true`"),
    "publish_attempt_store_unavailable": ("`503`", "`false`", "`true`"),
    "publish_artifact_unavailable_after_consume": (
        "`500`",
        "`true`",
        "`false`",
    ),
    "publish_attempt_state_unknown": (
        "`500`",
        "`false`, `true`, or `null`",
        "`false`",
    ),
    "publish_connector_failed": ("`502`", "`true`", "`false`"),
    "publish_outcome_ambiguous": ("`502`", "`true`", "`false`"),
}


@dataclass(frozen=True)
class RouteEntry:
    method: str
    path: str
    file: Path
    source: str
    has_api_key: bool
    has_admin_session: bool
    has_csrf: bool

    @property
    def route_id(self) -> str:
        return f"{self.method} {self.path}"


def _load_contract() -> dict[str, Any]:
    assert CONTRACT.exists(), "backend route auth contract is missing"
    return yaml.safe_load(CONTRACT.read_text())


def _route_ids(routes: list[dict[str, str]]) -> set[str]:
    return {f"{route['method']} {route['path']}" for route in routes}


def _normalized_source(path: Path) -> str:
    return "".join(path.read_text().split())


def _markdown_range(
    document: str,
    *,
    start_heading: str,
    end_heading: str,
) -> str:
    start_marker = f"{start_heading}\n"
    end_marker = f"\n{end_heading}\n"
    assert document.count(start_marker) == 1
    assert document.count(end_marker) == 1
    start = document.index(start_marker)
    end = document.index(end_marker, start)
    assert start < end
    return document[start:end]


def _uncertain_consume_contract_violations(section: str) -> list[str]:
    violations: list[str] = []
    header = "| HTTP | Code | `acceptance_consumed` | `retry_allowed` | Operator meaning |"
    if section.count(header) != 2:
        violations.append("publish error contract must contain two bounded tables")

    raw_rows = [
        line for line in section.splitlines() if line.lstrip().startswith("|") and line.strip().startswith("| `")
    ]
    parsed_rows: list[tuple[str, tuple[str, str, str]]] = []
    for row in raw_rows:
        columns = [cell.strip() for cell in row.strip().strip("|").split("|")]
        if len(columns) != 5 or not (columns[1].startswith("`") and columns[1].endswith("`")):
            violations.append("publish error row shape is invalid")
            continue
        parsed_rows.append(
            (
                columns[1][1:-1],
                (columns[0], columns[2], columns[3]),
            )
        )

    codes = [code for code, _ in parsed_rows]
    if len(codes) != 11 or len(set(codes)) != 11:
        violations.append("publish error tables must contain 11 unique codes")
    if set(codes) != set(EXPECTED_PUBLISH_ERROR_ROWS):
        violations.append("publish error code set must match the approved spec")
    for code, expected in EXPECTED_PUBLISH_ERROR_ROWS.items():
        matches = [actual for actual_code, actual in parsed_rows if actual_code == code]
        if matches != [expected]:
            violations.append(f"publish error row mismatch: {code}")

    note_start = "For `publish_attempt_state_unknown`, the three consume projections are exact:"
    note_end = "\n\nAuth `401`"
    if note_start not in section or note_end not in section:
        violations.append("bounded unknown-state operator note is missing")
        return violations
    note = section[section.index(note_start) : section.index(note_end)]

    tri_state_rules = [
        (
            "`acceptance_consumed=false`: consume is proven not to have "
            "completed for this attempt, but the `authorization_failed` "
            "attempt-state write is uncertain."
        ),
        (
            "`acceptance_consumed=true`: consume by this attempt is proven, "
            "but a later attempt-state write or projection is uncertain."
        ),
        ("`acceptance_consumed=null`: the consume outcome itself cannot be proven."),
    ]
    if any(rule not in note for rule in tri_state_rules):
        violations.append("unknown-state note must define all three consume truths")
    if "All three projections keep `retry_allowed=false`." not in note:
        violations.append("unknown-state note must link all three truths to no retry")
    if "does not authorize an automatic retry or acceptance restore" not in note:
        violations.append("unknown-state note must link false to no retry/no restore")
    return violations


def _is_direct_pytest_mark(node: ast.AST, marker: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == marker
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "pytest"
    )


def _is_direct_os_environ(node: ast.AST, variable: str) -> bool:
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "environ"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "os"
        and isinstance(node.slice, ast.Constant)
        and node.slice.value == variable
    )


def _string_literal_dict(node: ast.AST) -> dict[str, ast.expr] | None:
    if not isinstance(node, ast.Dict):
        return None

    items: dict[str, ast.expr] = {}
    for key, value in zip(node.keys, node.values, strict=True):
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str) or key.value in items:
            return None
        items[key.value] = value
    return items


def _live_publish_contract_violations(source: str) -> list[str]:
    tree = ast.parse(source)
    violations: list[str] = []

    pytestmark_assignments: list[ast.Assign | ast.AnnAssign] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if any(
            isinstance(candidate, ast.Name) and candidate.id == "pytestmark"
            for target in targets
            for candidate in ast.walk(target)
        ):
            pytestmark_assignments.append(node)

    if len(pytestmark_assignments) != 1:
        violations.append("live publish module must define exactly one module-level pytestmark")
    else:
        assignment = pytestmark_assignments[0]
        if (
            not isinstance(assignment, ast.Assign)
            or len(assignment.targets) != 1
            or not isinstance(assignment.targets[0], ast.Name)
            or assignment.targets[0].id != "pytestmark"
            or not isinstance(assignment.value, ast.List)
        ):
            violations.append("pytestmark must be a direct list assignment")
        else:
            markers = assignment.value.elts
            if sum(_is_direct_pytest_mark(item, "e2e") for item in markers) != 1:
                violations.append("pytestmark must contain exactly one pytest.mark.e2e")

            skipif_calls = [
                item for item in markers if isinstance(item, ast.Call) and _is_direct_pytest_mark(item.func, "skipif")
            ]
            if len(skipif_calls) != 1:
                violations.append("pytestmark must contain exactly one pytest.mark.skipif")
            else:
                skipif_call = skipif_calls[0]
                condition_matches = (
                    len(skipif_call.args) == 1
                    and isinstance(skipif_call.args[0], ast.UnaryOp)
                    and isinstance(skipif_call.args[0].op, ast.Not)
                    and isinstance(skipif_call.args[0].operand, ast.Call)
                    and isinstance(skipif_call.args[0].operand.func, ast.Name)
                    and skipif_call.args[0].operand.func.id == "_live_publish_authorized"
                    and skipif_call.args[0].operand.args == []
                    and skipif_call.args[0].operand.keywords == []
                )
                if not condition_matches:
                    violations.append("skipif must negate the exact no-argument live authorization guard")

                reason_keywords = [keyword for keyword in skipif_call.keywords if keyword.arg == "reason"]
                other_keywords = [keyword for keyword in skipif_call.keywords if keyword.arg != "reason"]
                reason = (
                    reason_keywords[0].value.value
                    if len(reason_keywords) == 1
                    and not other_keywords
                    and isinstance(reason_keywords[0].value, ast.Constant)
                    and isinstance(reason_keywords[0].value.value, str)
                    else ""
                )
                required_reason_fragments = (
                    "RUN_LIVE_PUBLISH=1",
                    "one exact acceptance ID",
                    "one exact platform",
                    "explicit publish API key",
                )
                if any(fragment not in reason for fragment in required_reason_fragments):
                    violations.append("skipif reason must explicitly name every authorization input")

    post_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "post"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "client"
    ]
    if len(post_calls) != 1:
        violations.append("live publish module must contain exactly one client.post call")
        return violations

    post_call = post_calls[0]
    if (
        len(post_call.args) != 1
        or not isinstance(post_call.args[0], ast.Constant)
        or post_call.args[0].value != "/distribution/publish"
    ):
        violations.append("client.post must target only /distribution/publish")

    json_keywords = [keyword for keyword in post_call.keywords if keyword.arg == "json"]
    if len(json_keywords) != 1:
        violations.append("client.post must contain exactly one direct json dict")
        return violations

    payload = _string_literal_dict(json_keywords[0].value)
    if payload is None:
        violations.append("client.post must contain exactly one direct json dict")
        return violations
    if set(payload) != {"acceptance_id", "platform", "metadata"}:
        violations.append("publish json must contain only acceptance_id, platform, and metadata")
    if not _is_direct_os_environ(
        payload.get("acceptance_id", ast.Constant()),
        "LIVE_PUBLISH_ACCEPTANCE_ID",
    ):
        violations.append("acceptance_id must come directly from LIVE_PUBLISH_ACCEPTANCE_ID")
    if not _is_direct_os_environ(
        payload.get("platform", ast.Constant()),
        "LIVE_PUBLISH_PLATFORM",
    ):
        violations.append("platform must come directly from LIVE_PUBLISH_PLATFORM")

    metadata = _string_literal_dict(payload.get("metadata", ast.Constant()))
    if metadata is None or set(metadata) != {"title", "description"}:
        violations.append("publish metadata must contain only title and description")

    return violations


def _router_prefix(tree: ast.AST) -> str:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = ast.unparse(node.func)
        if not func_name.endswith("APIRouter"):
            continue
        for keyword in node.keywords:
            if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant):
                return str(keyword.value.value)
    return ""


def _join_paths(prefix: str, route_path: str) -> str:
    if not prefix:
        return route_path
    if route_path == "/":
        return f"{prefix}/"
    return f"{prefix}{route_path}"


def _decorator_route(decorator: ast.expr) -> tuple[str, str] | None:
    if not isinstance(decorator, ast.Call):
        return None
    if not isinstance(decorator.func, ast.Attribute):
        return None
    if decorator.func.attr not in HTTP_METHODS:
        return None
    if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
        return None
    return decorator.func.attr.upper(), str(decorator.args[0].value)


def _routes_from_file(path: Path) -> list[RouteEntry]:
    source = path.read_text()
    tree = ast.parse(source)
    prefix = _router_prefix(tree)
    entries: list[RouteEntry] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        function_source = ast.get_source_segment(source, node) or ast.unparse(node)
        for decorator in node.decorator_list:
            route = _decorator_route(decorator)
            if route is None:
                continue
            method, raw_path = route
            path_text = _join_paths(prefix, raw_path)
            dependency_source = "\n".join([ast.unparse(decorator), ast.unparse(node.args)])
            entries.append(
                RouteEntry(
                    method=method,
                    path=path_text,
                    file=path,
                    source=function_source,
                    has_api_key="verify_api_key" in dependency_source,
                    has_admin_session="verify_admin_session" in dependency_source,
                    has_csrf="verify_csrf_token" in dependency_source,
                )
            )
    return entries


def _all_routes() -> list[RouteEntry]:
    files = set(ROUTER_FILES.values()) | set(MIXED_OR_PUBLIC_ROUTER_FILES) | set(ADMIN_ROUTER_FILES)
    return [route for path in sorted(files) for route in _routes_from_file(path)]


def test_contract_defines_current_public_and_secured_router_boundaries():
    contract = _load_contract()

    assert _route_ids(contract["public_routes"]) == {
        "GET /health",
        "GET /health/live",
        "GET /health/ready",
        "GET /metrics",
        "GET /api/media/{media_path:path}",
        "POST /api/admin/auth/login",
    }
    assert set(contract["api_key_router_mounts"]) == set(ROUTER_FILES)
    assert set(contract["public_router_mounts"]) == {"health.router", "prometheus.router"}
    assert set(contract["mixed_router_mounts"]) == {"media.router"}
    assert set(contract["admin_session_router_mounts"]) == {"admin_router"}

    media_route = next(route for route in contract["public_routes"] if route["path"] == "/api/media/{media_path:path}")
    assert "brand_assets" in media_route["reason"]
    assert "demo" in media_route["reason"]
    assert "tenant-bound token" in media_route["reason"]
    transparency = contract["transparency_routes"]
    assert transparency == {
        "authentication": "X-API-Key",
        "tenant_source": "AuthContext",
        "read_only": True,
        "client_sidecar_allowed": False,
        "routes": [
            {
                "name": "inspect",
                "method": "GET",
                "path": "/api/transparency/{resource_type}/{resource_id}",
            },
            {
                "name": "package",
                "method": "GET",
                "path": "/api/transparency/{resource_type}/{resource_id}/package",
            },
        ],
    }


def test_api_reference_authentication_matches_machine_route_contract():
    contract = _load_contract()
    api_reference = API_REFERENCE.read_text(encoding="utf-8")
    auth_section = _markdown_range(
        api_reference,
        start_heading="## Authentication",
        end_heading="## Table of Contents",
    )
    normalized_auth_section = " ".join(auth_section.split())

    assert _route_ids(contract["public_routes"]) == {
        "GET /health",
        "GET /health/live",
        "GET /health/ready",
        "GET /metrics",
        "GET /api/media/{media_path:path}",
        "POST /api/admin/auth/login",
    }
    for route_id in _route_ids(contract["public_routes"]):
        assert f"`{route_id}`" in normalized_auth_section
    for token in [
        "nginx/network",
        "brand_assets",
        "demo",
        "tenant-bound token",
        "rate limiting",
        "password verification",
        "admin session",
        "CSRF cookies",
        "X-API-Key",
        "state-changing admin",
    ]:
        assert token in normalized_auth_section
    assert "All endpoints **except**" not in normalized_auth_section


def test_api_include_router_auth_mounts_match_contract():
    contract = _load_contract()
    api_source = _normalized_source(API_PY)

    for router_name in contract["api_key_router_mounts"]:
        mount_prefix = f"app.include_router({router_name},"
        start = api_source.find(mount_prefix)
        assert start >= 0, f"{router_name} must be mounted"
        next_mount = api_source.find("app.include_router(", start + len(mount_prefix))
        mount_source = api_source[start : next_mount if next_mount >= 0 else None]
        assert "dependencies=[" in mount_source
        assert "Depends(verify_api_key)" in mount_source, f"{router_name} must be mounted with verify_api_key"

    for router_name in contract["public_router_mounts"] + contract["mixed_router_mounts"]:
        expected = f"app.include_router({router_name})"
        assert expected in api_source, f"{router_name} must remain explicitly classified"

    for router_name in contract["admin_session_router_mounts"]:
        expected = f"app.include_router({router_name})"
        assert expected in api_source, f"{router_name} must use admin session auth, not API key auth"


def test_public_routes_are_allowlisted_and_sensitive_routes_are_authenticated():
    contract = _load_contract()
    public_routes = _route_ids(contract["public_routes"])
    api_key_secured_files = {ROUTER_FILES[name] for name in contract["api_key_router_mounts"]}
    failures: list[str] = []

    for route in _all_routes():
        if route.route_id in public_routes:
            continue
        if route.file in api_key_secured_files or route.has_api_key:
            continue
        if route.path.startswith("/api/admin/") and route.has_admin_session:
            continue
        failures.append(f"{route.route_id} in {route.file.relative_to(REPO_ROOT)}")

    assert failures == []


def test_admin_state_changing_routes_keep_csrf_except_login():
    contract = _load_contract()
    csrf_exempt = _route_ids(contract["admin_csrf_exempt_routes"])
    failures: list[str] = []

    for route in _all_routes():
        if not route.path.startswith("/api/admin/"):
            continue
        if route.method not in STATE_CHANGING_METHODS:
            continue
        if route.route_id in csrf_exempt:
            continue
        if not route.has_csrf:
            failures.append(f"{route.route_id} in {route.file.relative_to(REPO_ROOT)}")

    assert failures == []


def test_auth_contract_runbook_is_link_checked():
    assert RUNBOOK.exists(), "backend route auth contract runbook is missing"
    runbook = RUNBOOK.read_text()
    for token in [
        "configs/backend-route-auth-contract.yaml",
        "verify_api_key",
        "verify_admin_session",
        "verify_csrf_token",
        "/health",
        "/api/media/{media_path:path}",
        "brand_assets",
        "demo",
        "tenant-bound token",
        "/api/media/sign",
    ]:
        assert token in runbook

    scope_targets = {
        line.strip()
        for line in DOCS_LINK_SCOPE.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert "docs/runbooks/backend-route-auth-contract.md" in scope_targets


def test_acceptance_and_publish_route_permission_contracts_are_exact():
    contract = _load_contract()

    assert "acceptance_record_routes" in contract, (
        "route auth contract must define acceptance create/read/revoke governance"
    )
    acceptance = contract["acceptance_record_routes"]
    assert acceptance["required_any_permission"] == ["artifact:accept", "all"]
    assert acceptance["provider_submit_only_allowed"] is False
    assert acceptance["routes"] == [
        {"name": "create", "method": "POST", "path": "/acceptance-records"},
        {
            "name": "read",
            "method": "GET",
            "path": "/acceptance-records/{acceptance_id}",
        },
        {
            "name": "revoke",
            "method": "POST",
            "path": "/acceptance-records/{acceptance_id}/revoke",
        },
    ]
    assert acceptance["public_consume_endpoint"] is False
    assert acceptance["distribution_integration"] == "W1-23 completed_local"
    assert all("/consume" not in route["path"] for route in acceptance["routes"])
    assert all("/consume" not in route["path"] for route in contract["public_routes"])

    publish = contract["publish_acceptance_routes"]
    assert publish["required_any_permission"] == ["artifact:publish", "all"]
    assert publish["artifact_accept_only_allowed"] is False
    assert publish["provider_submit_only_allowed"] is False
    assert publish["single_platform_only"] is True
    assert publish["client_artifact_path_allowed"] is False
    assert publish["body_human_assertion_allowed"] is False
    assert publish["public_consume_endpoint"] is False
    assert publish["routes"] == [
        {
            "name": "canonical",
            "method": "POST",
            "path": "/distribution/publish",
            "deprecated": False,
        },
        {
            "name": "legacy_adapter",
            "method": "POST",
            "path": "/publish/{video_id}",
            "deprecated": True,
        },
    ]


def test_publish_operator_docs_lock_stable_recovery_boundaries():
    assert PUBLISH_RUNBOOK.exists(), "publish acceptance runbook is missing"
    runbook = PUBLISH_RUNBOOK.read_text(encoding="utf-8")

    for token in [
        "artifact:publish",
        "acceptance_consumed",
        "retry_allowed",
        "production unchanged",
        "provider_call=false",
        "live_publish=false",
        "no automatic retry",
        "no restore",
        "publish_connector_not_ready",
        "publish_attempt_store_unavailable",
        "acceptance_not_found",
        "acceptance_expired",
        "acceptance_not_available",
        "acceptance_artifact_integrity_mismatch",
        "acceptance_store_unavailable",
        "publish_artifact_unavailable_after_consume",
        "publish_attempt_state_unknown",
        "publish_connector_failed",
        "publish_outcome_ambiguous",
    ]:
        assert token in runbook

    error_contract = _markdown_range(
        runbook,
        start_heading="## 5. Acceptance and attempt error tables",
        end_heading="## 6. Uncertain consume outcome",
    )
    uncertain_consume_recovery = _markdown_range(
        runbook,
        start_heading="## 5. Acceptance and attempt error tables",
        end_heading="## 8. Stale-row manual correlation",
    )
    assert "## 6. Uncertain consume outcome" in uncertain_consume_recovery
    assert "## 7. No automatic retry and no restore" in uncertain_consume_recovery
    assert _uncertain_consume_contract_violations(error_contract) == []

    retryable_mutation = error_contract.replace(
        "All three projections keep `retry_allowed=false`.",
        "All three projections keep `retry_allowed=true`.",
        1,
    )
    assert retryable_mutation != error_contract
    assert "unknown-state note must link all three truths to no retry" in (
        _uncertain_consume_contract_violations(retryable_mutation)
    )

    restore_mutation = error_contract.replace(
        " or acceptance restore",
        "",
        1,
    )
    assert restore_mutation != error_contract
    assert "unknown-state note must link false to no retry/no restore" in (
        _uncertain_consume_contract_violations(restore_mutation)
    )

    non_unknown_mutation = error_contract.replace(
        ("| `503` | `acceptance_store_unavailable` | `false` | `true` |"),
        ("| `503` | `acceptance_store_unavailable` | `false` | `false` |"),
        1,
    )
    assert non_unknown_mutation != error_contract
    assert "publish error row mismatch: acceptance_store_unavailable" in (
        _uncertain_consume_contract_violations(non_unknown_mutation)
    )


def test_publish_correlation_docs_use_exact_durable_consumer_operation():
    active_documents = {
        "publish runbook": PUBLISH_RUNBOOK,
        "acceptance lifecycle": ACCEPTANCE_RUNBOOK,
        "API reference": API_REFERENCE,
    }
    exact = "consumed_by_operation=distribution.publish"
    forbidden = "consumed_by_operation=publish"

    for label, path in active_documents.items():
        document = path.read_text(encoding="utf-8")
        assert exact in document, f"{label} must use the durable consumer operation"
        assert forbidden not in document, f"{label} contains the non-durable alias"


def test_live_publish_ast_detector_rejects_authority_mutations():
    live_test = LIVE_PUBLISH_TEST.read_text(encoding="utf-8")

    assert _live_publish_contract_violations(live_test) == []

    def mutation_violations(
        mutate: Any,
    ) -> list[str]:
        tree = ast.parse(live_test)
        mutate(tree)
        ast.fix_missing_locations(tree)
        return _live_publish_contract_violations(ast.unparse(tree))

    def pytestmark_list(tree: ast.Module) -> ast.List:
        assignment = next(
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "pytestmark"
        )
        assert isinstance(assignment.value, ast.List)
        return assignment.value

    def skipif_call(tree: ast.Module) -> ast.Call:
        marker_list = pytestmark_list(tree)
        marker = next(
            item
            for item in marker_list.elts
            if isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and item.func.attr == "skipif"
        )
        return marker

    def publish_payload(tree: ast.Module) -> ast.Dict:
        post_call = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "post"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "client"
        )
        json_keyword = next(keyword for keyword in post_call.keywords if keyword.arg == "json")
        assert isinstance(json_keyword.value, ast.Dict)
        return json_keyword.value

    def remove_skipif(tree: ast.Module) -> None:
        marker_list = pytestmark_list(tree)
        marker_list.elts.remove(skipif_call(tree))

    assert "pytestmark must contain exactly one pytest.mark.skipif" in mutation_violations(remove_skipif)

    def break_skipif_condition(tree: ast.Module) -> None:
        skipif_call(tree).args[0] = ast.Constant(value=False)

    assert "skipif must negate the exact no-argument live authorization guard" in mutation_violations(
        break_skipif_condition
    )

    def replace_payload_value(
        tree: ast.Module,
        *,
        key_name: str,
        hardcoded_value: str,
    ) -> None:
        payload = publish_payload(tree)
        index = next(
            index for index, key in enumerate(payload.keys) if isinstance(key, ast.Constant) and key.value == key_name
        )
        payload.values[index] = ast.Constant(value=hardcoded_value)

    assert "acceptance_id must come directly from LIVE_PUBLISH_ACCEPTANCE_ID" in mutation_violations(
        lambda tree: replace_payload_value(
            tree,
            key_name="acceptance_id",
            hardcoded_value="hardcoded-acceptance",
        )
    )
    assert "platform must come directly from LIVE_PUBLISH_PLATFORM" in mutation_violations(
        lambda tree: replace_payload_value(
            tree,
            key_name="platform",
            hardcoded_value="tiktok",
        )
    )


def test_live_publish_e2e_has_no_connector_or_body_authority_bypass(
    monkeypatch,
):
    live_test = LIVE_PUBLISH_TEST.read_text(encoding="utf-8")
    tree = ast.parse(live_test)

    top_level_imports = [node for node in tree.body if isinstance(node, ast.Import | ast.ImportFrom)]
    assert not any(
        isinstance(node, ast.ImportFrom)
        and (
            node.module == "src.api"
            or (node.module or "").startswith("src.connectors")
            or (node.module == "src" and any(alias.name in {"api", "connectors"} for alias in node.names))
        )
        for node in top_level_imports
    )
    assert not any(
        isinstance(node, ast.Import)
        and any(alias.name == "src.api" or alias.name.startswith("src.connectors") for alias in node.names)
        for node in top_level_imports
    )

    imported: list[tuple[str, tuple[str, ...]]] = []
    original_import = builtins.__import__

    def tracking_import(
        name: str,
        global_vars: dict[str, Any] | None = None,
        local_vars: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] | list[str] | None = (),
        level: int = 0,
    ) -> Any:
        normalized_fromlist = tuple(fromlist or ())
        imported.append((name, normalized_fromlist))
        return original_import(
            name,
            global_vars,
            local_vars,
            normalized_fromlist,
            level,
        )

    live_env = {
        "RUN_LIVE_PUBLISH": "1",
        "LIVE_PUBLISH_ACCEPTANCE_ID": "3f4b5088-4138-47c6-96ae-c918b8297010",
        "LIVE_PUBLISH_PLATFORM": "tiktok",
        "LIVE_PUBLISH_API_KEY": "explicit-live-publish-key",
    }
    for name in live_env:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(builtins, "__import__", tracking_import)
    try:
        namespace = runpy.run_path(
            str(LIVE_PUBLISH_TEST),
            run_name="_live_publish_governance_probe",
        )
    finally:
        monkeypatch.setattr(builtins, "__import__", original_import)
    assert not any(
        name == "src.api"
        or name.startswith("src.connectors")
        or (name == "src" and any(item == "api" or item.startswith("connectors") for item in fromlist))
        for name, fromlist in imported
    )

    authorized = namespace["_live_publish_authorized"]

    def authorized_with(values: dict[str, str]) -> bool:
        for name in live_env:
            monkeypatch.delenv(name, raising=False)
        for name, value in values.items():
            monkeypatch.setenv(name, value)
        return bool(authorized())

    assert authorized_with(live_env) is True
    assert authorized_with({**live_env, "LIVE_PUBLISH_PLATFORM": "shopify"}) is True
    for missing in live_env:
        assert authorized_with({name: value for name, value in live_env.items() if name != missing}) is False

    invalid_overrides = [{"RUN_LIVE_PUBLISH": value} for value in ("0", "true", " 1")] + [
        {"LIVE_PUBLISH_ACCEPTANCE_ID": "not-a-uuid"},
        {"LIVE_PUBLISH_ACCEPTANCE_ID": live_env["LIVE_PUBLISH_ACCEPTANCE_ID"].upper()},
        {"LIVE_PUBLISH_ACCEPTANCE_ID": ("3f4b5088-4138-17c6-96ae-c918b8297010")},
        {"LIVE_PUBLISH_ACCEPTANCE_ID": ("3f4b5088-4138-47c6-76ae-c918b8297010")},
        {"LIVE_PUBLISH_PLATFORM": "instagram"},
        {"LIVE_PUBLISH_PLATFORM": "TIKTOK"},
        {"LIVE_PUBLISH_PLATFORM": ""},
        {"LIVE_PUBLISH_API_KEY": ""},
    ]
    for override in invalid_overrides:
        assert authorized_with({**live_env, **override}) is False

    async_tests = [
        node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("test_")
    ]
    assert len(async_tests) == 1
    post_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "post"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "client"
    ]
    assert len(post_calls) == 1
    post_call = post_calls[0]
    assert len(post_call.args) == 1
    assert isinstance(post_call.args[0], ast.Constant)
    assert post_call.args[0].value == "/distribution/publish"

    all_imports = [node for node in ast.walk(tree) if isinstance(node, ast.Import | ast.ImportFrom)]
    assert not any(
        isinstance(node, ast.ImportFrom)
        and (
            (node.module or "").startswith("src.connectors")
            or (node.module == "src" and any(alias.name == "connectors" for alias in node.names))
        )
        for node in all_imports
    )
    assert not any(
        isinstance(node, ast.Import) and any(alias.name.startswith("src.connectors") for alias in node.names)
        for node in all_imports
    )
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(
        (isinstance(call.func, ast.Name) and call.func.id in {"get_connector", "publish_to_platform"})
        or (
            isinstance(call.func, ast.Attribute)
            and call.func.attr in {"get_connector", "publish_to_platform", "publish"}
        )
        for call in calls
    )

    headers_keyword = next(keyword for keyword in post_call.keywords if keyword.arg == "headers")
    assert isinstance(headers_keyword.value, ast.Dict)
    headers = {
        key.value: value
        for key, value in zip(
            headers_keyword.value.keys,
            headers_keyword.value.values,
            strict=True,
        )
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }
    assert set(headers) == {"X-API-Key"}
    api_key_value = headers["X-API-Key"]
    assert isinstance(api_key_value, ast.Subscript)
    assert isinstance(api_key_value.value, ast.Attribute)
    assert isinstance(api_key_value.value.value, ast.Name)
    assert api_key_value.value.value.id == "os"
    assert api_key_value.value.attr == "environ"
    assert isinstance(api_key_value.slice, ast.Constant)
    assert api_key_value.slice.value == "LIVE_PUBLISH_API_KEY"

    assert '"video_path"' not in live_test
    assert '"delivery_acceptance"' not in live_test


def test_acceptance_operator_and_api_docs_lock_lifecycle_boundaries():
    assert ACCEPTANCE_RUNBOOK.exists(), "artifact acceptance lifecycle runbook is missing"
    runbook = ACCEPTANCE_RUNBOOK.read_text()
    api_reference = API_REFERENCE.read_text()

    for document in (runbook, api_reference):
        for token in [
            "POST /acceptance-records",
            "GET /acceptance-records/{acceptance_id}",
            "POST /acceptance-records/{acceptance_id}/revoke",
            "artifact:accept",
            "provider:submit",
            "201",
            "200",
            "400",
            "403",
            "404",
            "409",
            "422",
            "503",
            "W1-23",
            "production unchanged",
            "provider_call=false",
            "acceptance_key_required",
            "acceptance_key_invalid",
            "acceptance_payload_conflict",
            "acceptance_not_found",
            "acceptance_source_not_terminal",
            "acceptance_source_not_eligible",
            "acceptance_artifact_mismatch",
            "acceptance_already_available",
            "acceptance_not_revocable",
            "acceptance_store_unavailable",
            "acceptance_not_available",
            "acceptance_expired",
            "acceptance_artifact_integrity_mismatch",
        ]:
            assert token in document

    for token in [
        "single-use",
        "internal",
        "no UI",
        "no HTTP consume",
        "expiry",
        "integrity",
        "rejection",
    ]:
        assert token in runbook


def test_acceptance_create_example_uses_canonical_assemble_artifact_path():
    api_reference = API_REFERENCE.read_text(encoding="utf-8")
    create_section = _markdown_range(
        api_reference,
        start_heading="### POST /acceptance-records",
        end_heading="### GET /acceptance-records/{acceptance_id}",
    )
    request_marker = "**Request:**\n\n```json\n"
    request_start = create_section.index(request_marker) + len(request_marker)
    request_end = create_section.index("\n```", request_start)
    request_example = json.loads(create_section[request_start:request_end])

    assert request_example["artifact_path"] == (
        "tenants/tenant-a/pending_review/s1_1783830000_a1b2c3d4/assemble/final.mp4"
    )
