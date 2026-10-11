"""create asks table

Revision ID: 016
Revises: 015
Create Date: 2026-10-11 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "016"
down_revision: Union[str, Sequence[str], None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUSES = "'completed', 'cut_off', 'failed', 'no_chunks'"


def upgrade() -> None:
    """Upgrade schema. Also gives the Credit Ledger's `ask_id` its foreign
    key, set to null when the Ask is deleted so its Ask Charge stays."""
    op.create_table(
        "asks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "cited_chunks", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("is_reranked", sa.Boolean(), nullable=False),
        sa.Column("is_degraded", sa.Boolean(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"status IN ({_STATUSES})", name="ck_asks_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_asks_tenant_id", "asks", ["tenant_id"])
    op.create_foreign_key(
        "credit_ledger_ask_id_fkey",
        "credit_ledger",
        "asks",
        ["ask_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("credit_ledger_ask_id_fkey", "credit_ledger", type_="foreignkey")
    op.drop_index("ix_asks_tenant_id", table_name="asks")
    op.drop_table("asks")
