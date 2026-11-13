# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

"""add doris_ids to superset platform

Revision ID: c34b29c1d559
Revises: edac50a5d2aa
Create Date: 2026-10-30 13:57:14.274296

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision: str = 'c34b29c1d559'
down_revision: Union[str, Sequence[str], None] = 'edac50a5d2aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema by adding doris_ids column to mw_superset_platform."""
    op.add_column(
        'mw_superset_platform',
        sa.Column('doris_ids', sqlalchemy_utils.types.json.JSONType(), nullable=True)
    )
    op.execute("UPDATE mw_superset_platform SET doris_ids = '[]' WHERE doris_ids IS NULL")


def downgrade() -> None:
    """Downgrade schema by dropping doris_ids column from mw_superset_platform."""
    op.drop_column('mw_superset_platform', 'doris_ids')
