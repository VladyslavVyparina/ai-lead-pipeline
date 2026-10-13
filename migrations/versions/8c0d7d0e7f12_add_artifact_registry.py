"""add private artifact registry

Revision ID: 8c0d7d0e7f12
Revises: 43f2ce0b8d11
Create Date: 2026-07-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c0d7d0e7f12"
down_revision: Union[str, Sequence[str], None] = "43f2ce0b8d11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("business_id", sa.Integer(), nullable=False),
        sa.Column("website_build_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("storage_backend", sa.String(length=32), nullable=False),
        sa.Column("bucket", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("is_private", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"]),
        sa.ForeignKeyConstraint(["website_build_id"], ["website_builds.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index("ix_artifacts_business_id", "artifacts", ["business_id"], unique=False)
    op.create_index("ix_artifacts_website_build_id", "artifacts", ["website_build_id"], unique=False)
    op.create_index("ix_artifacts_sha256", "artifacts", ["sha256"], unique=False)
    op.create_index("ix_artifacts_expires_at", "artifacts", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_artifacts_expires_at", table_name="artifacts")
    op.drop_index("ix_artifacts_sha256", table_name="artifacts")
    op.drop_index("ix_artifacts_website_build_id", table_name="artifacts")
    op.drop_index("ix_artifacts_business_id", table_name="artifacts")
    op.drop_table("artifacts")
