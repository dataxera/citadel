# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

"""Add kube_prometheus_stack status columns

Revision ID: c7a1f3e92b10
Revises: 08254395e9bf
Create Date: 2026-11-16 20:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision: str = 'c7a1f3e92b10'
down_revision: Union[str, Sequence[str], None] = '08254395e9bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add kube_prometheus_stack status columns."""
    op.add_column(
        'dxc_k8s_cluster_status',
        sa.Column('kube_prometheus_stack_installed', sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        'dxc_k8s_cluster_status',
        sa.Column('kube_prometheus_stack_version', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema by removing kube_prometheus_stack status columns."""
    op.drop_column('dxc_k8s_cluster_status', 'kube_prometheus_stack_version')
    op.drop_column('dxc_k8s_cluster_status', 'kube_prometheus_stack_installed')
