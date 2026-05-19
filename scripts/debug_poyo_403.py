#!/usr/bin/env python3
"""Debug why httpx gets 403 but curl works."""
import asyncio, sys, json, os, subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

API_KEY = os.getenv("POYO_API_KEY")
BODY = {"model": "seedance-2", "input": {"prompt": "test", "duration": 5}}

def test_curl():
    print("=== Test 1: subprocess curl ===")
    result = subprocess.run([
        "curl", "-s", "-w", "\nHTTP_CODE:%{http_code}\n",
        "-X", "POST", "https://api.poyo.ai/api/generate/submit",
        "-H", f"Authorization: Bearer {API_KEY}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(BODY),
    ], capture_output=True, text=True)
    print(result.stdout[-200:])
    print("---")

async def test_httpx_plain():
    print("=== Test 2: httpx with no extras ===")
    import httpx
    async with httpx.AsyncClient() as c:
        r = await c.post("https://api.poyo.ai/api/generate/submit",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            content=json.dumps(BODY).encode(),
        )
        print(f"status: {r.status_code}")
        print(f"body: {r.text[:200]}")
        print(f"headers sent: {dict(r.request.headers)}")
    print("---")

async def test_httpx_with_ua():
    print("=== Test 3: httpx with curl-like User-Agent ===")
    import httpx
    async with httpx.AsyncClient() as c:
        r = await c.post("https://api.poyo.ai/api/generate/submit",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "curl/8.0.0",
                "Accept": "*/*",
            },
            content=json.dumps(BODY).encode(),
        )
        print(f"status: {r.status_code}")
        print(f"body: {r.text[:200]}")
    print("---")

async def test_httpx_http1():
    print("=== Test 4: httpx forcing HTTP/1.1 ===")
    import httpx
    limits = httpx.Limits(max_keepalive_connections=0)
    async with httpx.AsyncClient(http2=False, limits=limits) as c:
        r = await c.post("https://api.poyo.ai/api/generate/submit",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            content=json.dumps(BODY).encode(),
        )
        print(f"status: {r.status_code}")
        print(f"body: {r.text[:200]}")
    print("---")

async def main():
    if not API_KEY:
        raise SystemExit("POYO_API_KEY is required")
    test_curl()
    await test_httpx_plain()
    await test_httpx_with_ua()
    await test_httpx_http1()

asyncio.run(main())
