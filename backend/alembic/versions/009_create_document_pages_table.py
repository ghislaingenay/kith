"""create document_pages table

Revision ID: 009
Revises: 008
Create Date: 2026-09-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '009'
down_revision: Union[str, Sequence[str], None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('document_pages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('document_id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('page_number', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=True),
    sa.Column('extraction_method', sa.String(), nullable=False),
    sa.Column('ocr_confidence', sa.Float(), nullable=True),
    sa.Column('error_detail', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("extraction_method IN ('text_layer', 'extraction_error')", name='ck_document_pages_extraction_method'),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    # Retries re-extract every page from 1 (ADR-0010): this unique index
    # exists so a retry's writes upsert cleanly onto a prior attempt's
    # rows, not to prevent duplicates that could otherwise occur.
    op.create_index(
        'uq_document_pages_document_id_page_number',
        'document_pages',
        ['document_id', 'page_number'],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_document_pages_document_id_page_number', table_name='document_pages')
    op.drop_table('document_pages')
