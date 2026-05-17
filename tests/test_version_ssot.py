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


def test_health_endpoint_uses_dynamic_version():
    from src import _version
    from src.routers import health
    import inspect

    src = inspect.getsource(health)
    assert '"version": APP_VERSION' in src, "health.py should use APP_VERSION, not literal"
    assert _version.APP_VERSION in src or "APP_VERSION" in src


def test_api_response_meta_uses_dynamic_version():
    from src import api
    import inspect

    src = inspect.getsource(api)
    assert "APP_VERSION" in src, "api.py should reference APP_VERSION"
    assert '"version": APP_VERSION' in src or 'version=APP_VERSION' in src
