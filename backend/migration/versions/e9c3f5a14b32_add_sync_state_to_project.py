# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

"""Add sync_state column to project

Revision ID: e9c3f5a14b32
Revises: d8b2e4f03a21
Create Date: 2026-11-19 22:46:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = 'e9c3f5a14b32'
down_revision: Union[str, Sequence[str], None] = 'd8b2e4f03a21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add sync_state column to dxc_project."""
    op.add_column(
        'dxc_project',
        sa.Column(
            'sync_state',
            sqlalchemy_utils.types.json.JSONType(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema by removing sync_state column from dxc_project."""
    op.drop_column('dxc_project', 'sync_state')
