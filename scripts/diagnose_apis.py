#!/usr/bin/env python3
"""Diagnose all external API dependencies for the S1 pipeline.

Usage:
  python scripts/diagnose_apis.py
  python scripts/diagnose_apis.py --json  # machine-readable output

Tests:
  1. LLM (Kimi) — connectivity + simple completion
  2. Seedance (via poyo.ai) — video generation submit status
  3. ElevenLabs — API key check, connectivity
  4. GPT-Image (via OpenAI) — API key check, connectivity
  5. Remotion — Node.js + npm check, binding check
  6. PostgreSQL — connection + table existence
  7. Filesystem — output directory write permission
  8. ffmpeg — binary availability + version

Each test returns: {"status": "ok|warning|error", "message": "...", "detail": {...}}
Exit code: 0 if all ok, 1 if warnings, 2 if errors
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path so we can import src.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from dotenv import load_dotenv

# Load .env before importing config
load_dotenv()

from src.config import (
    ELEVENLABS_API_KEY,
    KIMI_MODEL,
    OPENAI_API_KEY,
    OUTPUT_DIR,
    POYO_API_BASE_URL,
    POYO_API_KEY,
    SEEDANCE_API_BASE_URL,
    SEEDANCE_API_KEY,
)

# ── Terminal colors ──
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"

_OUTPUT_JSON = "--json" in sys.argv


def _color(status: str, text: str) -> str:
    if _OUTPUT_JSON:
        return text
    colors = {"ok": _GREEN, "warning": _YELLOW, "error": _RED}
    return f"{colors.get(status, '')}{text}{_RESET}"


def _print_result(name: str, result: dict) -> None:
    if _OUTPUT_JSON:
        return  # accumulated in all_results
    icon = {"ok": "PASS", "warning": "WARN", "error": "FAIL"}.get(result["status"], "????")
    colored = _color(result["status"], f"[{icon}]")
    print(f"  {colored}  {name}: {result['message']}")


all_results: list[dict[str, Any]] = []


def record(name: str, status: str, message: str, detail: dict | None = None) -> dict:
    result = {"name": name, "status": status, "message": message, "detail": detail or {}}
    all_results.append(result)
    _print_result(name, result)
    return result


# ═══════════════════════════════════════════════
#  1. LLM (Kimi) - connectivity + simple completion
# ═══════════════════════════════════════════════


async def check_llm() -> dict:
    """Try a simple prompt via the existing llm_client."""
    if not OPENAI_API_KEY:
        return record(
            "LLM (Kimi)",
            "warning",
            "OPENAI_API_KEY not set — Kimi/Moonshot uses the same key, skipping live test",
            {"provider": "kimi", "model": KIMI_MODEL, "api_key_set": False},
        )
    try:
        from src.tools.llm_client import LLMClient

        client = LLMClient(provider="kimi")
        response = await client.ainvoke(
            system_prompt="You are a helpful assistant.",
            user_message="Say hello in one short sentence.",
            model=KIMI_MODEL,
        )
        ok = bool(response and len(response.strip()) > 0)
        return record(
            "LLM (Kimi)",
            "ok" if ok else "error",
            f"Response received ({len(response)} chars)" if ok else "Empty response",
            {"provider": "kimi", "model": KIMI_MODEL, "response_preview": response[:120]},
        )
    except Exception as e:
        return record(
            "LLM (Kimi)",
            "error",
            f"Connection failed: {e}",
            {"provider": "kimi", "model": KIMI_MODEL, "error": str(e)[:300]},
        )


# ═══════════════════════════════════════════════
#  2. Seedance (via poyo.ai) — API key check + reachable
# ═══════════════════════════════════════════════


async def check_seedance() -> dict:
    """Check API key and base URL is reachable. Don't submit a job."""
    key = SEEDANCE_API_KEY or POYO_API_KEY
    base = POYO_API_BASE_URL if not SEEDANCE_API_KEY else SEEDANCE_API_BASE_URL

    if not key:
        return record(
            "Seedance",
            "warning",
            "No SEEDANCE_API_KEY or POYO_API_KEY — video generation will use stubs",
            {"api_key_set": False},
        )

    try:
        async with httpx.AsyncClient(
            base_url=base.rstrip("/"),
            headers={"Authorization": f"Bearer {key}"},
            timeout=10.0,
        ) as client:
            resp = await client.get("/api/generate/")
            # poyo.ai returns 200 or 4xx on the root; any response means reachable
            detail = {"base_url": base, "http_status": resp.status_code}
            if resp.status_code < 500:
                return record(
                    "Seedance",
                    "ok",
                    f"API reachable (HTTP {resp.status_code})",
                    detail,
                )
            else:
                return record(
                    "Seedance",
                    "warning",
                    f"API returned {resp.status_code} — may be degraded",
                    detail,
                )
    except httpx.ConnectError:
        return record(
            "Seedance",
            "error",
            f"Could not connect to {base}",
            {"base_url": base},
        )
    except Exception as e:
        return record(
            "Seedance",
            "error",
            f"Check failed: {e}",
            {"base_url": base, "error": str(e)[:300]},
        )


# ═══════════════════════════════════════════════
#  3. ElevenLabs — API key check, connectivity
# ═══════════════════════════════════════════════


async def check_elevenlabs() -> dict:
    """Check key is set. If not, note TTS will use poyo/Suno (music, not speech)."""
    if not ELEVENLABS_API_KEY:
        if POYO_API_KEY:
            return record(
                "TTS (ElevenLabs)",
                "warning",
                "No ELEVENLABS_API_KEY — TTS will fall back to poyo.ai (Suno music generation, not speech)",
                {"elevenlabs_key_set": False, "poyo_fallback": True},
            )
        else:
            return record(
                "TTS (ElevenLabs)",
                "warning",
                "No ELEVENLABS_API_KEY and no POYO_API_KEY — TTS will use stub audio files",
                {"elevenlabs_key_set": False, "poyo_fallback": False},
            )

    try:
        async with httpx.AsyncClient(
            base_url="https://api.elevenlabs.io/v1",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            timeout=10.0,
        ) as client:
            resp = await client.get("/voices")
            if resp.status_code == 200:
                data = resp.json()
                voice_count = len(data.get("voices", []))
                return record(
                    "TTS (ElevenLabs)",
                    "ok",
                    f"API key valid, {voice_count} voices available",
                    {"voice_count": voice_count},
                )
            elif resp.status_code == 401:
                return record(
                    "TTS (ElevenLabs)",
                    "error",
                    "API key rejected (HTTP 401)",
                    {"http_status": 401},
                )
            else:
                return record(
                    "TTS (ElevenLabs)",
                    "warning",
                    f"Unexpected HTTP {resp.status_code}",
                    {"http_status": resp.status_code},
                )
    except httpx.ConnectError:
        return record(
            "TTS (ElevenLabs)",
            "error",
            "Could not connect to api.elevenlabs.io",
        )
    except Exception as e:
        return record(
            "TTS (ElevenLabs)",
            "error",
            f"Check failed: {e}",
            {"error": str(e)[:300]},
        )


# ═══════════════════════════════════════════════
#  4. GPT-Image (via OpenAI) — API key check, connectivity
# ═══════════════════════════════════════════════


async def check_gpt_image() -> dict:
    """Check GPT-Image connectivity — prefers poyo.ai when available."""
    # poyo.ai proxy is preferred for GPT-Image (OPENAI_API_KEY may be a Kimi key)
    if POYO_API_KEY:
        try:
            from src.tools.poyo_client import PoyoClient
            poyo = PoyoClient()
            reachable = await poyo.test_connectivity()
            await poyo.close()
            if reachable:
                return record(
                    "GPT-Image (poyo.ai)",
                    "ok",
                    "poyo.ai proxy reachable — GPT-Image will use poyo backend",
                    {"backend": "poyo"},
                )
            return record(
                "GPT-Image (poyo.ai)",
                "warning",
                "poyo.ai unreachable — will try OpenAI or fall back to stubs",
                {"backend": "poyo_failed"},
            )
        except Exception:
            pass

    # Fallback: native OpenAI
    if not OPENAI_API_KEY:
        return record(
            "GPT-Image",
            "warning",
            "No POYO_API_KEY or OPENAI_API_KEY — thumbnail generation will use stubs",
            {"poyo_key_set": False, "openai_key_set": False},
        )

    try:
        async with httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            timeout=10.0,
        ) as client:
            resp = await client.get("/models")
            if resp.status_code == 200:
                models = resp.json().get("data", [])
                gpt_image_available = any(
                    m["id"] == "gpt-image-2" for m in models
                )
                return record(
                    "GPT-Image (OpenAI)",
                    "ok",
                    f"API key valid, gpt-image-2 {'available' if gpt_image_available else 'not seen'}",
                    {"gpt_image_2_available": gpt_image_available},
                )
            elif resp.status_code in (401, 403):
                if POYO_API_KEY:
                    return record(
                        "GPT-Image",
                        "warning",
                        "OpenAI key rejected but poyo.ai available — GPT-Image will use poyo",
                        {"openai_status": resp.status_code, "poyo_fallback": True},
                    )
                return record(
                    "GPT-Image (OpenAI)",
                    "error",
                    f"API key rejected (HTTP {resp.status_code})",
                    {"http_status": resp.status_code},
                )
            else:
                return record(
                    "GPT-Image (OpenAI)",
                    "warning",
                    f"Unexpected HTTP {resp.status_code}",
                    {"http_status": resp.status_code},
                )
    except httpx.ConnectError:
        return record(
            "GPT-Image (OpenAI)",
            "error",
            "Could not connect to api.openai.com",
        )
    except Exception as e:
        return record(
            "GPT-Image (OpenAI)",
            "error",
            f"Check failed: {e}",
            {"error": str(e)[:300]},
        )


# ═══════════════════════════════════════════════
#  5. Remotion — Node.js + npm check, binding check
# ═══════════════════════════════════════════════


def check_remotion() -> dict:
    """Check node exists, npm exists, remotion packages installed."""
    results = {}

    # Check Node.js
    node_path = shutil.which("node")
    if node_path:
        try:
            ver = subprocess.run(
                ["node", "--version"], capture_output=True, text=True, timeout=10
            )
            results["node"] = {"found": True, "version": ver.stdout.strip()}
        except Exception as e:
            results["node"] = {"found": True, "error": str(e)[:200]}
    else:
        results["node"] = {"found": False}

    # Check npm
    npm_path = shutil.which("npm")
    if npm_path:
        try:
            ver = subprocess.run(
                ["npm", "--version"], capture_output=True, text=True, timeout=10
            )
            results["npm"] = {"found": True, "version": ver.stdout.strip()}
        except Exception as e:
            results["npm"] = {"found": True, "error": str(e)[:200]}
    else:
        results["npm"] = {"found": False}

    # Check remotion package in rendering/
    rendering_dir = PROJECT_ROOT / "rendering"
    remotion_installed = False
    if (rendering_dir / "node_modules").exists():
        remotion_dir = rendering_dir / "node_modules" / "@remotion"
        if remotion_dir.exists() and any(remotion_dir.iterdir()):
            remotion_installed = True

    results["remotion_packages"] = {
        "found": remotion_installed,
        "rendering_dir": str(rendering_dir),
    }

    # Determine overall status
    errors = []
    warnings = []
    if not results["node"]["found"]:
        errors.append("Node.js not found on PATH")
    if not results["npm"]["found"]:
        errors.append("npm not found on PATH")
    if not remotion_installed:
        warnings.append("@remotion packages not installed in rendering/ — run: cd rendering && npm install")

    if errors:
        return record(
            "Remotion",
            "error",
            "; ".join(errors),
            results,
        )
    if warnings:
        return record(
            "Remotion",
            "warning",
            "; ".join(warnings),
            results,
        )
    return record(
        "Remotion",
        "ok",
        f"Node {results['node']['version']}, npm {results['npm']['version']}, @remotion packages OK",
        results,
    )


# ═══════════════════════════════════════════════
#  6. PostgreSQL — connection + table existence
# ═══════════════════════════════════════════════


async def check_postgres() -> dict:
    """Try asyncpg connection and check required tables."""
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn or not dsn.startswith("postgresql"):
        return record(
            "PostgreSQL",
            "warning",
            "No DATABASE_URL set (or not postgresql://) — pipeline will use SQLite/filesystem fallback",
            {"dsn_set": bool(dsn)},
        )

    try:
        import asyncpg

        conn = await asyncpg.connect(dsn, timeout=10)
        try:
            # Check connectivity
            val = await conn.fetchval("SELECT 1 AS test")
            connected = val == 1

            # Check required tables
            required = ["threads", "pipeline_states", "brand_packages", "influencers", "publish_logs"]
            present = []
            missing = []
            for table in required:
                exists = await conn.fetchval(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
                    table,
                )
                if exists:
                    present.append(table)
                else:
                    missing.append(table)

            if not missing:
                return record(
                    "PostgreSQL",
                    "ok",
                    f"Connected, all {len(present)} required tables present",
                    {"tables_present": present, "tables_missing": missing},
                )
            else:
                return record(
                    "PostgreSQL",
                    "warning",
                    f"Connected but tables missing: {', '.join(missing)}",
                    {"tables_present": present, "tables_missing": missing},
                )
        finally:
            await conn.close()
    except ImportError:
        return record(
            "PostgreSQL",
            "error",
            "asyncpg not installed — pip install asyncpg",
            {"library_available": False},
        )
    except Exception as e:
        return record(
            "PostgreSQL",
            "error",
            f"Connection failed: {e}",
            {"error": str(e)[:300], "dsn_prefix": dsn[:30] + "..." if len(dsn) > 30 else dsn},
        )


# ═══════════════════════════════════════════════
#  7. Filesystem — output directory write permission
# ═══════════════════════════════════════════════


def check_filesystem() -> dict:
    """Try writing and deleting a test file in output/."""
    try:
        test_file = OUTPUT_DIR / ".diagnose_write_test"
        test_file.write_text("diagnostic test")
        if not test_file.exists():
            return record(
                "Filesystem",
                "error",
                f"Write failed: {test_file} does not exist after write",
                {"output_dir": str(OUTPUT_DIR)},
            )
        test_file.unlink()
        return record(
            "Filesystem",
            "ok",
            f"Read/write OK in {OUTPUT_DIR}",
            {"output_dir": str(OUTPUT_DIR), "writable": True},
        )
    except PermissionError as e:
        return record(
            "Filesystem",
            "error",
            f"Permission denied writing to {OUTPUT_DIR}: {e}",
            {"output_dir": str(OUTPUT_DIR)},
        )
    except Exception as e:
        return record(
            "Filesystem",
            "error",
            f"Write test failed: {e}",
            {"output_dir": str(OUTPUT_DIR), "error": str(e)[:300]},
        )


# ═══════════════════════════════════════════════
#  8. ffmpeg — binary availability + version
# ═══════════════════════════════════════════════


def check_ffmpeg() -> dict:
    """Check ffmpeg binary is on PATH and get version."""
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        return record(
            "ffmpeg",
            "error",
            "ffmpeg not found on PATH — video assembly using ffmpeg will fail",
            {"available": False},
        )

    try:
        ver = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=10
        )
        first_line = ver.stdout.split("\n")[0] if ver.stdout else "(no output)"
        return record(
            "ffmpeg",
            "ok",
            first_line,
            {"available": True, "path": ffmpeg_path, "version": first_line},
        )
    except subprocess.TimeoutExpired:
        return record(
            "ffmpeg",
            "error",
            "ffmpeg -version timed out after 10s",
            {"available": True, "path": ffmpeg_path},
        )
    except Exception as e:
        return record(
            "ffmpeg",
            "error",
            f"ffmpeg check failed: {e}",
            {"available": True, "path": ffmpeg_path, "error": str(e)[:300]},
        )


# ═══════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════


async def main() -> int:
    print(f"{_BOLD}Hermes EVO — API Readiness Diagnostic{_RESET}")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Output dir:   {OUTPUT_DIR}")
    print(f"{'─' * 60}\n")

    # Run all checks (sync ones in executor, async ones directly)
    checks = [
        ("LLM (Kimi)", check_llm()),
        ("Seedance (poyo.ai)", check_seedance()),
        ("TTS (ElevenLabs)", check_elevenlabs()),
        ("GPT-Image (OpenAI)", check_gpt_image()),
        ("Remotion", asyncio.to_thread(check_remotion)),
        ("PostgreSQL", check_postgres()),
        ("Filesystem", asyncio.to_thread(check_filesystem)),
        ("ffmpeg", asyncio.to_thread(check_ffmpeg)),
    ]

    for name, coro in checks:
        try:
            await coro
        except Exception as e:
            record(name, "error", f"Unhandled exception in diagnostic: {e}", {"error": str(e)[:500]})

    # Summary
    print(f"\n{'─' * 60}")
    ok_count = sum(1 for r in all_results if r["status"] == "ok")
    warn_count = sum(1 for r in all_results if r["status"] == "warning")
    err_count = sum(1 for r in all_results if r["status"] == "error")

    print(f"{_BOLD}Summary:{_RESET}  {_color('ok', str(ok_count))} passed, "
          f"{_color('warning', str(warn_count))} warnings, "
          f"{_color('error', str(err_count))} errors "
          f"out of {len(all_results)} checks")

    if _OUTPUT_JSON:
        print(json.dumps(all_results, indent=2, default=str))
    else:
        # Print per-status details
        if err_count:
            print(f"\n{_BOLD}Errors:{_RESET}")
            for r in all_results:
                if r["status"] == "error":
                    print(f"  - {r['name']}: {r['message']}")
        if warn_count:
            print(f"\n{_BOLD}Warnings:{_RESET}")
            for r in all_results:
                if r["status"] == "warning":
                    print(f"  - {r['name']}: {r['message']}")

    if err_count:
        return 2
    if warn_count:
        return 1
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
