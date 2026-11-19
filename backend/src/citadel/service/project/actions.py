# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import asyncio
import functools
import jinja2 as j2
import logging
import os
import tempfile
import yaml
from typing import Any
from sqlmodel import select


from citadel.fw.action import BaseAction
from citadel.service.project.service import ProjectService
from citadel.service.k8s_cluster import K8sCluster, K8sClusterType
from citadel.service.project_user.model import ProjectLocalUser
from citadel.service.ldap_config.service import LdapConfigService
from citadel.crypto import decrypt_password
from citadel.fw.util import sanitize_label_value

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=32)
def _get_jinja_env() -> j2.Environment:
    template_directory = os.path.join(os.path.dirname(__file__), "templates")
    env = j2.Environment(loader=j2.FileSystemLoader(template_directory))
    return env


def _render_gateway_manifests(model, namespace: str) -> str:
    """Render Gateway and Certificate manifests from YAML templates."""
    vars = {
        "name": model.name,
        "namespace": namespace,
        "ingress_domain": model.ingress_domain,
    }

    env = _get_jinja_env()
    templates = sorted(env.list_templates())
    rendered = []
    for template_name in templates:
        if not template_name.endswith((".yaml", ".yml", ".yml.j2", ".yaml.j2")) or "03-trusted-certs" in template_name:
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
        from citadel.tasks.project_tasks import sync_project_integrations_task

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

        # 1. Render templates
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
                self.model, namespace
            )

        # 2d. Trusted Certificates Secret
        from citadel.service.trusted_certs.model import TrustedCert
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


