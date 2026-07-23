#!/usr/bin/env python3
"""Atomically bootstrap one empty PostgreSQL 18 database to the code head."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

_AUTH_VALUE = "APPLY_EMPTY_DATABASE_BASELINE"


class BootstrapError(RuntimeError):
    """Safe operator-facing bootstrap failure."""


def _validated_database_url() -> str:
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        raise BootstrapError("bootstrap_database_url_required")
    try:
        parsed = urlsplit(raw)
    except ValueError:
        raise BootstrapError("bootstrap_database_url_invalid") from None
    if (
        raw != raw.strip()
        or parsed.scheme not in {"postgres", "postgresql"}
        or not parsed.hostname
        or not parsed.path.strip("/")
        or parsed.fragment
    ):
        raise BootstrapError("bootstrap_database_url_invalid")
    prefix = "postgresql://" if parsed.scheme == "postgresql" else "postgres://"
    return "postgresql+psycopg://" + raw[len(prefix) :]


def _alembic_script(repo_root: Path) -> tuple[ScriptDirectory, str]:
    config = Config(str(repo_root / "migrations" / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(repo_root / "migrations" / "alembic"),
    )
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    if len(heads) != 1:
        raise BootstrapError("bootstrap_single_head_required")
    return script, heads[0]


def _assert_empty_postgres18(connection: object) -> None:
    identity = connection.execute(  # type: ignore[attr-defined]
        text(
            "SELECT current_database() AS database_name, "
            "current_setting('server_version_num') AS server_version_num"
        )
    ).mappings().one()
    if int(identity["server_version_num"]) // 10_000 != 18:
        raise BootstrapError("bootstrap_postgres18_required")
    existing = connection.execute(  # type: ignore[attr-defined]
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema() "
            "AND table_type = 'BASE TABLE' "
            "AND table_name <> 'alembic_version' "
            "ORDER BY table_name"
        )
    ).scalars().all()
    if existing:
        raise BootstrapError("database_not_empty_use_alembic_upgrade")
    version_table_exists = connection.execute(  # type: ignore[attr-defined]
        text(
            "SELECT EXISTS (SELECT FROM information_schema.tables "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'alembic_version')"
        )
    ).scalar_one()
    if version_table_exists:
        revisions = connection.execute(  # type: ignore[attr-defined]
            text("SELECT version_num FROM alembic_version LIMIT 1")
        ).scalars().all()
        if revisions:
            raise BootstrapError("database_has_alembic_lineage_use_upgrade")


def _assert_required_schema(connection: object) -> None:
    from src.storage.db import _REQUIRED_TABLE_COLUMNS, _REQUIRED_TABLES

    tables = set(
        connection.execute(  # type: ignore[attr-defined]
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema()"
            )
        ).scalars()
    )
    if not set(_REQUIRED_TABLES).issubset(tables):
        raise BootstrapError("bootstrap_required_schema_missing")
    for table_name, required_columns in _REQUIRED_TABLE_COLUMNS.items():
        columns = set(
            connection.execute(  # type: ignore[attr-defined]
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name = :table_name"
                ),
                {"table_name": table_name},
            ).scalars()
        )
        if not required_columns.issubset(columns):
            raise BootstrapError("bootstrap_required_schema_missing")


def bootstrap() -> tuple[str, int]:
    from src.storage.db import _REQUIRED_TABLES

    if os.environ.get("POSTGRES_BOOTSTRAP_AUTH") != _AUTH_VALUE:
        raise BootstrapError("bootstrap_authority_required")
    database_url = _validated_database_url()
    init_sql = (REPO_ROOT / "src" / "storage" / "migrations" / "001_init.sql").read_text(
        encoding="utf-8"
    )
    script, head_revision = _alembic_script(REPO_ROOT)
    engine = create_engine(database_url, poolclass=NullPool)
    try:
        with engine.begin() as connection:
            _assert_empty_postgres18(connection)
            connection.exec_driver_sql(init_sql)
            _assert_required_schema(connection)
            MigrationContext.configure(connection).stamp(script, head_revision)
            current_revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            if current_revision != head_revision:
                raise BootstrapError("bootstrap_revision_mismatch")
    finally:
        engine.dispose()
    return head_revision, len(_REQUIRED_TABLES)


def main() -> int:
    try:
        head_revision, table_count = bootstrap()
    except BootstrapError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR: postgres_bootstrap_failed", file=sys.stderr)
        return 1
    print(
        f"postgres_bootstrap=passed head={head_revision} required_tables={table_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
