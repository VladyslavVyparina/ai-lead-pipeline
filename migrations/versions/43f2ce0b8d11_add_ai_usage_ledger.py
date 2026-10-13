"""add AI usage ledger

Revision ID: 43f2ce0b8d11
Revises: 0e801a1684a5
Create Date: 2026-07-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "43f2ce0b8d11"
down_revision: Union[str, Sequence[str], None] = "0e801a1684a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_ledger",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=True),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("provider_request_id", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("usage_raw", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_ledger_business_id", "ai_usage_ledger", ["business_id"], unique=False)
    op.create_index(
        "ix_ai_usage_ledger_provider_request_id", "ai_usage_ledger", ["provider_request_id"], unique=False
    )
    op.create_index("ix_ai_usage_ledger_created_at", "ai_usage_ledger", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ai_usage_ledger_created_at", table_name="ai_usage_ledger")
    op.drop_index("ix_ai_usage_ledger_provider_request_id", table_name="ai_usage_ledger")
    op.drop_index("ix_ai_usage_ledger_business_id", table_name="ai_usage_ledger")
    op.drop_table("ai_usage_ledger")
