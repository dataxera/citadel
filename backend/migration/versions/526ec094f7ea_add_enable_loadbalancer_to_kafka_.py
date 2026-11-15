# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

"""add enable_loadbalancer to kafka platform

Revision ID: 526ec094f7ea
Revises: 28f414d381bc
Create Date: 2026-11-15 20:18:25.043374

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision: str = '526ec094f7ea'
down_revision: Union[str, Sequence[str], None] = '28f414d381bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema by adding enable_loadbalancer to kafka platform and kafka_external_url to state."""
    op.add_column(
        'mw_kafka_platform',
        sa.Column('enable_loadbalancer', sa.Boolean(), nullable=False, server_default=sa.text("false"))
    )
    op.add_column(
        'mw_kafka_platform_state',
        sa.Column('kafka_external_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema by dropping enable_loadbalancer from kafka platform and kafka_external_url from state."""
    op.drop_column('mw_kafka_platform_state', 'kafka_external_url')
    op.drop_column('mw_kafka_platform', 'enable_loadbalancer')
