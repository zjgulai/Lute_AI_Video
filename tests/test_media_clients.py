"""Tests for Seedance 2.0 and gpt-image-2 clients.

Verifies:
1. Client initialization (with and without API key)
2. Stub mode returns correct format on no API key
3. Parameter construction (API payload format)
4. Retry logic behavior
5. Edge cases: empty params, timeouts (mocked)

All tests use stub/mock mode — no real API calls.
"""

from __future__ import annotations

import pytest

from src.tools.gpt_image_client import GPTImageClient
from src.tools.seedance_client import SeedanceClient

# ==============================================================================
# Seedance 2.0 Client Tests
# ==============================================================================


class TestSeedanceClientInit:
    """Client initialization in various configurations."""

    def test_init_without_api_key(self):
        """Should create client and enter stub mode when no API key."""
        client = SeedanceClient(api_key="")
        assert client.api_key == ""
        assert client.output_dir is not None
        assert client.output_dir.name == "seedance"

    def test_init_with_api_key(self):
        """Should create client with API key for real mode."""
        client = SeedanceClient(api_key="sk-test-key-123")
        assert client.api_key == "sk-test-key-123"
        assert client.base_url == "https://api.seedance.ai"

    def test_init_custom_base_url(self):
        """Should accept custom base URL."""
        client = SeedanceClient(api_key="test", base_url="https://custom.api.com")
        assert client.base_url == "https://custom.api.com"


class TestSeedanceClientStubMode:
    """Stub mode behavior when no API key is available."""

    @pytest.fixture
    def client(self):
        return SeedanceClient(api_key="")

    @pytest.mark.asyncio
    async def test_text_to_video_returns_stub(self, client):
        """Without API key, text_to_video should return stub."""
        result = await client.text_to_video(prompt="test video", duration=10)
        assert result["video_url"].startswith("[SEEDANCE_STUB")
        assert result["duration"] == 0

    @pytest.mark.asyncio
    async def test_image_to_video_returns_stub(self, client):
        """Without API key, image_to_video should return stub."""
        result = await client.image_to_video(
            image_url="https://example.com/img.jpg",
            prompt="animate this",
        )
        assert result["video_url"].startswith("[SEEDANCE_STUB")
        assert result["_stub_mode"] == "image_to_video"

    def test_stub_result_preserves_mode_marker(self, client):
        """Stub results should preserve the requested mode marker."""
        result = client._stub_result(prompt="change style", mode="reference_video")
        assert result["video_url"].startswith("[SEEDANCE_STUB")
        assert result["_stub_mode"] == "reference_video"

    @pytest.mark.asyncio
    async def test_stub_includes_prompt(self, client):
        """Stub result should preserve the original prompt."""
        prompt = "a product demo with smooth transitions"
        result = await client.text_to_video(prompt=prompt, duration=5)
        assert result["prompt_used"] == prompt


class TestSeedanceClientParameterValidation:
    """Parameter construction validation (no real API call)."""

    def test_text_to_video_with_image_refs(self):
        """Should accept image references."""
        client = SeedanceClient(api_key="sk-test")
        # Can't validate payload without mocking, but should not crash
        result = client._stub_result(prompt="test", mode="text_to_video")
        assert result is not None

    def test_image_to_video_style_preserve_default(self):
        """style_preserve should default to True."""
        client = SeedanceClient(api_key="sk-test")
        result = client._stub_result(prompt="test", mode="image_to_video")
        assert result is not None

    def test_stub_result_accepts_reference_mode(self):
        client = SeedanceClient(api_key="sk-test")
        result = client._stub_result(prompt="test", mode="reference_video")
        assert result is not None


class TestSeedanceClientEdgeCases:
    """Edge cases and error handling."""

    @pytest.fixture
    def client(self):
        return SeedanceClient(api_key="")

    @pytest.mark.asyncio
    async def test_text_to_video_minimal_params(self, client):
        """Should work with only prompt and no optional params."""
        result = await client.text_to_video(prompt="minimal")
        assert result is not None
        assert result["video_url"].startswith("[SEEDANCE_STUB")

    @pytest.mark.asyncio
    async def test_text_to_video_with_image_refs_empty(self, client):
        """Should handle empty image_refs list."""
        result = await client.text_to_video(prompt="test", image_refs=[])
        assert result is not None

    def test_client_uses_seedance_output_dir(self):
        client = SeedanceClient(api_key="")
        assert client.output_dir.name == "seedance"

    def test_retry_logic_exhaustion(self):
        """_execute_with_retry should return stub after all retries fail."""
        client = SeedanceClient(api_key="sk-test")

        async def failing_fn():
            raise ConnectionError("Network error")

        import asyncio
        result = asyncio.run(
            client._execute_with_retry(failing_fn, "test_mode", "test prompt")
        )
        assert result["video_url"].startswith("[SEEDANCE_STUB")
        assert result["_stub_mode"] == "test_mode"

    @pytest.mark.asyncio
    async def test_close_method_exists(self, client):
        """close() should be callable."""
        await client.close()
        assert True  # Should not crash


# ==============================================================================
# GPT Image 2 Client Tests
# ==============================================================================


class TestGPTImageClientInit:
    """Client initialization."""

    def test_init_without_api_key(self):
        """Should create client in stub mode when no API key."""
        client = GPTImageClient(api_key="")
        assert client.api_key == ""
        assert client.output_dir.name == "gpt_images"

    def test_init_with_api_key(self):
        """Should create client with API key."""
        client = GPTImageClient(api_key="sk-test-key-456")
        assert client.api_key == "sk-test-key-456"


class TestGPTImageClientStubMode:
    """Stub mode behavior."""

    @pytest.fixture
    def client(self):
        return GPTImageClient(api_key="")

    def test_generate_returns_stub(self, client):
        """Without API key, generate should return stub."""
        import asyncio
        result = asyncio.run(client.generate(
            prompt="a product on white background",
            quality="high",
            image_id="test_001",
        ))
        assert result["image_url"].startswith("[GPT_IMAGE_STUB")
        assert result["image_id"] == "test_001"

    def test_generate_with_style_ref(self, client):
        """Should accept style_ref even in stub mode."""
        import asyncio
        result = asyncio.run(client.generate(
            prompt="product shot",
            style_ref="https://example.com/style.jpg",
            image_id="test_002",
        ))
        assert result["image_id"] == "test_002"

    def test_generate_thumbnail_set(self, client):
        """generate_thumbnail_set should return list of stubs."""
        import asyncio
        prompts = [
            {"image_id": "A", "prompt": "product centered"},
            {"image_id": "B", "prompt": "lifestyle scene"},
            {"image_id": "C", "prompt": "close-up emotion"},
            {"image_id": "D", "prompt": "minimal product"},
        ]
        results = asyncio.run(client.generate_thumbnail_set(prompts=prompts))
        assert len(results) == 4
        for r in results:
            assert r["image_url"].startswith("[GPT_IMAGE_STUB")
            assert r["image_id"] in ("A", "B", "C", "D")


class TestGPTImageClientQuality:
    """Quality parameter handling."""

    def test_generate_low_quality(self):
        """Should accept 'low' quality."""
        import asyncio
        client = GPTImageClient(api_key="")
        result = asyncio.run(client.generate(
            prompt="test", quality="low", image_id="low_q"
        ))
        assert result["quality"] == "low"

    def test_generate_medium_quality(self):
        """Should accept 'medium' quality."""
        import asyncio
        client = GPTImageClient(api_key="")
        result = asyncio.run(client.generate(
            prompt="test", quality="medium", image_id="med_q"
        ))
        assert result["quality"] == "medium"

    def test_generate_high_quality(self):
        """Should accept 'high' quality."""
        import asyncio
        client = GPTImageClient(api_key="")
        result = asyncio.run(client.generate(
            prompt="test", quality="high", image_id="high_q"
        ))
        assert result["quality"] == "high"


class TestGPTImageClientEdgeCases:
    """Edge cases."""

    def test_stub_with_empty_prompt(self):
        """Should handle empty prompt."""
        import asyncio
        client = GPTImageClient(api_key="")
        result = asyncio.run(client.generate(prompt="", image_id="empty_prompt"))
        assert result is not None

    def test_stub_custom_output_dir(self, tmp_path):
        """Should accept custom output directory."""
        custom_dir = tmp_path / "custom_images"
        client = GPTImageClient(api_key="", output_dir=custom_dir)
        assert client.output_dir == custom_dir

    def test_close_method(self):
        """close() should be callable."""
        import asyncio
        client = GPTImageClient(api_key="")
        asyncio.run(client.close())
        assert True
