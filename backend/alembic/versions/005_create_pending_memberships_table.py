"""create pending_memberships table

Revision ID: 005
Revises: 004
Create Date: 2026-09-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, Sequence[str], None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('pending_memberships',
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False, server_default='pending'),
    sa.Column('invited_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("role IN ('owner', 'admin', 'member', 'viewer')", name='ck_pending_memberships_role'),
    sa.CheckConstraint("status IN ('pending', 'accepted', 'rejected', 'expired')", name='ck_pending_memberships_status'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('tenant_id', 'email')
    )
    op.create_index('idx_pending_memberships_email', 'pending_memberships', ['email'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_pending_memberships_email', table_name='pending_memberships')
    op.drop_table('pending_memberships')
