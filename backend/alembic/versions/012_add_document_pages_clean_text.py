"""add document_pages.clean_text

Revision ID: 012
Revises: 011
Create Date: 2026-10-02 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: Union[str, Sequence[str], None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("document_pages", sa.Column("clean_text", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("document_pages", "clean_text")
