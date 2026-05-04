"""alter_threads_thread_id_to_text

Revision ID: a3c8f2d1b450
Revises: 1efc41794d64
Create Date: 2026-05-04 16:00:00.000000

P0-B: src/routers/pipeline.py 用 str(uuid.uuid4()) 生成完整 36 字符 UUID,
但旧 schema thread_id 列限定 VARCHAR(16) — PG 启用时 /pipeline/start 写入失败。
扩到 TEXT 不限长度,与 routers 对齐。

downgrade 注意:旧库若已存在 36 字符 thread_id,downgrade 会因长度超限失败。
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a3c8f2d1b450'
down_revision: Union[str, None] = '1efc41794d64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE threads ALTER COLUMN thread_id TYPE TEXT;")


def downgrade() -> None:
    op.execute("ALTER TABLE threads ALTER COLUMN thread_id TYPE VARCHAR(16);")
