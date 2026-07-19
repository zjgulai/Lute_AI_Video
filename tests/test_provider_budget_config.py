"""W1-30 strict server-owned per-job budget parsing."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    ("raw", "expected_nanos"),
    [
        ("0.000000001", 1),
        ("1", 1_000_000_000),
        ("5.00", 5_000_000_000),
        ("9223372036.854775807", 2**63 - 1),
    ],
)
def test_budget_parser_accepts_only_exact_canonical_positive_decimal(
    raw: str,
    expected_nanos: int,
) -> None:
    from src.models.provider_cost import parse_provider_job_budget_usd_to_nanos

    assert parse_provider_job_budget_usd_to_nanos(raw) == expected_nanos


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        " ",
        " 5.00",
        "5.00 ",
        "0",
        "0.000000000",
        "-1",
        "+1",
        "01",
        ".5",
        "1.",
        "1e1",
        "1E1",
        "NaN",
        "Infinity",
        "inf",
        "0.0000000001",
        "1.1234567890",
        "9223372036.854775808",
    ],
)
def test_budget_parser_rejects_missing_ambiguous_noncanonical_and_overflow(
    raw: object,
) -> None:
    from src.models.provider_cost import (
        ProviderCostContractError,
        parse_provider_job_budget_usd_to_nanos,
    )

    with pytest.raises(ProviderCostContractError) as exc_info:
        parse_provider_job_budget_usd_to_nanos(raw)  # type: ignore[arg-type]
    assert exc_info.value.code == "provider_budget_configuration_invalid"


@pytest.mark.parametrize("raw", [1, 1.0, True, object()])
def test_budget_parser_never_accepts_non_string_authority(raw: object) -> None:
    from src.models.provider_cost import (
        ProviderCostContractError,
        parse_provider_job_budget_usd_to_nanos,
    )

    with pytest.raises(ProviderCostContractError):
        parse_provider_job_budget_usd_to_nanos(raw)  # type: ignore[arg-type]


def test_missing_budget_has_no_implicit_five_dollar_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PROVIDER_JOB_BUDGET_USD", raising=False)
    import src.config as config

    reloaded = importlib.reload(config)
    assert reloaded.PROVIDER_JOB_BUDGET_USD is None


def test_invalid_budget_does_not_break_import_or_eagerly_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROVIDER_JOB_BUDGET_USD", "not-a-decimal")
    import src.config as config

    reloaded = importlib.reload(config)
    assert reloaded.PROVIDER_JOB_BUDGET_USD == "not-a-decimal"

    from src.api import app
    from src.pipeline.generation_policy import GenerationSafetyIntent
    from src.services.fast_mode import FastModeService

    assert app is not None
    assert GenerationSafetyIntent().enable_media_synthesis is False
    assert FastModeService is not None


def test_example_documents_budget_as_comment_only() -> None:
    from pathlib import Path

    text = Path(".env.example").read_text(encoding="utf-8")
    assert "# PROVIDER_JOB_BUDGET_USD=5.00" in text
    assert "\nPROVIDER_JOB_BUDGET_USD=" not in text
