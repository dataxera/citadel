# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import logging
from typing import Literal
from fastapi import Depends, HTTPException
from kubernetes.client.rest import ApiException
from pydantic import BaseModel, Field
from mindweaver.fw.permission import require
from .service import K8sClusterService, _UNSET
from .state import K8sClusterState
from .permission import ConfigureNodes, Refresh, View

logger = logging.getLogger(__name__)

# Register state
K8sClusterService.with_state()(K8sClusterState)


class NodeLabelsUpdateRequest(BaseModel):
    """Payload for updating node labels, user-defined roles, and GPU provisioning labels."""

    set_labels: dict[str, str] = Field(default_factory=dict)
    remove_labels: list[str] = Field(default_factory=list)
    roles: list[str] | None = None
    gpu_vendor: Literal["nvidia", "amd", "none"] | None = None


class ClusterTopologyUpdateRequest(BaseModel):
    """Payload for updating cluster rack hierarchy roles, presets, and node assignments."""

    roles: list[str] | None = None
    presets: list[dict[str, str]] | None = None
    assignments: dict[str, dict[str, str | None]] | None = None


@K8sClusterService.model_view("POST", "/_refresh", dependencies=[require(Refresh)])
async def refresh_status_view(
    id: int, svc: K8sClusterService = Depends(K8sClusterService.get_service)
):
    """Manual status refresh view"""
    model = await svc.get(id)
    await svc.poll_status(model)
    return {"status": "success"}


@K8sClusterService.model_view(
    "PUT", "/_nodes/{node_name}/labels", dependencies=[require(ConfigureNodes)]
)
async def update_node_labels_view(
    id: int,
    node_name: str,
    payload: NodeLabelsUpdateRequest,
    svc: K8sClusterService = Depends(K8sClusterService.get_service),
):
    """Update labels, user-defined roles, and NVIDIA/AMD GPU provisioning labels for a node."""
    model = await svc.get(id)
    gpu_vendor = (
        payload.gpu_vendor if "gpu_vendor" in payload.model_fields_set else _UNSET
    )
    try:
        return await svc.update_node_labels(
            model=model,
            node_name=node_name,
            set_labels=payload.set_labels,
            remove_labels=payload.remove_labels,
            roles=payload.roles,
            gpu_vendor=gpu_vendor,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ApiException as e:
        status = e.status if e.status in (400, 404, 409, 422) else 502
        raise HTTPException(status_code=status, detail=e.reason or str(e)) from e


@K8sClusterService.model_view("GET", "/_topology", dependencies=[require(View)])
async def get_cluster_topology_view(
    id: int, svc: K8sClusterService = Depends(K8sClusterService.get_service)
):
    """Retrieve cluster rack hierarchy topology, user-defined roles, and node assignments."""
    model = await svc.get(id)
    return await svc.get_topology(model)


@K8sClusterService.model_view(
    "PUT", "/_topology", dependencies=[require(ConfigureNodes)]
)
async def update_cluster_topology_view(
    id: int,
    payload: ClusterTopologyUpdateRequest,
    svc: K8sClusterService = Depends(K8sClusterService.get_service),
):
    """Update cluster rack hierarchy topology, custom role catalog, and node assignments."""
    model = await svc.get(id)
    try:
        return await svc.update_topology(
            model=model,
            roles=payload.roles,
            presets=payload.presets,
            assignments=payload.assignments,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ApiException as e:
        status = e.status if e.status in (400, 404, 409, 422) else 502
        raise HTTPException(status_code=status, detail=e.reason or str(e)) from e


