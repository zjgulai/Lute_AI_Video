"""Tests for GAP-16: PostgresSaver persistence in pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest
from langgraph.checkpoint.memory import MemorySaver

from src.graph.pipeline import compile_pipeline, get_pipeline_history


class TestPostgresSaver:
    """PostgresSaver integration tests.

    无真实 Postgres 时:
    - 不传 db_url → 使用 MemorySaver
    - 传 db_url 但连不上 → fail-fast raise RuntimeError(P0-04 / P1-2 设计)
    - 显式 checkpointer → 完全忽略 db_url
    """

    def test_compile_fallback_bad_db_url(self):
        """坏 db_url 必须 fail-fast,不再 silent fallback。

        P0-04 / P1-2: 生产依赖持久化,如果 db_url 设置但 PG 不可达,必须 raise
        RuntimeError 而不是退回 MemorySaver(那样会让用户以为有持久化但实际重启全丢)。
        """
        with pytest.raises(RuntimeError, match="PostgreSQL connection failed"):
            compile_pipeline(
                db_url="postgresql://localhost:9999/nonexistent"
            )

    def test_compile_no_db_url_uses_memory_saver(self):
        """显式不传 db_url 时,允许用 MemorySaver(开发/测试模式)。"""
        compiled = compile_pipeline()
        assert compiled.checkpointer is not None
        assert isinstance(compiled.checkpointer, MemorySaver)

    def test_custom_checkpointer_still_works(self):
        """Explicit checkpointer is not overridden by db_url."""
        custom = MemorySaver()
        compiled = compile_pipeline(
            checkpointer=custom,
            db_url="postgresql://localhost:9999/nonexistent",
        )
        # db_url should be ignored when checkpointer is provided
        assert compiled.checkpointer is custom


class TestPipelineHistory:
    """get_pipeline_history tests."""

    def test_history_nonexistent_thread(self):
        """Nonexistent thread → snapshots empty, status not_found."""
        compiled = compile_pipeline()
        result = get_pipeline_history(compiled, "nope-nope")
        assert result["status"] in ("not_found", "complete")
        assert isinstance(result["snapshots"], list)

    def test_history_after_stream(self):
        """After a pipeline run, history returns at least one snapshot."""
        compiled = compile_pipeline()
        from langchain_core.runnables import RunnableConfig
        config: RunnableConfig = {"configurable": {"thread_id": "history-test"}}  # type: ignore[typeddict-item]

        async def _run():
            return [ev async for ev in compiled.astream(
                {
                    "product_catalog": {},
                    "brand_guidelines": {},
                    "target_platforms": ["tiktok"],
                    "target_languages": ["en"],
                    "content_calendar_week": "2026-W17",
                    "current_step": "init",
                    "errors": [],
                    "human_reviews": {},
                    "pipeline_complete": False,
                },
                config,
            )]

        import asyncio

        asyncio.run(_run())
        result = get_pipeline_history(compiled, "history-test")
        assert len(result["snapshots"]) >= 1
        assert "target_platforms" in result["snapshots"][0]


class TestThreadIdSchema:
    """P0-B: threads.thread_id 必须能容纳 str(uuid.uuid4()) 36 字符串。"""

    INIT_SQL = Path(__file__).resolve().parent.parent / "src" / "storage" / "migrations" / "001_init.sql"

    def test_init_sql_uses_text_for_thread_id(self):
        """fresh `docker compose up` 装的 schema 必须用 TEXT 而不是 VARCHAR(16)。"""
        sql = self.INIT_SQL.read_text()
        assert "thread_id TEXT UNIQUE NOT NULL" in sql, (
            "init.sql 必须用 TEXT 容纳完整 UUID。当前 thread_id 列定义不匹配。"
        )
        assert "thread_id VARCHAR" not in sql, (
            "init.sql 残留旧 VARCHAR thread_id 定义,会与 routers/pipeline.py 的 "
            "uuid.uuid4() 36 字符值冲突。"
        )

    def test_alter_migration_exists(self):
        """alembic 必须有把现有 PG 库 thread_id 扩到 TEXT 的迁移。"""
        versions_dir = Path(__file__).resolve().parent.parent / "migrations" / "alembic" / "versions"
        migrations = list(versions_dir.glob("*alter*thread_id*text*.py"))
        assert migrations, (
            "缺 alembic 迁移把 threads.thread_id 从 VARCHAR(16) 扩到 TEXT。"
            "fresh PG 由 init.sql 建表,但已有 PG 库需要 alembic 迁移升级。"
        )


class TestStateModuleUsesPostgresWhenDatabaseUrlSet:
    """P0-E: _state.py 在有 DATABASE_URL 时必须用 PostgresSaver,而不是 MemorySaver。"""

    def test_state_module_picks_pg_when_db_url_set(self):
        """_state.py:21 读 DATABASE_URL/SUPABASE_DB_URL 决策 checkpointer 类型。"""
        import os

        # 本测试依赖 .env 里有真实 DATABASE_URL 指向可用 PG。CI 无 PG 时 skip。
        db_url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
        if not db_url or not db_url.startswith("postgresql"):
            pytest.skip("需要真实 DATABASE_URL 才能验 PostgresSaver 路径")

        try:
            import psycopg  # type: ignore[import-not-found]
            with psycopg.connect(db_url, connect_timeout=2) as conn:
                conn.close()
        except Exception as exc:  # type: ignore[misc]
            pytest.skip(f"DATABASE_URL 指向的 PG 当前不可达: {exc}")

        # 重新 import 触发模块顶部的 compile_pipeline(db_url=...)
        import importlib

        from src.routers import _state as state_mod

        importlib.reload(state_mod)

        try:
            from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore[import-not-found]
        except ImportError:
            pytest.skip("langgraph-postgres 未安装")

        pipeline = state_mod.get_pipeline()
        assert isinstance(pipeline.checkpointer, PostgresSaver), (
            f"DATABASE_URL 设置时 _state.py 应该用 PostgresSaver,实际用了 "
            f"{type(pipeline.checkpointer).__name__}"
        )
