"""Static guard for FastAPI route authentication boundaries."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
API_PY = REPO_ROOT / "src" / "api.py"
CONTRACT = REPO_ROOT / "configs" / "backend-route-auth-contract.yaml"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "backend-route-auth-contract.md"
DOCS_LINK_SCOPE = REPO_ROOT / "configs" / "docs-link-check-scope.txt"

ROUTER_FILES = {
    "pipeline.router": REPO_ROOT / "src" / "routers" / "pipeline.py",
    "scenario.router": REPO_ROOT / "src" / "routers" / "scenario.py",
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
            dependency_source = "\n".join(
                [ast.unparse(decorator), ast.unparse(node.args)]
            )
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
        "GET /metrics",
        "GET /api/media/{media_path:path}",
        "POST /api/admin/auth/login",
    }
    assert set(contract["api_key_router_mounts"]) == set(ROUTER_FILES)
    assert set(contract["public_router_mounts"]) == {"health.router", "prometheus.router"}
    assert set(contract["mixed_router_mounts"]) == {"media.router"}
    assert set(contract["admin_session_router_mounts"]) == {"admin_router"}


def test_api_include_router_auth_mounts_match_contract():
    contract = _load_contract()
    api_source = _normalized_source(API_PY)

    for router_name in contract["api_key_router_mounts"]:
        expected = f"app.include_router({router_name},dependencies=[Depends(verify_api_key)])"
        expected_with_trailing_comma = (
            f"app.include_router({router_name},dependencies=[Depends(verify_api_key)],)"
        )
        assert expected in api_source or expected_with_trailing_comma in api_source, (
            f"{router_name} must be mounted with verify_api_key"
        )

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
    ]:
        assert token in runbook

    scope_targets = {
        line.strip()
        for line in DOCS_LINK_SCOPE.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert "docs/runbooks/backend-route-auth-contract.md" in scope_targets
