# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

"""add integrations_status and sync_state to cluster status

Revision ID: d8a9e4c1b203
Revises: c32a8f604cf4
Create Date: 2026-11-16 06:42:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = 'd8a9e4c1b203'
down_revision: Union[str, Sequence[str], None] = 'c32a8f604cf4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema by adding integrations_status and sync_state to mw_k8s_cluster_status."""
    op.add_column(
        'mw_k8s_cluster_status',
        sa.Column(
            'integrations_status',
            sqlalchemy_utils.types.json.JSONType(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        'mw_k8s_cluster_status',
        sa.Column(
            'sync_state',
            sqlalchemy_utils.types.json.JSONType(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema by dropping integrations_status and sync_state from mw_k8s_cluster_status."""
    op.drop_column('mw_k8s_cluster_status', 'sync_state')
    op.drop_column('mw_k8s_cluster_status', 'integrations_status')
