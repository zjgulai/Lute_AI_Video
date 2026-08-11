from __future__ import annotations

import pytest


def test_app_version_string():
    from src._version import APP_VERSION
    assert isinstance(APP_VERSION, str)
    assert APP_VERSION


def test_app_version_matches_pyproject():
    from pathlib import Path

    from src._version import APP_VERSION

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    text = pyproject.read_text()
    for line in text.splitlines():
        if line.startswith("version = "):
            expected = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
    else:
        pytest.skip("version not in pyproject.toml")
    assert APP_VERSION == expected or APP_VERSION == "0.0.0+dev"


def test_env_version_cannot_override_pyproject_authority(monkeypatch):
    from src import _version

    monkeypatch.setattr(_version, "_read_pyproject_version", lambda: "2.0.0")
    monkeypatch.setattr(_version, "version", lambda _name: "2.0.0")
    monkeypatch.setenv("APP_VERSION", "9.9.9")

    with pytest.raises(RuntimeError, match="pyproject authority"):
        _version.get_version()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a" * 40, "a" * 40),
        ("local-dev-dirty", "local-dev-dirty"),
        ("", "unavailable"),
        ("not-a-sha", "unavailable"),
    ],
)
def test_source_revision_is_strict_and_public(monkeypatch, raw, expected):
    from src import _version

    monkeypatch.setenv("RELEASE_SOURCE_SHA", raw)
    assert _version.get_source_revision() == expected


def test_health_endpoint_uses_dynamic_version():
    import inspect

    from src import _version
    from src.routers import health

    src = inspect.getsource(health)
    assert '"version": APP_VERSION' in src, "health.py should use APP_VERSION, not literal"
    assert _version.APP_VERSION in src or "APP_VERSION" in src


@pytest.mark.asyncio
async def test_liveness_exposes_version_and_source_revision_separately():
    from src._version import APP_SOURCE_REVISION, APP_VERSION
    from src.routers.health import liveness

    result = await liveness()

    assert result["version"] == APP_VERSION
    assert result["source_revision"] == APP_SOURCE_REVISION


def test_api_response_meta_uses_dynamic_version():
    import inspect

    from src import api

    src = inspect.getsource(api)
    assert "APP_VERSION" in src, "api.py should reference APP_VERSION"
    assert '"version": APP_VERSION' in src or 'version=APP_VERSION' in src
