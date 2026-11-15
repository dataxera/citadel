# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import asyncio
import functools
import jinja2 as j2
import logging
import os
import tempfile
import yaml
from typing import Any, Optional
from sqlmodel import select


from mindweaver.fw.action import BaseAction
from mindweaver.service.project.service import ProjectService
from mindweaver.service.k8s_cluster import K8sCluster, K8sClusterType
from mindweaver.service.project_user.model import ProjectLocalUser
from mindweaver.service.ldap_config.service import LdapConfigService
from mindweaver.crypto import decrypt_password
from mindweaver.fw.util import sanitize_label_value

logger = logging.getLogger(__name__)


async def _get_existing_nodeport(cluster, namespace: str) -> Optional[int]:
    """Retrieve existing Envoy HTTPS nodePort if it has been dynamically allocated."""
    from kubernetes import client, config
    def _get():
        try:
            if cluster.type == K8sClusterType.IN_CLUSTER:
                config.load_incluster_config()
            else:
                if not cluster.kubeconfig:
                    return None
                with tempfile.NamedTemporaryFile(mode="w", delete=False) as kf:
                    kf.write(cluster.kubeconfig)
                    kf.flush()
                    config.load_kube_config(config_file=kf.name)
            core_v1 = client.CoreV1Api()
            # Try project namespace first
            try:
                svcs = core_v1.list_namespaced_service(namespace=namespace)
                for svc in svcs.items:
                    if "envoy" in svc.metadata.name or "project-gateway" in svc.metadata.name:
                        for p in svc.spec.ports:
                            if p.port == 443 and getattr(p, "node_port", None):
                                return p.node_port
            except Exception:
                pass

            # Try envoy-gateway-system namespace next
            expected_prefix = f"envoy-{namespace}-project-gateway"
            try:
                eg_svcs = core_v1.list_namespaced_service(namespace="envoy-gateway-system")
                for svc in eg_svcs.items:
                    if svc.metadata.name.startswith(expected_prefix):
                        for p in svc.spec.ports:
                            if p.port == 443 and getattr(p, "node_port", None):
                                return p.node_port
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Error checking existing nodeport: {e}")
        return None
    return await asyncio.to_thread(_get)


@functools.lru_cache(maxsize=32)
def _get_jinja_env() -> j2.Environment:
    template_directory = os.path.join(os.path.dirname(__file__), "templates")
    env = j2.Environment(loader=j2.FileSystemLoader(template_directory))
    return env


def _render_gateway_manifests(model, namespace: str, service_type: str = "LoadBalancer", nodeport: Optional[int] = None) -> str:
    """Render Gateway and Certificate manifests from YAML templates."""
    # Handle older test calls passing nodeport as the 3rd positional argument
    if isinstance(service_type, int):
        nodeport = service_type
        service_type = "NodePort"

    vars = {
        "name": model.name,
        "namespace": namespace,
        "ingress_domain": model.ingress_domain,
        "service_type": service_type,
        "nodeport": nodeport,
    }

    env = _get_jinja_env()
    templates = sorted(env.list_templates())
    rendered = []
    for template_name in templates:
        if not template_name.endswith((".yaml", ".yml", ".yml.j2", ".yaml.j2")) or "dex-app" in template_name or "03-trusted-certs" in template_name:
            continue
        template = env.get_template(template_name)
        rendered.append(template.render(**vars))

    return "\n---\n".join(r for r in rendered if r.strip())



async def apply_manifest_to_cluster(cluster: K8sCluster, manifest: str) -> None:
    """Apply a Kubernetes manifest to a cluster using kubectl."""
    if not manifest.strip():
        return
    kubeconfig_path = None
    temp_kf = None
    temp_m = None
    try:
        if cluster.type == K8sClusterType.REMOTE:
            if not cluster.kubeconfig:
                raise ValueError(f"Cluster {cluster.name} has no kubeconfig")
            temp_kf = tempfile.NamedTemporaryFile(mode="w", delete=False)
            temp_kf.write(cluster.kubeconfig)
            temp_kf.flush()
            temp_kf.close()
            kubeconfig_path = temp_kf.name

        temp_m = tempfile.NamedTemporaryFile(mode="w", delete=False)
        temp_m.write(manifest)
        temp_m.flush()
        temp_m.close()

        cmd = ["kubectl"]
        if kubeconfig_path:
            cmd.extend(["--kubeconfig", kubeconfig_path])
        cmd.extend(["apply", "--server-side", "--force-conflicts", "-f", temp_m.name])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Kubectl command failed: {stderr.decode()}")
    finally:
        if temp_m:
            try:
                os.unlink(temp_m.name)
            except Exception:
                pass
        if temp_kf:
            try:
                os.unlink(temp_kf.name)
            except Exception:
                pass





@ProjectService.register_action("sync_project_integrations")
class SyncProjectIntegrationsAction(BaseAction):
    """
    Action to sync project integrations: create ArgoCD project, deploy self-signed issuer, and deploy gateway.
    """

    async def available(self) -> bool:
        return self.model.k8s_cluster_id is not None and bool(self.model.ingress_domain)

    async def __call__(self, **kwargs):
        from mindweaver.tasks.project_tasks import sync_project_integrations_task

        sync_project_integrations_task.delay(self.model.id)
        return {
            "status": "success",
            "message": "Project integrations synchronization triggered.",
        }

    async def run(self):
        logger.info(f"Syncing integrations for project {self.model.name}")

        stmt_cluster = select(K8sCluster).where(K8sCluster.id == self.model.k8s_cluster_id)
        res_cluster = await self.session.exec(stmt_cluster)
        cluster = res_cluster.one()

        namespace = self.model.k8s_namespace or self.model.name

        # 1. Check/Persist nodeport
        if not self.model.envoy_nodeport:
            existing_port = await _get_existing_nodeport(cluster, namespace)
            if existing_port:
                self.model.envoy_nodeport = existing_port
                self.session.add(self.model)
                await self.session.commit()
                await self.session.refresh(self.model)

        # 2. Render templates
        env = _get_jinja_env()
        
        # 2a. ArgoCD Project
        argocd_project_template = env.get_template("00-argocd-project.yml.j2")
        argocd_project_manifest = argocd_project_template.render(
            name=self.model.name,
            namespace=namespace,
        )

        # 2b. Issuer
        issuer_template = env.get_template("02-self-signed-issuer.yml.j2")
        issuer_manifest = issuer_template.render(
            name=self.model.name,
            namespace=namespace,
        )

        # 2c. Gateway
        gateway_manifest = ""
        if self.model.ingress_domain:
            gateway_manifest = _render_gateway_manifests(
                self.model, namespace, self.model.envoy_gateway_service_type, self.model.envoy_nodeport
            )

        # 2d. Trusted Certificates Secret
        from mindweaver.service.trusted_certs.model import TrustedCert
        import base64
        stmt_certs = select(TrustedCert).where(TrustedCert.project_id == self.model.id)
        res_certs = await self.session.exec(stmt_certs)
        certs = res_certs.all()
        trusted_certs = [
            {
                "name": c.name,
                "certificate": c.certificate,
                "certificate_b64": base64.b64encode(c.certificate.encode("utf-8")).decode("utf-8")
            }
            for c in certs
        ]

        trusted_certs_template = env.get_template("03-trusted-certs.yml.j2")
        trusted_certs_manifest = trusted_certs_template.render(
            name=self.model.name,
            namespace=namespace,
            trusted_certs=trusted_certs,
        )

        # 3. Apply manifests
        await apply_manifest_to_cluster(cluster, argocd_project_manifest)
        await apply_manifest_to_cluster(cluster, issuer_manifest)
        if trusted_certs_manifest:
            await apply_manifest_to_cluster(cluster, trusted_certs_manifest)
        if gateway_manifest:
            await apply_manifest_to_cluster(cluster, gateway_manifest)


