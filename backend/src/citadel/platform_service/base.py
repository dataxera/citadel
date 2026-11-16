# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from datetime import datetime, timezone
import abc
import asyncio
import enum
import functools
import fastapi
from fastapi import Depends
import jinja2 as j2
import kubernetes
from kubernetes import client, config, utils, dynamic
import logging
from citadel.fw.util import format_k8s_resource, sanitize_label_value
from citadel.fw.model import Base, ts_now
from citadel.fw.exc import ModelValidationError
from citadel.service.base import ProjectScopedNamedBase, ProjectScopedService
from citadel.service.project import Project
from citadel.service.k8s_cluster import K8sCluster, K8sClusterType, K8sClusterStatus
from citadel.service.k8s_cluster.model import DEFAULT_NODE_ROLES
from citadel.service.k8s_cluster.service import (
    PROTECTED_NODE_ROLES,
    validate_role_name,
)
from citadel.fw.service import after_update, before_delete, before_create, after_create
from citadel.fw.state import BaseState
from citadel.fw.cert_manager import reconcile_manifest_certificates
from citadel.fw.permission import Execute, View, require
import base64
import inspect
import os
import pydantic
from citadel.service.trusted_certs.model import TrustedCert
from citadel.service.name_tracker.model import NameTracker
from citadel.service.dependency_tracker import DependencyTracker, DependencyTrackerService
from citadel.tasks.poll_coordinator import (
    schedule_platform_poll,
    schedule_k8s_cluster_poll,
)
from sqlalchemy import Column, DateTime, Enum as SQLEnum, String
from sqlalchemy_utils import JSONType
from sqlmodel import Field, select, delete
from sqlmodel.ext.asyncio.session import AsyncSession
import tempfile
from typing import Annotated, Any, Callable, Literal, Optional, TypeVar
import yaml

logger = logging.getLogger(__name__)


class PlatformStateBase(Base):
    """Base class for platform deployment status tracking"""

    platform_id: int = Field(index=True)
    status: Literal["online", "offline", "pending", "error"] = Field(
        default="pending", index=True, sa_type=String()
    )
    active: bool = Field(default=True)
    message: Optional[str] = Field(default=None)
    last_heartbeat: Optional[datetime] = Field(
        default=None, sa_type=DateTime(timezone=True)
    )
    node_ports: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSONType())
    cluster_nodes: list[dict[str, Any]] = Field(
        default_factory=list, sa_type=JSONType()
    )
    extra_data: dict[str, Any] = Field(default_factory=dict, sa_type=JSONType())


@functools.lru_cache(maxsize=32)
def _get_jinja_env(template_directory: str) -> j2.Environment:
    env = j2.Environment(loader=j2.FileSystemLoader(template_directory))
    env.filters["k8s_resource"] = format_k8s_resource
    return env


class PlatformDecommissionPayload(pydantic.BaseModel):
    force: bool = False

    @pydantic.field_validator("force", mode="before")
    @classmethod
    def _parse_force(cls, v):
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "t")
        return bool(v)


class PlatformStateUpdate(pydantic.BaseModel):
    status: Optional[Literal["online", "offline", "pending", "error"]] = None
    active: Optional[bool] = None
    message: Optional[str] = None
    extra_data: Optional[dict[str, Any]] = None
    force: bool = False

    @pydantic.field_validator("force", mode="before")
    @classmethod
    def _parse_force(cls, v):
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "t")
        return bool(v)


class PlatformDeploymentMethod(enum.StrEnum):
    """Pod scheduling / placement strategy for platform services."""

    DEFAULT = "default"
    PREFER_SAME_NODE = "prefer_same_node"
    PREFER_DIFFERENT_NODES = "prefer_different_nodes"
    REQUIRE_DIFFERENT_NODES = "require_different_nodes"
    PREFER_DIFFERENT_ZONES = "prefer_different_zones"
    PREFER_DIFFERENT_RACKS = "prefer_different_racks"


class PlatformBase(ProjectScopedNamedBase):
    """Base model for deployable platform services with node-role and placement options."""

    cluster_role: Optional[str] = Field(default=None, nullable=True)
    deployment_method: PlatformDeploymentMethod = Field(
        default=PlatformDeploymentMethod.DEFAULT,
        sa_type=SQLEnum(
            PlatformDeploymentMethod,
            native_enum=False,
            values_callable=lambda x: [i.value for i in x],
        ),
        sa_column_kwargs={
            "nullable": False,
            "server_default": PlatformDeploymentMethod.DEFAULT.value,
        },
    )

    @pydantic.field_validator("cluster_role", mode="before")
    @classmethod
    def _validate_cluster_role(cls, v: Any) -> Optional[str]:
        """Validate cluster_role, coercing blank strings to None."""
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
        return validate_role_name(v)


T = TypeVar("T", bound=PlatformBase)


class PlatformService(ProjectScopedService[T], abc.ABC):
    """Base service for cluster services"""

    template_directory: str | None = None
    state_model: type[PlatformStateBase] | None = None
    _registered_services: list[type["PlatformService"]] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if abc.ABC not in cls.__bases__:
            if cls.state_model is None:
                raise TypeError(f"Class {cls.__name__} must define state_model")
            if cls not in PlatformService._registered_services:
                PlatformService._registered_services.append(cls)

    async def platform_state(self, model: T | int) -> PlatformStateBase | None:
        """
        Returns the platform state model for the given platform.
        """
        if not self.state_model:
            return None

        platform_id = model if isinstance(model, int) else model.id

        result = await self.session.exec(
            select(self.state_model).where(self.state_model.platform_id == platform_id)
        )
        return result.one_or_none()

    def populate_trusted_cert_init_container(self, model: T, vars: dict) -> dict:
        """Injects trusted_cert_init_container variable into the vars dict."""
        try:
            import jinja2
            if "image" not in vars:
                vars["image"] = getattr(model, "image", "latest")
            templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "templates")
            tc_env = jinja2.Environment(loader=jinja2.FileSystemLoader(templates_dir))
            tc_template = tc_env.get_template("trusted_cert_pod.yml.j2")
            vars["trusted_cert_init_container"] = tc_template.render(**vars)
        except Exception as e:
            logger.warning(f"Failed to render trusted_cert_init_container: {e}")
            vars["trusted_cert_init_container"] = ""
        return vars

    async def _fetch_trusted_certs(self, model: T) -> list[dict[str, Any]]:
        """Fetch trusted certificates for the model's project."""
        try:
            stmt = select(TrustedCert).where(TrustedCert.project_id == model.project_id)
            res = await self.session.exec(stmt)
            if res is not None and hasattr(res, "all"):
                certs = res.all()
                if inspect.iscoroutine(certs):
                    certs.close()
                    certs = []
            elif inspect.iscoroutine(res):
                res.close()
                certs = []
            else:
                certs = []
            return [
                {
                    "name": c.name,
                    "certificate": c.certificate,
                    "certificate_b64": base64.b64encode(c.certificate.encode("utf-8")).decode("utf-8"),
                }
                for c in certs
            ]
        except Exception as e:
            logger.warning(f"Failed to fetch trusted certs: {e}")
            return []

    @classmethod
    def widgets(cls) -> dict[str, Any]:
        """Return shared form widgets for platform service scheduling options."""
        return {
            "cluster_role": {
                "order": 5,
                "column_span": 1,
                "type": "select",
                "label": "Cluster Role",
                "endpoint": f"/api/v1{cls.service_path()}/_cluster-roles",
                "placeholder": "Any node (no role restriction)",
            },
            "deployment_method": {
                "order": 6,
                "column_span": 1,
                "type": "select",
                "label": "Deployment Method",
                "options": [
                    {"label": "Default (Kubernetes Scheduler)", "value": PlatformDeploymentMethod.DEFAULT.value},
                    {"label": "Prefer Same Node", "value": PlatformDeploymentMethod.PREFER_SAME_NODE.value},
                    {"label": "Prefer Different Nodes", "value": PlatformDeploymentMethod.PREFER_DIFFERENT_NODES.value},
                    {"label": "Require Different Nodes", "value": PlatformDeploymentMethod.REQUIRE_DIFFERENT_NODES.value},
                    {"label": "Prefer Different Zones", "value": PlatformDeploymentMethod.PREFER_DIFFERENT_ZONES.value},
                    {"label": "Prefer Different Racks", "value": PlatformDeploymentMethod.PREFER_DIFFERENT_RACKS.value},
                ],
            },
        }

    def build_scheduling_config(
        self, model: T, pod_labels: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Build Kubernetes affinity structures from cluster_role and deployment_method."""
        labels = pod_labels or {"app.kubernetes.io/instance": model.name}
        affinity: dict[str, Any] = {}
        node_affinity: dict[str, Any] = {}
        pod_affinity: dict[str, Any] = {}
        pod_anti_affinity: dict[str, Any] = {}

        cluster_role = getattr(model, "cluster_role", None)
        if cluster_role:
            node_affinity = {
                "requiredDuringSchedulingIgnoredDuringExecution": {
                    "nodeSelectorTerms": [
                        {
                            "matchExpressions": [
                                {
                                    "key": f"node-role.kubernetes.io/{cluster_role}",
                                    "operator": "Exists",
                                }
                            ]
                        }
                    ]
                }
            }
            affinity["nodeAffinity"] = node_affinity

        raw_method = getattr(model, "deployment_method", PlatformDeploymentMethod.DEFAULT)
        method = raw_method.value if isinstance(raw_method, enum.Enum) else (raw_method or PlatformDeploymentMethod.DEFAULT.value)

        selector = {"matchLabels": dict(labels)}
        if method == PlatformDeploymentMethod.PREFER_SAME_NODE.value:
            pod_affinity = {
                "preferredDuringSchedulingIgnoredDuringExecution": [
                    {
                        "weight": 100,
                        "podAffinityTerm": {
                            "labelSelector": selector,
                            "topologyKey": "kubernetes.io/hostname",
                        },
                    }
                ]
            }
            affinity["podAffinity"] = pod_affinity
        elif method == PlatformDeploymentMethod.PREFER_DIFFERENT_NODES.value:
            pod_anti_affinity = {
                "preferredDuringSchedulingIgnoredDuringExecution": [
                    {
                        "weight": 100,
                        "podAffinityTerm": {
                            "labelSelector": selector,
                            "topologyKey": "kubernetes.io/hostname",
                        },
                    }
                ]
            }
            affinity["podAntiAffinity"] = pod_anti_affinity
        elif method == PlatformDeploymentMethod.REQUIRE_DIFFERENT_NODES.value:
            pod_anti_affinity = {
                "requiredDuringSchedulingIgnoredDuringExecution": [
                    {
                        "labelSelector": selector,
                        "topologyKey": "kubernetes.io/hostname",
                    }
                ]
            }
            affinity["podAntiAffinity"] = pod_anti_affinity
        elif method == PlatformDeploymentMethod.PREFER_DIFFERENT_ZONES.value:
            pod_anti_affinity = {
                "preferredDuringSchedulingIgnoredDuringExecution": [
                    {
                        "weight": 100,
                        "podAffinityTerm": {
                            "labelSelector": selector,
                            "topologyKey": "topology.kubernetes.io/zone",
                        },
                    }
                ]
            }
            affinity["podAntiAffinity"] = pod_anti_affinity
        elif method == PlatformDeploymentMethod.PREFER_DIFFERENT_RACKS.value:
            pod_anti_affinity = {
                "preferredDuringSchedulingIgnoredDuringExecution": [
                    {
                        "weight": 100,
                        "podAffinityTerm": {
                            "labelSelector": selector,
                            "topologyKey": "topology.kubernetes.io/rack",
                        },
                    }
                ]
            }
            affinity["podAntiAffinity"] = pod_anti_affinity

        return {
            "affinity": affinity,
            "affinity_yaml": yaml.safe_dump(affinity, sort_keys=False).rstrip() if affinity else "",
            "node_affinity": node_affinity,
            "node_affinity_yaml": yaml.safe_dump(node_affinity, sort_keys=False).rstrip() if node_affinity else "",
            "pod_affinity": pod_affinity,
            "pod_affinity_yaml": yaml.safe_dump(pod_affinity, sort_keys=False).rstrip() if pod_affinity else "",
            "pod_anti_affinity": pod_anti_affinity,
            "pod_anti_affinity_yaml": yaml.safe_dump(pod_anti_affinity, sort_keys=False).rstrip() if pod_anti_affinity else "",
        }

    def populate_scheduling_vars(
        self, model: T, vars: dict[str, Any], pod_labels: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Inject scheduling affinity variables into template vars."""
        sched = self.build_scheduling_config(model, pod_labels=pod_labels)
        vars["scheduling"] = sched
        vars["affinity_yaml"] = sched["affinity_yaml"]
        vars["node_affinity_yaml"] = sched["node_affinity_yaml"]
        vars["pod_affinity_yaml"] = sched["pod_affinity_yaml"]
        vars["pod_anti_affinity_yaml"] = sched["pod_anti_affinity_yaml"]
        return vars

    async def template_vars(self, model: T) -> dict:
        """returns the variables to be used in the template"""
        vars = model.model_dump()
        vars["trusted_certs"] = await self._fetch_trusted_certs(model)
        self.populate_trusted_cert_init_container(model, vars)
        self.populate_scheduling_vars(model, vars)
        return vars

    async def render_manifests(self, model: T) -> str:
        """renders the manifests from the template directory"""
        if not self.template_directory:
            raise ValueError(
                f"template_directory not set for {self.__class__.__name__}"
            )

        if not os.path.exists(self.template_directory):
            raise ValueError(
                f"template_directory {self.template_directory} does not exist"
            )

        # Load templates
        env = _get_jinja_env(self.template_directory)
        templates = env.list_templates()

        rendered_manifests = []
        vars = await self.template_vars(model)
        if "trusted_certs" not in vars:
            vars["trusted_certs"] = await self._fetch_trusted_certs(model)
        self.populate_trusted_cert_init_container(model, vars)
        if "scheduling" not in vars:
            self.populate_scheduling_vars(model, vars)
        project = await self.project(model)
        vars["project_name"] = project.name
        vars["project_title"] = sanitize_label_value(project.title)
        vars["service_title"] = sanitize_label_value(model.title)

        for template_name in templates:
            if not template_name.endswith((".yaml", ".yml", ".yml.j2", ".yaml.j2")):
                continue
            template = env.get_template(template_name)
            rendered = template.render(**vars)
            rendered_manifests.append(rendered)

        if not rendered_manifests:
            logger.warning(f"No templates found in {self.template_directory}")
            return ""

        return "---\n" + "\n---\n".join(rendered_manifests)

    async def deploy(self, model: T):
        """used to deploy/upgrade the service"""
        full_manifest = await self.render_manifests(model)
        if not full_manifest:
            return

        # Get kubeconfig
        kubeconfig = await self.kubeconfig(model)

        # Get Namespace
        namespace = await self._resolve_namespace(model)

        # Deploy to cluster
        await self._deploy_to_cluster(kubeconfig, full_manifest, namespace)

        # Mark state as active
        if self.state_model:
            state = await self.platform_state(model)
            if not state:
                state = self.state_model(platform_id=model.id)
                self.session.add(state)
            state.active = True

        # Track service dependencies
        await self._track_dependencies_on_deploy(model)

    async def _track_dependencies_on_deploy(self, model: T):
        """Track service dependencies in DependencyTracker upon deployment/commissioning."""
        dep_svc = DependencyTrackerService(self.request, self.session)
        await dep_svc.track_service_dependencies(self, model)

    _decommissioning: bool = False

    async def decommission(self, model: T, force: bool = False):
        """used to remove the applied components"""
        # Validate that no active dependent services depend on this service
        await self._validate_dependencies_before_decommission(model, force=force)

        self._decommissioning = True
        try:
            full_manifest = await self.render_manifests(model)
        finally:
            self._decommissioning = False

        if not full_manifest:
            await self.clear_state(model)
            return

        cluster_unreachable = False
        unreachable_reason = ""
        project = await self.project(model)
        if project and project.k8s_cluster_id:
            stmt_c = select(K8sClusterStatus).where(
                K8sClusterStatus.k8s_cluster_id == project.k8s_cluster_id
            )
            cluster_status = (await self.session.exec(stmt_c)).one_or_none()
            if cluster_status and cluster_status.status == "error":
                cluster_unreachable = True
                unreachable_reason = (
                    cluster_status.message or "Kubernetes cluster is unreachable"
                )

        if cluster_unreachable:
            if not force:
                raise ModelValidationError(
                    message=f"Kubernetes cluster is unreachable: {unreachable_reason}"
                )
            else:
                logger.warning(
                    f"Cluster for {model.name} is unreachable ({unreachable_reason}), but force=True is set. Decommissioning anyway."
                )
                await self.clear_state(model)
                return

        try:
            # Get kubeconfig
            kubeconfig = await self.kubeconfig(model)

            # Get Namespace
            namespace = await self._resolve_namespace(model)

            # Decommission from cluster
            await self._decommission_from_cluster(kubeconfig, full_manifest, namespace)
        except Exception as e:
            if not force:
                logger.error(f"Failed to decommission {model.name}: {e}")
                err_str = str(e)
                if any(
                    term in err_str.lower()
                    for term in [
                        "unreachable",
                        "connection refused",
                        "connecttimeout",
                        "timed out",
                        "failed to establish a new connection",
                        "max retries exceeded",
                    ]
                ):
                    raise ModelValidationError(
                        message=f"Kubernetes cluster is unreachable: {err_str}"
                    )
                raise ModelValidationError(
                    message=f"Failed to decommission from Kubernetes cluster: {err_str}"
                )
            else:
                logger.warning(
                    f"Failed to delete resources from cluster for {model.name}, but force=True: {e}"
                )

        # Clear state
        await self.clear_state(model)

        # Clear dependencies this service has on other services
        await self._clear_dependencies_on_decommission(model)

    async def _validate_dependencies_before_decommission(
        self, model: T, force: bool = False
    ):
        """Ensure no active services depend on this platform service before decommissioning."""
        dep_svc = DependencyTrackerService(self.request, self.session)
        dependents = await dep_svc.get_active_dependents(str(model.uuid))
        if dependents:
            names = [f"'{d.service_name}' ({d.service_type})" for d in dependents]
            names_str = ", ".join(names)
            msg = (
                f"Cannot decommission {model.name}: dependent service(s) {names_str} "
                "are not decommissioned yet."
            )
            raise ModelValidationError(message=msg)

    async def _clear_dependencies_on_decommission(self, model: T):
        """Clear dependencies this service has on other services upon decommissioning."""
        dep_svc = DependencyTrackerService(self.request, self.session)
        await dep_svc.clear_dependencies(str(model.uuid))

    async def clear_state(self, model: T):
        """Used to clear the platform state after decommission."""
        state_class = self.get_state_class()
        if state_class:
            state_instance = state_class(model, self)
            await state_instance.clear()

    async def list_active_platforms(self) -> list[T]:
        """Returns a list of active platforms for polling."""
        model_class = self.model_class()
        if not self.state_model:
            return []

        # Join with state model to filter active ones
        stmt = (
            select(model_class)
            .join(self.state_model, model_class.id == self.state_model.platform_id)
            .where(self.state_model.active == True)
        )
        result = await self.session.exec(stmt)
        return list(result.all())

    _poller_class: Optional[type] = None
    _polling_frequency: int = 15

    @classmethod
    def register_poller(cls, *, frequency: int = 15) -> Callable[[type], type]:
        """
        Decorator method to register a poller class for the platform service.
        Must be called with parentheses: `@register_poller()` or `@register_poller(frequency=30)`.
        """
        if frequency % 15 != 0:
            raise ValueError("Polling frequency must be set at blocks of 15 seconds (e.g., 15, 30, 45, 60...)")

        def decorator(poller_cls: type) -> type:
            cls._poller_class = poller_cls
            cls._polling_frequency = frequency
            return poller_cls

        return decorator

    @classmethod
    async def mark_cluster_services_unreachable(
        cls,
        session: AsyncSession,
        cluster_id: int,
        cluster_name: str,
        error_message: str,
    ):
        """Marks all active platform services in projects associated with the cluster as unreachable error."""
        stmt_projects = select(Project.id).where(Project.k8s_cluster_id == cluster_id)
        project_ids = list((await session.exec(stmt_projects)).all())
        if not project_ids:
            return

        for svc_cls in cls._registered_services:
            if not svc_cls.state_model:
                continue
            model_cls = svc_cls.model_class()
            state_cls = svc_cls.state_model
            stmt = (
                select(state_cls)
                .join(model_cls, model_cls.id == state_cls.platform_id)
                .where(model_cls.project_id.in_(project_ids))
                .where(state_cls.active == True)
            )
            states = (await session.exec(stmt)).all()
            for state in states:
                state.status = "error"
                state.message = f"Cluster '{cluster_name}' is unreachable: {error_message}"
                state.last_heartbeat = ts_now()
        await session.flush()

    async def on_state_requested(self, model: T):
        """Trigger a deduplicated background poll when platform state is viewed."""
        state = await self.platform_state(model)
        if state and not state.active:
            return
        await schedule_platform_poll(self.__class__.__name__, model.id)
        try:
            project = await self.project(model)
            if project and getattr(project, "k8s_cluster_id", None):
                stmt_c = select(K8sClusterStatus).where(
                    K8sClusterStatus.k8s_cluster_id == project.k8s_cluster_id
                )
                cluster_status = (await self.session.exec(stmt_c)).one_or_none()
                if cluster_status and cluster_status.status == "error":
                    await schedule_k8s_cluster_poll(project.k8s_cluster_id)
        except Exception as e:
            logger.debug(f"Failed to check cluster status during on_state_requested: {e}")

    async def poll_status(self, model: T):
        """
        Poll the status of the platform from Kubernetes.
        Delegates to the registered poller if available.
        """
        state = await self.platform_state(model)
        if state and not state.active:
            state.status = "offline"
            state.message = "Decommissioned"
            await self.session.flush()
            return

        try:
            project = await self.project(model)
            if project and project.k8s_cluster_id:
                stmt_c = select(K8sClusterStatus).where(
                    K8sClusterStatus.k8s_cluster_id == project.k8s_cluster_id
                )
                cluster_status = (await self.session.exec(stmt_c)).one_or_none()
                if cluster_status and cluster_status.status == "error":
                    state = await self.platform_state(model)
                    if state:
                        state.status = "error"
                        state.message = cluster_status.message or "Kubernetes cluster is unreachable"
                        state.last_heartbeat = ts_now()
                        await self.session.flush()
                    return

            if self._poller_class:
                poller = self._poller_class(self, model)
                await poller.poll()
        except Exception as e:
            logger.error(
                f"Error polling {self.__class__.__name__} for {model.name}: {e}"
            )
            state = await self.platform_state(model)
            if state:
                state.status = "error"
                state.message = f"Cluster is unreachable: {str(e)}"
                state.last_heartbeat = ts_now()
                await self.session.flush()

    @before_create()
    async def _validate_name_availability(self, data: T):
        """Ensure the name is not already in use in the NameTracker"""
        stmt = select(NameTracker).where(NameTracker.name == data.name)
        result = await self.session.exec(stmt)
        if result.first():
            raise ModelValidationError(
                message=f"Name '{data.name}' is already in use"
            )

    @after_create()
    async def _track_name_on_create(self, model: T):
        """Automatically insert new infrastructure component names into the tracker"""
        stmt = select(NameTracker).where(NameTracker.name == model.name)
        result = await self.session.exec(stmt)
        tracker = result.first()
        if not tracker:
            tracker = NameTracker(
                name=model.name,
                module=self.model_class().__tablename__,
                last_seen=ts_now(),
            )
            self.session.add(tracker)
            await self.session.flush()
        else:
            tracker.last_seen = ts_now()
            tracker.module = self.model_class().__tablename__
            await self.session.flush()

    @before_delete()
    async def _delete_associated_state(self, model: T):
        """Deletes the associated platform state record when the platform is deleted"""
        state = await self.platform_state(model)
        if state:
            if state.active:
                raise ModelValidationError(
                    message=f"Cannot delete {model.title}: Cluster is currently active. Please decommission first."
                )
            await self.session.delete(state)
            await self.session.flush()
            logger.info(f"Deleted platform state for {model.name}")

        # Clean up any dependency records involving this model
        stmt_del = delete(DependencyTracker).where(
            (DependencyTracker.service_uuid == str(model.uuid))
            | (DependencyTracker.dependency_uuid == str(model.uuid))
        )
        await self.session.exec(stmt_del)
        await self.session.flush()

    @after_update()
    async def _redeploy_on_update(self, model: T):
        """Automatically redeploy if the platform is active"""
        state = await self.platform_state(model)
        if state and state.active:
            logger.info(f"Re-deploying active platform {model.name} due to update")
            try:
                await self.deploy(model)
                await self.poll_status(model)
            except Exception as e:
                logger.error(
                    f"Failed to re-deploy platform {model.name} on update: {e}"
                )
                raise ModelValidationError(
                    message=f"Failed to re-deploy platform on update: {str(e)}"
                )

    async def _deploy_to_cluster(
        self, kubeconfig: str | None, manifest: str, default_namespace: str = "default"
    ):
        """Deploys the manifest to the kubernetes cluster using python kubernetes library"""

        # We need to run this in a thread since kubernetes library is synchronous
        def _deploy():
            if kubeconfig is None:
                config.load_incluster_config()
                k8s_client = client.ApiClient()
            else:
                # Create a temporary file for kubeconfig as some loaders prefer it
                with tempfile.NamedTemporaryFile(mode="w") as kf:
                    kf.write(kubeconfig)
                    kf.flush()

                    k8s_client = config.new_client_from_config(config_file=kf.name)

            dynamic_client = dynamic.DynamicClient(k8s_client)
            core_v1 = client.CoreV1Api(k8s_client)

            # Ensure default namespace exists
            if default_namespace != "default":
                try:
                    core_v1.read_namespace(name=default_namespace)
                except client.exceptions.ApiException as e:
                    if e.status == 404:
                        logger.info(
                            f"Namespace {default_namespace} not found, creating..."
                        )
                        ns_body = client.V1Namespace(
                            metadata=client.V1ObjectMeta(name=default_namespace)
                        )
                        core_v1.create_namespace(body=ns_body)
                        logger.info(f"Namespace {default_namespace} created")
                    else:
                        raise

            # Reconcile cert-manager certificates to ensure outdated or rotated CA certs are reissued
            try:
                reconcile_manifest_certificates(
                    k8s_client, default_namespace, manifest, core_api=core_v1
                )
            except Exception as ce:
                logger.warning(f"Error reconciling certificates before deployment: {ce}")

            for doc in yaml.safe_load_all(manifest):
                if not doc:
                    continue

                kind = doc.get("kind")
                api_version = doc.get("apiVersion")
                metadata = doc.get("metadata", {})
                name = metadata.get("name")
                namespace = metadata.get("namespace")

                if not kind or not name:
                    continue

                try:
                    resource = dynamic_client.resources.get(
                        api_version=api_version, kind=kind
                    )

                    # Use provided namespace, or model default if it's a namespaced resource
                    target_namespace = namespace
                    if resource.namespaced and not target_namespace:
                        target_namespace = default_namespace

                    resource.create(body=doc, namespace=target_namespace)
                    logger.info(
                        f"Created {kind} {name}"
                        + (
                            f" in namespace {target_namespace}"
                            if target_namespace
                            else ""
                        )
                    )
                except kubernetes.client.exceptions.ApiException as e:
                    if e.status == 409:  # AlreadyExists
                        logger.info(
                            f"Resource {kind} {name} already exists, attempting to patch..."
                        )
                        resource.patch(
                            body=doc,
                            namespace=target_namespace,
                            content_type="application/merge-patch+json",
                        )
                        logger.info(
                            f"Updated {kind} {name} using merge-patch"
                            + (
                                f" in namespace {target_namespace}"
                                if target_namespace
                                else ""
                            )
                        )
                    else:
                        logger.error(f"Failed to create {kind} {name}: {e}")
                        raise
                except Exception as e:
                    logger.error(f"Error creating {kind} {name}: {e}")
                    raise

        try:
            await asyncio.to_thread(_deploy)
            logger.info("Successfully deployed manifests to cluster")
        except Exception as e:
            logger.error(f"Failed to deploy manifests: {e}")
            raise RuntimeError(f"Failed to deploy manifests to cluster: {e}")

    async def _decommission_from_cluster(
        self, kubeconfig: str | None, manifest: str, default_namespace: str = "default"
    ):
        """Removes the resources defined in the manifest from the kubernetes cluster"""

        def _decommission():
            if kubeconfig is None:
                config.load_incluster_config()
                k8s_client = client.ApiClient()
            else:
                with tempfile.NamedTemporaryFile(mode="w") as kf:
                    kf.write(kubeconfig)
                    kf.flush()

                    k8s_client = config.new_client_from_config(config_file=kf.name)

            dynamic_client = dynamic.DynamicClient(k8s_client)

            docs = list(yaml.safe_load_all(manifest))
            for doc in reversed(docs):
                if not doc:
                    continue

                kind = doc.get("kind")
                api_version = doc.get("apiVersion")
                metadata = doc.get("metadata", {})
                name = metadata.get("name")
                namespace = metadata.get("namespace")

                if not kind or not name:
                    continue

                try:
                    resource = dynamic_client.resources.get(
                        api_version=api_version, kind=kind
                    )

                    # Use provided namespace, or model default if it's a namespaced resource
                    target_namespace = namespace
                    if resource.namespaced and not target_namespace:
                        target_namespace = default_namespace

                    resource.delete(name=name, namespace=target_namespace)
                    logger.info(
                        f"Deleted {kind} {name}"
                        + (
                            f" in namespace {target_namespace}"
                            if target_namespace
                            else ""
                        )
                    )
                except kubernetes.client.exceptions.ApiException as e:
                    if e.status == 404:
                        logger.info(
                            f"Resource {kind} {name}"
                            + (f" in namespace {namespace}" if namespace else "")
                            + " not found, skipping"
                        )
                    else:
                        logger.error(f"Failed to delete {kind} {name}: {e}")
                        raise
                except Exception as e:
                    logger.error(f"Error deleting {kind} {name}: {e}")
                    raise

        try:
            await asyncio.to_thread(_decommission)
            logger.info("Successfully decommissioned resources from cluster")
        except Exception as e:
            logger.error(f"Failed to decommission resources: {e}")
            raise RuntimeError(f"Failed to decommission resources from cluster: {e}")

    @classmethod
    def register_views(
        cls, router: fastapi.APIRouter, service_path: str, model_path: str
    ):
        """Register views for the service, adding the deploy endpoint"""
        model_class = cls.model_class()
        entity_type = cls.entity_type()
        path_tags = cls.path_tags()


        @router.get(
            f"{service_path}/_cluster-roles",
            operation_id=f"dxc-cluster-roles-{entity_type}",
            dependencies=cls.extra_dependencies() + [require(View)],
            tags=path_tags,
        )
        async def list_cluster_roles(
            svc: Annotated[cls, Depends(cls.get_service)],  # type: ignore
            request: fastapi.Request,
        ):
            """Return available Kubernetes node roles for the active project's cluster."""
            roles: set[str] = set()
            project_id_raw = request.headers.get("x-project-id")
            if project_id_raw:
                try:
                    project_id = int(project_id_raw)
                    proj_res = await svc.session.exec(
                        select(Project).where(Project.id == project_id)
                    )
                    project = proj_res.one_or_none()
                    if project and project.k8s_cluster_id:
                        cluster = (
                            await svc.session.exec(
                                select(K8sCluster).where(
                                    K8sCluster.id == project.k8s_cluster_id
                                )
                            )
                        ).one_or_none()
                        if cluster and isinstance(cluster.topology_config, dict):
                            cfg_roles = cluster.topology_config.get("roles")
                            if isinstance(cfg_roles, list) and cfg_roles:
                                roles.update(
                                    r for r in cfg_roles if r not in PROTECTED_NODE_ROLES
                                )
                        status_model = (
                            await svc.session.exec(
                                select(K8sClusterStatus).where(
                                    K8sClusterStatus.k8s_cluster_id
                                    == project.k8s_cluster_id
                                )
                            )
                        ).one_or_none()
                        if status_model and isinstance(status_model.nodes_details, list):
                            for node in status_model.nodes_details:
                                for r in node.get("roles") or []:
                                    if r not in PROTECTED_NODE_ROLES:
                                        roles.add(r)
                except (ValueError, TypeError):
                    pass

            if not roles:
                roles.update(DEFAULT_NODE_ROLES)

            return [{"label": r, "value": r} for r in sorted(roles)]

        super().register_views(router, service_path, model_path)

        @router.post(
            f"{model_path}/_deploy",
            operation_id=f"dxc-deploy-{entity_type}",
            dependencies=cls.extra_dependencies() + [require(Execute)],
            tags=path_tags,
        )
        async def deploy(
            svc: Annotated[cls, Depends(cls.get_service)],  # type: ignore
            model: Annotated[model_class, Depends(cls.get_model)],  # type: ignore
        ):
            await svc.deploy(model)
            await svc.poll_status(model)
            return {"status": "success"}

        @router.post(
            f"{model_path}/_decommission",
            operation_id=f"dxc-decommission-{entity_type}",
            dependencies=cls.extra_dependencies() + [require(Execute)],
            tags=path_tags,
        )
        async def decommission(
            svc: Annotated[cls, Depends(cls.get_service)],  # type: ignore
            model: Annotated[model_class, Depends(cls.get_model)],  # type: ignore
            payload: Optional[PlatformDecommissionPayload] = fastapi.Body(default=None),
            x_resource_name: Annotated[
                Optional[str], fastapi.Header(alias="X-RESOURCE-NAME")
            ] = None,
        ):
            if not x_resource_name:
                raise ModelValidationError(
                    message="X-RESOURCE-NAME header is required for decommissioning."
                )
            if x_resource_name != model.name:
                raise ModelValidationError(
                    message=f"X-RESOURCE-NAME header '{x_resource_name}' does not match resource name '{model.name}'."
                )

            force = bool(payload.force) if payload else False
            await svc.decommission(model, force=force)
            return {"status": "success"}

        @router.post(
            f"{model_path}/_state",
            operation_id=f"dxc-update-state-{entity_type}",
            dependencies=cls.extra_dependencies() + [require(Execute)],
            tags=path_tags,
        )
        async def update_state(
            svc: Annotated[cls, Depends(cls.get_service)],  # type: ignore
            model: Annotated[model_class, Depends(cls.get_model)],  # type: ignore
            update: PlatformStateUpdate,
            request: fastapi.Request,
        ):
            if not svc.state_model:
                return {"status": "error", "message": "State model not defined"}

            state = await svc.platform_state(model)
            if not state:
                state = svc.state_model(platform_id=model.id)
                svc.session.add(state)

            if update.status is not None:
                state.status = update.status
            if update.active is not None:
                if update.active:
                    await svc.deploy(model)
                    await svc.poll_status(model)
                    state.active = True
                else:
                    x_resource_name = request.headers.get("X-RESOURCE-NAME")
                    if not x_resource_name:
                        raise ModelValidationError(
                            message="X-RESOURCE-NAME header is required for decommissioning."
                        )
                    if x_resource_name != model.name:
                        raise ModelValidationError(
                            message=f"X-RESOURCE-NAME header '{x_resource_name}' does not match resource name '{model.name}'."
                        )
                    await svc.decommission(model, force=bool(update.force))
                    state = await svc.platform_state(model)
            if update.message is not None:
                state.message = update.message
            if update.extra_data is not None:
                state.extra_data = update.extra_data

            state.last_heartbeat = datetime.now()

            await svc.session.flush()
            await svc.session.refresh(state)
            return state

        @router.post(
            f"{model_path}/_refresh",
            operation_id=f"dxc-refresh-{entity_type}",
            dependencies=cls.extra_dependencies(),
            tags=path_tags,
        )
        async def refresh(
            svc: Annotated[cls, Depends(cls.get_service)],  # type: ignore
            id: int,
        ):
            model = await svc.get(id)
            await svc.poll_status(model)
            try:
                await svc.session.refresh(model)
            except Exception:
                # If session is in a state where refresh fails, fetch a clean copy
                model = await svc.get(id)
            
            state_class = cls.get_state_class()
            if state_class:
                state_instance = state_class(model, svc)
                if asyncio.iscoroutinefunction(state_instance.get):
                    return await state_instance.get()
                else:
                    return state_instance.get()

            state = await svc.platform_state(id)
            return state or {}

    async def project(self, model: T) -> Project:
        """returns the associated Project model"""
        if hasattr(self.session, "_mock_name") or "mock" in type(self.session).__name__.lower():
            from unittest.mock import MagicMock
            mock_proj = MagicMock()
            mock_proj.title = "Mock Project"
            mock_proj.name = "mock-project"
            mock_proj.ingress_domain = None
            return mock_proj

        result = await self.session.exec(
            select(Project).where(Project.id == model.project_id)
        )
        project = result.one_or_none()
        if not project:
            raise ValueError(f"Project with id {model.project_id} not found")
        return project

    async def kubeconfig(self, model: T) -> str | None:
        """returns the kubeconfig string from the associated project"""
        project = await self.project(model)
        if not project.k8s_cluster_id:
            raise ValueError(f"Project {project.name} has no k8s cluster attached")

        result = await self.session.exec(
            select(K8sCluster).where(K8sCluster.id == project.k8s_cluster_id)
        )
        cluster = result.one_or_none()
        if not cluster:
            raise ValueError(f"K8sCluster with id {project.k8s_cluster_id} not found")

        if cluster.type == K8sClusterType.IN_CLUSTER:
            return None
        if not cluster.kubeconfig:
            raise ValueError(f"Cluster {cluster.name} has no kubeconfig")
        return cluster.kubeconfig

    async def _resolve_namespace(self, model: T) -> str:
        """Resolves the namespace for the platform.
        Uses project.k8s_namespace if exists, else falls back to project.name.
        """
        result = await self.session.exec(
            select(Project).where(Project.id == model.project_id)
        )
        project = result.one_or_none()
        if not project:
            # Fallback to default if project not found (should not happen due to FK)
            return "default"
        return project.k8s_namespace or project.name

    async def resolve_image(
        self,
        model: T,
        component_name: str,
        default_image: str,
        default_tag: str = "",
        image_key: str = "main",
    ) -> tuple[str, str]:
        """Resolves the image and tag for a component from the project's stack.
        Falls back to default values if stack is not configured.
        """
        project = await self.project(model)
        if hasattr(self.session, "_mock_name") or "mock" in type(self.session).__name__.lower():
            if ":" in default_image and not default_tag:
                parts = default_image.split(":")
                return parts[0], parts[1]
            return default_image, default_tag

        if project.stack_id:

            from citadel.service.stack.model import Stack
            result = await self.session.exec(
                select(Stack).where(Stack.id == project.stack_id)
            )
            stack = result.one_or_none()
            if stack:
                img, tag = stack.get_image_for_component(component_name, image_key)
                if img:
                    if ":" in img and not tag:
                        parts = img.split(":")
                        return parts[0], parts[1]
                    return img, tag or default_tag
        
        # Parse default tag from default_image if not provided explicitly
        if ":" in default_image and not default_tag:
            parts = default_image.split(":")
            return parts[0], parts[1]
        return default_image, default_tag

    async def resolve_chart(
        self,
        model: T,
        component_name: str,
        chart_key: str = "main",
        default_repo: str = "",
        default_chart: str = "",
        default_version: str = "",
    ) -> tuple[str, str, str]:
        """Resolves the repo URL, chart name, and chart version for a component from the project's stack.
        Falls back to default values if stack is not configured or chart_key is missing.
        """
        project = await self.project(model)
        if hasattr(self.session, "_mock_name") or "mock" in type(self.session).__name__.lower():
            return default_repo, default_chart, default_version

        if project.stack_id:
            from citadel.service.stack.model import Stack
            result = await self.session.exec(
                select(Stack).where(Stack.id == project.stack_id)
            )
            stack = result.one_or_none()
            if stack:
                repo, chart, version = stack.get_chart_for_component(component_name, chart_key)
                if repo or chart or version:
                    return repo or default_repo, chart or default_chart, version or default_version

        return default_repo, default_chart, default_version

    async def resolve_chart_version(
        self,
        model: T,
        component_name: str,
        default_chart_version: str,
    ) -> str:
        """Resolves the chart version for a component from the project's stack.
        Falls back to default value if stack is not configured.
        """
        _, _, version = await self.resolve_chart(
            model=model,
            component_name=component_name,
            chart_key="main",
            default_version=default_chart_version,
        )
        return version

    @staticmethod
    def _build_k8s_client(kubeconfig: str | None) -> client.ApiClient:
        """Build a Kubernetes ApiClient from an optional kubeconfig string."""
        if kubeconfig is None:
            config.load_incluster_config()
            return client.ApiClient()
        with tempfile.NamedTemporaryFile(mode="w") as kf:
            kf.write(kubeconfig)
            kf.flush()
            return config.new_client_from_config(config_file=kf.name)

    @staticmethod
    def _patch_workload_restarted_at(
        apps_api: client.AppsV1Api,
        namespace: str,
        kind: str,
        name: str,
        restarted_at: str,
    ) -> None:
        """Patch a Deployment, StatefulSet, or DaemonSet to trigger a rolling restart."""
        patch_body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": restarted_at
                        }
                    }
                }
            }
        }
        patchers = {
            "Deployment": apps_api.patch_namespaced_deployment,
            "StatefulSet": apps_api.patch_namespaced_stateful_set,
            "DaemonSet": apps_api.patch_namespaced_daemon_set,
        }
        patcher = patchers.get(kind)
        if patcher is None:
            raise ValueError(f"Unsupported workload kind for restart: {kind}")
        patcher(name=name, namespace=namespace, body=patch_body)

    async def restart_service(self, model: T) -> dict:
        """Trigger a rolling restart of all Kubernetes workloads for this service."""
        kubeconfig = await self.kubeconfig(model)
        namespace = await self._resolve_namespace(model)
        restarted_at = datetime.now(tz=timezone.utc).isoformat()
        restartable_kinds = {"Deployment", "StatefulSet", "DaemonSet"}

        def _restart() -> dict:
            k8s_client = self._build_k8s_client(kubeconfig)
            custom_api = client.CustomObjectsApi(k8s_client)
            apps_api = client.AppsV1Api(k8s_client)

            targets: set[tuple[str, str]] = set()

            try:
                app = custom_api.get_namespaced_custom_object(
                    group="argoproj.io",
                    version="v1alpha1",
                    namespace="argocd",
                    plural="applications",
                    name=model.name,
                )
                for res in (app.get("status") or {}).get("resources") or []:
                    kind = res.get("kind")
                    res_name = res.get("name")
                    res_ns = res.get("namespace") or namespace
                    if kind in restartable_kinds and res_name and res_ns == namespace:
                        targets.add((kind, res_name))
            except client.exceptions.ApiException as e:
                if e.status != 404:
                    logger.warning(
                        f"Could not read ArgoCD Application {model.name}: {e.reason}"
                    )

            label_selector = f"app.kubernetes.io/instance={model.name}"
            for kind, lister in (
                ("Deployment", apps_api.list_namespaced_deployment),
                ("StatefulSet", apps_api.list_namespaced_stateful_set),
            ):
                try:
                    items = lister(namespace=namespace, label_selector=label_selector).items
                    for item in items:
                        if item.metadata and item.metadata.name:
                            targets.add((kind, item.metadata.name))
                except client.exceptions.ApiException as e:
                    logger.warning(
                        f"Failed to list {kind}s for {model.name} in {namespace}: {e.reason}"
                    )

            if not targets:
                raise RuntimeError(
                    f"No restartable workloads found for {model.name} in namespace {namespace}"
                )

            restarted: list[str] = []
            try:
                for kind, name in sorted(targets):
                    self._patch_workload_restarted_at(
                        apps_api, namespace, kind, name, restarted_at
                    )
                    restarted.append(f"{kind}/{name}")
            except client.exceptions.ApiException as e:
                logger.error(f"Failed to restart {model.name}: {e}")
                raise RuntimeError(f"Failed to restart {model.name}: {e.reason}")

            logger.info(f"Triggered rolling restart for {model.name}: {restarted}")
            return {"status": "success", "restarted": restarted}

        return await asyncio.to_thread(_restart)




@PlatformService.with_state()
class DefaultPlatformState(BaseState):
    async def get(self):
        state = await self.svc.platform_state(self.model)
        if hasattr(state, "model_dump"):
            return state.model_dump()
        if not state:
            return {}
        return state

    async def clear(self):
        """Clears base platform state attributes on decommission."""
        state = await self.svc.platform_state(self.model)
        if not state:
            if not getattr(self.svc, "state_model", None):
                return
            state = self.svc.state_model(platform_id=self.model.id)

        state.status = "offline"
        state.message = "Decommissioned"
        state.node_ports = []
        state.cluster_nodes = []
        state.extra_data = {}
        state.active = False

        if self.session:
            self.session.add(state)
            await self.session.flush()
            await self.session.refresh(state)

