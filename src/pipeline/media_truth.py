"""Exact media simulation truth helpers shared by scenario pipelines."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def aggregate_simulated(items: Sequence[Mapping[str, Any]]) -> bool | None:
    """Return exact aggregate truth, or ``None`` when any item is unknown."""

    if not items:
        return None
    values = [item.get("simulated") for item in items]
    if any(type(value) is not bool for value in values):
        return None
    return any(value is True for value in values)


def media_paths(value: Any, key: str) -> list[str]:
    """Read canonical path collections while tolerating legacy path lists."""

    if isinstance(value, Mapping):
        paths = value.get(key)
    else:
        paths = value
    if not isinstance(paths, Sequence) or isinstance(paths, (str, bytes, bytearray)):
        return []
    return [path for path in paths if isinstance(path, str) and path]
