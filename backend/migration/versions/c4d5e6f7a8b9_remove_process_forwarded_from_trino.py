# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

"""remove process_forwarded from trino platform

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-11-16 12:28:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop process_forwarded column from mw_trino_platform."""
    op.drop_column("mw_trino_platform", "process_forwarded")


def downgrade() -> None:
    """Re-add process_forwarded column to mw_trino_platform."""
    op.add_column(
        "mw_trino_platform",
        sa.Column(
            "process_forwarded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
