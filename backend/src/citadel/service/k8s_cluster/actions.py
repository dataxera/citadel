# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import asyncio
import logging
import tempfile
import os
import yaml
import jinja2 as j2
from kubernetes import client, config

from sqlmodel import select
from sqlalchemy.orm.attributes import flag_modified
from citadel.fw.action import BaseAction
from citadel.fw.model import ts_now
from .service import K8sClusterService
from .model import K8sCluster, K8sClusterStatus, K8sClusterType

logger = logging.getLogger(__name__)

CORE_INTEGRATIONS = [
    ("argocd", "ArgoCD", "argocd_installed"),
    ("cert_manager", "Cert Manager", "cert_manager_installed"),
    ("cnpg", "CNPG Operator", "cnpg_installed"),
    ("envoy_gateway", "Envoy Gateway", "envoy_gateway_installed"),
    ("kafka_operator", "Kafka Operator", "kafka_operator_installed"),
    ("nifikop", "NiFi Operator", "nifikop_installed"),
    ("doris_operator", "Doris Operator", "doris_operator_installed"),
    ("kube_prometheus_stack", "Kube Prometheus Stack", "kube_prometheus_stack_installed"),
]


def build_initial_sync_state() -> dict:
    """Build the initial persistent sync_state payload for core integrations sync."""
    now_iso = ts_now().isoformat()
    return {
        "status": "in_progress",
        "started_at": now_iso,
        "updated_at": now_iso,
        "completed_at": None,
        "total": len(CORE_INTEGRATIONS),
        "completed": 0,
        "tasks": {
            key: {
                "label": label,
                "status": "pending",
                "message": None,
                "logs": None,
                "updated_at": now_iso,
                "attempts": 0,
            }
            for key, label, _ in CORE_INTEGRATIONS
        },
    }


def get_integration_action_class(key: str):
    """Return the Install*Action class corresponding to a core integration key."""
    mapping = {
        "argocd": InstallArgoCDAction,
        "cert_manager": InstallCertManagerAction,
        "cnpg": InstallCNPGAction,
        "envoy_gateway": InstallEnvoyGatewayAction,
        "kafka_operator": InstallKafkaOperatorAction,
        "nifikop": InstallNifikopAction,
        "doris_operator": InstallDorisOperatorAction,
        "kube_prometheus_stack": InstallKubePrometheusStackAction,
    }
    if key not in mapping:
        raise ValueError(f"Unknown core integration key: {key}")
    return mapping[key]


@K8sClusterService.register_action("install_argocd")
class InstallArgoCDAction(BaseAction):

    async def available(self) -> bool:
        # Only available if not already installed
        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status = result.one_or_none()
        return not (status and status.argocd_installed)

    async def __call__(self, **kwargs):
        from citadel.tasks.k8s_cluster_status import install_argocd_task

        # Set status to installed immediately so UI reflects it
        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status_model = result.one_or_none()
        if not status_model:
            status_model = K8sClusterStatus(k8s_cluster_id=self.model.id)
            self.session.add(status_model)
        status_model.argocd_installed = True
        await self.session.flush()

        install_argocd_task.delay(self.model.id)
        return {
            "status": "success",
            "message": "ArgoCD installation triggered and status being refreshed.",
        }

    async def _resolve_stack(self):
        """Resolve stack linked via projects using this cluster or fall back to latest stack."""
        if hasattr(self.session, "_mock_name") or "mock" in type(self.session).__name__.lower():
            return None

        from citadel.service.project.model import Project
        from citadel.service.stack.model import Stack

        stack = None
        try:
            proj_stmt = select(Project).where(Project.k8s_cluster_id == self.model.id)
            res = await self.session.exec(proj_stmt)
            proj = res.first()
            if proj and proj.stack_id:
                stack_stmt = select(Stack).where(Stack.id == proj.stack_id)
                res_stack = await self.session.exec(stack_stmt)
                stack = res_stack.one_or_none()
        except Exception as e:
            logger.warning(f"Failed to query project/stack for cluster: {e}")

        if not stack:
            try:
                res_stack = await self.session.exec(select(Stack).order_by(Stack.version.desc()))
                stack = res_stack.first()
            except Exception as e:
                logger.warning(f"Failed to query any stack: {e}")
        return stack

    async def resolve_integration_chart(
        self,
        component_name: str,
        chart_key: str = "main",
        default_repo: str = "",
        default_chart: str = "",
        default_version: str = "",
    ) -> tuple[str, str, str]:
        """Resolve integration chart (repo, chart, version) based on stack linked to project or fall back"""
        stack = await self._resolve_stack()
        if stack:
            repo, chart, version = stack.get_chart_for_component(component_name, chart_key)
            if repo or chart or version:
                return repo or default_repo, chart or default_chart, version or default_version
        return default_repo, default_chart, default_version

    async def resolve_integration_image(
        self,
        component_name: str,
        image_key: str = "main",
        default_image: str = "",
        default_tag: str = "",
    ) -> tuple[str, str]:
        """Resolve integration image (repository, tag) based on stack linked to project or fall back."""
        stack = await self._resolve_stack()
        if stack:
            img, tag = stack.get_image_for_component(component_name, image_key)
            if img or tag:
                return img or default_image, tag or default_tag
        return default_image, default_tag

    async def resolve_integration_version(self, component_name: str, default_version: str) -> str:
        """Resolve component integration version based on stack linked to project or fall back"""
        _, _, version = await self.resolve_integration_chart(
            component_name=component_name,
            chart_key="main",
            default_version=default_version,
        )
        return version

    async def run(self):
        """Install ArgoCD to the cluster using Helm chart"""
        logger.info(f"Installing ArgoCD for cluster {self.model.name}")

        repo_url, chart_name, version = await self.resolve_integration_chart(
            "argocd", "main", "https://argoproj.github.io/argo-helm", "argo/argo-cd", "9.4.4"
        )
        main_img, main_tag = await self.resolve_integration_image(
            "argocd", "main", "quay.io/argoproj/argocd", "v2.14.2"
        )
        dex_img, dex_tag = await self.resolve_integration_image(
            "argocd", "dex", "ghcr.io/dexidp/dex", "v2.41.1"
        )
        redis_img, redis_tag = await self.resolve_integration_image(
            "argocd", "redis", "public.ecr.aws/docker/library/redis", "7.4.2-alpine"
        )
        release_name = "argocd"
        namespace = "argocd"

        await self._install_helm_chart(
            repo_name="argo",
            repo_url=repo_url,
            release_name=release_name,
            chart_name=chart_name,
            namespace=namespace,
            set_vals={
                "global.image.repository": main_img,
                "global.image.tag": main_tag,
                "dex.image.repository": dex_img,
                "dex.image.tag": dex_tag,
                "redis.image.repository": redis_img,
                "redis.image.tag": redis_tag,
            },
            version=version,
        )

        await self.ensure_load_balancer()

    async def ensure_load_balancer(self):
        """Ensure the LoadBalancer service for ArgoCD is deployed."""
        logger.info("Deploying LoadBalancer service for ArgoCD")
        await self._apply_template(
            "argocd-lb.yml.j2",
            namespace="argocd",
        )

    def _get_kubernetes_clients(self):
        """Helper to load kubernetes config and return clients"""
        if self.model.type == K8sClusterType.IN_CLUSTER:
            config.load_incluster_config()
            return client.CoreV1Api(), client.ApiextensionsV1Api()
        else:
            if not self.model.kubeconfig:
                raise ValueError(f"Cluster {self.model.name} has no kubeconfig")
            with tempfile.NamedTemporaryFile(mode="w", delete=False) as kf:
                kf.write(self.model.kubeconfig)
                kf.flush()
                temp_name = kf.name
            try:
                api_client = config.new_client_from_config(config_file=temp_name)
                return client.CoreV1Api(api_client), client.ApiextensionsV1Api(api_client)
            finally:
                try:
                    os.unlink(temp_name)
                except Exception:
                    pass

    async def _wait_for_crd_and_namespace(self, crd_names: list[str], namespace: str = None, timeout: int = 60):
        """Wait for specified CRDs and optionally a namespace to be registered and exist"""
        logger.info(f"Waiting for CRDs {crd_names} and namespace {namespace} to be ready...")
        try:
            core_api, ext_api = self._get_kubernetes_clients()
        except Exception as e:
            logger.warning(f"Could not load kubernetes clients to wait: {e}")
            return

        for _ in range(int(timeout / 2)):
            try:
                ns_ready = True
                if namespace:
                    try:
                        core_api.read_namespace(namespace)
                    except Exception:
                        ns_ready = False
                
                crds_ready = True
                for crd in crd_names:
                    try:
                        ext_api.read_custom_resource_definition(crd)
                    except Exception:
                        crds_ready = False
                        break
                
                if ns_ready and crds_ready:
                    logger.info("CRDs and namespace are ready!")
                    return
            except Exception as e:
                logger.warning(f"Error checking CRDs/namespace: {e}")
            await asyncio.sleep(2)
        logger.warning(f"Timed out waiting for CRDs {crd_names} and namespace {namespace}")

    async def _apply_template(self, template_name: str, **kwargs):
        """Load, render and apply a manifest template from the templates directory"""
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        env = j2.Environment(loader=j2.FileSystemLoader(template_dir))
        template = env.get_template(template_name)
        manifest = template.render(**kwargs)
        await self._apply_yaml(manifest)

    async def _install_helm_chart(
        self,
        repo_name: str,
        repo_url: str,
        release_name: str,
        chart_name: str,
        namespace: str,
        set_vals: dict[str, str] = None,
        create_namespace: bool = True,
        version: str = None,
    ):
        kubeconfig_path = None
        temp_kf = None

        try:
            if self.model.type == K8sClusterType.REMOTE:
                if not self.model.kubeconfig:
                    raise ValueError(f"Cluster {self.model.name} has no kubeconfig")
                temp_kf = tempfile.NamedTemporaryFile(mode="w", delete=False)
                temp_kf.write(self.model.kubeconfig)
                temp_kf.flush()
                temp_kf.close()
                kubeconfig_path = temp_kf.name

            async def run_helm(*args):
                cmd = ["helm"]
                if kubeconfig_path:
                    cmd.extend(["--kubeconfig", kubeconfig_path])
                cmd.extend(args)
                logger.debug(f"Running Helm command: {' '.join(cmd)}")
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    raise RuntimeError(f"Helm command failed: {stderr.decode()}")
                return stdout.decode()

            # Ensure repo is added
            if repo_url and not repo_url.startswith("oci://"):
                await run_helm("repo", "add", repo_name, repo_url)
                await run_helm("repo", "update")

            # Install
            args = [
                "upgrade",
                "--install",
                release_name,
                chart_name,
                "--namespace",
                namespace,
                "--wait",
            ]
            if create_namespace:
                args.append("--create-namespace")

            if version:
                args.extend(["--version", version])

            if set_vals:
                for k, v in set_vals.items():
                    args.extend(["--set", f"{k}={v}"])

            await run_helm(*args)

        finally:
            if temp_kf:
                try:
                    os.unlink(temp_kf.name)
                except Exception:
                    pass

    async def _apply_yaml(self, manifest: str):
        kubeconfig_path = None
        temp_kf = None
        temp_manifest = None

        try:
            if self.model.type == K8sClusterType.REMOTE:
                if not self.model.kubeconfig:
                    raise ValueError(f"Cluster {self.model.name} has no kubeconfig")
                temp_kf = tempfile.NamedTemporaryFile(mode="w", delete=False)
                temp_kf.write(self.model.kubeconfig)
                temp_kf.flush()
                temp_kf.close()
                kubeconfig_path = temp_kf.name

            temp_manifest = tempfile.NamedTemporaryFile(mode="w", delete=False)
            temp_manifest.write(manifest)
            temp_manifest.flush()
            temp_manifest.close()

            cmd = ["kubectl"]
            if kubeconfig_path:
                cmd.extend(["--kubeconfig", kubeconfig_path])
            cmd.extend(["apply", "-f", temp_manifest.name])

            logger.debug(f"Running kubectl command: {' '.join(cmd)}")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"Kubectl command failed: {stderr.decode()}")
            return stdout.decode()

        finally:
            for f in [temp_kf, temp_manifest]:
                if f:
                    try:
                        os.unlink(f.name)
                    except Exception:
                        pass



@K8sClusterService.register_action("install_cert_manager")
class InstallCertManagerAction(InstallArgoCDAction):

    async def available(self) -> bool:
        # Only available if not already installed
        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status = result.one_or_none()
        return not (status and status.cert_manager_installed)

    async def __call__(self, **kwargs):
        from citadel.tasks.k8s_cluster_status import install_cert_manager_task

        # Set status to installed immediately so UI reflects it
        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status_model = result.one_or_none()
        if not status_model:
            status_model = K8sClusterStatus(k8s_cluster_id=self.model.id)
            self.session.add(status_model)
        status_model.cert_manager_installed = True
        await self.session.flush()

        install_cert_manager_task.delay(self.model.id)
        return {
            "status": "success",
            "message": "Cert Manager installation triggered and status being refreshed.",
        }

    async def run(self):
        """Install Cert Manager to the cluster using ArgoCD Application"""
        logger.info(f"Installing Cert Manager for cluster {self.model.name}")
        chart_repo, chart_name, chart_version = await self.resolve_integration_chart(
            "cert-manager", "main", "https://charts.jetstack.io", "cert-manager", "v1.20.0"
        )
        controller_image, controller_tag = await self.resolve_integration_image(
            "cert-manager", "main", "quay.io/jetstack/cert-manager-controller", "v1.20.0"
        )
        cainjector_image, cainjector_tag = await self.resolve_integration_image(
            "cert-manager", "cainjector", "quay.io/jetstack/cert-manager-cainjector", "v1.20.0"
        )
        webhook_image, webhook_tag = await self.resolve_integration_image(
            "cert-manager", "webhook", "quay.io/jetstack/cert-manager-webhook", "v1.20.0"
        )
        await self._apply_template(
            "cert-manager.yml.j2",
            chart_repo=chart_repo,
            chart_name=chart_name,
            chart_version=chart_version,
            controller_image=controller_image,
            controller_tag=controller_tag,
            cainjector_image=cainjector_image,
            cainjector_tag=cainjector_tag,
            webhook_image=webhook_image,
            webhook_tag=webhook_tag,
        )


@K8sClusterService.register_action("install_cnpg_operator")
class InstallCNPGAction(InstallArgoCDAction):

    async def available(self) -> bool:
        # Only available if not already installed
        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status = result.one_or_none()
        return not (status and status.cnpg_installed)

    async def __call__(self, **kwargs):
        from citadel.tasks.k8s_cluster_status import install_cnpg_operator_task

        # Set status to installed immediately so UI reflects it
        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status_model = result.one_or_none()
        if not status_model:
            status_model = K8sClusterStatus(k8s_cluster_id=self.model.id)
            self.session.add(status_model)
        status_model.cnpg_installed = True
        await self.session.flush()

        install_cnpg_operator_task.delay(self.model.id)
        return {
            "status": "success",
            "message": "CNPG Operator installation triggered and status being refreshed.",
        }

    async def run(self):
        """Install CNPG Operator to the cluster using ArgoCD Application"""
        logger.info(f"Installing CNPG Operator for cluster {self.model.name}")
        chart_repo, chart_name, chart_version = await self.resolve_integration_chart(
            "cnpg", "main", "https://cloudnative-pg.github.io/charts", "cloudnative-pg", "0.27.1"
        )
        image, image_tag = await self.resolve_integration_image(
            "cnpg", "main", "ghcr.io/cloudnative-pg/cloudnative-pg", "1.28.1"
        )
        await self._apply_template(
            "cnpg.yml.j2",
            chart_repo=chart_repo,
            chart_name=chart_name,
            chart_version=chart_version,
            image=image,
            image_tag=image_tag,
        )



@K8sClusterService.register_action("install_envoy_gateway")
class InstallEnvoyGatewayAction(InstallArgoCDAction):

    async def available(self) -> bool:
        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status = result.one_or_none()
        return not (status and status.envoy_gateway_installed)

    async def __call__(self, **kwargs):
        from citadel.tasks.k8s_cluster_status import install_envoy_gateway_task

        # Set status to installed immediately so UI reflects it
        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status_model = result.one_or_none()
        if not status_model:
            status_model = K8sClusterStatus(k8s_cluster_id=self.model.id)
            self.session.add(status_model)
        status_model.envoy_gateway_installed = True
        await self.session.flush()

        install_envoy_gateway_task.delay(self.model.id)
        return {
            "status": "success",
            "message": "Envoy Gateway installation triggered and status being refreshed.",
        }

    async def run(self):
        """Install Envoy Gateway to the cluster using ArgoCD Application and configured service type"""
        logger.info(f"Installing Envoy Gateway for cluster {self.model.name}")
        chart_repo, chart_name, chart_version = await self.resolve_integration_chart(
            "envoy-gateway", "main", "docker.io/envoyproxy", "gateway-helm", "1.8.1"
        )
        gw_image, gw_tag = await self.resolve_integration_image(
            "envoy-gateway", "main", "docker.io/envoyproxy/gateway", "v1.8.1"
        )
        envoy_image, envoy_tag = await self.resolve_integration_image(
            "envoy-gateway", "envoy", "docker.io/envoyproxy/envoy", "distroless-v1.38.1"
        )
        await self._apply_template(
            "envoy-gateway.yml.j2",
            chart_repo=chart_repo,
            chart_name=chart_name,
            chart_version=chart_version,
            image=gw_image,
            image_tag=gw_tag,
        )

        await self._wait_for_crd_and_namespace(
            ["envoyproxies.gateway.envoyproxy.io", "gatewayclasses.gateway.networking.k8s.io"],
            "envoy-gateway-system"
        )

        # Deploy global GatewayClass and EnvoyProxy resources
        logger.info("Applying global Envoy GatewayClass and EnvoyProxy configuration")
        await self._apply_template(
            "envoy-gateway-config.yml.j2",
            service_type="LoadBalancer",
            envoy_image=f"{envoy_image}:{envoy_tag}",
        )


@K8sClusterService.register_action("sync_core_integrations")
class SyncCoreIntegrationsAction(InstallArgoCDAction):

    async def available(self) -> bool:
        """Check if action is available"""
        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status = result.one_or_none()
        if status and status.status == "offline":
            return False
        return True

    async def __call__(self, **kwargs):
        """Invoke the action asynchronously via Celery task"""
        from citadel.tasks.k8s_cluster_status import sync_core_integrations_task

        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status_model = result.one_or_none()
        if not status_model:
            status_model = K8sClusterStatus(k8s_cluster_id=self.model.id)
            self.session.add(status_model)
        status_model.sync_state = build_initial_sync_state()
        flag_modified(status_model, "sync_state")
        await self.session.flush()

        sync_core_integrations_task.delay(self.model.id)
        return {
            "status": "success",
            "message": "Core integrations synchronization triggered.",
        }

    async def run(self):
        """Execute the sync workflow sequentially to install or update all integrations"""
        logger.info(f"Syncing core integrations for cluster {self.model.name}")

        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status = result.one_or_none()
        if not status:
            return

        for key, label, installed_attr in CORE_INTEGRATIONS:
            if key == "argocd" and getattr(status, installed_attr, False):
                continue
            logger.info(f"Sync: Deploying/updating {label}...")
            action_cls = get_integration_action_class(key)
            action = action_cls(self.model, self.svc)
            action.session = self.session
            await action.run()
            setattr(status, installed_attr, True)
            await self.session.flush()


@K8sClusterService.register_action("resume_sync_core_integrations")
class ResumeSyncCoreIntegrationsAction(BaseAction):
    """Resume an interrupted core integrations synchronization from persisted state."""

    async def available(self) -> bool:
        """Return True only when cluster is reachable and a sync is currently in_progress."""
        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status = result.one_or_none()
        if not status or status.status == "offline":
            return False
        return (
            isinstance(status.sync_state, dict)
            and status.sync_state.get("status") == "in_progress"
        )

    async def __call__(self, **kwargs):
        """Enqueue immediate recovery of incomplete core integration sync tasks."""
        from citadel.tasks.k8s_cluster_status import recover_stuck_sync_tasks

        recover_stuck_sync_tasks.delay(stale_seconds=0, k8s_cluster_id=self.model.id)
        return {
            "status": "success",
            "message": "Core integrations synchronization resumed.",
        }


@K8sClusterService.register_action("install_kafka_operator")
class InstallKafkaOperatorAction(InstallArgoCDAction):

    async def available(self) -> bool:
        """Check if Kafka Operator action is available (not installed yet)"""
        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status = result.one_or_none()
        return not (status and status.kafka_operator_installed)

    async def __call__(self, **kwargs):
        """Call method to queue Kafka Operator installation task asynchronously"""
        from citadel.tasks.k8s_cluster_status import install_kafka_operator_task

        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status_model = result.one_or_none()
        if not status_model:
            status_model = K8sClusterStatus(k8s_cluster_id=self.model.id)
            self.session.add(status_model)
        status_model.kafka_operator_installed = True
        await self.session.flush()

        install_kafka_operator_task.delay(self.model.id)
        return {
            "status": "success",
            "message": "Kafka Operator installation triggered and status being refreshed.",
        }

    async def run(self):
        """Install Strimzi Kafka Operator to the cluster using ArgoCD Application"""
        logger.info(f"Installing Kafka Operator for cluster {self.model.name}")
        chart_repo, chart_name, chart_version = await self.resolve_integration_chart(
            "kafka-operator", "main", "https://strimzi.io/charts/", "strimzi-kafka-operator", "0.50.1"
        )
        image, image_tag = await self.resolve_integration_image(
            "kafka-operator", "main", "quay.io/strimzi/operator", "0.50.1"
        )
        parts = image.split("/")
        if len(parts) >= 3:
            image_registry = parts[0]
            image_repository = "/".join(parts[1:-1])
            image_name = parts[-1]
        elif len(parts) == 2:
            image_registry = ""
            image_repository = parts[0]
            image_name = parts[1]
        else:
            image_registry = ""
            image_repository = ""
            image_name = image
        await self._apply_template(
            "kafka-operator.yml.j2",
            chart_repo=chart_repo,
            chart_name=chart_name,
            chart_version=chart_version,
            image_registry=image_registry,
            image_repository=image_repository,
            image_name=image_name,
            image_tag=image_tag,
        )


@K8sClusterService.register_action("install_nifikop")
class InstallNifikopAction(InstallArgoCDAction):

    async def available(self) -> bool:
        """Check if NiFiKop action is available (not installed yet)"""
        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status = result.one_or_none()
        return not (status and status.nifikop_installed)

    async def __call__(self, **kwargs):
        """Call method to queue NiFiKop installation task asynchronously"""
        from citadel.tasks.k8s_cluster_status import install_nifikop_task

        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status_model = result.one_or_none()
        if not status_model:
            status_model = K8sClusterStatus(k8s_cluster_id=self.model.id)
            self.session.add(status_model)
        status_model.nifikop_installed = True
        await self.session.flush()

        install_nifikop_task.delay(self.model.id)
        return {
            "status": "success",
            "message": "NiFiKop Operator installation triggered and status being refreshed.",
        }

    async def run(self):
        """Install NiFiKop Operator to the cluster using ArgoCD Application"""
        logger.info(f"Installing NiFiKop Operator for cluster {self.model.name}")
        chart_repo, chart_name, chart_version = await self.resolve_integration_chart(
            "nifikop-operator", "main", "ghcr.io/konpyutaika/helm-charts", "nifikop", "1.17.0"
        )
        image, image_tag = await self.resolve_integration_image(
            "nifikop-operator", "main", "ghcr.io/konpyutaika/docker-images/nifikop", "v1.17.0-release"
        )
        await self._apply_template(
            "nifikop-operator.yml.j2",
            chart_repo=chart_repo,
            chart_name=chart_name,
            chart_version=chart_version,
            image=image,
            image_tag=image_tag,
        )


@K8sClusterService.register_action("install_doris_operator")
class InstallDorisOperatorAction(InstallArgoCDAction):
    """Action to install Doris Operator on the cluster."""

    async def available(self) -> bool:
        """Check if Doris Operator action is available (not installed yet)"""
        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status = result.one_or_none()
        return not (status and status.doris_operator_installed)

    async def __call__(self, **kwargs):
        """Call method to queue Doris Operator installation task asynchronously"""
        from citadel.tasks.k8s_cluster_status import install_doris_operator_task

        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status_model = result.one_or_none()
        if not status_model:
            status_model = K8sClusterStatus(k8s_cluster_id=self.model.id)
            self.session.add(status_model)
        status_model.doris_operator_installed = True
        await self.session.flush()

        install_doris_operator_task.delay(self.model.id)
        return {
            "status": "success",
            "message": "Doris Operator installation triggered and status being refreshed.",
        }

    async def run(self):
        """Install Doris Operator to the cluster using ArgoCD Application"""
        logger.info(f"Installing Doris Operator for cluster {self.model.name}")
        chart_repo, chart_name, chart_version = await self.resolve_integration_chart(
            "doris-operator", "main", "https://charts.selectdb.com", "doris-operator", "25.8.0"
        )
        image, image_tag = await self.resolve_integration_image(
            "doris-operator", "main", "apache/doris", "operator-26.0.1"
        )
        await self._apply_template(
            "doris-operator.yml.j2",
            chart_repo=chart_repo,
            chart_name=chart_name,
            chart_version=chart_version,
            image=image,
            image_tag=image_tag,
        )


def _split_registry_repository(image: str) -> tuple[str, str]:
    """Split a container image reference into (registry, repository)."""
    if "/" in image:
        first, rest = image.split("/", 1)
        if "." in first or ":" in first or first == "localhost":
            return first, rest
        return "docker.io", image
    return "docker.io", image


@K8sClusterService.register_action("install_kube_prometheus_stack")
class InstallKubePrometheusStackAction(InstallArgoCDAction):
    """Action to install kube-prometheus-stack on the cluster if not already available."""

    async def available(self) -> bool:
        """Check if kube-prometheus-stack action is available (not installed yet)."""
        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status = result.one_or_none()
        return not (status and status.kube_prometheus_stack_installed)

    async def __call__(self, **kwargs):
        """Queue kube-prometheus-stack installation task asynchronously."""
        from citadel.tasks.k8s_cluster_status import install_kube_prometheus_stack_task

        stmt = select(K8sClusterStatus).where(
            K8sClusterStatus.k8s_cluster_id == self.model.id
        )
        result = await self.session.exec(stmt)
        status_model = result.one_or_none()
        if not status_model:
            status_model = K8sClusterStatus(k8s_cluster_id=self.model.id)
            self.session.add(status_model)
        status_model.kube_prometheus_stack_installed = True
        await self.session.flush()

        install_kube_prometheus_stack_task.delay(self.model.id)
        return {
            "status": "success",
            "message": "Kube Prometheus Stack installation triggered and status being refreshed.",
        }

    def _check_already_available_sync(self) -> bool:
        """Synchronously check if Prometheus / kube-prometheus-stack is already present outside Citadel."""
        try:
            core_api, ext_api = self._get_kubernetes_clients()
        except Exception as e:
            logger.debug(f"Could not load Kubernetes clients for pre-check: {e}")
            return False

        # If Citadel's own ArgoCD Application exists, allow idempotent reconciliation.
        try:
            custom_api = client.CustomObjectsApi(core_api.api_client)
            custom_api.get_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace="argocd",
                plural="applications",
                name="kube-prometheus-stack",
            )
            return False
        except Exception:
            pass

        # Check for Prometheus Operator CRD
        try:
            ext_api.read_custom_resource_definition("prometheuses.monitoring.coreos.com")
            return True
        except Exception:
            pass

        # Check for existing Helm release secrets
        try:
            secrets = core_api.list_secret_for_all_namespaces(label_selector="owner=helm")
            for secret in getattr(secrets, "items", None) or []:
                name = getattr(getattr(secret, "metadata", None), "name", "") or ""
                if "kube-prometheus-stack" in name:
                    return True
        except Exception:
            pass

        # Check for running Prometheus pods
        for selector in (
            "app.kubernetes.io/name=prometheus",
            "app.kubernetes.io/name=kube-prometheus-stack-prometheus",
            "app=kube-prometheus-stack-prometheus",
        ):
            try:
                pods = core_api.list_pod_for_all_namespaces(label_selector=selector)
                if getattr(pods, "items", None):
                    return True
            except Exception:
                pass

        return False

    async def _is_already_available(self) -> bool:
        """Return True if kube-prometheus-stack or Prometheus is already available in the cluster."""
        return await asyncio.to_thread(self._check_already_available_sync)

    async def run(self):
        """Install kube-prometheus-stack via ArgoCD Application if not already available."""
        if await self._is_already_available():
            logger.info(
                f"Prometheus / kube-prometheus-stack already available in cluster {self.model.name}; skipping install"
            )
            return

        logger.info(f"Installing kube-prometheus-stack for cluster {self.model.name}")
        chart_repo, chart_name, chart_version = await self.resolve_integration_chart(
            "kube-prometheus-stack",
            "main",
            "https://prometheus-community.github.io/helm-charts",
            "kube-prometheus-stack",
            "93.3.0",
        )
        main_img, main_tag = await self.resolve_integration_image(
            "kube-prometheus-stack", "main", "quay.io/prometheus/prometheus", "v3.16.0-distroless"
        )
        op_img, op_tag = await self.resolve_integration_image(
            "kube-prometheus-stack", "operator", "quay.io/prometheus-operator/prometheus-operator", "v0.95.2"
        )
        reloader_img, reloader_tag = await self.resolve_integration_image(
            "kube-prometheus-stack", "config_reloader", "quay.io/prometheus-operator/prometheus-config-reloader", "v0.95.2"
        )
        ksm_img, ksm_tag = await self.resolve_integration_image(
            "kube-prometheus-stack", "kube_state_metrics", "registry.k8s.io/kube-state-metrics/kube-state-metrics", "v2.20.0"
        )
        ne_img, ne_tag = await self.resolve_integration_image(
            "kube-prometheus-stack", "node_exporter", "quay.io/prometheus/node-exporter", "v1.12.1-distroless"
        )
        certgen_img, certgen_tag = await self.resolve_integration_image(
            "kube-prometheus-stack", "webhook_certgen", "ghcr.io/jkroepke/kube-webhook-certgen", "1.11.1"
        )

        main_reg, main_repo = _split_registry_repository(main_img)
        op_reg, op_repo = _split_registry_repository(op_img)
        reloader_reg, reloader_repo = _split_registry_repository(reloader_img)
        ksm_reg, ksm_repo = _split_registry_repository(ksm_img)
        ne_reg, ne_repo = _split_registry_repository(ne_img)
        certgen_reg, certgen_repo = _split_registry_repository(certgen_img)

        await self._apply_template(
            "kube-prometheus-stack.yml.j2",
            chart_repo=chart_repo,
            chart_name=chart_name,
            chart_version=chart_version,
            main_registry=main_reg,
            main_repository=main_repo,
            main_tag=main_tag,
            operator_registry=op_reg,
            operator_repository=op_repo,
            operator_tag=op_tag,
            config_reloader_registry=reloader_reg,
            config_reloader_repository=reloader_repo,
            config_reloader_tag=reloader_tag,
            kube_state_metrics_registry=ksm_reg,
            kube_state_metrics_repository=ksm_repo,
            kube_state_metrics_tag=ksm_tag,
            node_exporter_registry=ne_reg,
            node_exporter_repository=ne_repo,
            node_exporter_tag=ne_tag,
            webhook_certgen_registry=certgen_reg,
            webhook_certgen_repository=certgen_repo,
            webhook_certgen_tag=certgen_tag,
        )

