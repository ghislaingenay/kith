"""create tenants table

Revision ID: 003
Revises: 002
Create Date: 2026-09-16 23:21:06.245056

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, Sequence[str], None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('tenants',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('slug', sa.String(length=100), nullable=False),
    sa.Column('tier', sa.String(), nullable=False),
    sa.Column('max_users', sa.Integer(), nullable=False),
    sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("tier IN ('free', 'professional', 'enterprise')", name='ck_tenants_tier'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('tenants')
