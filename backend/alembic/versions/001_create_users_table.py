"""create users table

Revision ID: 001
Revises:
Create Date: 2026-09-16 23:21:06.245056

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('email_verified', sa.Boolean(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_users_email_active_unique', 'users', ['email'], unique=True, postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('idx_users_is_active', 'users', ['is_active'], unique=False, postgresql_where=sa.text('deleted_at IS NULL'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_users_is_active', table_name='users', postgresql_where=sa.text('deleted_at IS NULL'))
    op.drop_index('idx_users_email_active_unique', table_name='users', postgresql_where=sa.text('deleted_at IS NULL'))
    op.drop_table('users')
