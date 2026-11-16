# SPDX-FileCopyrightText: Copyright © 2025 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from typing import Optional
from sqlmodel import Field
from sqlalchemy import String
from citadel.service import NamedBase


class Project(NamedBase, table=True):
    __tablename__ = "dxc_project"
    description: str = Field(default="", nullable=True)
    k8s_namespace: Optional[str] = Field(
        default=None, sa_type=String(length=32), nullable=True
    )
    k8s_cluster_id: int = Field(foreign_key="dxc_k8s_cluster.id")
    ldap_config_id: Optional[int] = Field(
        default=None, foreign_key="dxc_ldap_config.id"
    )
    ingress_domain: Optional[str] = Field(
        default=None, sa_type=String(length=255), nullable=True
    )
    stack_id: Optional[int] = Field(
        default=None, foreign_key="dxc_stack.id", index=True
    )


