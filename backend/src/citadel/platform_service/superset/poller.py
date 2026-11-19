# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import asyncio
import logging
import tempfile
from kubernetes import client, config
from citadel.fw.model import ts_now
from citadel.crypto import decrypt_password
from .model import SupersetPlatform
from .service import SupersetPlatformService

logger = logging.getLogger(__name__)


@SupersetPlatformService.register_poller()
class SupersetPoller:
    """Poller for Superset platform service."""

    def __init__(self, service: SupersetPlatformService, model: SupersetPlatform):
        self.service = service
        self.model = model

    async def poll(self):
        """Polls the status of the ArgoCD application and Kubernetes resources."""
        kubeconfig = await self.service.kubeconfig(self.model)
        namespace = await self.service._resolve_namespace(self.model)
        state = await self.service.platform_state(self.model)
        is_active = state.active if state else True

        def _poll(active: bool):
            if kubeconfig is None:
                config.load_incluster_config()
                k8s_client = client.ApiClient()
            else:
                with tempfile.NamedTemporaryFile(mode="w") as kf:
                    kf.write(kubeconfig)
                    kf.flush()
                    k8s_client = config.new_client_from_config(config_file=kf.name)
            k8s_client.configuration.request_timeout = 10

            custom_api = client.CustomObjectsApi(k8s_client)
            core_v1 = client.CoreV1Api(k8s_client)

            # 1. Check ArgoCD Application Status
            try:
                argo_app = custom_api.get_namespaced_custom_object(
                    group="argoproj.io",
                    version="v1alpha1",
                    namespace="argocd",
                    plural="applications",
                    name=self.model.name,
                )
                sync_status = (
                    argo_app.get("status", {}).get("sync", {}).get("status", "Unknown")
                )
                health_status = (
                    argo_app.get("status", {})
                    .get("health", {})
                    .get("status", "Unknown")
                )

                if health_status == "Healthy":
                    status = "online"
                elif health_status in ["Progressing", "Pending"]:
                    status = "pending"
                else:
                    status = "error"

                message = f"Sync: {sync_status}, Health: {health_status}"
            except Exception as e:
                if not active:
                    status = "offline"
                    message = "Decommissioned"
                else:
                    status = "error"
                    message = f"Cluster is unreachable: {str(e)}"
                return status, message, {}, [], []

            # 2. Fetch Pod Status
            try:
                pods = core_v1.list_namespaced_pod(
                    namespace=namespace,
                    label_selector=f"app.kubernetes.io/instance={self.model.name}",
                )
                active_pods = [
                    p for p in pods.items if p.status.phase != "Succeeded"
                ]
                ready_pods = sum(
                    1
                    for p in active_pods
                    if p.status.phase == "Running"
                    and any(c.ready for c in (p.status.container_statuses or []))
                )
                total_pods = len(active_pods)
                if status == "online" and (total_pods == 0 or ready_pods < total_pods):
                    status = "pending"
                message += f" | Pods: {ready_pods}/{total_pods}"
            except Exception as e:
                logger.error(f"Failed to fetch pods for {self.model.name}: {e}")
                if status == "online":
                    status = "pending"

            # 3. NodePorts are intentionally disabled (Superset UI uses Ingress or internal ClusterIP)
            node_ports = []

            # 4. Fetch Nodes for IP info
            cluster_nodes = []
            try:
                nodes = core_v1.list_node()
                for node in nodes.items:
                    node_info = {"hostname": "unknown", "ipv4": None, "ipv6": None}
                    for addr in node.status.addresses:
                        if addr.type == "Hostname":
                            node_info["hostname"] = addr.address
                        elif addr.type == "InternalIP":
                            if ":" in addr.address:
                                node_info["ipv6"] = addr.address
                            else:
                                node_info["ipv4"] = addr.address
                    cluster_nodes.append(node_info)
            except Exception as e:
                logger.error(f"Failed to fetch nodes: {e}")

            return (
                status,
                message,
                argo_app.get("status", {}),
                node_ports,
                cluster_nodes,
            )

        status, message, extra_data, node_ports, cluster_nodes = (
            await asyncio.to_thread(_poll, is_active)
        )

        state = await self.service.platform_state(self.model)
        if not state:
            state = self.service.state_model(platform_id=self.model.id)
            self.service.session.add(state)

        if not state.active:
            state.status = "offline"
            state.message = "Decommissioned"
            await self.service.session.flush()
            return

        if status == "error":
            state.status = status
            state.message = message
            state.last_heartbeat = ts_now()
            await self.service.session.flush()
            return

        state.status = status
        state.message = message
        project = await self.service.project(self.model)
        if extra_data is None:
            extra_data = {}
        extra_data["namespace"] = namespace
        extra_data["ingress_domain"] = project.ingress_domain
        state.extra_data = extra_data
        state.node_ports = node_ports
        state.cluster_nodes = cluster_nodes

        # Populate admin credentials
        state.admin_user = "admin"
        state.admin_password = decrypt_password(self.model.admin_password)

        # Derive Superset URI (Ingress when configured, otherwise internal ClusterIP service)
        if status == "online":
            if project.ingress_domain:
                state.superset_uri = f"https://{self.model.name}.{project.ingress_domain}"
                state.superset_uri_ipv6 = None
            else:
                state.superset_uri = (
                    f"http://{self.model.name}.{namespace}.svc.cluster.local:8088"
                )
                state.superset_uri_ipv6 = None

        state.last_heartbeat = ts_now()
        await self.service.session.flush()
