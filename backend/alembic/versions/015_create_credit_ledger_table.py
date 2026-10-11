"""create credit_ledger table

Revision ID: 015
Revises: 014
Create Date: 2026-10-10 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "015"
down_revision: Union[str, Sequence[str], None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KINDS = "'ask_charge', 'adjustment'"


def upgrade() -> None:
    """Upgrade schema. Existing Tenants get no rows, so they start at 0
    Credits (ADR-0017: no backfill). `ask_id` gets its foreign key once the
    `asks` table exists."""
    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("tokens", sa.BigInteger(), nullable=False),
        sa.Column("ask_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(f"kind IN ({_KINDS})", name="ck_credit_ledger_kind"),
        sa.CheckConstraint(
            "kind <> 'adjustment' OR (note IS NOT NULL AND btrim(note) <> '')",
            name="ck_credit_ledger_adjustment_note",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credit_ledger_tenant_id", "credit_ledger", ["tenant_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_credit_ledger_tenant_id", table_name="credit_ledger")
    op.drop_table("credit_ledger")
