# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import enum
from datetime import datetime
from typing import Optional, Any

from sqlmodel import Field, Column
from sqlalchemy import String, Enum as SQLEnum, DateTime, text
from sqlalchemy_utils import JSONType

from citadel.service import NamedBase
from citadel.fw.model import Base, ts_now


DEFAULT_TOPOLOGY_LEVELS: list[dict[str, str]] = [
    {"name": "region", "label": "Region", "key": "topology.kubernetes.io/region"},
    {"name": "zone", "label": "Zone", "key": "topology.kubernetes.io/zone"},
    {"name": "rack", "label": "Rack", "key": "topology.kubernetes.io/rack"},
]

DEFAULT_NODE_ROLES: tuple[str, ...] = (
    "ingest",
    "queue",
    "compute",
    "database",
    "warehouse",
    "application",
)


class K8sClusterType(enum.StrEnum):
    IN_CLUSTER = "in-cluster"
    REMOTE = "remote"


class K8sCluster(NamedBase, table=True):
    __tablename__ = "dxc_k8s_cluster"
    description: str = Field(default="", nullable=True)

    type: K8sClusterType = Field(
        default=K8sClusterType.REMOTE,
        sa_column=Column(
            SQLEnum(
                K8sClusterType,
                native_enum=False,
                values_callable=lambda x: [i.value for i in x],
            ),
            nullable=False,
            server_default=K8sClusterType.REMOTE.value,
        ),
    )
    kubeconfig: Optional[str] = Field(default=None, sa_type=String)
    topology_config: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONType(), nullable=False, server_default=text("'{}'")),
    )


class K8sClusterStatus(Base, table=True):
    __tablename__ = "dxc_k8s_cluster_status"

    k8s_cluster_id: int = Field(foreign_key="dxc_k8s_cluster.id", unique=True)
    status: str = Field(default="unknown")  # online, offline, error
    message: Optional[str] = Field(default=None)

    k8s_version: Optional[str] = Field(default=None)
    node_count: int = Field(default=0)
    nodes_status: dict[str, Any] = Field(default_factory=dict, sa_type=JSONType())
    nodes_details: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSONType())
    node_ips: list[str] = Field(default_factory=list, sa_type=JSONType())

    cpu_total: float = Field(default=0.0)
    cpu_allocated: float = Field(default=0.0)
    ram_total: float = Field(default=0.0)
    ram_allocated: float = Field(default=0.0)

    argocd_installed: bool = Field(default=False)
    argocd_version: Optional[str] = Field(default=None)

    cert_manager_installed: bool = Field(default=False)
    cert_manager_version: Optional[str] = Field(default=None)

    cnpg_installed: bool = Field(default=False)
    cnpg_version: Optional[str] = Field(default=None)

    cluster_issuer_installed: bool = Field(default=False)

    envoy_gateway_installed: bool = Field(default=False)
    envoy_gateway_version: Optional[str] = Field(default=None)

    kafka_operator_installed: bool = Field(default=False)
    kafka_operator_version: Optional[str] = Field(default=None)

    nifikop_installed: bool = Field(default=False)
    nifikop_version: Optional[str] = Field(default=None)

    doris_operator_installed: bool = Field(default=False)
    doris_operator_version: Optional[str] = Field(default=None)

    kube_prometheus_stack_installed: bool = Field(default=False)
    kube_prometheus_stack_version: Optional[str] = Field(default=None)

    integrations_status: dict[str, Any] = Field(default_factory=dict, sa_type=JSONType())
    sync_state: dict[str, Any] = Field(default_factory=dict, sa_type=JSONType())

    last_update: datetime = Field(
        default_factory=ts_now, sa_type=DateTime(timezone=True)
    )
