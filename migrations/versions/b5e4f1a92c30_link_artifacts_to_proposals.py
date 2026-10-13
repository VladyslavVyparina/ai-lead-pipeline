"""link artifacts to proposals

Revision ID: b5e4f1a92c30
Revises: 8c0d7d0e7f12
Create Date: 2026-07-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b5e4f1a92c30"
down_revision: Union[str, Sequence[str], None] = "8c0d7d0e7f12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite cannot add a foreign key through ALTER TABLE. Batch mode recreates
    # the table safely and also recovers a local run interrupted after the
    # column was added but before the constraint could be created.
    existing_columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("artifacts")}
    with op.batch_alter_table("artifacts") as batch:
        if "proposal_id" not in existing_columns:
            batch.add_column(sa.Column("proposal_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_artifacts_proposal_id", "proposals", ["proposal_id"], ["id"])
        batch.create_index("ix_artifacts_proposal_id", ["proposal_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("artifacts") as batch:
        batch.drop_index("ix_artifacts_proposal_id")
        batch.drop_constraint("fk_artifacts_proposal_id", type_="foreignkey")
        batch.drop_column("proposal_id")
