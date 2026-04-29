"""add assigned_users column to app_roles

Revision ID: f2_app_role_assigned_users
Revises: f1_merge_aa9_e2
Create Date: 2026-04-29

Adds a JSON-serialized text column for individual user (email) assignments,
parallel to the existing assigned_groups column. Auth resolution will treat
the two as OR-combined (slice in a follow-up PR per #197).

Idempotent: uses inspector to skip if the column already exists, in case the
migration has been hand-applied during development.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2_app_role_assigned_users'
down_revision: Union[str, None] = 'f1_merge_aa9_e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(col['name'] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    """Add assigned_users column with default '[]' for existing rows."""
    if not _has_column('app_roles', 'assigned_users'):
        op.add_column(
            'app_roles',
            sa.Column(
                'assigned_users',
                sa.Text(),
                nullable=False,
                server_default='[]',
            ),
        )


def downgrade() -> None:
    """Drop assigned_users column."""
    if _has_column('app_roles', 'assigned_users'):
        op.drop_column('app_roles', 'assigned_users')
