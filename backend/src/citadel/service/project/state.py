# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import logging
from sqlmodel import select, func
from citadel.fw.state import BaseState
from .service import ProjectService

logger = logging.getLogger(__name__)


def _is_not_found_error(exc: Exception) -> bool:
    """Return True if an exception represents a Kubernetes 404 Not Found error."""
    return getattr(exc, "status", None) == 404


def _find_condition(resource: dict, condition_type: str) -> dict | None:
    """Find a status condition entry by type on a Kubernetes custom resource dict."""
    conditions = (resource or {}).get("status", {}).get("conditions", [])
    for cond in conditions:
        if cond.get("type") == condition_type:
            return cond
    return None


def _check_custom_resource_ready(
    custom_api,
    *,
    group: str,
    version: str,
    namespace: str,
    plural: str,
    name: str,
    display_name: str,
) -> dict[str, str]:
    """Check existence and Ready condition of a namespaced Kubernetes custom resource."""
    try:
        res = custom_api.get_namespaced_custom_object(
            group=group,
            version=version,
            namespace=namespace,
            plural=plural,
            name=name,
        )
    except Exception as exc:
        if _is_not_found_error(exc):
            return {"status": "offline", "message": f"{display_name} '{name}' not found"}
        return {"status": "error", "message": f"Failed to check {display_name}: {exc}"}

    ready_cond = _find_condition(res, "Ready")
    if ready_cond:
        if ready_cond.get("status") == "True":
            return {"status": "online", "message": f"{display_name} '{name}' ready"}
        reason = ready_cond.get("message") or ready_cond.get("reason") or "Not ready yet"
        return {"status": "pending", "message": reason}
    return {"status": "pending", "message": f"{display_name} '{name}' status unknown"}


def _check_project_integrations(
    core_v1,
    custom_api,
    *,
    project_name: str,
    namespace: str,
    ingress_domain: str | None,
    secret_names: set[str],
    ports_info: list,
) -> dict[str, dict[str, str]]:
    """Evaluate health and presence of all project-level Kubernetes integrations."""
    integrations: dict[str, dict[str, str]] = {}

    # 1. Namespace
    try:
        ns_obj = core_v1.read_namespace(name=namespace)
        phase = getattr(getattr(ns_obj, "status", None), "phase", None) or "Active"
        if phase == "Active":
            integrations["namespace"] = {
                "status": "online",
                "message": f"Namespace '{namespace}' active",
            }
        else:
            integrations["namespace"] = {
                "status": "pending",
                "message": f"Namespace '{namespace}' phase: {phase}",
            }
    except Exception as exc:
        if _is_not_found_error(exc):
            integrations["namespace"] = {
                "status": "offline",
                "message": f"Namespace '{namespace}' not found",
            }
        else:
            integrations["namespace"] = {
                "status": "error",
                "message": f"Failed to check namespace: {exc}",
            }

    # 2. ArgoCD AppProject
    try:
        custom_api.get_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            namespace="argocd",
            plural="appprojects",
            name=project_name,
        )
        integrations["argocd_project"] = {
            "status": "online",
            "message": f"AppProject '{project_name}' configured",
        }
    except Exception as exc:
        if _is_not_found_error(exc):
            integrations["argocd_project"] = {
                "status": "offline",
                "message": f"AppProject '{project_name}' not found",
            }
        else:
            integrations["argocd_project"] = {
                "status": "error",
                "message": f"Failed to check AppProject: {exc}",
            }

    # 3. Self-Signed Issuer
    integrations["self_signed_issuer"] = _check_custom_resource_ready(
        custom_api,
        group="cert-manager.io",
        version="v1",
        namespace=namespace,
        plural="issuers",
        name=f"{project_name}-selfsigned-issuer",
        display_name="Issuer",
    )

    # 4. Trusted Certs Secret
    if "trusted-certs" in secret_names:
        integrations["trusted_certs"] = {
            "status": "online",
            "message": "Secret 'trusted-certs' present",
        }
    else:
        integrations["trusted_certs"] = {
            "status": "offline",
            "message": "Secret 'trusted-certs' not found",
        }

    # 5. Envoy Gateway & 6. Wildcard Certificate (require ingress_domain)
    if not ingress_domain:
        integrations["envoy_gateway"] = {
            "status": "offline",
            "message": "Ingress domain not configured",
        }
        integrations["wildcard_certificate"] = {
            "status": "offline",
            "message": "Ingress domain not configured",
        }
        return integrations

    try:
        gw = custom_api.get_namespaced_custom_object(
            group="gateway.networking.k8s.io",
            version="v1",
            namespace=namespace,
            plural="gateways",
            name="project-gateway",
        )
        programmed = _find_condition(gw, "Programmed")
        accepted = _find_condition(gw, "Accepted")
        if programmed and programmed.get("status") == "True":
            integrations["envoy_gateway"] = {
                "status": "online",
                "message": "Gateway 'project-gateway' programmed",
            }
        elif accepted and accepted.get("status") == "True":
            integrations["envoy_gateway"] = {
                "status": "pending",
                "message": "Gateway accepted, awaiting programming",
            }
        elif ports_info:
            integrations["envoy_gateway"] = {
                "status": "online",
                "message": "Gateway service active",
            }
        else:
            integrations["envoy_gateway"] = {
                "status": "pending",
                "message": "Gateway 'project-gateway' configuring",
            }
    except Exception as exc:
        if _is_not_found_error(exc):
            if ports_info:
                integrations["envoy_gateway"] = {
                    "status": "online",
                    "message": "Gateway service active",
                }
            else:
                integrations["envoy_gateway"] = {
                    "status": "offline",
                    "message": "Gateway 'project-gateway' not found",
                }
        else:
            integrations["envoy_gateway"] = {
                "status": "error",
                "message": f"Failed to check Gateway: {exc}",
            }

    integrations["wildcard_certificate"] = _check_custom_resource_ready(
        custom_api,
        group="cert-manager.io",
        version="v1",
        namespace=namespace,
        plural="certificates",
        name=f"envoy-{project_name}",
        display_name="Certificate",
    )

    return integrations


@ProjectService.with_state()
class ProjectState(BaseState):
    """
    Project state provides an overview of project resources and cluster health.
    """

    async def get(self):
        from citadel.platform_service.pgsql import (
            PgSqlPlatform,
            PgSqlPlatformState,
        )
        from citadel.platform_service.trino import (
            TrinoPlatform,
            TrinoPlatformState,
        )
        from citadel.platform_service.hive_metastore import (
            HiveMetastorePlatform,
            HiveMetastorePlatformState,
        )
        from citadel.platform_service.superset import (
            SupersetPlatform,
            SupersetPlatformState,
        )
        from citadel.platform_service.airflow import (
            AirflowPlatform,
            AirflowPlatformState,
        )
        from citadel.platform_service.kafka import (
            KafkaPlatform,
            KafkaPlatformState,
        )
        from citadel.platform_service.nifi import (
            NifiPlatform,
            NifiPlatformState,
        )
        from citadel.service.k8s_cluster import K8sClusterStatus

        # Helper to get counts
        async def _get_count(plat_cls, state_cls):
            stmt = (
                select(func.count(plat_cls.id))
                .join(
                    state_cls,
                    plat_cls.id == state_cls.platform_id,
                    isouter=True,
                )
                .where(plat_cls.project_id == self.model.id)
                .where(state_cls.active == True)
            )
            res = await self.svc.session.exec(stmt)
            return res.one_or_none() or 0

        pgsql_count = await _get_count(PgSqlPlatform, PgSqlPlatformState)
        trino_count = await _get_count(TrinoPlatform, TrinoPlatformState)
        hive_metastore_count = await _get_count(HiveMetastorePlatform, HiveMetastorePlatformState)
        superset_count = await _get_count(SupersetPlatform, SupersetPlatformState)
        airflow_count = await _get_count(AirflowPlatform, AirflowPlatformState)
        kafka_count = await _get_count(KafkaPlatform, KafkaPlatformState)
        nifi_count = await _get_count(NifiPlatform, NifiPlatformState)

        # Get cluster status
        status_data = {}
        cluster_node_ips = []
        if self.model.k8s_cluster_id:
            stmt_status = select(K8sClusterStatus).where(
                K8sClusterStatus.k8s_cluster_id == self.model.k8s_cluster_id
            )
            result_status = await self.svc.session.exec(stmt_status)
            status_model = result_status.one_or_none()

            if status_model:
                status_data = status_model.model_dump(
                    exclude={"id", "k8s_cluster_id", "last_update"}
                )
                status_data["last_update"] = status_model.last_update.isoformat()
                cluster_node_ips = getattr(status_model, "node_ips", None) or []

        # Dynamic check for project k8s integrations, ingress ports, and Dex OIDC
        dex_installed = False
        dex_version = None
        ingress_ports = []
        integrations_status = {}
        namespace = self.model.k8s_namespace or self.model.name
        if self.model.k8s_cluster_id and namespace and status_data.get("status") != "error":
            from citadel.service.k8s_cluster import K8sCluster, K8sClusterType
            stmt_c = select(K8sCluster).where(K8sCluster.id == self.model.k8s_cluster_id)
            res_c = await self.svc.session.exec(stmt_c)
            cluster_model = res_c.one_or_none()
            if cluster_model:
                import tempfile
                import asyncio
                from kubernetes import client, config

                def _get_project_k8s_status():
                    try:
                        conf = client.Configuration()
                        if cluster_model.type == K8sClusterType.IN_CLUSTER:
                            config.load_incluster_config(client_configuration=conf)
                        else:
                            if not cluster_model.kubeconfig:
                                return False, None, [], {}
                            with tempfile.NamedTemporaryFile(mode="w") as kf:
                                kf.write(cluster_model.kubeconfig)
                                kf.flush()
                                config.load_kube_config(config_file=kf.name, client_configuration=conf)
                        conf.request_timeout = 5
                        k8s_client = client.ApiClient(conf)
                        core_v1 = client.CoreV1Api(k8s_client)
                        custom_api = client.CustomObjectsApi(k8s_client)

                        ports_info = []
                        try:
                            # Helper to extract load balancer ingress
                            def _get_lb_ips(service):
                                ips = []
                                if service.status and service.status.load_balancer and service.status.load_balancer.ingress:
                                    for ing in service.status.load_balancer.ingress:
                                        if ing.ip:
                                            ips.append(ing.ip)
                                        elif ing.hostname:
                                            ips.append(ing.hostname)
                                return ips

                            # 1. Search in project namespace
                            try:
                                svcs = core_v1.list_namespaced_service(namespace=namespace)
                                for svc in svcs.items:
                                    if "envoy" in svc.metadata.name or "project-gateway" in svc.metadata.name:
                                        lb_ips = _get_lb_ips(svc)
                                        for p in svc.spec.ports:
                                            ports_info.append({
                                                "name": svc.metadata.name,
                                                "port": p.port,
                                                "node_port": p.node_port if getattr(p, "node_port", None) else None,
                                                "protocol": p.protocol,
                                                "load_balancer_ips": lb_ips,
                                            })
                            except Exception as ns_svc_e:
                                if not _is_not_found_error(ns_svc_e):
                                    logger.warning(f"Failed to list services in namespace {namespace}: {ns_svc_e}")

                            # 2. Search in envoy-gateway-system namespace for prefix matching
                            expected_prefix = f"envoy-{namespace}-project-gateway"
                            try:
                                eg_svcs = core_v1.list_namespaced_service(namespace="envoy-gateway-system")
                                for svc in eg_svcs.items:
                                    if svc.metadata.name.startswith(expected_prefix):
                                        lb_ips = _get_lb_ips(svc)
                                        for p in svc.spec.ports:
                                            ports_info.append({
                                                "name": svc.metadata.name,
                                                "port": p.port,
                                                "node_port": p.node_port if getattr(p, "node_port", None) else None,
                                                "protocol": p.protocol,
                                                "load_balancer_ips": lb_ips,
                                            })
                            except Exception as eg_e:
                                if not _is_not_found_error(eg_e):
                                    logger.warning(f"Failed to list services in envoy-gateway-system: {eg_e}")
                        except Exception as e:
                            logger.warning(f"Failed to list Envoy/gateway services: {e}")

                        secret_names = set()
                        installed = False
                        version = None
                        try:
                            secrets = core_v1.list_namespaced_secret(namespace=namespace)
                            for secret in secrets.items:
                                secret_names.add(secret.metadata.name)
                                if secret.metadata.name.startswith("sh.helm.release.v1.dex"):
                                    installed = True
                            if not installed:
                                dex_svcs = core_v1.list_namespaced_service(
                                    namespace=namespace,
                                    label_selector="app.kubernetes.io/name=dex"
                                )
                                if dex_svcs.items:
                                    installed = True

                            if installed:
                                pods = core_v1.list_namespaced_pod(
                                    namespace=namespace,
                                    label_selector="app.kubernetes.io/name=dex"
                                )
                                if pods.items:
                                    pod = pods.items[0]
                                    version = pod.metadata.labels.get("app.kubernetes.io/version")
                                    if not version and pod.spec.containers:
                                        image = pod.spec.containers[0].image
                                        if ":" in image:
                                            version = image.split(":")[-1]
                        except Exception as dex_e:
                            if not _is_not_found_error(dex_e):
                                logger.warning(f"Failed to check project Dex/secrets status: {dex_e}")

                        integrations = _check_project_integrations(
                            core_v1,
                            custom_api,
                            project_name=self.model.name,
                            namespace=namespace,
                            ingress_domain=self.model.ingress_domain,
                            secret_names=secret_names,
                            ports_info=ports_info,
                        )
                        return installed, version, ports_info, integrations
                    except Exception as e:
                        logger.warning(f"Failed to check project k8s status: {e}")
                        return False, None, [], {}

                dex_installed, dex_version, ingress_ports, integrations_status = await asyncio.to_thread(
                    _get_project_k8s_status
                )

        return {
            "pgsql": pgsql_count,
            "trino": trino_count,
            "hive_metastore": hive_metastore_count,
            "superset": superset_count,
            "airflow": airflow_count,
            "kafka": kafka_count,
            "nifi": nifi_count,
            "cluster": status_data,
            "dex_installed": dex_installed,
            "dex_version": dex_version,
            "cluster_node_ips": cluster_node_ips,
            "ingress_ports": ingress_ports,
            "integrations_status": integrations_status,
            "sync_state": self.model.sync_state or {},
        }

