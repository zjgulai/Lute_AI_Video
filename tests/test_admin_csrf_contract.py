"""Cross-layer contract for admin CSRF protection."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FILE = REPO_ROOT / "configs" / "admin-csrf-contract.yaml"
RUNBOOK_FILE = REPO_ROOT / "docs" / "runbooks" / "admin-csrf-contract.md"
DOCS_LINK_SCOPE_FILE = REPO_ROOT / "configs" / "docs-link-check-scope.txt"
ADMIN_DEPS = REPO_ROOT / "src" / "routers" / "_admin_deps.py"
ADMIN_AUTH = REPO_ROOT / "src" / "routers" / "admin" / "auth.py"
ADMIN_ROUTER_DIR = REPO_ROOT / "src" / "routers" / "admin"
API_TS = REPO_ROOT / "web" / "src" / "components" / "api.ts"
ADMIN_APP_DIR = REPO_ROOT / "web" / "src" / "app" / "admin"

STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
READ_ONLY_METHODS = ["GET", "HEAD", "OPTIONS"]


@dataclass(frozen=True)
class AdminRoute:
    method: str
    path: str
    file: Path
    function_source: str
    dependency_source: str

    @property
    def route_id(self) -> str:
        return f"{self.method} {self.path}"

    @property
    def has_session(self) -> bool:
        return "verify_admin_session" in self.dependency_source

    @property
    def has_csrf(self) -> bool:
        return "verify_csrf_token" in self.dependency_source


def _load_contract() -> dict[str, Any]:
    assert CONTRACT_FILE.is_file(), "admin CSRF contract file is missing"
    return yaml.safe_load(CONTRACT_FILE.read_text())


def _route_ids(routes: list[dict[str, str]]) -> set[str]:
    return {f"{route['method']} {route['path']}" for route in routes}


def _decorator_route(decorator: ast.expr) -> tuple[str, str] | None:
    if not isinstance(decorator, ast.Call):
        return None
    if not isinstance(decorator.func, ast.Attribute):
        return None
    method = decorator.func.attr.upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        return None
    if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
        return None
    return method, str(decorator.args[0].value)


def _admin_routes() -> list[AdminRoute]:
    routes: list[AdminRoute] = []
    for path in sorted(ADMIN_ROUTER_DIR.glob("*.py")):
        source = path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            function_source = ast.get_source_segment(source, node) or ast.unparse(node)
            for decorator in node.decorator_list:
                route = _decorator_route(decorator)
                if route is None:
                    continue
                method, route_path = route
                dependency_source = "\n".join(
                    [ast.unparse(decorator), ast.unparse(node.args)]
                )
                routes.append(
                    AdminRoute(
                        method=method,
                        path=route_path,
                        file=path,
                        function_source=function_source,
                        dependency_source=dependency_source,
                    )
                )
    return routes


def test_admin_csrf_contract_file_matches_backend_constants():
    contract = _load_contract()
    admin_deps_source = ADMIN_DEPS.read_text()

    assert contract["cookie_name"] == "admin_csrf"
    assert contract["request_header"] == "X-CSRF-Token"
    assert contract["fastapi_header_param"] == "x_csrf_token"
    assert contract["read_only_methods"] == READ_ONLY_METHODS
    assert set(contract["state_changing_methods"]) == STATE_CHANGING_METHODS
    assert contract["frontend_helper"] == "adminFetch"
    assert contract["cookie"]["path"] == "/"
    assert contract["cookie"]["http_only"] is False
    assert "CSRF_COOKIE_NAME = \"admin_csrf\"" in admin_deps_source
    assert "CSRF_HEADER_NAME = \"x-csrf-token\"" in admin_deps_source
    for method in READ_ONLY_METHODS:
        assert method in admin_deps_source


def test_login_sets_browser_readable_csrf_cookie_for_admin_pages():
    auth_source = ADMIN_AUTH.read_text()

    assert "key=CSRF_COOKIE_NAME" in auth_source
    assert "httponly=False" in auth_source
    assert 'samesite="lax"' in auth_source
    assert 'path="/",' in auth_source
    assert '"csrf_token": csrf_token' in auth_source
    assert "response.delete_cookie(\n        key=CSRF_COOKIE_NAME,\n        path=\"/\"," in auth_source


def test_admin_state_changing_routes_require_session_and_csrf_except_login():
    contract = _load_contract()
    csrf_exempt = _route_ids(contract["csrf_exempt_routes"])
    failures: list[str] = []

    for route in _admin_routes():
        if route.route_id in csrf_exempt:
            continue
        if not route.has_session:
            failures.append(f"{route.route_id} missing verify_admin_session")
        if route.method in STATE_CHANGING_METHODS and not route.has_csrf:
            failures.append(f"{route.route_id} missing verify_csrf_token")

    assert failures == []


def test_frontend_admin_fetch_uses_double_submit_header_and_no_api_key():
    api_source = API_TS.read_text()

    assert "credentials: \"include\"" in api_source
    assert "delete (mergedInit.headers as Record<string, string>)[\"X-API-Key\"]" in api_source
    assert "document.cookie.match(/(?:^|; )admin_csrf=([^;]+)/)" in api_source
    assert "\"X-CSRF-Token\"" in api_source
    assert "decodeURIComponent(m[1])" in api_source
    for method in READ_ONLY_METHODS:
        assert f'method !== "{method}"' in api_source


def test_admin_frontend_mutations_use_admin_fetch_helper_only():
    raw_fetch_failures: list[str] = []
    admin_mutations: list[str] = []

    for path in sorted(ADMIN_APP_DIR.rglob("*.tsx")):
        if path.name.endswith(".test.tsx"):
            continue
        source = path.read_text()
        if "fetch(" in source:
            raw_fetch_failures.append(str(path.relative_to(REPO_ROOT)))
        for match in re.finditer(
            r"adminFetch(?:Json)?\((?P<body>.*?method:\s*[\"'](?P<method>POST|PUT|PATCH|DELETE)[\"'].*?)\)",
            source,
            re.DOTALL,
        ):
            admin_mutations.append(
                f"{path.relative_to(REPO_ROOT)}:{match.group('method')}"
            )

    assert raw_fetch_failures == []
    assert admin_mutations, "admin frontend must keep mutating calls behind adminFetch/adminFetchJson"


def test_admin_csrf_runbook_is_link_checked():
    assert RUNBOOK_FILE.is_file()

    runbook = RUNBOOK_FILE.read_text()
    for token in [
        "configs/admin-csrf-contract.yaml",
        "verify_csrf_token",
        "adminFetch",
        "X-CSRF-Token",
        "admin_csrf",
        "path=/",
    ]:
        assert token in runbook

    scope_targets = {
        line.strip()
        for line in DOCS_LINK_SCOPE_FILE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert "docs/runbooks/admin-csrf-contract.md" in scope_targets
