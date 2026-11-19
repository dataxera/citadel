# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import asyncio
import base64
import contextvars
import functools
import jinja2 as j2
import logging
import os
import tempfile
import traceback
import yaml
from typing import Any, Awaitable, Callable
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select


from citadel.fw.action import BaseAction
from citadel.fw.model import ts_now
from citadel.service.project.service import ProjectService
from citadel.service.k8s_cluster import K8sCluster, K8sClusterType
from citadel.service.project_user.model import ProjectLocalUser
from citadel.service.ldap_config.service import LdapConfigService
from citadel.service.trusted_certs.model import TrustedCert
from citadel.crypto import decrypt_password
from citadel.fw.util import sanitize_label_value

logger = logging.getLogger(__name__)
_apply_log_callback: contextvars.ContextVar[Callable[[str], Awaitable[None]] | None] = (
    contextvars.ContextVar("_apply_log_callback", default=None)
)

PROJECT_INTEGRATIONS = [
    ("namespace", "Namespace"),
    ("argocd_project", "ArgoCD Project"),
    ("self_signed_issuer", "Self-Signed Issuer"),
    ("trusted_certs", "Trusted Certs"),
    ("envoy_gateway", "Envoy Gateway"),
    ("wildcard_certificate", "Wildcard Certificate"),
]


def build_initial_project_sync_state() -> dict[str, Any]:
    """Build the initial persistent sync_state payload for project integrations sync."""
    now_iso = ts_now().isoformat()
    return {
        "status": "in_progress",
        "started_at": now_iso,
        "updated_at": now_iso,
        "completed_at": None,
        "total": len(PROJECT_INTEGRATIONS),
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
            for key, label in PROJECT_INTEGRATIONS
        },
    }


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



async def apply_manifest_to_cluster(
    cluster: K8sCluster,
    manifest: str,
    log_callback: Callable[[str], Awaitable[None]] | None = None,
) -> None:
    """Apply a Kubernetes manifest to a cluster using kubectl."""
    if not manifest.strip():
        return
    if log_callback is None:
        log_callback = _apply_log_callback.get()
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

        if log_callback is not None:
            await log_callback("$ kubectl apply --server-side --force-conflicts -f <manifest>\n")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.communicate()
            raise RuntimeError("Kubectl command timed out after 60s") from exc
        stdout_text = stdout.decode(errors="replace") if stdout else ""
        stderr_text = stderr.decode(errors="replace") if stderr else ""
        if log_callback is not None:
            combined = "".join(t for t in (stdout_text, stderr_text) if t)
            if combined:
                await log_callback(combined if combined.endswith("\n") else f"{combined}\n")

        if proc.returncode != 0:
            raise RuntimeError(f"Kubectl command failed: {stderr_text}")
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


async def _update_project_sync_task_state(
    session,
    project,
    task_key: str,
    status: str,
    *,
    message: str | None = None,
    logs: str | None = None,
    mark_remaining_failed_on_error: bool = False,
) -> None:
    """Persist task-level progress into project.sync_state and commit."""
    now_iso = ts_now().isoformat()
    sync_state = dict(project.sync_state or build_initial_project_sync_state())
    tasks = dict(sync_state.get("tasks") or {})
    task_entry = dict(tasks.get(task_key) or {"label": task_key, "attempts": 0})

    if status == "running":
        task_entry["attempts"] = int(task_entry.get("attempts", 0)) + 1
    task_entry["status"] = status
    task_entry["updated_at"] = now_iso
    if message is not None:
        task_entry["message"] = message
    if logs is not None:
        task_entry["logs"] = logs
    tasks[task_key] = task_entry

    if mark_remaining_failed_on_error:
        for other_key, other_task in tasks.items():
            if other_key != task_key and other_task.get("status") == "pending":
                updated_other = dict(other_task)
                updated_other["status"] = "failed"
                updated_other["message"] = "Skipped due to earlier error"
                updated_other["updated_at"] = now_iso
                tasks[other_key] = updated_other

    completed_count = sum(1 for t in tasks.values() if t.get("status") == "completed")
    has_failed = any(t.get("status") == "failed" for t in tasks.values())
    all_done = all(t.get("status") in ("completed", "failed") for t in tasks.values())

    sync_state["tasks"] = tasks
    sync_state["completed"] = completed_count
    sync_state["total"] = len(PROJECT_INTEGRATIONS)
    sync_state["updated_at"] = now_iso

    if has_failed and mark_remaining_failed_on_error:
        sync_state["status"] = "error"
        sync_state["completed_at"] = now_iso
    elif all_done:
        sync_state["status"] = "error" if has_failed else "completed"
        sync_state["completed_at"] = now_iso
    else:
        sync_state["status"] = "in_progress"

    project.sync_state = sync_state
    flag_modified(project, "sync_state")
    await session.commit()





@ProjectService.register_action("sync_project_integrations")
class SyncProjectIntegrationsAction(BaseAction):
    """
    Action to sync project integrations: namespace, ArgoCD project, self-signed issuer,
    trusted certs, Envoy gateway, and wildcard certificate.
    """

    log_callback: Callable[[str], Awaitable[None]] | None = None

    async def available(self) -> bool:
        return self.model.k8s_cluster_id is not None

    async def __call__(self, **kwargs):
        from citadel.tasks.project_tasks import sync_project_integrations_task

        self.model.sync_state = build_initial_project_sync_state()
        flag_modified(self.model, "sync_state")
        await self.session.flush()

        sync_project_integrations_task.delay(self.model.id)
        return {
            "status": "success",
            "message": "Project integrations synchronization triggered.",
        }

    async def _render_integration_manifest(self, integration_key: str) -> tuple[str, str | None]:
        """Render the Kubernetes manifest(s) for a single project integration key."""
        namespace = self.model.k8s_namespace or self.model.name
        env = _get_jinja_env()

        if integration_key == "namespace":
            return f"apiVersion: v1\nkind: Namespace\nmetadata:\n  name: {namespace}\n", None

        if integration_key == "argocd_project":
            return (
                env.get_template("00-argocd-project.yml.j2").render(
                    name=self.model.name,
                    namespace=namespace,
                ),
                None,
            )

        if integration_key == "self_signed_issuer":
            return (
                env.get_template("02-self-signed-issuer.yml.j2").render(
                    name=self.model.name,
                    namespace=namespace,
                ),
                None,
            )

        if integration_key == "trusted_certs":
            stmt_certs = select(TrustedCert).where(TrustedCert.project_id == self.model.id)
            res_certs = await self.session.exec(stmt_certs)
            certs = res_certs.all()
            trusted_certs = [
                {
                    "name": c.name,
                    "certificate": c.certificate,
                    "certificate_b64": base64.b64encode(c.certificate.encode("utf-8")).decode("utf-8"),
                }
                for c in certs
            ]
            return (
                env.get_template("03-trusted-certs.yml.j2").render(
                    name=self.model.name,
                    namespace=namespace,
                    trusted_certs=trusted_certs,
                ),
                None,
            )

        if integration_key == "envoy_gateway":
            if not self.model.ingress_domain:
                return "", "Ingress domain not configured (skipped)"
            envoy_proxy_manifest = env.get_template("01-envoy-proxy.yml.j2").render(
                name=self.model.name,
                namespace=namespace,
                ingress_domain=self.model.ingress_domain,
            )
            gateway_manifest = env.get_template("10-gateway.yml.j2").render(
                name=self.model.name,
                namespace=namespace,
                ingress_domain=self.model.ingress_domain,
            )
            return f"{envoy_proxy_manifest}\n---\n{gateway_manifest}", None

        if integration_key == "wildcard_certificate":
            if not self.model.ingress_domain:
                return "", "Ingress domain not configured (skipped)"
            return (
                env.get_template("30-wildcard-certificate.yml.j2").render(
                    name=self.model.name,
                    namespace=namespace,
                    ingress_domain=self.model.ingress_domain,
                ),
                None,
            )

        raise ValueError(f"Unknown project integration key: {integration_key}")

    async def run_integration(self, integration_key: str) -> str | None:
        """Execute sync for a single project integration, streaming logs to self.log_callback."""
        stmt_cluster = select(K8sCluster).where(K8sCluster.id == self.model.k8s_cluster_id)
        res_cluster = await self.session.exec(stmt_cluster)
        cluster = res_cluster.one()

        manifest, skip_message = await self._render_integration_manifest(integration_key)
        if skip_message is not None:
            if self.log_callback is not None:
                await self.log_callback(f"{skip_message}\n")
            return skip_message

        if self.log_callback is not None:
            token = _apply_log_callback.set(self.log_callback)
            try:
                await apply_manifest_to_cluster(cluster, manifest)
            finally:
                _apply_log_callback.reset(token)
        else:
            await apply_manifest_to_cluster(cluster, manifest)
        return None

    async def _run_sync_step(
        self,
        cluster: K8sCluster,
        task_key: str,
        manifest: str,
        *,
        skip_message: str | None = None,
    ) -> None:
        """Execute a single project integration sync step and persist its progress/logs."""
        log_chunks: list[str] = []

        async def _collect_log(chunk: str) -> None:
            log_chunks.append(chunk)

        await _update_project_sync_task_state(
            self.session,
            self.model,
            task_key,
            "running",
            logs="",
        )
        if skip_message is not None:
            await _update_project_sync_task_state(
                self.session,
                self.model,
                task_key,
                "completed",
                message=skip_message,
                logs=f"{skip_message}\n",
            )
            return

        token = _apply_log_callback.set(_collect_log)
        try:
            await apply_manifest_to_cluster(cluster, manifest)
            await _update_project_sync_task_state(
                self.session,
                self.model,
                task_key,
                "completed",
                logs="".join(log_chunks),
            )
        except Exception as exc:
            err_logs = "".join(log_chunks) + "\n" + traceback.format_exc()
            await _update_project_sync_task_state(
                self.session,
                self.model,
                task_key,
                "failed",
                message=str(exc) or type(exc).__name__,
                logs=err_logs.lstrip(),
                mark_remaining_failed_on_error=True,
            )
            raise
        finally:
            _apply_log_callback.reset(token)

    async def run(self):
        """Execute all project integration sync steps sequentially with persistent progress."""
        logger.info(f"Syncing integrations for project {self.model.name}")

        if not isinstance(self.model.sync_state, dict) or self.model.sync_state.get("status") != "in_progress":
            self.model.sync_state = build_initial_project_sync_state()
            flag_modified(self.model, "sync_state")
            await self.session.commit()

        stmt_cluster = select(K8sCluster).where(K8sCluster.id == self.model.k8s_cluster_id)
        res_cluster = await self.session.exec(stmt_cluster)
        cluster = res_cluster.one()

        for key, _ in PROJECT_INTEGRATIONS:
            manifest, skip_message = await self._render_integration_manifest(key)
            await self._run_sync_step(cluster, key, manifest, skip_message=skip_message)


@ProjectService.register_action("resume_sync_project_integrations")
class ResumeSyncProjectIntegrationsAction(BaseAction):
    """Resume an interrupted or stale project integrations synchronization."""

    async def available(self) -> bool:
        """Return True when a project integrations sync is currently marked in_progress."""
        return (
            self.model.k8s_cluster_id is not None
            and isinstance(self.model.sync_state, dict)
            and self.model.sync_state.get("status") == "in_progress"
        )

    async def __call__(self, **kwargs):
        """Enqueue immediate recovery of incomplete project integration sync tasks."""
        from citadel.tasks.project_tasks import recover_stuck_project_sync_tasks

        recover_stuck_project_sync_tasks.delay(stale_seconds=0, project_id=self.model.id)
        return {
            "status": "success",
            "message": "Project integrations synchronization resumed.",
        }


