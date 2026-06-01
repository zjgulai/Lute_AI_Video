#!/usr/bin/env python3
"""Check that frontend OpenAPI TypeScript types match the local FastAPI app.

The guard never fetches `/openapi.json` from localhost or production. It imports
the local FastAPI app, writes a temporary OpenAPI schema, renders TypeScript with
the pinned local `openapi-typescript` binary, then compares the result.
"""

from __future__ import annotations

import argparse
import difflib
import io
import json
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = REPO_ROOT / "web"
GENERATED_TYPES = WEB_ROOT / "src" / "types" / "api.generated.ts"
GENERATOR = WEB_ROOT / "node_modules" / ".bin" / "openapi-typescript"


def export_local_openapi_schema(schema_path: Path) -> dict[str, Any]:
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()
    with redirect_stdout(captured_stdout), redirect_stderr(captured_stderr):
        from src.api import app

        schema = app.openapi()

    schema_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return schema


def _run_typegen(*, schema_path: Path, output_path: Path, generator: Path) -> None:
    if not generator.is_file():
        raise FileNotFoundError(
            f"openapi-typescript is not installed at {generator}. "
            "Run `cd web && npm install` before checking API type drift."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [str(generator), str(schema_path), "-o", str(output_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = "\n".join(part for part in [result.stdout, result.stderr] if part)
        raise RuntimeError(f"openapi-typescript failed with exit {result.returncode}\n{detail}")


def _diff_text(expected: str, actual: str, *, fromfile: str, tofile: str, limit: int = 240) -> str:
    diff = list(difflib.unified_diff(
        expected.splitlines(keepends=True),
        actual.splitlines(keepends=True),
        fromfile=fromfile,
        tofile=tofile,
    ))
    if len(diff) > limit:
        diff = diff[:limit] + [f"... diff truncated after {limit} lines\n"]
    return "".join(diff)


def check_or_write(
    *,
    generated_types: Path = GENERATED_TYPES,
    schema_path: Path | None = None,
    generator: Path = GENERATOR,
    write: bool = False,
) -> int:
    with tempfile.TemporaryDirectory(prefix="openapi-types-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        schema = schema_path or tmp_path / "openapi.json"
        rendered = generated_types if write else tmp_path / "api.generated.ts"

        export_local_openapi_schema(schema)
        _run_typegen(schema_path=schema, output_path=rendered, generator=generator)

        if write:
            print(f"OpenAPI types regenerated from local schema: {generated_types}")
            return 0

        expected = rendered.read_text(encoding="utf-8")
        actual = generated_types.read_text(encoding="utf-8") if generated_types.exists() else ""
        if expected == actual:
            print("OpenAPI generated types are up to date.")
            return 0

        print(
            "api.generated.ts is stale. Run `cd web && npm run typegen:api` "
            "and commit the regenerated file.",
            file=sys.stderr,
        )
        print(
            _diff_text(actual, expected, fromfile=str(generated_types), tofile="local-openapi-generated"),
            file=sys.stderr,
        )
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check frontend OpenAPI TypeScript drift")
    parser.add_argument("--write", action="store_true", help="Regenerate api.generated.ts in place")
    parser.add_argument("--generated-types", type=Path, default=GENERATED_TYPES)
    parser.add_argument("--schema-path", type=Path, default=None)
    parser.add_argument("--generator", type=Path, default=GENERATOR)
    args = parser.parse_args(argv)

    try:
        return check_or_write(
            generated_types=args.generated_types,
            schema_path=args.schema_path,
            generator=args.generator,
            write=args.write,
        )
    except Exception as exc:
        print(f"OpenAPI type drift check failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
