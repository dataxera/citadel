# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

"""add enable_loadbalancer to pgsql platform

Revision ID: c32a8f604cf4
Revises: 526ec094f7ea
Create Date: 2026-11-16 01:11:00.879477

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision: str = 'c32a8f604cf4'
down_revision: Union[str, Sequence[str], None] = '526ec094f7ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema by adding enable_loadbalancer to pgsql platform."""
    op.add_column(
        'mw_pgsql_platform',
        sa.Column('enable_loadbalancer', sa.Boolean(), nullable=False, server_default=sa.text("false"))
    )


def downgrade() -> None:
    """Downgrade schema by dropping enable_loadbalancer from pgsql platform."""
    op.drop_column('mw_pgsql_platform', 'enable_loadbalancer')
