"""Tests for src/routers/_state.coerce_video_duration.

Defends the dict-typed submit endpoints against non-numeric input that
historically reached seedance and crashed with TypeError. See V-2 QA
finding 2026-05-11 for the original reproduction.

Cases:
- Missing / None  -> default 30
- Pass-through    -> 15/30/45/60/90 returned as-is
- Numeric string  -> coerced to int + clamped
- Out-of-tier int -> clamped to nearest valid tier
- Float           -> truncated and clamped
- Garbage string  -> raises HTTPException(422) with Pydantic-shaped detail
- Bool            -> raises HTTPException(422)
- Other type      -> raises HTTPException(422)
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException


def test_missing_returns_default():
    from src.routers._state import coerce_video_duration

    assert coerce_video_duration({}) == 30
    assert coerce_video_duration({"video_duration": None}) == 30
    assert coerce_video_duration({}, default=60) == 60


@pytest.mark.parametrize("v", [15, 30, 45, 60, 90])
def test_valid_int_pass_through(v):
    from src.routers._state import coerce_video_duration

    assert coerce_video_duration({"video_duration": v}) == v


def test_numeric_string_coerced():
    from src.routers._state import coerce_video_duration

    assert coerce_video_duration({"video_duration": "30"}) == 30
    assert coerce_video_duration({"video_duration": "  45  "}) == 45


@pytest.mark.parametrize("input_v,expected", [
    (10, 15),
    (20, 15),
    (35, 30),
    (50, 45),
    (75, 60),
    (100, 90),
    (1000, 90),
])
def test_out_of_tier_int_clamps_to_nearest(input_v, expected):
    from src.routers._state import coerce_video_duration

    assert coerce_video_duration({"video_duration": input_v}) == expected


def test_float_truncated_and_clamped():
    from src.routers._state import coerce_video_duration

    assert coerce_video_duration({"video_duration": 30.7}) == 30
    assert coerce_video_duration({"video_duration": 14.9}) == 15


def test_garbage_string_raises_422():
    from src.routers._state import coerce_video_duration

    with pytest.raises(HTTPException) as exc_info:
        coerce_video_duration({"video_duration": "not-a-number"})
    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert isinstance(detail, list) and len(detail) == 1
    assert detail[0]["loc"] == ["body", "video_duration"]
    assert "not-a-number" in detail[0]["msg"]


def test_bool_raises_422():
    from src.routers._state import coerce_video_duration

    with pytest.raises(HTTPException) as exc_info:
        coerce_video_duration({"video_duration": True})
    assert exc_info.value.status_code == 422


def test_other_type_raises_422():
    from src.routers._state import coerce_video_duration

    with pytest.raises(HTTPException) as exc_info:
        coerce_video_duration({"video_duration": [30]})
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail[0]["loc"] == ["body", "video_duration"]
