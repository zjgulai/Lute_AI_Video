"""Test Sora 2 Pro availability via poyo.ai — stdlib only (urllib)."""

import pytest

# P0-C deferred: 这是 ad-hoc API 探查脚本,需要真实 POYO_API_KEY + 联网。
# 不应该作为单元测试常驻 CI。下一期决定:迁到 scripts/ 还是删除。
# 先 skip 让 P0-C 批量 add 测试时 CI 不红。
pytest.skip("P0-C deferred: ad-hoc API probe, not a unit test", allow_module_level=True)

import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# Load .env manually (stdlib)
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ[key.strip()] = val.strip()

POYO_API_KEY = os.getenv("POYO_API_KEY", "")
POYO_API_BASE = os.getenv("POYO_API_BASE_URL", "https://api.poyo.ai").rstrip("/")
OUTPUT_DIR = Path(__file__).parent.parent / "output" / "seedance"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SORA_MODELS = [
    # First test: known working model to verify API key + connectivity
    "seedance-2-fast",
    # Then try Sora variants
    "sora-2-pro",
    "sora-2",
    "sora-2.0-pro",
    "sora2-pro",
]

TEST_PROMPT = (
    "Scene: A close-up of hands organizing a baby's trunk organizer caddy, "
    "pulling out a diaper from a labeled compartment. "
    "Shot type: close-up. "
    "Action: hands reach into caddy, find diaper in 2 seconds. "
    "Lighting: natural warm daylight through car trunk. "
    "Camera: handheld intimate. "
    "Pacing: quick, authentic."
)


def api_post(url: str, body: dict) -> dict:
    """POST JSON, return parsed response."""
    data = json.dumps(body).encode()
    req = Request(url, data=data, headers={
        "Authorization": f"Bearer {POYO_API_KEY}",
        "Content-Type": "application/json",
    })
    try:
        resp = urlopen(req, timeout=30)
        return json.loads(resp.read())
    except HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return {"code": e.code, "message": str(e)}
    except Exception as e:
        return {"code": -1, "message": str(e)}


def api_get(url: str) -> dict:
    req = Request(url, headers={
        "Authorization": f"Bearer {POYO_API_KEY}",
    })
    try:
        resp = urlopen(req, timeout=15)
        return json.loads(resp.read())
    except HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return {"code": e.code, "message": str(e)}
    except Exception as e:
        return {"code": -1, "message": str(e)}


def download_file(url: str, filepath: Path) -> bool:
    try:
        req = Request(url, headers={"Authorization": f"Bearer {POYO_API_KEY}"})
        resp = urlopen(req, timeout=60)
        filepath.write_bytes(resp.read())
        return True
    except Exception as e:
        print(f"    Download error: {e}")
        return False


def test_model(model_name: str):  # -> dict | None
    print(f"\n{'='*50}")
    print(f"Testing model: {model_name}")
    print(f"{'='*50}")

    submit_body = {
        "model": model_name,
        "input": {
            "prompt": TEST_PROMPT,
            "aspect_ratio": "9:16",
            "resolution": "720p",
            "duration": 8,
            "generate_audio": False,
        },
    }

    # Step 1: Submit
    print(f"  Submitting...")
    print(f"  URL: {POYO_API_BASE}/api/generate/submit")
    submit_url = f"{POYO_API_BASE}/api/generate/submit"
    data = api_post(submit_url, submit_body)

    print(f"  Full response: {data}")
    code = data.get("code", -1)
    msg = data.get("message", "N/A")
    print(f"  Response code: {code}")
    print(f"  Message: {msg}")

    if code != 200:
        print(f"  ❌ Not available (code={code})")
        return None

    task_id = data.get("data", {}).get("task_id", "")
    if not task_id:
        print(f"  ❌ No task_id")
        return None

    print(f"  ✅ Task submitted: {task_id}")

    # Step 2: Poll
    status_url = f"{POYO_API_BASE}/api/generate/status/{task_id}"
    max_polls = 40
    for i in range(max_polls):
        time.sleep(5.0)
        status_data = api_get(status_url)
        task = status_data.get("data", {})
        status = task.get("status", "")
        progress = task.get("progress", 0)
        print(f"  Poll {i+1}: status={status}, progress={progress}%")

        if status == "finished":
            files = task.get("files", [])
            if files:
                video_url = files[0].get("file_url", "")
                print(f"  🎬 Video URL: {video_url}")
                filename = f"sora2pro_test_{model_name}_{task_id[:8]}.mp4"
                filepath = OUTPUT_DIR / filename
                if download_file(video_url, filepath):
                    size_mb = filepath.stat().st_size / (1024 * 1024)
                    print(f"  ✅ Downloaded: {filename} ({size_mb:.2f} MB)")
                    return {
                        "model": model_name,
                        "task_id": task_id,
                        "filepath": str(filepath),
                        "size_mb": size_mb,
                        "status": "success",
                    }
                else:
                    return {"model": model_name, "task_id": task_id, "status": "download_failed"}
            else:
                print(f"  ⚠️ Finished but no files in response")
                return {"model": model_name, "task_id": task_id, "status": "no_files"}

        if status == "failed":
            err = task.get("error_message", "unknown")
            print(f"  ❌ Task failed: {err}")
            return None

    print(f"  ⏰ Polling timed out after {max_polls * 5}s")
    return None


def quick_submit(model_name: str) -> str | None:
    """Submit only — return task_id if accepted, None otherwise."""
    submit_body = {
        "model": model_name,
        "input": {
            "prompt": TEST_PROMPT,
            "aspect_ratio": "9:16",
            "resolution": "720p",
            "duration": 8,
            "generate_audio": False,
        },
    }
    submit_url = f"{POYO_API_BASE}/api/generate/submit"
    data = api_post(submit_url, submit_body)
    code = data.get("code", -1)
    msg = data.get("message", "")
    tid = data.get("data", {}).get("task_id", "")
    status = "✅ ACCEPTED" if code == 200 else f"❌ {code} {msg}"
    print(f"  [{model_name:20s}] {status}")
    if tid:
        print(f"                    task_id={tid}")
    return tid if code == 200 else None


def main():
    print("Sora 2 Pro Availability Test via poyo.ai")
    print(f"Base URL: {POYO_API_BASE}")
    print(f"API Key: {'SET' if POYO_API_KEY else 'NOT SET'} ({POYO_API_KEY[:12]}...{POYO_API_KEY[-4:]})")

    if not POYO_API_KEY:
        print("❌ POYO_API_KEY not set. Check .env file.")
        return

    # Phase 1: Quick submit test for all models
    print("\n─── Phase 1: Submit test ───")
    candidates: dict[str, str] = {}  # model_name → task_id
    for model in SORA_MODELS:
        tid = quick_submit(model)
        if tid:
            candidates[model] = tid

    if not candidates:
        print(f"\n❌ No model accepted. All tried: {SORA_MODELS}")
        print(f"   Possible causes: API key lacks Sora access, or wrong base URL.")
        return

    # Phase 2: Poll the first accepted model
    print(f"\n─── Phase 2: Poll first accepted model ───")
    model, task_id = next(iter(candidates.items()))
    print(f"  Polling {model} task {task_id}...")
    status_url = f"{POYO_API_BASE}/api/generate/status/{task_id}"
    for i in range(40):
        time.sleep(5.0)
        status_data = api_get(status_url)
        task = status_data.get("data", {})
        status = task.get("status", "")
        progress = task.get("progress", 0)
        print(f"  Poll {i+1}: status={status}, progress={progress}%")
        if status == "finished":
            files = task.get("files", [])
            if files:
                video_url = files[0].get("file_url", "")
                print(f"  🎬 Downloading from: {video_url[:80]}...")
                filename = f"sora2pro_test_{model}_{task_id[:8]}.mp4"
                filepath = OUTPUT_DIR / filename
                if download_file(video_url, filepath):
                    size_mb = filepath.stat().st_size / (1024 * 1024)
                    print(f"\n{'='*70}")
                    print(f"✅ SUCCESS!")
                    print(f"   Model: '{model}'")
                    print(f"   Output: {filepath} ({size_mb:.2f} MB)")
                    print(f"{'='*70}")
                return
            else:
                print(f"  ⚠️ Finished but no files")
                return
        if status == "failed":
            err = task.get("error_message", "unknown")
            print(f"  ❌ Task failed: {err}")
            return
    print(f"  ⏰ Poll timeout")


if __name__ == "__main__":
    main()
