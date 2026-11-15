# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import asyncio
import logging
import tempfile
from typing import Any

from kubernetes import client, config
from sqlmodel import select

from mindweaver.service import Service
from mindweaver.fw.model import ts_now
from mindweaver.tasks.poll_coordinator import schedule_k8s_cluster_poll
from .model import K8sCluster, K8sClusterStatus, K8sClusterType
from . import permission

logger = logging.getLogger(__name__)


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

                # Get Nodes
                nodes = core_v1.list_node()
                node_count = len(nodes.items)
                nodes_status = {}
                cpu_total = 0.0
                ram_total = 0.0

                def _parse_res(res):
                    if res.endswith("Ki"):
                        return float(res[:-2]) / 1024 / 1024
                    if res.endswith("Mi"):
                        return float(res[:-2]) / 1024
                    if res.endswith("Gi"):
                        return float(res[:-2])
                    if res.endswith("m"):
                        return float(res[:-1]) / 1000
                    try:
                        return float(res)
                    except ValueError:
                        return 0.0

                node_ips = []
                for node in nodes.items:
                    name = node.metadata.name
                    status = "Unknown"
                    for cond in node.status.conditions:
                        if cond.type == "Ready":
                            status = "Ready" if cond.status == "True" else "NotReady"
                            break
                    nodes_status[name] = status

                    for addr in node.status.addresses:
                        if addr.type in ["InternalIP", "ExternalIP"] and addr.address not in node_ips:
                            node_ips.append(addr.address)

                    # Resource totals
                    cpu_total += _parse_res(node.status.capacity.get("cpu", "0"))
                    # Convert memory to GiB
                    ram_total += _parse_res(node.status.capacity.get("memory", "0"))

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
                    "cpu_total": cpu_total,
                    "ram_total": ram_total,
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
            status_model.cpu_total = info["cpu_total"]
            status_model.ram_total = info["ram_total"]
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
