#!/usr/bin/env python3
"""Quick diagnosis of poyo.ai connectivity for image/video/tts services."""
import asyncio
import os
import sys

sys.path.insert(0, "/Users/pray/project/hermes_evo/AI_vedio")

from src.config import POYO_API_KEY, POYO_API_BASE_URL, POYO_IMAGE_MODEL


async def main():
    print(f"POYO_API_KEY:    {POYO_API_KEY[:20]}..." if POYO_API_KEY else "POYO_API_KEY:    NOT SET")
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
