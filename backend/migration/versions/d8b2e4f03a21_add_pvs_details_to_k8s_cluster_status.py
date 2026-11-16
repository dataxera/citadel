# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

"""Add pvs_details column to k8s_cluster_status

Revision ID: d8b2e4f03a21
Revises: c7a1f3e92b10
Create Date: 2026-11-17 07:21:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = 'd8b2e4f03a21'
down_revision: Union[str, Sequence[str], None] = 'c7a1f3e92b10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add pvs_details column."""
    op.add_column(
        'dxc_k8s_cluster_status',
        sa.Column(
            'pvs_details',
            sqlalchemy_utils.types.json.JSONType(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema by removing pvs_details column."""
    op.drop_column('dxc_k8s_cluster_status', 'pvs_details')
