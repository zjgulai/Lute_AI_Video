#!/usr/bin/env python3
"""Quick diagnosis of poyo.ai connectivity for image/video/tts services.

This submits a real poyo.ai image generation request and may consume credits.
Run only after recharge with CONFIRM_POYO_PROBE=1 and POYO_API_KEY set.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/Users/pray/project/hermes_evo/AI_vedio")

from src.config import POYO_API_BASE_URL, POYO_API_KEY, POYO_IMAGE_MODEL  # noqa: I001

CONFIRM_ENV = "CONFIRM_POYO_PROBE"


def mask_key(key: str) -> str:
    if len(key) <= 10:
        return "***"
    return f"{key[:6]}...{key[-4:]}"


def require_probe_confirmation() -> None:
    if os.getenv(CONFIRM_ENV) != "1":
        raise SystemExit(
            f"{CONFIRM_ENV}=1 is required because this script submits a real poyo.ai generation request "
            "and may consume credits."
        )


async def main():
    if not POYO_API_KEY:
        raise SystemExit("POYO_API_KEY is required")
    require_probe_confirmation()

    print(f"POYO_API_KEY:    {mask_key(POYO_API_KEY)}")
    print(f"POYO_BASE_URL:   {POYO_API_BASE_URL}")
    print(f"POYO_IMAGE_MODEL: {POYO_IMAGE_MODEL}")
    print("-" * 50)

    from src.tools.poyo_client import PoyoClient

    client = PoyoClient()

    # Test 1: Connectivity
    print("[Test 1] API connectivity...")
    health = await client.test_connectivity()
    print(f"  Reachable: {health['reachable']} (status: {health['status_code']})")
    print(f"  Detail: {health['detail']}")
    if not health['reachable']:
        print("  FAILED: Cannot reach poyo.ai API")
        await client.close()
        return

    # Test 2: Image generation (lightweight test)
    print("\n[Test 2] Image generation (gpt-image-2 via poyo)...")
    try:
        result = await client.submit_poll_download(
            model=POYO_IMAGE_MODEL,
            input_payload={
                "prompt": "A simple red circle on white background, minimal",
                "size": "1:1",
                "quality": "low",
            },
            output_path="/tmp/poyo_test_image.png",
            poll_interval=3.0,
            max_polls=40,
        )
        print(f"  SUCCESS: {result['file_url'][:60]}...")
        print(f"  Local: {result['local_path']}")
        print(f"  Size: {os.path.getsize(result['local_path'])} bytes")
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")

    await client.close()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
