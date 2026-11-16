# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import asyncio
import logging
import re
import tempfile
from typing import Any

from kubernetes import client, config
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from mindweaver.service import Service
from mindweaver.fw.model import ts_now
from mindweaver.tasks.poll_coordinator import schedule_k8s_cluster_poll
from .model import (
    DEFAULT_NODE_ROLES,
    DEFAULT_TOPOLOGY_LEVELS,
    K8sCluster,
    K8sClusterStatus,
    K8sClusterType,
)
from . import permission

logger = logging.getLogger(__name__)

_UNSET = object()

_LABEL_PREFIX_RE = re.compile(
    r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?(\.[a-z0-9]([-a-z0-9]*[a-z0-9])?)*$"
)
_LABEL_NAME_RE = re.compile(r"^[A-Za-z0-9]([-A-Za-z0-9_.]*[A-Za-z0-9])?$")

PROTECTED_NODE_LABELS = frozenset(
    {
        "kubernetes.io/hostname",
        "kubernetes.io/os",
        "kubernetes.io/arch",
        "beta.kubernetes.io/os",
        "beta.kubernetes.io/arch",
    }
)
PROTECTED_NODE_LABEL_PREFIXES = (
    "k3s.io/",
    "k3s.cattle.io/",
)
PROTECTED_NODE_LABEL_SUFFIX_PREFIXES = (
    ".k3s.io/",
    ".k3s.cattle.io/",
)
PROTECTED_NODE_ROLES = frozenset({"control-plane", "master", "etcd"})


def is_protected_node_label(key: str) -> bool:
    """Return True if the node label key is system- or K3s-managed and must not be modified."""
    if key in PROTECTED_NODE_LABELS:
        return True
    if key.startswith(PROTECTED_NODE_LABEL_PREFIXES):
        return True
    if "/" in key:
        prefix = key.split("/", 1)[0] + "/"
        if prefix.endswith(PROTECTED_NODE_LABEL_SUFFIX_PREFIXES):
            return True
    return False

NVIDIA_GPU_LABEL = "nvidia.com/gpu.present"
NVIDIA_PCI_LABEL = "feature.node.kubernetes.io/pci-10de.present"
AMD_GPU_LABEL = "amd.com/gpu.present"
AMD_PCI_LABEL = "feature.node.kubernetes.io/pci-1002.present"


def validate_k8s_label_key(key: str) -> str:
    """Validate a Kubernetes label key (optional DNS prefix + name)."""
    if not isinstance(key, str) or not key:
        raise ValueError("Label key must be a non-empty string")
    if key.count("/") > 1:
        raise ValueError(f"Invalid label key '{key}': multiple '/' characters")
    if "/" in key:
        prefix, name = key.split("/", 1)
        if not prefix or len(prefix) > 253 or not _LABEL_PREFIX_RE.match(prefix):
            raise ValueError(f"Invalid label key prefix '{prefix}'")
    else:
        name = key
    if not name or len(name) > 63 or not _LABEL_NAME_RE.match(name):
        raise ValueError(f"Invalid label key name '{name}'")
    return key


def validate_k8s_label_value(value: str) -> str:
    """Validate a Kubernetes label value."""
    if not isinstance(value, str):
        raise ValueError("Label value must be a string")
    if value == "":
        return value
    if len(value) > 63 or not _LABEL_NAME_RE.match(value):
        raise ValueError(f"Invalid label value '{value}'")
    return value


def validate_role_name(role: str) -> str:
    """Validate a user-defined Kubernetes node role name."""
    if not isinstance(role, str) or not role:
        raise ValueError("Role name must be a non-empty string")
    if role in PROTECTED_NODE_ROLES:
        raise ValueError(f"Role '{role}' is system-managed and cannot be modified")
    if len(role) > 63 or not _LABEL_NAME_RE.match(role):
        raise ValueError(f"Invalid role name '{role}'")
    return role


def sanitize_topology_label_value(value: str) -> str:
    """Convert a hierarchical topology value (possibly containing '/') into a valid K8s label value."""
    return value.replace("/", "-")


def validate_topology_value(value: str, allow_slash: bool = False) -> str:
    """Validate a topology tier value, optionally allowing '/' for hierarchical rack paths."""
    if not isinstance(value, str) or not value:
        raise ValueError("Topology value must be a non-empty string")
    if not allow_slash:
        return validate_k8s_label_value(value)
    if value.startswith("/") or value.endswith("/") or "//" in value:
        raise ValueError(f"Invalid hierarchical topology value '{value}'")
    for segment in value.split("/"):
        if not segment or not _LABEL_NAME_RE.match(segment):
            raise ValueError(f"Invalid segment '{segment}' in topology value '{value}'")
    sanitized = sanitize_topology_label_value(value)
    if len(sanitized) > 63:
        raise ValueError(f"Topology value '{value}' exceeds 63 characters")
    return value

_BYTE_UNITS_TO_GIB: dict[str, float] = {
    "Ki": 1024 / (1024**3),
    "Mi": (1024**2) / (1024**3),
    "Gi": 1.0,
    "Ti": 1024.0,
    "Pi": 1024.0**2,
    "Ei": 1024.0**3,
    "k": 1000 / (1024**3),
    "K": 1000 / (1024**3),
    "M": (1000**2) / (1024**3),
    "G": (1000**3) / (1024**3),
    "T": (1000**4) / (1024**3),
    "P": (1000**5) / (1024**3),
    "E": (1000**6) / (1024**3),
}


def parse_k8s_cpu(res: str | None) -> float:
    """Parse a Kubernetes CPU quantity string into cores."""
    if not res:
        return 0.0
    val = str(res).strip()
    if not val:
        return 0.0
    try:
        if val.endswith("n"):
            return float(val[:-1]) / 1_000_000_000
        if val.endswith("u"):
            return float(val[:-1]) / 1_000_000
        if val.endswith("m"):
            return float(val[:-1]) / 1000
        return float(val)
    except ValueError:
        return 0.0


def parse_k8s_bytes_to_gib(res: str | None) -> float:
    """Parse a Kubernetes memory or storage quantity string into GiB."""
    if not res:
        return 0.0
    val = str(res).strip()
    if not val:
        return 0.0
    for suffix, multiplier in _BYTE_UNITS_TO_GIB.items():
        if val.endswith(suffix):
            try:
                return float(val[: -len(suffix)]) * multiplier
            except ValueError:
                return 0.0
    try:
        return float(val) / (1024**3)
    except ValueError:
        return 0.0


def _extract_container_requests(container) -> tuple[float, float, float]:
    """Extract (cpu_cores, ram_gib, ephemeral_gib) requests from a container spec."""
    resources = getattr(container, "resources", None)
    requests = getattr(resources, "requests", None) or {}
    return (
        parse_k8s_cpu(requests.get("cpu")),
        parse_k8s_bytes_to_gib(requests.get("memory")),
        parse_k8s_bytes_to_gib(requests.get("ephemeral-storage")),
    )


def compute_pod_requests(pod) -> tuple[float, float, float]:
    """Compute effective (cpu_cores, ram_gib, ephemeral_gib) requests for a pod."""
    spec = getattr(pod, "spec", None)
    if not spec:
        return (0.0, 0.0, 0.0)

    cpu_sum = 0.0
    ram_sum = 0.0
    eph_sum = 0.0
    for container in getattr(spec, "containers", None) or []:
        c_cpu, c_ram, c_eph = _extract_container_requests(container)
        cpu_sum += c_cpu
        ram_sum += c_ram
        eph_sum += c_eph

    init_cpu_max = 0.0
    init_ram_max = 0.0
    init_eph_max = 0.0
    for init_container in getattr(spec, "init_containers", None) or []:
        ic_cpu, ic_ram, ic_eph = _extract_container_requests(init_container)
        if getattr(init_container, "restart_policy", None) == "Always":
            cpu_sum += ic_cpu
            ram_sum += ic_ram
            eph_sum += ic_eph
        else:
            init_cpu_max = max(init_cpu_max, ic_cpu)
            init_ram_max = max(init_ram_max, ic_ram)
            init_eph_max = max(init_eph_max, ic_eph)

    return (
        max(cpu_sum, init_cpu_max),
        max(ram_sum, init_ram_max),
        max(eph_sum, init_eph_max),
    )


def build_nodes_details(
    nodes_items: list[Any],
    pods_items: list[Any],
    topology_levels: list[dict[str, str]] | None = None,
) -> tuple[
    dict[str, str],
    list[str],
    float,
    float,
    float,
    float,
    list[dict[str, Any]],
]:
    """Aggregate node health, capacity, labels, topology, GPU info, and pod utilization per node."""
    pod_requests_by_node: dict[str, list[float]] = {}
    for pod in pods_items or []:
        phase = getattr(getattr(pod, "status", None), "phase", None)
        if phase in ("Succeeded", "Failed"):
            continue
        node_name = getattr(getattr(pod, "spec", None), "node_name", None)
        if not node_name:
            continue
        p_cpu, p_ram, p_eph = compute_pod_requests(pod)
        acc = pod_requests_by_node.setdefault(node_name, [0.0, 0.0, 0.0])
        acc[0] += p_cpu
        acc[1] += p_ram
        acc[2] += p_eph

    nodes_status: dict[str, str] = {}
    node_ips: list[str] = []
    cpu_total = 0.0
    ram_total = 0.0
    cpu_allocated = 0.0
    ram_allocated = 0.0
    nodes_details: list[dict[str, Any]] = []

    for node in nodes_items or []:
        name = node.metadata.name
        status = "Unknown"
        for cond in getattr(node.status, "conditions", None) or []:
            if cond.type == "Ready":
                status = "Ready" if cond.status == "True" else "NotReady"
                break
        nodes_status[name] = status

        internal_ip = None
        external_ip = None
        for addr in getattr(node.status, "addresses", None) or []:
            if addr.type in ["InternalIP", "ExternalIP"] and addr.address not in node_ips:
                node_ips.append(addr.address)
            if addr.type == "InternalIP" and not internal_ip:
                internal_ip = addr.address
            elif addr.type == "ExternalIP" and not external_ip:
                external_ip = addr.address

        capacity = getattr(node.status, "capacity", None) or {}
        node_cpu_total = parse_k8s_cpu(capacity.get("cpu"))
        node_ram_total = parse_k8s_bytes_to_gib(capacity.get("memory"))
        node_eph_total = parse_k8s_bytes_to_gib(capacity.get("ephemeral-storage"))

        req_cpu, req_ram, req_eph = pod_requests_by_node.get(name, [0.0, 0.0, 0.0])

        cpu_total += node_cpu_total
        ram_total += node_ram_total
        cpu_allocated += req_cpu
        ram_allocated += req_ram

        created_at = getattr(node.metadata, "creation_timestamp", None)
        raw_labels = getattr(node.metadata, "labels", None)
        labels = dict(raw_labels) if isinstance(raw_labels, dict) else {}
        roles = sorted(
            key.split("node-role.kubernetes.io/", 1)[1]
            for key in labels
            if key.startswith("node-role.kubernetes.io/")
            and key.split("node-role.kubernetes.io/", 1)[1]
        )

        levels = topology_levels or DEFAULT_TOPOLOGY_LEVELS
        topology = {
            lvl["name"]: labels[lvl["key"]]
            for lvl in levels
            if lvl.get("key") in labels and labels[lvl["key"]] != ""
        }

        def _parse_int(val: Any) -> int:
            try:
                return int(val)
            except (TypeError, ValueError):
                return 0

        nvidia_cap = _parse_int(capacity.get("nvidia.com/gpu"))
        amd_cap = _parse_int(capacity.get("amd.com/gpu"))
        intel_cap = _parse_int(capacity.get("intel.com/gpu"))

        gpu_vendor: str | None = None
        gpu_count = 0
        if (
            nvidia_cap > 0
            or labels.get(NVIDIA_GPU_LABEL) == "true"
            or labels.get(NVIDIA_PCI_LABEL) == "true"
        ):
            gpu_vendor = "nvidia"
            gpu_count = nvidia_cap
        elif (
            amd_cap > 0
            or labels.get(AMD_GPU_LABEL) == "true"
            or labels.get(AMD_PCI_LABEL) == "true"
        ):
            gpu_vendor = "amd"
            gpu_count = amd_cap
        elif intel_cap > 0:
            gpu_vendor = "intel"
            gpu_count = intel_cap

        gpu_product = (
            labels.get("nvidia.com/gpu.product")
            or labels.get("amd.com/gpu.product")
            or None
        )

        node_info = getattr(node.status, "node_info", None)
        version = getattr(node_info, "kubelet_version", None) if node_info else None

        nodes_details.append(
            {
                "hostname": name,
                "ip": internal_ip or external_ip,
                "status": status,
                "roles": roles,
                "labels": labels,
                "topology": topology,
                "gpu_vendor": gpu_vendor,
                "gpu_count": gpu_count,
                "gpu_product": gpu_product,
                "creation_timestamp": created_at.isoformat() if created_at else None,
                "version": version,
                "cpu_total": round(node_cpu_total, 4),
                "cpu_requested": round(req_cpu, 4),
                "ram_total": round(node_ram_total, 4),
                "ram_requested": round(req_ram, 4),
                "ephemeral_storage_total": round(node_eph_total, 4),
                "ephemeral_storage_requested": round(req_eph, 4),
            }
        )

    return (
        nodes_status,
        node_ips,
        cpu_total,
        ram_total,
        cpu_allocated,
        ram_allocated,
        nodes_details,
    )


class K8sClusterService(Service[K8sCluster]):
    permissions = permission

    @classmethod
    def model_class(cls) -> type[K8sCluster]:
        return K8sCluster

    async def on_state_requested(self, model: K8sCluster):
        """Trigger a deduplicated background poll when cluster state is viewed."""
        await schedule_k8s_cluster_poll(model.id)

    async def delete(self, model_id: int):
        """Delete cluster and its associated status record."""
        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == model_id
        )
        result = await self.session.exec(stmt)
        status_model = result.one_or_none()
        if status_model:
            await self.session.delete(status_model)
        await super().delete(model_id)

    async def poll_status(self, model: K8sCluster):
        """Poll cluster status and update K8sClusterStatus"""
        logger.info(f"Polling status for k8s_cluster {model.name}")

        try:
            def _get_version(pod):
                version = pod.metadata.labels.get("app.kubernetes.io/version")
                if not version and pod.spec.containers:
                    # Try to extract from image tag
                    image = pod.spec.containers[0].image
                    if ":" in image:
                        version = image.split(":")[-1]
                return version

            def _get_k8s_info():
                conf = client.Configuration()
                if model.type == K8sClusterType.IN_CLUSTER:
                    config.load_incluster_config(client_configuration=conf)
                else:
                    if not model.kubeconfig:
                        raise ValueError(f"Cluster {model.name} has no kubeconfig")
                    with tempfile.NamedTemporaryFile(mode="w") as kf:
                        kf.write(model.kubeconfig)
                        kf.flush()
                        config.load_kube_config(config_file=kf.name, client_configuration=conf)

                conf.request_timeout = 10
                k8s_client = client.ApiClient(conf)
                core_v1 = client.CoreV1Api(k8s_client)
                version_api = client.VersionApi(k8s_client)

                # Get Version
                ver = version_api.get_code()
                k8s_version = ver.git_version

                # Get Nodes and Pods for per-node resource utilization
                nodes = core_v1.list_node()
                node_count = len(nodes.items)
                all_pods_items = []
                try:
                    all_pods = core_v1.list_pod_for_all_namespaces()
                    all_pods_items = all_pods.items or []
                except Exception as e:
                    logger.warning(f"Failed to list pods for node requests: {e}")

                topology_levels = (
                    model.topology_config.get("levels")
                    if isinstance(model.topology_config, dict)
                    else None
                )
                (
                    nodes_status,
                    node_ips,
                    cpu_total,
                    ram_total,
                    cpu_allocated,
                    ram_allocated,
                    nodes_details,
                ) = build_nodes_details(
                    nodes.items,
                    all_pods_items,
                    topology_levels=topology_levels,
                )

                def _pod_readiness(pods_items) -> tuple[str, str]:
                    if not pods_items:
                        return "pending", "Waiting for pods"
                    ready_count = 0
                    has_error = False
                    for pod in pods_items:
                        phase = getattr(getattr(pod, "status", None), "phase", None)
                        statuses = (
                            getattr(getattr(pod, "status", None), "container_statuses", None)
                            or []
                        )
                        if phase == "Running" and any(
                            getattr(c, "ready", False) for c in statuses
                        ):
                            ready_count += 1
                        elif phase in ("Failed", "Unknown"):
                            has_error = True
                        else:
                            for c in statuses:
                                waiting = getattr(
                                    getattr(c, "state", None), "waiting", None
                                )
                                reason = getattr(waiting, "reason", None) if waiting else None
                                if reason in (
                                    "CrashLoopBackOff",
                                    "ErrImagePull",
                                    "ImagePullBackOff",
                                    "CreateContainerConfigError",
                                ):
                                    has_error = True
                                    break
                    total = len(pods_items)
                    if ready_count == total and total > 0:
                        return "online", f"Pods: {ready_count}/{total} ready"
                    if has_error:
                        return "error", f"Pods: {ready_count}/{total} ready (error)"
                    return "pending", f"Pods: {ready_count}/{total} ready"

                argo_apps: dict[str, dict] = {}
                try:
                    custom_api = client.CustomObjectsApi(k8s_client)
                    apps_resp = custom_api.list_namespaced_custom_object(
                        group="argoproj.io",
                        version="v1alpha1",
                        namespace="argocd",
                        plural="applications",
                    )
                    for app_obj in (apps_resp or {}).get("items", []):
                        app_name = app_obj.get("metadata", {}).get("name")
                        if app_name:
                            argo_apps[app_name] = app_obj
                except Exception as e:
                    logger.debug(f"Could not list ArgoCD applications: {e}")

                def _integration_status(
                    installed: bool,
                    version: str | None,
                    pods_items: list,
                    argo_app_name: str | None = None,
                ) -> tuple[dict[str, Any], bool]:
                    if argo_app_name and argo_app_name in argo_apps:
                        app_obj = argo_apps[argo_app_name]
                        sync_st = (
                            app_obj.get("status", {})
                            .get("sync", {})
                            .get("status", "Unknown")
                        )
                        health_st = (
                            app_obj.get("status", {})
                            .get("health", {})
                            .get("status", "Unknown")
                        )
                        if health_st == "Healthy":
                            st = "online"
                        elif health_st in (
                            "Progressing",
                            "Suspended",
                            "Missing",
                        ) or sync_st in ("Unknown", "OutOfSync"):
                            st = "pending"
                        else:
                            st = "error"
                        return (
                            {
                                "status": st,
                                "version": version,
                                "message": f"Sync: {sync_st}, Health: {health_st}",
                            },
                            True,
                        )
                    if installed:
                        st, msg = _pod_readiness(pods_items)
                        return (
                            {"status": st, "version": version, "message": msg},
                            True,
                        )
                    return (
                        {
                            "status": "offline",
                            "version": None,
                            "message": "Not installed",
                        },
                        False,
                    )

                # Check ArgoCD
                argocd_installed = False
                argocd_version = None
                argocd_pods = []
                secrets = None
                try:
                    secrets = core_v1.list_secret_for_all_namespaces(
                        label_selector="owner=helm"
                    )
                except Exception as e:
                    logger.warning(f"Failed to list Helm secrets: {e}")

                try:
                    if secrets:
                        for secret in secrets.items:
                            if secret.metadata.name.startswith("sh.helm.release.v1.argocd"):
                                argocd_installed = True
                                break

                    if not argocd_installed:
                        svcs = core_v1.list_service_for_all_namespaces(
                            label_selector="app.kubernetes.io/name=argocd-server"
                        )
                        if svcs.items:
                            argocd_installed = True

                    if argocd_installed:
                        pods = core_v1.list_pod_for_all_namespaces(
                            label_selector="app.kubernetes.io/name=argocd-server"
                        )
                        argocd_pods = pods.items or []
                        if argocd_pods:
                            argocd_version = _get_version(argocd_pods[0])
                except Exception as e:
                    logger.warning(f"Failed to check ArgoCD presence: {e}")

                # Check Cert Manager
                cert_manager_installed = False
                cert_manager_version = None
                cert_manager_pods = []
                try:
                    if secrets:
                        for secret in secrets.items:
                            if secret.metadata.name.startswith(
                                "sh.helm.release.v1.cert-manager"
                            ):
                                cert_manager_installed = True
                                break
                    if not cert_manager_installed:
                        svcs = core_v1.list_service_for_all_namespaces(
                            label_selector="app.kubernetes.io/name=cert-manager"
                        )
                        if svcs.items:
                            cert_manager_installed = True

                    if cert_manager_installed or "cert-manager" in argo_apps:
                        pods = core_v1.list_pod_for_all_namespaces(
                            label_selector="app.kubernetes.io/name=cert-manager"
                        )
                        cert_manager_pods = pods.items or []
                        if cert_manager_pods:
                            cert_manager_version = _get_version(cert_manager_pods[0])
                except Exception as e:
                    logger.warning(f"Failed to check Cert Manager presence: {e}")

                # Check CNPG
                cnpg_installed = False
                cnpg_version = None
                cnpg_pods = []
                try:
                    if secrets:
                        for secret in secrets.items:
                            if secret.metadata.name.startswith("sh.helm.release.v1.cnpg-operator"):
                                cnpg_installed = True
                                break
                    if not cnpg_installed:
                        svcs = core_v1.list_service_for_all_namespaces(
                            label_selector="app.kubernetes.io/name=cloudnative-pg"
                        )
                        if svcs.items:
                            cnpg_installed = True

                    if cnpg_installed or "cnpg-operator" in argo_apps:
                        pods = core_v1.list_pod_for_all_namespaces(
                            label_selector="app.kubernetes.io/name=cloudnative-pg"
                        )
                        cnpg_pods = pods.items or []
                        if cnpg_pods:
                            cnpg_version = _get_version(cnpg_pods[0])
                except Exception as e:
                    logger.warning(f"Failed to check CNPG presence: {e}")


                # Check Envoy Gateway
                envoy_gateway_installed = False
                envoy_gateway_version = None
                envoy_gateway_pods = []
                try:
                    if secrets:
                        for secret in secrets.items:
                            if secret.metadata.name.startswith("sh.helm.release.v1.eg") or secret.metadata.name.startswith("sh.helm.release.v1.envoy-gateway"):
                                envoy_gateway_installed = True
                                break
                    if not envoy_gateway_installed:
                        svcs = core_v1.list_service_for_all_namespaces(
                            label_selector="control-plane=envoy-gateway"
                        )
                        if not svcs.items:
                            svcs = core_v1.list_service_for_all_namespaces(
                                label_selector="app.kubernetes.io/name=gateway-helm"
                            )
                        if not svcs.items:
                            svcs = core_v1.list_service_for_all_namespaces(
                                label_selector="app.kubernetes.io/name=envoy-gateway"
                            )
                        if svcs.items:
                            envoy_gateway_installed = True

                    if envoy_gateway_installed or "envoy-gateway" in argo_apps:
                        pods = core_v1.list_pod_for_all_namespaces(
                            label_selector="control-plane=envoy-gateway"
                        )
                        if not pods.items:
                            pods = core_v1.list_pod_for_all_namespaces(
                                label_selector="app.kubernetes.io/name=gateway-helm"
                            )
                        if not pods.items:
                            pods = core_v1.list_pod_for_all_namespaces(
                                label_selector="app.kubernetes.io/name=envoy-gateway"
                            )
                        envoy_gateway_pods = pods.items or []
                        if envoy_gateway_pods:
                            envoy_gateway_version = _get_version(envoy_gateway_pods[0])
                except Exception as e:
                    logger.warning(f"Failed to check Envoy Gateway presence: {e}")

                # Check Kafka Operator
                kafka_operator_installed = False
                kafka_operator_version = None
                kafka_operator_pods = []
                try:
                    if secrets:
                        for secret in secrets.items:
                            if secret.metadata.name.startswith("sh.helm.release.v1.strimzi-kafka-operator") or secret.metadata.name.startswith("sh.helm.release.v1.kafka-operator"):
                                kafka_operator_installed = True
                                break
                    pods = core_v1.list_pod_for_all_namespaces(
                        label_selector="app.kubernetes.io/name=strimzi-kafka-operator"
                    )
                    if not pods.items:
                        pods = core_v1.list_pod_for_all_namespaces(
                            label_selector="app.kubernetes.io/name=kafka-operator"
                        )
                    if not pods.items:
                        pods = core_v1.list_pod_for_all_namespaces(
                            label_selector="name=strimzi-cluster-operator"
                        )
                    if not pods.items:
                        pods = core_v1.list_pod_for_all_namespaces(
                            label_selector="strimzi.io/kind=cluster-operator"
                        )
                    kafka_operator_pods = pods.items or []
                    if kafka_operator_pods:
                        kafka_operator_installed = True
                        kafka_operator_version = _get_version(kafka_operator_pods[0])
                except Exception as e:
                    logger.warning(f"Failed to check Kafka Operator presence: {e}")

                # Check NiFiKop Operator
                nifikop_installed = False
                nifikop_version = None
                nifikop_pods = []
                try:
                    if secrets:
                        for secret in secrets.items:
                            if secret.metadata.name.startswith("sh.helm.release.v1.nifikop"):
                                nifikop_installed = True
                                break
                    pods = core_v1.list_pod_for_all_namespaces(
                        label_selector="app.kubernetes.io/name=nifikop"
                    )
                    if not pods.items:
                        pods = core_v1.list_pod_for_all_namespaces(
                            label_selector="control-plane=nifikop"
                        )
                    nifikop_pods = pods.items or []
                    if nifikop_pods:
                        if not nifikop_installed:
                            nifikop_installed = True
                        nifikop_version = _get_version(nifikop_pods[0])
                except Exception as e:
                    logger.warning(f"Failed to check NiFiKop Operator presence: {e}")

                # Check Doris Operator
                doris_operator_installed = False
                doris_operator_version = None
                doris_operator_pods = []
                try:
                    if secrets:
                        for secret in secrets.items:
                            if secret.metadata.name.startswith("sh.helm.release.v1.doris-operator") or secret.metadata.name.startswith("sh.helm.release.v1.selectdb-doris-operator"):
                                doris_operator_installed = True
                                break
                    pods = core_v1.list_pod_for_all_namespaces(
                        label_selector="app.kubernetes.io/name=doris-operator"
                    )
                    if not pods.items:
                        pods = core_v1.list_pod_for_all_namespaces(
                            label_selector="control-plane=doris-operator"
                        )
                    doris_operator_pods = pods.items or []
                    if doris_operator_pods:
                        if not doris_operator_installed:
                            doris_operator_installed = True
                        doris_operator_version = _get_version(doris_operator_pods[0])
                except Exception as e:
                    logger.warning(f"Failed to check Doris Operator presence: {e}")

                argocd_st, argocd_installed = _integration_status(
                    argocd_installed, argocd_version, argocd_pods
                )
                cert_manager_st, cert_manager_installed = _integration_status(
                    cert_manager_installed, cert_manager_version, cert_manager_pods, "cert-manager"
                )
                cnpg_st, cnpg_installed = _integration_status(
                    cnpg_installed, cnpg_version, cnpg_pods, "cnpg-operator"
                )
                envoy_gateway_st, envoy_gateway_installed = _integration_status(
                    envoy_gateway_installed, envoy_gateway_version, envoy_gateway_pods, "envoy-gateway"
                )
                kafka_operator_st, kafka_operator_installed = _integration_status(
                    kafka_operator_installed, kafka_operator_version, kafka_operator_pods, "kafka-operator"
                )
                nifikop_st, nifikop_installed = _integration_status(
                    nifikop_installed, nifikop_version, nifikop_pods, "nifikop-operator"
                )
                doris_operator_st, doris_operator_installed = _integration_status(
                    doris_operator_installed, doris_operator_version, doris_operator_pods, "doris-operator"
                )

                integrations_status = {
                    "argocd": argocd_st,
                    "cert_manager": cert_manager_st,
                    "cnpg": cnpg_st,
                    "envoy_gateway": envoy_gateway_st,
                    "kafka_operator": kafka_operator_st,
                    "nifikop": nifikop_st,
                    "doris_operator": doris_operator_st,
                }

                return {
                    "k8s_version": k8s_version,
                    "node_count": node_count,
                    "nodes_status": nodes_status,
                    "nodes_details": nodes_details,
                    "cpu_total": cpu_total,
                    "cpu_allocated": cpu_allocated,
                    "ram_total": ram_total,
                    "ram_allocated": ram_allocated,
                    "argocd_installed": argocd_installed,
                    "argocd_version": argocd_version,
                    "cert_manager_installed": cert_manager_installed,
                    "cert_manager_version": cert_manager_version,
                    "cnpg_installed": cnpg_installed,
                    "cnpg_version": cnpg_version,

                    "envoy_gateway_installed": envoy_gateway_installed,
                    "envoy_gateway_version": envoy_gateway_version,
                    "kafka_operator_installed": kafka_operator_installed,
                    "kafka_operator_version": kafka_operator_version,
                    "nifikop_installed": nifikop_installed,
                    "nifikop_version": nifikop_version,
                    "doris_operator_installed": doris_operator_installed,
                    "doris_operator_version": doris_operator_version,
                    "integrations_status": integrations_status,
                    "node_ips": node_ips,
                }

            info = await asyncio.to_thread(_get_k8s_info)

            # Update database
            stmt = select(K8sClusterStatus).where(
                K8sClusterStatus.k8s_cluster_id == model.id
            )
            result = await self.session.exec(stmt)
            status_model = result.one_or_none()

            if not status_model:
                status_model = K8sClusterStatus(k8s_cluster_id=model.id)
                self.session.add(status_model)

            status_model.status = "online"
            status_model.k8s_version = info["k8s_version"]
            status_model.node_count = info["node_count"]
            status_model.nodes_status = info["nodes_status"]
            status_model.nodes_details = info["nodes_details"]
            status_model.cpu_total = info["cpu_total"]
            status_model.cpu_allocated = info["cpu_allocated"]
            status_model.ram_total = info["ram_total"]
            status_model.ram_allocated = info["ram_allocated"]
            status_model.argocd_installed = info["argocd_installed"]
            status_model.argocd_version = info["argocd_version"]
            status_model.cert_manager_installed = info["cert_manager_installed"]
            status_model.cert_manager_version = info["cert_manager_version"]
            status_model.cnpg_installed = info["cnpg_installed"]
            status_model.cnpg_version = info["cnpg_version"]

            status_model.envoy_gateway_installed = info["envoy_gateway_installed"]
            status_model.envoy_gateway_version = info["envoy_gateway_version"]
            status_model.kafka_operator_installed = info["kafka_operator_installed"]
            status_model.kafka_operator_version = info["kafka_operator_version"]
            status_model.nifikop_installed = info["nifikop_installed"]
            status_model.nifikop_version = info["nifikop_version"]
            status_model.doris_operator_installed = info["doris_operator_installed"]
            status_model.doris_operator_version = info["doris_operator_version"]
            status_model.integrations_status = info["integrations_status"]
            status_model.node_ips = info["node_ips"]
            status_model.last_update = ts_now()
            status_model.message = None

        except Exception as e:
            logger.error(f"Failed to poll status for cluster {model.name}: {e}")
            stmt = select(K8sClusterStatus).where(
                K8sClusterStatus.k8s_cluster_id == model.id
            )
            result = await self.session.exec(stmt)
            status_model = result.one_or_none()
            if not status_model:
                status_model = K8sClusterStatus(k8s_cluster_id=model.id)
                self.session.add(status_model)
            status_model.status = "error"
            status_model.message = f"Cluster is unreachable: {str(e)}"
            status_model.last_update = ts_now()

            # Workaround circular import: PlatformService imports k8s_cluster
            from mindweaver.platform_service.base import PlatformService
            await PlatformService.mark_cluster_services_unreachable(
                self.session, model.id, model.name, str(e)
            )

        await self.session.flush()

    @classmethod
    def _get_core_v1_client(cls, model: K8sCluster) -> client.CoreV1Api:
        """Build a synchronous Kubernetes CoreV1Api client for the given cluster."""
        conf = client.Configuration()
        if model.type == K8sClusterType.IN_CLUSTER:
            config.load_incluster_config(client_configuration=conf)
        else:
            if not model.kubeconfig:
                raise ValueError(f"Cluster {model.name} has no kubeconfig")
            with tempfile.NamedTemporaryFile(mode="w") as kf:
                kf.write(model.kubeconfig)
                kf.flush()
                config.load_kube_config(config_file=kf.name, client_configuration=conf)
        conf.request_timeout = 10
        return client.CoreV1Api(client.ApiClient(conf))

    @staticmethod
    def _build_gpu_label_patch(gpu_vendor: str | None) -> dict[str, str | None]:
        """Build strategic-merge label patch for NVIDIA/AMD GPU provisioning labels."""
        if gpu_vendor == "nvidia":
            return {
                NVIDIA_GPU_LABEL: "true",
                AMD_GPU_LABEL: None,
                AMD_PCI_LABEL: None,
            }
        if gpu_vendor == "amd":
            return {
                AMD_GPU_LABEL: "true",
                AMD_PCI_LABEL: "true",
                NVIDIA_GPU_LABEL: None,
            }
        if gpu_vendor in (None, "", "none"):
            return {
                NVIDIA_GPU_LABEL: None,
                NVIDIA_PCI_LABEL: None,
                AMD_GPU_LABEL: None,
                AMD_PCI_LABEL: None,
            }
        raise ValueError(f"Unsupported GPU vendor '{gpu_vendor}'")

    async def update_node_labels(
        self,
        model: K8sCluster,
        node_name: str,
        set_labels: dict[str, str] | None = None,
        remove_labels: list[str] | None = None,
        roles: list[str] | None = None,
        gpu_vendor: Any = _UNSET,
    ) -> dict[str, Any]:
        """Update node labels, user-defined roles, and GPU provisioning labels on a K8s node."""
        patch_labels: dict[str, str | None] = {}

        for k, v in (set_labels or {}).items():
            validate_k8s_label_key(k)
            validate_k8s_label_value(v)
            if is_protected_node_label(k):
                raise ValueError(f"Label '{k}' is system-protected and cannot be modified")
            if k.startswith("node-role.kubernetes.io/"):
                role_part = k.split("node-role.kubernetes.io/", 1)[1]
                validate_role_name(role_part)
            patch_labels[k] = v

        for k in remove_labels or []:
            validate_k8s_label_key(k)
            if is_protected_node_label(k):
                raise ValueError(f"Label '{k}' is system-protected and cannot be removed")
            if k.startswith("node-role.kubernetes.io/"):
                role_part = k.split("node-role.kubernetes.io/", 1)[1]
                validate_role_name(role_part)
            patch_labels[k] = None

        validated_roles: list[str] | None = None
        if roles is not None:
            validated_roles = [validate_role_name(r) for r in roles]

        if gpu_vendor is not _UNSET:
            patch_labels.update(self._build_gpu_label_patch(gpu_vendor))

        def _patch():
            core_v1 = self._get_core_v1_client(model)
            if validated_roles is not None:
                node_obj = core_v1.read_node(name=node_name)
                raw = getattr(getattr(node_obj, "metadata", None), "labels", None)
                existing_labels = dict(raw) if isinstance(raw, dict) else {}
                existing_user_roles = {
                    k.split("node-role.kubernetes.io/", 1)[1]
                    for k in existing_labels
                    if k.startswith("node-role.kubernetes.io/")
                    and k.split("node-role.kubernetes.io/", 1)[1] not in PROTECTED_NODE_ROLES
                }
                desired_roles = set(validated_roles)
                for r in existing_user_roles - desired_roles:
                    patch_labels[f"node-role.kubernetes.io/{r}"] = None
                for r in desired_roles:
                    patch_labels[f"node-role.kubernetes.io/{r}"] = ""

            if patch_labels:
                core_v1.patch_node(
                    name=node_name,
                    body={"metadata": {"labels": patch_labels}},
                )

        await asyncio.to_thread(_patch)
        await self.poll_status(model)
        return {"status": "success", "node": node_name, "patched_labels": patch_labels}

    async def get_topology(self, model: K8sCluster) -> dict[str, Any]:
        """Return cluster rack hierarchy levels, user-defined roles, presets, and node assignments."""
        cfg = model.topology_config if isinstance(model.topology_config, dict) else {}
        levels = list(DEFAULT_TOPOLOGY_LEVELS)
        saved_roles = set(
            cfg["roles"] if "roles" in cfg and cfg["roles"] is not None else DEFAULT_NODE_ROLES
        )
        saved_presets = cfg.get("presets") if isinstance(cfg.get("presets"), list) else []
        presets: list[dict[str, str]] = []
        for entry in saved_presets:
            if isinstance(entry, dict):
                clean = {
                    lvl["name"]: str(entry[lvl["name"]]).strip()
                    for lvl in levels
                    if entry.get(lvl["name"])
                }
                if clean and clean not in presets:
                    presets.append(clean)

        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == model.id
        )
        res = await self.session.exec(stmt)
        status_model = res.one_or_none()
        nodes_details = (
            list(status_model.nodes_details)
            if status_model and isinstance(status_model.nodes_details, list)
            else []
        )

        assignments: dict[str, dict[str, str]] = {}
        saved_assignments = cfg.get("assignments") or {}
        for host, vals in saved_assignments.items():
            if isinstance(vals, dict):
                assignments[host] = {k: v for k, v in vals.items() if v}

        for node in nodes_details:
            host = node.get("hostname")
            if not host:
                continue
            node_labels = node.get("labels") or {}
            node_topo = dict(assignments.get(host) or {})
            for lvl in levels:
                key = lvl.get("key")
                name = lvl.get("name")
                if key and name and node_labels.get(key):
                    live_val = node_labels[key]
                    saved_val = node_topo.get(name)
                    if not saved_val or sanitize_topology_label_value(saved_val) != live_val:
                        node_topo[name] = live_val
            if node_topo:
                assignments[host] = node_topo
            for r in node.get("roles") or []:
                if r not in PROTECTED_NODE_ROLES:
                    saved_roles.add(r)

        return {
            "levels": levels,
            "roles": sorted(saved_roles),
            "presets": presets,
            "assignments": assignments,
            "nodes": nodes_details,
        }

    async def update_topology(
        self,
        model: K8sCluster,
        roles: list[str] | None = None,
        presets: list[dict[str, str]] | None = None,
        assignments: dict[str, dict[str, str | None]] | None = None,
    ) -> dict[str, Any]:
        """Persist rack hierarchy roles/presets/assignments and patch topology labels onto K8s nodes."""
        cfg = dict(model.topology_config) if isinstance(model.topology_config, dict) else {}
        active_levels = list(DEFAULT_TOPOLOGY_LEVELS)

        if roles is not None:
            cfg["roles"] = sorted({validate_role_name(r) for r in roles})

        level_key_by_name = {lvl["name"]: lvl["key"] for lvl in active_levels}

        if presets is not None:
            clean_presets: list[dict[str, str]] = []
            for entry in presets:
                if not isinstance(entry, dict):
                    raise ValueError("Each topology preset must be an object of region/zone/rack")
                clean_entry: dict[str, str] = {}
                for tier_name in level_key_by_name:
                    raw_val = entry.get(tier_name)
                    if raw_val is None or str(raw_val).strip() == "":
                        continue
                    val = str(raw_val).strip()
                    validate_topology_value(val, allow_slash=(tier_name == "rack"))
                    clean_entry[tier_name] = val
                for unknown_key in entry:
                    if unknown_key not in level_key_by_name:
                        raise ValueError(f"Unknown topology level '{unknown_key}'")
                if not clean_entry:
                    raise ValueError("Topology preset must specify at least one of region, zone, or rack")
                if clean_entry not in clean_presets:
                    clean_presets.append(clean_entry)
            cfg["presets"] = clean_presets

        active_presets = cfg.get("presets") if isinstance(cfg.get("presets"), list) else []
        node_patches: dict[str, dict[str, str | None]] = {}

        if assignments is not None:
            stored_assignments = dict(cfg.get("assignments") or {})
            for hostname, tier_map in assignments.items():
                patch_map: dict[str, str | None] = {}
                clean_tiers = dict(stored_assignments.get(hostname) or {})
                candidate_entry: dict[str, str] = {}
                for tier_name, tier_val in tier_map.items():
                    if tier_name not in level_key_by_name:
                        raise ValueError(f"Unknown topology level '{tier_name}'")
                    k8s_key = level_key_by_name[tier_name]
                    if tier_val is None or tier_val == "":
                        patch_map[k8s_key] = None
                        clean_tiers.pop(tier_name, None)
                    else:
                        allow_slash = tier_name == "rack"
                        validate_topology_value(tier_val, allow_slash=allow_slash)
                        patch_map[k8s_key] = sanitize_topology_label_value(tier_val)
                        clean_tiers[tier_name] = tier_val
                        candidate_entry[tier_name] = tier_val
                if candidate_entry and active_presets and candidate_entry not in active_presets:
                    raise ValueError(
                        f"Topology combination {candidate_entry} is not in configured presets"
                    )
                stored_assignments[hostname] = clean_tiers
                if patch_map:
                    node_patches[hostname] = patch_map
            cfg["assignments"] = stored_assignments

        model.topology_config = cfg
        flag_modified(model, "topology_config")
        await self.session.flush()

        if node_patches:
            def _patch_all():
                core_v1 = self._get_core_v1_client(model)
                for hostname, patch_map in node_patches.items():
                    core_v1.patch_node(
                        name=hostname,
                        body={"metadata": {"labels": patch_map}},
                    )

            await asyncio.to_thread(_patch_all)
            await self.poll_status(model)

        return await self.get_topology(model)

    @classmethod
    def widgets(cls) -> dict[str, Any]:
        return {
            "description": {"order": 5, "column_span": 2},
            "type": {
                "order": 10,
                "type": "select",
                "options": [
                    {"label": "In-Cluster", "value": "in-cluster"},
                    {"label": "Remote", "value": "remote"},
                ],
                "label": "K8S Cluster Type",
            },
            "kubeconfig": {
                "order": 11,
                "type": "textarea",
                "column_span": 2,
                "label": "Kubeconfig",
            },
        }
