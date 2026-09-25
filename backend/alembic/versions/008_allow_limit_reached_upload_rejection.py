"""allow limit_reached as an upload rejection kind

Revision ID: 008
Revises: 007
Create Date: 2026-09-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, Sequence[str], None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint('ck_uploads_rejection_kind', 'uploads', type_='check')
    op.create_check_constraint(
        'ck_uploads_rejection_kind',
        'uploads',
        "rejection_kind IN ('duplicate', 'invalid_file', 'limit_reached')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    # A rejection that was a Limit becomes a plain refusal of the file.
    op.execute(
        "UPDATE uploads SET rejection_kind = 'invalid_file' "
        "WHERE rejection_kind = 'limit_reached'"
    )
    op.drop_constraint('ck_uploads_rejection_kind', 'uploads', type_='check')
    op.create_check_constraint(
        'ck_uploads_rejection_kind',
        'uploads',
        "rejection_kind IN ('duplicate', 'invalid_file')",
    )
