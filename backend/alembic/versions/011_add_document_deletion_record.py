"""add documents.deleted_at and documents.deleted_by

Revision ID: 011
Revises: 010
Create Date: 2026-10-02 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: Union[str, Sequence[str], None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "documents", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("documents", sa.Column("deleted_by", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_documents_deleted_by_users",
        "documents",
        "users",
        ["deleted_by"],
        ["id"],
        ondelete="SET NULL",
    )
    # Older deleted rows get updated_at as an approximate time so the CHECK holds.
    op.execute(
        "UPDATE documents SET deleted_at = updated_at "
        "WHERE ingestion_status = 'deleted'"
    )
    op.create_check_constraint(
        "ck_documents_deleted_at_iff_deleted",
        "documents",
        "(ingestion_status = 'deleted') = (deleted_at IS NOT NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "ck_documents_deleted_at_iff_deleted", "documents", type_="check"
    )
    op.drop_constraint("fk_documents_deleted_by_users", "documents", type_="foreignkey")
    op.drop_column("documents", "deleted_by")
    op.drop_column("documents", "deleted_at")
