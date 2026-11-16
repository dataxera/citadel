# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

"""add topology_config to k8s_cluster

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-11-16 11:18:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema by adding topology_config to mw_k8s_cluster."""
    op.add_column(
        'mw_k8s_cluster',
        sa.Column(
            'topology_config',
            sqlalchemy_utils.types.json.JSONType(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema by dropping topology_config from mw_k8s_cluster."""
    op.drop_column('mw_k8s_cluster', 'topology_config')
