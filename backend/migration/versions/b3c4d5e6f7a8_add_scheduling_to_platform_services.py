# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

"""add cluster_role and deployment_method to platform services

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-11-16 12:06:30.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PLATFORM_TABLES = (
    "mw_pgsql_platform",
    "mw_hive_metastore_platform",
    "mw_trino_platform",
    "mw_superset_platform",
    "mw_airflow_platform",
    "mw_kafka_platform",
    "mw_nifi_platform",
    "mw_doris_platform",
)


def upgrade() -> None:
    """Add cluster_role and deployment_method columns to all platform service tables."""
    for table_name in PLATFORM_TABLES:
        op.add_column(
            table_name,
            sa.Column("cluster_role", sa.String(), nullable=True),
        )
        op.add_column(
            table_name,
            sa.Column(
                "deployment_method",
                sa.String(),
                nullable=False,
                server_default="default",
            ),
        )


def downgrade() -> None:
    """Drop cluster_role and deployment_method columns from all platform service tables."""
    for table_name in PLATFORM_TABLES:
        op.drop_column(table_name, "deployment_method")
        op.drop_column(table_name, "cluster_role")
