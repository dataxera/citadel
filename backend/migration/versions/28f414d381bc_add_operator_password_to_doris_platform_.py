# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

"""add operator_password to doris platform and state

Revision ID: 28f414d381bc
Revises: c34b29c1d559
Create Date: 2026-11-13 21:58:00.700787

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision: str = '28f414d381bc'
down_revision: Union[str, Sequence[str], None] = 'c34b29c1d559'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema by adding operator credentials to doris platform and state tables."""
    op.add_column(
        'mw_doris_platform',
        sa.Column('operator_password', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=sa.text("''"))
    )
    op.add_column(
        'mw_doris_platform_state',
        sa.Column('operator_user', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )
    op.add_column(
        'mw_doris_platform_state',
        sa.Column('operator_password', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema by dropping operator credentials from doris platform and state tables."""
    op.drop_column('mw_doris_platform_state', 'operator_password')
    op.drop_column('mw_doris_platform_state', 'operator_user')
    op.drop_column('mw_doris_platform', 'operator_password')
