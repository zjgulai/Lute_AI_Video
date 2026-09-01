#!/usr/bin/env python3
"""Evaluate fixed XMind transport/browser budgets without field-CWV promotion."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import urllib.parse
from pathlib import Path
from typing import Any

try:
    from scripts.xmind_transport_probe import collect_transport_evidence
except ModuleNotFoundError:
    from xmind_transport_probe import collect_transport_evidence

SCHEMA = "xmind-performance-budget.v1"
ORIGIN = "https://xmind.lute-tlz-dddd.top"
ROUTE_PATHS = ("/", "/models/index.html", "/router.html", "/models/socratic-midwifery-ea89f905ee32.html")
PROFILES = ("desktop-1440x900", "mobile-390x844")
SEARCH_QUERIES = ("第一性原理", "苏格拉底", "决策", "情绪", "AI")


class ContractError(ValueError): pass


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{label} must be finite and non-negative")
    return result


def _fresh_utc(value: Any, max_age_hours: int, clock_skew_minutes: int) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.utcoffset() != dt.timedelta(0):
        return False
    age = dt.datetime.now(dt.UTC) - parsed
    return -dt.timedelta(minutes=clock_skew_minutes) <= age <= dt.timedelta(hours=max_age_hours)


def nearest_rank(values: list[float] | list[int], percentile: int) -> float:
    if not values:
        raise ValueError("at least one sample is required")
    if percentile < 1 or percentile > 100:
        raise ValueError("percentile must be between 1 and 100")
    ordered = sorted(_number(value, "percentile sample") for value in values)
    index = math.ceil((percentile / 100) * len(ordered)) - 1
    result = ordered[index]
    return int(result) if result.is_integer() else result


def load_contract(path: Path | str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise ContractError("contract root must be an object")
    if payload.get("schema") != SCHEMA or payload.get("origin") != ORIGIN:
        raise ContractError("contract schema or origin is not the fixed XMind gate")
    if payload.get("sampling") != {
        "warmups": 1,
        "measured_runs": 5,
        "percentile": 75,
        "percentile_method": "nearest-rank",
        "cache": "disabled",
    }:
        raise ContractError("sampling protocol must remain fixed")
    routes = payload.get("routes")
    if not isinstance(routes, list) or [item.get("path") for item in routes] != list(ROUTE_PATHS):
        raise ContractError("route inventory must remain fixed and ordered")
    required_route_keys = {
        "content_marker",
        "max_p75_ttfb_ms",
        "max_each_ttfb_ms",
        "max_p75_total_ms",
        "max_each_total_ms",
        "max_encoded_bytes",
        "max_decoded_bytes",
    }
    for route in routes:
        if not isinstance(route, dict) or not required_route_keys <= route.keys():
            raise ContractError("each route must define identity and transport budgets")
        if not isinstance(route["content_marker"], str) or not route["content_marker"]:
            raise ContractError("each route requires a non-empty content marker")
        for key in required_route_keys - {"content_marker"}:
            if _number(route[key], f"route {key}") <= 0:
                raise ContractError(f"route {key} must be positive")
        if route["max_p75_ttfb_ms"] > 800 or route["max_each_ttfb_ms"] > 4000:
            raise ContractError("route TTFB thresholds cannot be weakened")
        fixed_route_values = {
            "/": ("前车之鉴", 2000, 8000, 100000, 100000),
            "/models/index.html": ("模型库", 4000, 8000, 750000, 4000000),
            "/router.html": ("Agent", 3000, 8000, 250000, 250000),
            "/models/socratic-midwifery-ea89f905ee32.html": ("苏格拉底", 2000, 8000, 100000, 100000),
        }
        actual_route_values = (route["content_marker"], route["max_p75_total_ms"], route["max_each_total_ms"],
                               route["max_encoded_bytes"],
                               route["max_decoded_bytes"])
        if actual_route_values != fixed_route_values[route["path"]]:
            raise ContractError("route identity, total-time, and size budgets must remain fixed")

    lab = payload.get("lab_browser")
    expected_lab = {
        "max_p75_ttfb_ms": 800,
        "max_p75_fcp_ms": 1800,
        "max_p75_lcp_ms": 2500,
        "max_each_lcp_ms": 4000,
        "max_p75_cls": 0.1,
        "max_each_cls": 0.1,
        "max_console_warnings": 0,
        "max_console_errors": 0,
        "max_failed_requests": 0,
        "required_profiles": list(PROFILES),
    }
    if lab != expected_lab:
        raise ContractError("browser thresholds and profiles must remain fixed")
    protocol = payload.get("browser_evidence_protocol")
    if protocol != {
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
    }:
        raise ContractError("browser evidence identity and freshness protocol must remain fixed")
    search = payload.get("synthetic_search_response")
    if (not isinstance(search, dict) or search.get("path") != "/models/index.html"
            or search.get("queries") != list(SEARCH_QUERIES)):
        raise ContractError("synthetic search query inventory must remain fixed")
    if search.get("required_profile") != "desktop-1440x900":
        raise ContractError("synthetic search profile must remain fixed")
    if search.get("max_p75_ms") != 200 or search.get("max_each_ms") != 500:
        raise ContractError("synthetic search thresholds cannot be weakened")
    if search.get("measured_runs_per_query") != 5:
        raise ContractError("synthetic search sample count must remain fixed")
    if search.get("min_visible_results_per_query") != 1:
        raise ContractError("synthetic search minimum result count must remain fixed")
    if search.get("must_match_visible_result_count") is not True:
        raise ContractError("search result count parity is mandatory")
    if search.get("must_not_be_labelled_inp") is not True:
        raise ContractError("synthetic search evidence must not be labelled INP")
    field = payload.get("field_cwv")
    if field != {
        "status_without_crux_or_rum": "UNKNOWN",
        "percentile": 75,
        "max_lcp_ms": 2500,
        "max_inp_ms": 200,
        "max_cls": 0.1,
        "required_for_claim": "field-cwv-passed",
    }:
        raise ContractError("field CWV boundary must remain fixed")
    return payload


def _report(violations: list[str]) -> dict[str, Any]:
    return {
        "status": "PASS" if not violations else "BLOCKED",
        "violations": violations,
        "field_cwv_status": "UNKNOWN",
    }


def evaluate_lab_evidence(contract: dict[str, Any], evidence: Any) -> dict[str, Any]:
    violations: list[str] = []
    if not isinstance(evidence, dict):
        return _report(["browser evidence root must be an object"])
    if evidence.get("schema") != "xmind-browser-lab-evidence.v1":
        violations.append("browser evidence schema mismatch")
    if evidence.get("origin") != contract["origin"]:
        violations.append("browser evidence origin mismatch")
    if evidence.get("cache") != "disabled":
        violations.append("browser evidence must use a disabled cache")
    protocol = contract["browser_evidence_protocol"]
    if evidence.get("network_profile") != protocol["network_profile"]:
        violations.append("browser network profile mismatch")
    if evidence.get("cpu_profile") != protocol["cpu_profile"]:
        violations.append("browser CPU profile mismatch")
    for field in ("browser_name", "browser_version", "os"):
        if not isinstance(evidence.get(field), str) or not evidence[field].strip():
            violations.append(f"browser evidence {field} is missing")
    if not _fresh_utc(evidence.get("captured_at_utc"), protocol["max_age_hours"],
                      protocol["allowed_clock_skew_minutes"]):
        violations.append("browser evidence timestamp is missing, invalid, or stale")
    routes = evidence.get("routes")
    if not isinstance(routes, dict):
        return _report(violations + ["browser routes evidence must be an object"])

    expected_paths = [route["path"] for route in contract["routes"]]
    if set(routes) != set(expected_paths):
        violations.append("browser evidence must contain exactly the fixed routes")
    lab = contract["lab_browser"]
    required_profiles = lab["required_profiles"]
    required_runs = contract["sampling"]["measured_runs"]
    numeric_fields = ("ttfb_ms", "fcp_ms", "lcp_ms", "cls")
    warmups = evidence.get("warmups")
    if not isinstance(warmups, dict):
        warmups = {}
        violations.append("browser warmup attestation is missing")

    for path in expected_paths:
        profiles = routes.get(path)
        if not isinstance(profiles, dict):
            violations.append(f"{path}: route evidence is missing")
            continue
        if set(profiles) != set(required_profiles):
            violations.append(f"{path}: required browser profiles are incomplete")
        for profile in required_profiles:
            warmup = warmups.get(path, {}).get(profile) if isinstance(warmups.get(path), dict) else None
            if warmup != {"runs": protocol["warmup_runs_per_route_profile"],
                          "errors": protocol["max_warmup_errors"]}:
                violations.append(f"{path} [{profile}]: warmup attestation mismatch")
            samples = profiles.get(profile)
            label = f"{path} [{profile}]"
            expected_url = urllib.parse.urljoin(contract["origin"], path)
            viewport = protocol["profiles"][profile]
            if not isinstance(samples, list) or len(samples) != required_runs:
                violations.append(f"{label}: exactly {required_runs} runs are required")
                continue
            metric_values: dict[str, list[float]] = {key: [] for key in numeric_fields}
            for index, sample in enumerate(samples, start=1):
                if not isinstance(sample, dict):
                    violations.append(f"{label} run {index}: sample must be an object")
                    continue
                try:
                    for key in numeric_fields:
                        metric_values[key].append(_number(sample.get(key), f"{label} {key}"))
                except ValueError as exc:
                    violations.append(str(exc))
                    continue
                if sample.get("run_id") != protocol["measured_run_ids"][index - 1]:
                    violations.append(f"{label} run {index}: run identity mismatch")
                ttfb, fcp, lcp = (metric_values[key][-1] for key in ("ttfb_ms", "fcp_ms", "lcp_ms"))
                if ttfb <= 0 or fcp <= 0 or lcp <= 0 or not ttfb <= fcp <= lcp:
                    violations.append(f"{label} run {index}: timing metrics are zero or causally invalid")
                if sample.get("status") != 200 or sample.get("redirects") != 0:
                    violations.append(f"{label} run {index}: HTTP identity check failed")
                if sample.get("requested_url") != expected_url or sample.get("final_url") != expected_url:
                    violations.append(f"{label} run {index}: exact URL identity mismatch")
                if (sample.get("viewport_width") != viewport["width"]
                        or sample.get("viewport_height") != viewport["height"]):
                    violations.append(f"{label} run {index}: viewport identity mismatch")
                if sample.get("cache_disabled") is not True:
                    violations.append(f"{label} run {index}: per-run cache identity mismatch")
                if not _fresh_utc(sample.get("captured_at_utc"), protocol["max_age_hours"],
                                  protocol["allowed_clock_skew_minutes"]):
                    violations.append(f"{label} run {index}: timestamp is missing, invalid, or stale")
                if sample.get("main_content_visible") is not True:
                    violations.append(f"{label} run {index}: main content is not visible")
                for field, threshold_key in (
                    ("console_warnings", "max_console_warnings"),
                    ("console_errors", "max_console_errors"),
                    ("failed_requests", "max_failed_requests"),
                ):
                    value = sample.get(field)
                    if (not isinstance(value, int) or isinstance(value, bool)
                            or value < 0 or value > lab[threshold_key]):
                        violations.append(f"{label} run {index}: {field} exceeds budget")

            if any(len(values) != required_runs for values in metric_values.values()):
                continue
            percentile = contract["sampling"]["percentile"]
            for metric, threshold_key in (
                ("ttfb_ms", "max_p75_ttfb_ms"),
                ("fcp_ms", "max_p75_fcp_ms"),
                ("lcp_ms", "max_p75_lcp_ms"),
                ("cls", "max_p75_cls"),
            ):
                value = nearest_rank(metric_values[metric], percentile)
                if value > lab[threshold_key]:
                    violations.append(f"{label}: p75 {metric} {value} exceeds {lab[threshold_key]}")
            if max(metric_values["lcp_ms"]) > lab["max_each_lcp_ms"]:
                violations.append(f"{label}: single-run LCP exceeds {lab['max_each_lcp_ms']}ms")
            if max(metric_values["cls"]) > lab["max_each_cls"]:
                violations.append(f"{label}: single-run CLS exceeds {lab['max_each_cls']}")
    return _report(violations)


def evaluate_synthetic_search_evidence(contract: dict[str, Any], evidence: Any) -> dict[str, Any]:
    violations: list[str] = []
    search = contract["synthetic_search_response"]
    if not isinstance(evidence, dict):
        return _report(["synthetic search evidence is missing"])
    if evidence.get("metric") != "synthetic-search-response":
        violations.append("search metric must be named synthetic-search-response, not INP")
    if evidence.get("path") != search["path"]:
        violations.append("synthetic search path mismatch")
    expected_url = urllib.parse.urljoin(contract["origin"], search["path"])
    if evidence.get("requested_url") != expected_url or evidence.get("final_url") != expected_url:
        violations.append("synthetic search exact URL identity mismatch")
    if evidence.get("profile") != search["required_profile"]:
        violations.append("synthetic search profile mismatch")
    protocol = contract["browser_evidence_protocol"]
    expected_viewport = protocol["profiles"][search["required_profile"]]
    if (evidence.get("viewport_width") != expected_viewport["width"]
            or evidence.get("viewport_height") != expected_viewport["height"]):
        violations.append("synthetic search viewport identity mismatch")
    if evidence.get("cache_disabled") is not True:
        violations.append("synthetic search cache identity mismatch")
    if not _fresh_utc(evidence.get("captured_at_utc"), protocol["max_age_hours"],
                      protocol["allowed_clock_skew_minutes"]):
        violations.append("synthetic search timestamp is missing, invalid, or stale")
    queries = evidence.get("queries")
    if not isinstance(queries, dict) or set(queries) != set(search["queries"]):
        return _report(violations + ["synthetic search evidence must contain exactly the fixed queries"])
    for query in search["queries"]:
        samples = queries.get(query)
        if not isinstance(samples, list) or len(samples) != search["measured_runs_per_query"]:
            violations.append(f"search {query}: exact sample count is required")
            continue
        durations: list[float] = []
        for index, sample in enumerate(samples, start=1):
            if not isinstance(sample, dict):
                violations.append(f"search {query} run {index}: sample must be an object")
                continue
            try:
                duration = _number(sample.get("duration_ms"), "search duration_ms")
            except ValueError as exc:
                violations.append(str(exc))
                continue
            if duration <= 0:
                violations.append(f"search {query} run {index}: duration must be positive")
            durations.append(duration)
            if sample.get("run_id") != protocol["measured_run_ids"][index - 1]:
                violations.append(f"search {query} run {index}: run identity mismatch")
            counts = (sample.get("result_count"), sample.get("visible_article_count"))
            if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in counts):
                violations.append(f"search {query} run {index}: result counts must be non-negative integers")
            elif counts[0] != counts[1]:
                violations.append(f"search {query} run {index}: visible result count mismatch")
            elif counts[0] < search["min_visible_results_per_query"]:
                violations.append(f"search {query} run {index}: visible result count is below minimum")
        if len(durations) != search["measured_runs_per_query"]:
            continue
        if nearest_rank(durations, 75) > search["max_p75_ms"]:
            violations.append(f"search {query}: p75 response exceeds budget")
        if max(durations) > search["max_each_ms"]:
            violations.append(f"search {query}: single response exceeds budget")
    return _report(violations)


def example_transport_evidence(contract: dict[str, Any]) -> dict[str, Any]:
    routes: dict[str, list[dict[str, Any]]] = {}
    for route in contract["routes"]:
        url = urllib.parse.urljoin(contract["origin"], route["path"])
        routes[route["path"]] = [
            {
                "status": 200,
                "redirects": 0,
                "requested_url": url,
                "final_url": url,
                "content_type": "text/html",
                "content_marker_found": True,
                "ttfb_ms": 100 + index,
                "total_ms": 200 + index,
                "encoded_bytes": min(1000, route["max_encoded_bytes"]),
                "decoded_bytes": min(1000, route["max_decoded_bytes"]),
            }
            for index in range(contract["sampling"]["measured_runs"])
        ]
    return {
        "schema": "xmind-transport-evidence.v1",
        "origin": contract["origin"],
        "cache": "disabled",
        "warmup_errors": [],
        "routes": routes,
    }


def evaluate_transport_evidence(contract: dict[str, Any], evidence: Any) -> dict[str, Any]:
    violations: list[str] = []
    if not isinstance(evidence, dict):
        return _report(["transport evidence root must be an object"])
    if evidence.get("schema") != "xmind-transport-evidence.v1":
        violations.append("transport evidence schema mismatch")
    if evidence.get("origin") != contract["origin"] or evidence.get("cache") != "disabled":
        violations.append("transport origin or cache protocol mismatch")
    if evidence.get("warmup_errors") != []:
        violations.append("one or more transport warmups failed")
    routes = evidence.get("routes")
    if not isinstance(routes, dict):
        return _report(violations + ["transport routes evidence must be an object"])
    expected_paths = [route["path"] for route in contract["routes"]]
    if set(routes) != set(expected_paths):
        violations.append("transport evidence must contain exactly the fixed routes")
    required_runs = contract["sampling"]["measured_runs"]
    percentile = contract["sampling"]["percentile"]

    for route in contract["routes"]:
        path = route["path"]
        samples = routes.get(path)
        if not isinstance(samples, list) or len(samples) != required_runs:
            violations.append(f"{path}: exactly {required_runs} transport runs are required")
            continue
        expected_url = urllib.parse.urljoin(contract["origin"], path)
        ttfb_values: list[float] = []
        total_values: list[float] = []
        for index, sample in enumerate(samples, start=1):
            label = f"{path} run {index}"
            if not isinstance(sample, dict):
                violations.append(f"{label}: sample must be an object")
                continue
            try:
                ttfb = _number(sample.get("ttfb_ms"), f"{label} TTFB")
                total = _number(sample.get("total_ms"), f"{label} total time")
                encoded = _number(sample.get("encoded_bytes"), f"{label} encoded bytes")
                decoded = _number(sample.get("decoded_bytes"), f"{label} decoded bytes")
            except ValueError as exc:
                violations.append(str(exc))
                continue
            ttfb_values.append(ttfb)
            total_values.append(total)
            if sample.get("status") != 200 or sample.get("redirects") != 0:
                violations.append(f"{label}: HTTP status or redirect policy failed")
            if sample.get("requested_url") != expected_url or sample.get("final_url") != expected_url:
                violations.append(f"{label}: final URL identity mismatch")
            if not str(sample.get("content_type", "")).lower().startswith("text/html"):
                violations.append(f"{label}: content type is not text/html")
            if sample.get("content_marker_found") is not True:
                violations.append(f"{label}: required content marker is missing")
            if ttfb > route["max_each_ttfb_ms"]:
                violations.append(f"{label}: TTFB exceeds single-run budget")
            if total > route["max_each_total_ms"]:
                violations.append(f"{label}: total time exceeds single-run budget")
            if encoded > route["max_encoded_bytes"] or decoded > route["max_decoded_bytes"]:
                violations.append(f"{label}: response size exceeds budget")
        if len(ttfb_values) != required_runs:
            continue
        if nearest_rank(ttfb_values, percentile) > route["max_p75_ttfb_ms"]:
            violations.append(f"{path}: p75 TTFB exceeds budget")
        if nearest_rank(total_values, percentile) > route["max_p75_total_ms"]:
            violations.append(f"{path}: p75 total time exceeds budget")
    return _report(violations)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    default_contract = Path(__file__).resolve().parents[1] / "configs" / "xmind-performance-budget.json"
    parser.add_argument("--contract", type=Path, default=default_contract)
    parser.add_argument("--lab-evidence", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    contract = load_contract(args.contract)
    transport = collect_transport_evidence(contract)
    transport_report = evaluate_transport_evidence(contract, transport)
    if args.lab_evidence is None:
        lab_report = _report(["browser lab evidence was not supplied"])
        search_report = _report(["synthetic search evidence was not supplied"])
    else:
        browser_evidence = json.loads(args.lab_evidence.read_text())
        lab_report = evaluate_lab_evidence(contract, browser_evidence)
        search_report = evaluate_synthetic_search_evidence(
            contract,
            browser_evidence.get("synthetic_search_response"),
        )
    status = (
        "PASS"
        if transport_report["status"] == lab_report["status"] == search_report["status"] == "PASS"
        else "BLOCKED"
    )
    print(
        json.dumps(
            {
                "schema": "xmind-performance-gate-report.v1",
                "status": status,
                "transport": transport_report,
                "lab_browser": lab_report,
                "synthetic_search_response": search_report,
                "field_cwv_status": "UNKNOWN",
                "claim_boundary": "lab/transport evidence is not field Core Web Vitals evidence",
                "transport_evidence": transport,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
