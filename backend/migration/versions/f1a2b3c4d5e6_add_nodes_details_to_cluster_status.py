# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

"""add nodes_details to cluster status

Revision ID: f1a2b3c4d5e6
Revises: d8a9e4c1b203
Create Date: 2026-11-16 07:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'd8a9e4c1b203'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema by adding nodes_details to mw_k8s_cluster_status."""
    op.add_column(
        'mw_k8s_cluster_status',
        sa.Column(
            'nodes_details',
            sqlalchemy_utils.types.json.JSONType(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema by dropping nodes_details from mw_k8s_cluster_status."""
    op.drop_column('mw_k8s_cluster_status', 'nodes_details')
