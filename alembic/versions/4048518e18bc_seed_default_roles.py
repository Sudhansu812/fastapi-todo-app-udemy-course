"""seed default roles

Revision ID: 4048518e18bc
Revises: 8a0b0f4c43df
Create Date: 2026-08-27 16:51:49.708261

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4048518e18bc'
down_revision: Union[str, Sequence[str], None] = '8a0b0f4c43df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


roles_table = sa.table(
    "roles",
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("description", sa.String),
    sa.column("is_active", sa.Boolean),
)

DEFAULT_ROLES = [
    {"code": "admin", "name": "Administrator", "description": "Full access to all resources.", "is_active": True},
    {"code": "user", "name": "User", "description": "Standard access — can manage their own todos.", "is_active": True},
]


def upgrade() -> None:
    """Upgrade schema."""
    op.bulk_insert(roles_table, DEFAULT_ROLES)


def downgrade() -> None:
    """Downgrade schema."""
    codes = [role["code"] for role in DEFAULT_ROLES]
    op.execute(roles_table.delete().where(roles_table.c.code.in_(codes)))
