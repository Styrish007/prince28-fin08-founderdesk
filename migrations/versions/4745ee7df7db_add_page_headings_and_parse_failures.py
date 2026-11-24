"""add page headings and parse_failures

Revision ID: 4745ee7df7db
Revises: 41dbe4766b59
Create Date: 2026-11-24 13:44:07.323344

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '4745ee7df7db'
down_revision: Union[str, Sequence[str], None] = '41dbe4766b59'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'parse_failures',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('path', sa.Text(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('reason', sa.String(length=50), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('attempts', sa.Integer(), server_default='1', nullable=False),
        sa.Column('first_failed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_parse_failures'))
    )
    op.create_index(op.f('ix_parse_failures_path'), 'parse_failures', ['path'], unique=True)
    op.create_index(op.f('ix_parse_failures_sha256'), 'parse_failures', ['sha256'], unique=False)
    op.add_column('pages', sa.Column('headings', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('pages', 'headings')
    op.drop_index(op.f('ix_parse_failures_sha256'), table_name='parse_failures')
    op.drop_index(op.f('ix_parse_failures_path'), table_name='parse_failures')
    op.drop_table('parse_failures')
