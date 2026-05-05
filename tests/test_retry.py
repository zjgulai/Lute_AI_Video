"""Tests for retry_with_backoff utility — GAP-1 proof."""

import asyncio
import pytest

from src.tools.retry import (
    retry_with_backoff,
    MaxRetriesExceededError,
    is_retryable,
)


class TestIsRetryable:
    def test_connection_error_is_retryable(self):
        assert is_retryable(Exception("Connection refused"))

    def test_timeout_is_retryable(self):
        assert is_retryable(Exception("timed out"))
        assert is_retryable(Exception("Timeout"))

    def test_http_429_is_retryable(self):
        assert is_retryable(Exception("429 Too Many Requests"))

    def test_http_5xx_is_retryable(self):
        assert is_retryable(Exception("500 Internal Server Error"))
        assert is_retryable(Exception("503 Service Unavailable"))

    def test_http_4xx_non_retryable(self):
        assert not is_retryable(Exception("400 Bad Request"))
        assert not is_retryable(Exception("401 Unauthorized"))
        assert not is_retryable(Exception("403 Forbidden"))
        assert not is_retryable(Exception("404 Not Found"))

    def test_eof_and_reset(self):
        assert is_retryable(Exception("EOF occurred"))
        assert is_retryable(Exception("connection reset by peer"))

    def test_dns_unreachable(self):
        assert is_retryable(Exception("Name or service not known"))
        assert is_retryable(Exception("no route to host"))

    def test_generic_exception_not_retryable(self):
        assert not is_retryable(Exception("some weird error"))


class TestRetryWithBackoff:
    async def test_success_on_first_attempt(self):
        call_count = 0

        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await retry_with_backoff(succeed)
        assert result == "ok"
        assert call_count == 1

    async def test_retries_then_succeeds(self):
        call_count = 0

        async def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Connection refused")
            return "ok"

        result = await retry_with_backoff(fails_twice, max_retries=3)
        assert result == "ok"
        assert call_count == 3

    async def test_exhausts_retries_raises_error(self):
        call_count = 0

        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise Exception("Connection refused")

        with pytest.raises(MaxRetriesExceededError):
            await retry_with_backoff(always_fails, max_retries=2, base_delay=0.01)

        # 1 initial + 2 retries = 3 attempts
        assert call_count == 3

    async def test_non_retryable_error_raised_immediately(self):
        call_count = 0

        async def bad_request():
            nonlocal call_count
            call_count += 1
            raise Exception("400 Bad Request")

        with pytest.raises(Exception, match="400 Bad Request"):
            await retry_with_backoff(bad_request, max_retries=3, base_delay=0.01)

        assert call_count == 1

    async def test_zero_retries_no_retry(self):
        """max_retries=0 should attempt once and fail immediately."""
        call_count = 0

        async def fail():
            nonlocal call_count
            call_count += 1
            raise Exception("Connection refused")

        with pytest.raises(MaxRetriesExceededError):
            await retry_with_backoff(fail, max_retries=0, base_delay=0.01)

        assert call_count == 1  # one attempt only

    async def test_retry_count_matches_max_retries(self):
        """Verify exact retry count behavior: attempt 1 + max_retries retries."""
        call_count = 0

        async def fail():
            nonlocal call_count
            call_count += 1
            raise Exception("timed out")

        with pytest.raises(MaxRetriesExceededError):
            await retry_with_backoff(fail, max_retries=2, base_delay=0.01)

        # 1 initial + 2 retries = 3
        assert call_count == 3

    async def test_backoff_delay_increases(self):
        """Verify that each retry waits longer than the previous."""
        import time

        call_count = 0

        async def fail():
            nonlocal call_count
            call_count += 1
            raise Exception("Connection refused")

        start = time.monotonic()
        with pytest.raises(MaxRetriesExceededError):
            await retry_with_backoff(fail, max_retries=2, base_delay=0.1)
        elapsed = time.monotonic() - start

        # base=0.1: delays = ~0.1 + ~0.2 + jitter = at least 0.3s
        assert elapsed >= 0.25, f"Too fast: {elapsed:.3f}s"
        assert call_count == 3
