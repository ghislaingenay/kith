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
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('status', sa.String(), server_default='pending', nullable=False),
    sa.Column('invited_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('accepted_by_user_id', sa.UUID(), nullable=True),
    sa.CheckConstraint("role IN ('owner', 'admin', 'member', 'viewer')", name='ck_pending_memberships_role'),
    sa.CheckConstraint("status IN ('pending', 'accepted', 'revoked', 'expired')", name='ck_pending_memberships_status'),
    sa.CheckConstraint('email = lower(btrim(email))', name='ck_pending_memberships_email_normalized'),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['accepted_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_pending_memberships_email', 'pending_memberships', ['email'], unique=False)
    op.create_index(
        'uq_pending_memberships_one_pending',
        'pending_memberships',
        ['tenant_id', 'email'],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_pending_memberships_one_pending', table_name='pending_memberships', postgresql_where=sa.text("status = 'pending'"))
    op.drop_index('idx_pending_memberships_email', table_name='pending_memberships')
    op.drop_table('pending_memberships')
