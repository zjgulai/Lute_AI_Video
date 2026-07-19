"""Add tenant-bound provider cost accounts and attempts.

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a6b7c8d9e0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_budget_accounts",
        sa.Column("account_id", UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("job_kind", sa.String(length=32), nullable=False),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column(
            "scenario_or_resource_type",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column("cap_usd_nanos", sa.BigInteger(), nullable=False),
        sa.Column(
            "reserved_usd_nanos",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "settled_usd_nanos",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("budget_source_kind", sa.String(length=32), nullable=False),
        sa.Column("budget_source_ref", sa.String(length=128), nullable=True),
        sa.Column("budget_policy_version", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("account_id", name="pk_job_budget_accounts"),
        sa.UniqueConstraint(
            "tenant_id",
            "job_kind",
            "job_id",
            name="uq_job_budget_accounts_tenant_job",
        ),
        sa.CheckConstraint(
            "job_kind IN ('canonical', 'compatibility')",
            name="ck_job_budget_accounts_job_kind",
        ),
        sa.CheckConstraint(
            "budget_source_kind IN ('server_config', 'validated_authorization')",
            name="ck_job_budget_accounts_source_kind",
        ),
        sa.CheckConstraint(
            "(budget_source_kind = 'server_config' AND budget_source_ref IS NULL) OR "
            "(budget_source_kind = 'validated_authorization' AND "
            "budget_source_ref IS NOT NULL)",
            name="ck_job_budget_accounts_source_ref",
        ),
        sa.CheckConstraint(
            "cap_usd_nanos > 0",
            name="ck_job_budget_accounts_cap",
        ),
        sa.CheckConstraint(
            "reserved_usd_nanos >= 0",
            name="ck_job_budget_accounts_reserved",
        ),
        sa.CheckConstraint(
            "settled_usd_nanos >= 0",
            name="ck_job_budget_accounts_settled",
        ),
        sa.CheckConstraint(
            "reserved_usd_nanos + settled_usd_nanos <= cap_usd_nanos",
            name="ck_job_budget_accounts_conservation",
        ),
    )

    op.create_table(
        "provider_cost_attempts",
        sa.Column("attempt_id", UUID(as_uuid=False), nullable=False),
        sa.Column("account_id", UUID(as_uuid=False), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("job_kind", sa.String(length=32), nullable=False),
        sa.Column("job_id", sa.String(length=128), nullable=False),
        sa.Column(
            "scenario_or_resource_type",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column("logical_operation", sa.String(length=160), nullable=False),
        sa.Column("ordinal", sa.BigInteger(), nullable=False),
        sa.Column("attempt_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("canonical_model", sa.String(length=128), nullable=False),
        sa.Column("provider_billing_region", sa.String(length=64), nullable=False),
        sa.Column("catalog_operation", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=16), nullable=False),
        sa.Column("billing_fact_kind", sa.String(length=32), nullable=False),
        sa.Column("price_rule_id", sa.String(length=160), nullable=False),
        sa.Column("price_catalog_version", sa.String(length=128), nullable=False),
        sa.Column("price_rule_version", sa.String(length=32), nullable=False),
        sa.Column("reservation_billing_facts", JSONB(), nullable=False),
        sa.Column("settlement_billing_facts", JSONB(), nullable=True),
        sa.Column("reserved_usd_nanos", sa.BigInteger(), nullable=False),
        sa.Column(
            "settled_usd_nanos",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("provider_reported_cost_usd_nanos", sa.BigInteger(), nullable=True),
        sa.Column(
            "provider_reported_credit_micro_units",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column("provider_reported_currency", sa.String(length=16), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("external_task_id", sa.String(length=128), nullable=True),
        sa.Column("provider_trace_id", sa.String(length=128), nullable=True),
        sa.Column("safe_error_code", sa.String(length=64), nullable=True),
        sa.Column("reservation_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submission_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("attempt_id", name="pk_provider_cost_attempts"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["job_budget_accounts.account_id"],
            name="fk_provider_cost_attempts_account",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "account_id",
            "logical_operation",
            "ordinal",
            name="uq_provider_cost_attempts_operation_ordinal",
        ),
        sa.CheckConstraint(
            "job_kind IN ('canonical', 'compatibility')",
            name="ck_provider_cost_attempts_job_kind",
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_provider_cost_attempts_ordinal"),
        sa.CheckConstraint(
            "reserved_usd_nanos > 0",
            name="ck_provider_cost_attempts_reserved",
        ),
        sa.CheckConstraint(
            "settled_usd_nanos >= 0 AND "
            "settled_usd_nanos <= reserved_usd_nanos",
            name="ck_provider_cost_attempts_settled",
        ),
        sa.CheckConstraint(
            "provider_reported_cost_usd_nanos IS NULL OR "
            "provider_reported_cost_usd_nanos >= 0",
            name="ck_provider_cost_attempts_reported_cost",
        ),
        sa.CheckConstraint(
            "provider_reported_credit_micro_units IS NULL OR "
            "provider_reported_credit_micro_units >= 0",
            name="ck_provider_cost_attempts_reported_credits",
        ),
        sa.CheckConstraint(
            "provider_reported_currency IS NULL OR provider_reported_currency = 'USD'",
            name="ck_provider_cost_attempts_reported_currency",
        ),
        sa.CheckConstraint(
            "provider_billing_region IN ('deepseek_global_usd', 'poyo_global_usd', "
            "'siliconflow_global_usd')",
            name="ck_provider_cost_attempts_region",
        ),
        sa.CheckConstraint(
            "catalog_operation IN ('chat_completion', 'speech_synthesis', "
            "'image_generation', 'text_to_video', 'image_to_video')",
            name="ck_provider_cost_attempts_catalog_operation",
        ),
        sa.CheckConstraint(
            "media_type IN ('text', 'audio', 'image', 'video')",
            name="ck_provider_cost_attempts_media_type",
        ),
        sa.CheckConstraint(
            "billing_fact_kind IN ('llm_tokens.v1', 'tts_utf8_bytes.v1', "
            "'image_count.v1', 'video_task.v1', 'video_duration.v1')",
            name="ck_provider_cost_attempts_fact_kind",
        ),
        sa.CheckConstraint(
            "state IN ('reserved', 'submission_started', 'submitted', 'settled', "
            "'released', 'ambiguous', 'accounting_error')",
            name="ck_provider_cost_attempts_state",
        ),
        sa.CheckConstraint(
            "(state = 'reserved' AND submission_started_at IS NULL "
            "AND submitted_at IS NULL AND terminal_at IS NULL "
            "AND settlement_billing_facts IS NULL AND settled_usd_nanos = 0) OR "
            "(state = 'submission_started' AND submission_started_at IS NOT NULL "
            "AND submitted_at IS NULL AND terminal_at IS NULL "
            "AND settlement_billing_facts IS NULL AND settled_usd_nanos = 0) OR "
            "(state = 'submitted' AND submission_started_at IS NOT NULL "
            "AND submitted_at IS NOT NULL AND terminal_at IS NULL "
            "AND settlement_billing_facts IS NULL AND settled_usd_nanos = 0) OR "
            "(state = 'settled' AND submission_started_at IS NOT NULL "
            "AND terminal_at IS NOT NULL AND settlement_billing_facts IS NOT NULL "
            "AND settled_usd_nanos > 0) OR "
            "(state = 'released' AND terminal_at IS NOT NULL "
            "AND settlement_billing_facts IS NULL AND settled_usd_nanos = 0) OR "
            "(state IN ('ambiguous', 'accounting_error') "
            "AND terminal_at IS NOT NULL AND settled_usd_nanos = 0 "
            "AND safe_error_code IS NOT NULL)",
            name="ck_provider_cost_attempts_state_fields",
        ),
    )
    op.create_index(
        "idx_provider_cost_attempts_account_state",
        "provider_cost_attempts",
        ["account_id", "state"],
    )
    op.execute(
        """
        CREATE INDEX idx_provider_cost_attempts_reservation_expiry
            ON provider_cost_attempts(reservation_expires_at)
            WHERE state = 'reserved'
        """
    )


def downgrade() -> None:
    op.drop_index(
        "idx_provider_cost_attempts_reservation_expiry",
        table_name="provider_cost_attempts",
    )
    op.drop_index(
        "idx_provider_cost_attempts_account_state",
        table_name="provider_cost_attempts",
    )
    op.drop_table("provider_cost_attempts")
    op.drop_table("job_budget_accounts")
