"""add upload declared hash and rejection kind, unique live document hash per tenant

Revision ID: 007
Revises: 006
Create Date: 2026-09-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, Sequence[str], None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Uploads started before this column existed have no declared hash; they
    # fail the hash comparison at finalize and are refused as corrupt.
    op.add_column('uploads', sa.Column('declared_sha256', sa.String(length=64), nullable=False, server_default=''))
    op.alter_column('uploads', 'declared_sha256', server_default=None)
    op.add_column('uploads', sa.Column('rejection_kind', sa.String(), nullable=True))
    op.create_check_constraint(
        'ck_uploads_rejection_kind',
        'uploads',
        "rejection_kind IN ('duplicate', 'invalid_file')",
    )
    op.create_index(
        'uq_documents_tenant_content_hash_active',
        'documents',
        ['tenant_id', 'content_hash'],
        unique=True,
        postgresql_where=sa.text("ingestion_status <> 'deleted'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_documents_tenant_content_hash_active', table_name='documents')
    op.drop_constraint('ck_uploads_rejection_kind', 'uploads', type_='check')
    op.drop_column('uploads', 'rejection_kind')
    op.drop_column('uploads', 'declared_sha256')
