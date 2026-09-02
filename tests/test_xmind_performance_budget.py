"""Contracts for the executable, public-read-only XMind performance gate."""

from __future__ import annotations

import datetime as dt
import gzip
import http.client
import importlib.util
import json
import urllib.error
from email.message import Message
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BUDGET_PATH = REPO_ROOT / "configs" / "xmind-performance-budget.json"
CHECKER_PATH = REPO_ROOT / "scripts" / "check_xmind_performance.py"
PROBE_PATH = REPO_ROOT / "scripts" / "xmind_transport_probe.py"


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_xmind_performance", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("xmind_transport_probe_test", PROBE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def checker() -> ModuleType:
    return _load_checker()


@pytest.fixture
def probe() -> ModuleType:
    return _load_probe()


@pytest.fixture
def budget(checker: ModuleType) -> dict[str, Any]:
    return checker.load_contract(BUDGET_PATH)


def test_xmind_budget_is_strict_fixed_and_cannot_be_relabelled_as_field_cwv(
    budget: dict[str, Any],
) -> None:
    assert budget["schema"] == "xmind-performance-budget.v1"
    assert budget["origin"] == "https://xmind.lute-tlz-dddd.top"
    assert budget["sampling"] == {
        "warmups": 1,
        "measured_runs": 5,
        "percentile": 75,
        "percentile_method": "nearest-rank",
        "cache": "disabled",
    }
    assert [route["path"] for route in budget["routes"]] == [
        "/",
        "/models/index.html",
        "/router.html",
        "/models/socratic-midwifery-ea89f905ee32.html",
    ]
    assert budget["lab_browser"] == {
        "max_p75_ttfb_ms": 800,
        "max_p75_fcp_ms": 1800,
        "max_p75_lcp_ms": 2500,
        "max_each_lcp_ms": 4000,
        "max_p75_cls": 0.1,
        "max_each_cls": 0.1,
        "max_console_warnings": 0,
        "max_console_errors": 0,
        "max_failed_requests": 0,
        "required_profiles": ["desktop-1440x900", "mobile-390x844"],
    }
    assert budget["browser_evidence_protocol"] == {
        "max_age_hours": 24,
        "allowed_clock_skew_minutes": 5,
        "warmup_runs_per_route_profile": 1,
        "max_warmup_errors": 0,
        "measured_run_ids": [1, 2, 3, 4, 5],
        "network_profile": "unthrottled",
        "cpu_profile": "unthrottled",
        "profiles": {
            "desktop-1440x900": {"width": 1440, "height": 900},
            "mobile-390x844": {"width": 390, "height": 844},
        },
    }
    assert budget["synthetic_search_response"] == {
        "path": "/models/index.html",
        "required_profile": "desktop-1440x900",
        "queries": ["第一性原理", "苏格拉底", "决策", "情绪", "AI"],
        "max_p75_ms": 200,
        "max_each_ms": 500,
        "min_visible_results_per_query": 1,
        "measured_runs_per_query": 5,
        "must_match_visible_result_count": True,
        "must_not_be_labelled_inp": True,
    }
    assert budget["field_cwv"] == {
        "status_without_crux_or_rum": "UNKNOWN",
        "percentile": 75,
        "max_lcp_ms": 2500,
        "max_inp_ms": 200,
        "max_cls": 0.1,
        "required_for_claim": "field-cwv-passed",
    }


def test_nearest_rank_percentile_is_deterministic(checker: ModuleType) -> None:
    assert checker.nearest_rank([4888, 1544, 2076, 1796, 1480], 75) == 2076
    assert checker.nearest_rank([0, 0, 0, 0, 0], 75) == 0
    with pytest.raises(ValueError, match="at least one sample"):
        checker.nearest_rank([], 75)


def _valid_lab_evidence(budget: dict[str, Any]) -> dict[str, Any]:
    routes = {}
    warmups = {}
    captured_at = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    profile_sizes = budget["browser_evidence_protocol"]["profiles"]
    for route in budget["routes"]:
        path = route["path"]
        routes[path] = {}
        warmups[path] = {}
        for profile in ("desktop-1440x900", "mobile-390x844"):
            warmups[path][profile] = {"runs": 1, "errors": 0}
            url = f"{budget['origin']}{path}"
            viewport = profile_sizes[profile]
            routes[path][profile] = [
                {
                    "run_id": index + 1,
                    "status": 200,
                    "redirects": 0,
                    "requested_url": url,
                    "final_url": url,
                    "viewport_width": viewport["width"],
                    "viewport_height": viewport["height"],
                    "cache_disabled": True,
                    "captured_at_utc": captured_at,
                    "ttfb_ms": 400 + index,
                    "fcp_ms": 900 + index,
                    "lcp_ms": 1200 + index,
                    "cls": 0,
                    "console_warnings": 0,
                    "console_errors": 0,
                    "failed_requests": 0,
                    "main_content_visible": True,
                }
                for index in range(5)
            ]
    return {
        "schema": "xmind-browser-lab-evidence.v1",
        "origin": budget["origin"],
        "cache": "disabled",
        "captured_at_utc": captured_at,
        "browser_name": "Chromium",
        "browser_version": "fixture-1",
        "os": "fixture-os",
        "network_profile": "unthrottled",
        "cpu_profile": "unthrottled",
        "warmups": warmups,
        "routes": routes,
    }


def test_lab_evaluator_fails_closed_on_a_poor_lcp_outlier(
    checker: ModuleType,
    budget: dict[str, Any],
) -> None:
    evidence = _valid_lab_evidence(budget)
    evidence["routes"]["/models/index.html"]["desktop-1440x900"][2]["lcp_ms"] = 4888

    report = checker.evaluate_lab_evidence(budget, evidence)

    assert report["status"] == "BLOCKED"
    assert any("single-run LCP" in item for item in report["violations"])
    assert report["field_cwv_status"] == "UNKNOWN"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-route",
        "missing-profile",
        "too-few-runs",
        "console-error",
        "hidden-main-content",
        "negative-metric",
        "zero-metric",
        "causality-error",
        "wrong-url",
        "wrong-viewport",
        "duplicate-run-id",
        "missing-warmup",
        "stale-evidence",
    ],
)
def test_lab_evaluator_rejects_incomplete_or_erroring_evidence(
    checker: ModuleType,
    budget: dict[str, Any],
    mutation: str,
) -> None:
    evidence = _valid_lab_evidence(budget)
    routes = evidence["routes"]
    if mutation == "missing-route":
        routes.pop("/router.html")
    elif mutation == "missing-profile":
        routes["/"].pop("mobile-390x844")
    elif mutation == "too-few-runs":
        routes["/"]["desktop-1440x900"].pop()
    elif mutation == "console-error":
        routes["/"]["desktop-1440x900"][0]["console_errors"] = 1
    elif mutation == "hidden-main-content":
        routes["/"]["desktop-1440x900"][0]["main_content_visible"] = False
    elif mutation == "negative-metric":
        routes["/"]["desktop-1440x900"][0]["lcp_ms"] = -1
    elif mutation == "zero-metric":
        routes["/"]["desktop-1440x900"][0]["lcp_ms"] = 0
    elif mutation == "causality-error":
        routes["/"]["desktop-1440x900"][0]["fcp_ms"] = 1300
        routes["/"]["desktop-1440x900"][0]["lcp_ms"] = 1200
    elif mutation == "wrong-url":
        routes["/"]["desktop-1440x900"][0]["final_url"] = "https://example.com/"
    elif mutation == "wrong-viewport":
        routes["/"]["mobile-390x844"][0]["viewport_width"] = 1440
    elif mutation == "duplicate-run-id":
        routes["/"]["desktop-1440x900"][1]["run_id"] = 1
    elif mutation == "missing-warmup":
        evidence["warmups"]["/"].pop("desktop-1440x900")
    else:
        evidence["captured_at_utc"] = "2000-01-01T00:00:00Z"

    report = checker.evaluate_lab_evidence(budget, evidence)

    assert report["status"] == "BLOCKED"
    assert report["violations"]


def test_valid_lab_evidence_passes_only_the_synthetic_gate(
    checker: ModuleType,
    budget: dict[str, Any],
) -> None:
    report = checker.evaluate_lab_evidence(budget, _valid_lab_evidence(budget))

    assert report["status"] == "PASS"
    assert report["violations"] == []
    assert report["field_cwv_status"] == "UNKNOWN"


def test_transport_evaluator_rejects_threshold_and_identity_drift(
    checker: ModuleType,
    budget: dict[str, Any],
) -> None:
    evidence = checker.example_transport_evidence(budget)
    evidence["routes"]["/router.html"][0]["ttfb_ms"] = 9000
    evidence["routes"]["/"][1]["final_url"] = "https://example.com/"

    report = checker.evaluate_transport_evidence(budget, evidence)

    assert report["status"] == "BLOCKED"
    assert any("TTFB" in item for item in report["violations"])
    assert any("final URL" in item for item in report["violations"])


def test_runtime_contract_rejects_route_budget_weakening(
    checker: ModuleType,
    tmp_path: Path,
) -> None:
    payload = json.loads(BUDGET_PATH.read_text())
    payload["routes"][1]["max_decoded_bytes"] += 1
    weakened = tmp_path / "weakened-budget.json"
    weakened.write_text(json.dumps(payload))

    with pytest.raises(checker.ContractError, match="budgets must remain fixed"):
        checker.load_contract(weakened)

    payload = json.loads(BUDGET_PATH.read_text())
    payload["synthetic_search_response"]["path"] = "/"
    weakened.write_text(json.dumps(payload))
    with pytest.raises(checker.ContractError, match="query inventory must remain fixed"):
        checker.load_contract(weakened)


def test_valid_search_evidence_is_identity_bound_and_passes(
    checker: ModuleType,
    budget: dict[str, Any],
) -> None:
    path = budget["synthetic_search_response"]["path"]
    evidence = {
        "metric": "synthetic-search-response",
        "path": path,
        "requested_url": f"{budget['origin']}{path}",
        "final_url": f"{budget['origin']}{path}",
        "profile": "desktop-1440x900",
        "viewport_width": 1440,
        "viewport_height": 900,
        "cache_disabled": True,
        "captured_at_utc": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "queries": {
            query: [
                {
                    "run_id": index + 1,
                    "duration_ms": 10,
                    "result_count": 1,
                    "visible_article_count": 1,
                }
                for index in range(5)
            ]
            for query in budget["synthetic_search_response"]["queries"]
        },
    }

    report = checker.evaluate_synthetic_search_evidence(budget, evidence)

    assert report["status"] == "PASS"
    evidence["final_url"] = "https://example.com/"
    assert checker.evaluate_synthetic_search_evidence(budget, evidence)["status"] == "BLOCKED"


@pytest.mark.parametrize("mutation", ["wrong-viewport", "duplicate-run-id", "zero-duration"])
def test_search_evaluator_rejects_false_pass_identity_and_timing(
    checker: ModuleType,
    budget: dict[str, Any],
    mutation: str,
) -> None:
    path = budget["synthetic_search_response"]["path"]
    evidence = {
        "metric": "synthetic-search-response",
        "path": path,
        "requested_url": f"{budget['origin']}{path}",
        "final_url": f"{budget['origin']}{path}",
        "profile": "desktop-1440x900",
        "viewport_width": 1440,
        "viewport_height": 900,
        "cache_disabled": True,
        "captured_at_utc": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "queries": {
            query: [
                {"run_id": index + 1, "duration_ms": 10,
                 "result_count": 1, "visible_article_count": 1}
                for index in range(5)
            ]
            for query in budget["synthetic_search_response"]["queries"]
        },
    }
    if mutation == "wrong-viewport":
        evidence["viewport_width"] = 390
    elif mutation == "duplicate-run-id":
        evidence["queries"]["第一性原理"][1]["run_id"] = 1
    else:
        evidence["queries"]["第一性原理"][0]["duration_ms"] = 0

    report = checker.evaluate_synthetic_search_evidence(budget, evidence)

    assert report["status"] == "BLOCKED"
    assert report["violations"]


def test_search_evaluator_rejects_missing_result_counts(
    checker: ModuleType,
    budget: dict[str, Any],
) -> None:
    evidence = {
        "metric": "synthetic-search-response",
        "path": "/models/index.html",
        "queries": {
            query: [{"duration_ms": 1} for _ in range(5)]
            for query in budget["synthetic_search_response"]["queries"]
        },
    }

    report = checker.evaluate_synthetic_search_evidence(budget, evidence)

    assert report["status"] == "BLOCKED"
    assert any("result counts" in item for item in report["violations"])

    for samples in evidence["queries"].values():
        for sample in samples:
            sample.update({"result_count": 0, "visible_article_count": 0})
    report = checker.evaluate_synthetic_search_evidence(budget, evidence)
    assert report["status"] == "BLOCKED"
    assert any("below minimum" in item for item in report["violations"])


def test_transport_probe_converts_redirect_and_body_errors_to_blocked_samples(
    probe: ModuleType,
    budget: dict[str, Any],
) -> None:
    route = budget["routes"][0]
    expected_url = f"{budget['origin']}/"

    class FakeResponse:
        status = 200

        def __init__(self, body: bytes = b"", *, encoding: str = "identity", error: Exception | None = None):
            self.body = body
            self.error = error
            self.headers = {
                "Content-Encoding": encoding,
                "Content-Type": "text/html; charset=utf-8",
                "Cache-Control": "no-store",
            }

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            if self.error is not None:
                raise self.error
            return self.body[:size]

        def geturl(self) -> str:
            return expected_url

    class FakeOpener:
        def __init__(self, outcome: object):
            self.outcome = outcome

        def open(self, *_args: object, **_kwargs: object) -> FakeResponse:
            if isinstance(self.outcome, BaseException):
                raise self.outcome
            assert isinstance(self.outcome, FakeResponse)
            return self.outcome

    redirect = urllib.error.HTTPError(expected_url, 302, "redirect", Message(), None)
    redirected = probe.fetch_transport_sample(FakeOpener(redirect), route, budget["origin"])
    assert redirected["status"] == 302
    assert redirected["redirects"] == 1

    incomplete = http.client.IncompleteRead(b"partial", 10)
    truncated = probe.fetch_transport_sample(FakeOpener(FakeResponse(error=incomplete)), route, budget["origin"])
    assert truncated["status"] == 0
    assert "IncompleteRead" in truncated["error"]

    broken_gzip = bytearray(gzip.compress("前车之鉴".encode() * 100))
    broken_gzip[10] ^= 0xFF
    malformed = probe.fetch_transport_sample(
        FakeOpener(FakeResponse(bytes(broken_gzip), encoding="gzip")),
        route,
        budget["origin"],
    )
    assert malformed["status"] == 0
    assert "error" in malformed

    oversized_body = "前车之鉴".encode() + b"x" * route["max_encoded_bytes"]
    oversized = probe.fetch_transport_sample(
        FakeOpener(FakeResponse(oversized_body)),
        route,
        budget["origin"],
    )
    assert oversized["encoded_bytes"] == route["max_encoded_bytes"] + 1
    assert probe.NoRedirectHandler().redirect_request(None, None, 302, "", {}, expected_url) is None


def test_checker_has_no_url_or_sample_count_weakening_flags() -> None:
    text = CHECKER_PATH.read_text()
    probe_text = PROBE_PATH.read_text()

    compile(text, str(CHECKER_PATH), "exec")
    compile(probe_text, str(PROBE_PATH), "exec")
    assert 'add_argument("--url"' not in text
    assert 'add_argument("--samples"' not in text
    assert "CERT_NONE" not in text + probe_text
    assert "check_hostname = False" not in text + probe_text
    assert "HTTPRedirectHandler" in probe_text
    json.loads(BUDGET_PATH.read_text())
