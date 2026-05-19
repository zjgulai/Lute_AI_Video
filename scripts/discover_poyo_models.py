#!/usr/bin/env python3
"""Discover available poyo.ai models by trial."""
import asyncio, httpx, os

API_KEY = os.getenv("POYO_API_KEY")
BASE = "https://api.poyo.ai"

IMAGE_MODELS = ["gpt-image-2", "gpt-image-1", "gpt-4o-image", "seedream", "dall-e-3", "dalle-3"]
AUDIO_MODELS = ["tts", "voice", "speech", "ai-music", "aimusic", "extend-music", "music"]

async def test_model(client, model, payload):
    body = {"model": model, "input": payload}
    try:
        r = await client.post("/api/generate/submit", json=body, timeout=30)
        data = r.json()
        code = data.get("code")
        if code == 200:
            task_id = data.get("data", {}).get("task_id")
            print(f"  ✅ {model}: task_id={task_id}")
            # Cancel immediately to avoid charges
            return True
        else:
            msg = data.get("message", data.get("msg", str(data)))
            print(f"  ❌ {model}: {msg[:120]}")
            return False
    except Exception as e:
        print(f"  ❌ {model}: {e}")
        return False

async def main():
    if not API_KEY:
        raise SystemExit("POYO_API_KEY is required")
    client = httpx.AsyncClient(
        base_url=BASE,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    print("=== Testing IMAGE models ===")
    img_payload = {"prompt": "A cute baby bottle on white background", "n": 1, "size": "1024x1792"}
    for m in IMAGE_MODELS:
        await test_model(client, m, img_payload)
    
    print("\n=== Testing AUDIO models ===")
    audio_payload = {"prompt": "A warm female voice saying hello", "duration": 5}
    for m in AUDIO_MODELS:
        await test_model(client, m, audio_payload)
    
    await client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
