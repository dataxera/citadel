# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import asyncio
import base64
import copy
from datetime import datetime, timezone
import time
import traceback
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from citadel.celery_app import app
from citadel.config import logger
from citadel.fw.model import get_engine, ts_now
from citadel.service.k8s_cluster.model import K8sCluster  # noqa: F401
from citadel.service.ldap_config.model import LdapConfig  # noqa: F401
from citadel.service.project.model import Project
from citadel.service.project.service import ProjectService
from citadel.service.stack.model import Stack  # noqa: F401
from .base import run_async
from .resiliency import (
    acquire_task_lock,
    is_task_locked,
    release_task_lock,
    run_with_lock_heartbeat,
)

MAX_SYNC_LOG_CHARS = 100_000


def _project_sync_lock_key(project_id: int, key: str) -> str:
    """Return the distributed Redis lock key for a project integration sync task."""
    return f"project_sync:{project_id}:{key}"


def _trim_sync_logs(text: str, max_chars: int = MAX_SYNC_LOG_CHARS) -> str:
    """Trim sync logs from the front if they exceed max_chars."""
    if len(text) <= max_chars:
        return text
    marker = "...[earlier logs truncated]...\n"
    keep = max_chars - len(marker)
    return marker + text[-keep:]


def _is_timestamp_stale(updated_at_iso: str | None, stale_seconds: int) -> bool:
    """Return True if an ISO timestamp is missing or older than stale_seconds."""
    if stale_seconds <= 0:
        return True
    if not updated_at_iso:
        return True
    try:
        dt = datetime.fromisoformat(updated_at_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (ts_now() - dt).total_seconds()
        return age >= stale_seconds
    except Exception:
        return True


def _reconcile_project_sync_state_totals(sync_state: dict) -> bool:
    """Recompute completed count and top-level status from task entries. Returns True if all finished."""
    tasks = sync_state.get("tasks", {})
    done_statuses = {"completed", "failed"}
    completed_count = sum(1 for t in tasks.values() if t.get("status") in done_statuses)
    total = sync_state.get("total", len(tasks))
    sync_state["completed"] = completed_count
    sync_state["updated_at"] = ts_now().isoformat()

    all_done = total > 0 and completed_count >= total
    if all_done:
        has_failure = any(t.get("status") == "failed" for t in tasks.values())
        sync_state["status"] = "error" if has_failure else "completed"
        if not sync_state.get("completed_at"):
            sync_state["completed_at"] = ts_now().isoformat()
    else:
        sync_state["status"] = "in_progress"
    return all_done


async def _append_project_sync_task_logs(
    session: AsyncSession,
    project_id: int,
    key: str,
    chunk: str,
    max_log_chars: int = MAX_SYNC_LOG_CHARS,
) -> None:
    """Append streamed log output to a single project integration's sync_state entry under a row lock."""
    if not chunk:
        return
    from citadel.service.project.actions import build_initial_project_sync_state

    stmt = select(Project).where(Project.id == project_id).with_for_update()
    res = await session.exec(stmt)
    project = res.one_or_none()
    if not project:
        return

    now_iso = ts_now().isoformat()
    sync_state = copy.deepcopy(project.sync_state or build_initial_project_sync_state())
    tasks = sync_state.setdefault("tasks", {})
    if key in tasks:
        existing = tasks[key].get("logs") or ""
        tasks[key]["logs"] = _trim_sync_logs(existing + chunk, max_log_chars)
        tasks[key]["updated_at"] = now_iso
    sync_state["updated_at"] = now_iso

    project.sync_state = sync_state
    flag_modified(project, "sync_state")
    await session.commit()


class _ProjectSyncTaskLogStreamer:
    """Buffered async log writer that flushes task output chunks to Project.sync_state periodically."""

    def __init__(
        self,
        session: AsyncSession,
        project_id: int,
        key: str,
        flush_interval: float = 0.25,
    ) -> None:
        self._session = session
        self._project_id = project_id
        self._key = key
        self._flush_interval = flush_interval
        self._buffer: list[str] = []
        self._last_flush = 0.0
        self._lock = asyncio.Lock()
        self._trailing_task: asyncio.Task | None = None

    async def write(self, text: str) -> None:
        """Buffer a log line/chunk and flush to DB immediately on interval or via a trailing timer."""
        if not text:
            return
        async with self._lock:
            self._buffer.append(text)
            if time.monotonic() - self._last_flush >= self._flush_interval:
                await self._flush_locked()
            elif self._trailing_task is None or self._trailing_task.done():
                self._trailing_task = asyncio.create_task(self._delayed_flush())

    async def _delayed_flush(self) -> None:
        """Flush buffered lines after flush_interval if no subsequent write triggered a flush."""
        try:
            await asyncio.sleep(self._flush_interval)
            async with self._lock:
                await self._flush_locked()
        except asyncio.CancelledError:
            pass

    async def flush(self) -> None:
        """Cancel any pending trailing flush and flush all remaining buffered log output to DB."""
        if self._trailing_task and not self._trailing_task.done():
            self._trailing_task.cancel()
            try:
                await self._trailing_task
            except asyncio.CancelledError:
                pass
        self._trailing_task = None
        async with self._lock:
            await self._flush_locked()

    async def _flush_locked(self) -> None:
        if not self._buffer:
            return
        chunk = "".join(self._buffer)
        self._buffer.clear()
        await _append_project_sync_task_logs(
            self._session, self._project_id, self._key, chunk
        )
        self._last_flush = time.monotonic()


async def _update_project_sync_task_state(
    session: AsyncSession,
    project_id: int,
    key: str,
    task_status: str,
    message: str | None = None,
    logs: str | None = None,
    mark_remaining_failed_on_error: bool = False,
    append_logs: bool = False,
) -> bool:
    """Update a single project integration's sync_state entry under a row lock. Returns True if all finished."""
    from citadel.service.project.actions import build_initial_project_sync_state

    stmt = select(Project).where(Project.id == project_id).with_for_update()
    res = await session.exec(stmt)
    project = res.one_or_none()
    if not project:
        return False

    now_iso = ts_now().isoformat()
    sync_state = copy.deepcopy(project.sync_state or build_initial_project_sync_state())
    tasks = sync_state.setdefault("tasks", {})
    if key in tasks:
        tasks[key]["status"] = task_status
        tasks[key]["message"] = message
        if logs is not None:
            if append_logs and tasks[key].get("logs"):
                combined = f"{tasks[key]['logs'].rstrip()}\n\n{logs}"
                tasks[key]["logs"] = _trim_sync_logs(combined)
            else:
                tasks[key]["logs"] = _trim_sync_logs(logs)
        tasks[key]["updated_at"] = now_iso
        if task_status == "running":
            tasks[key]["attempts"] = tasks[key].get("attempts", 0) + 1

    if mark_remaining_failed_on_error and task_status == "failed":
        for other_key, other_info in tasks.items():
            if other_key != key and other_info.get("status") in ("pending", "running"):
                other_info["status"] = "failed"
                other_info["message"] = f"Skipped: {key} failed"
                other_info["updated_at"] = now_iso

    all_done = _reconcile_project_sync_state_totals(sync_state)

    project.sync_state = sync_state
    flag_modified(project, "sync_state")
    await session.commit()
    return all_done


@app.task(acks_late=True, reject_on_worker_lost=True)
def sync_project_integrations_task(project_id: int):
    """Trigger integrations sync orchestrator for a specific project."""
    logger.info(f"Triggering integrations sync for project {project_id}")
    run_async(_sync_project_integrations_task(project_id))


async def _sync_project_integrations_task(project_id: int):
    """Orchestrate project integrations sync: ensure Namespace first, then dispatch subtasks."""
    from citadel.service.project.actions import (
        PROJECT_INTEGRATIONS,
        SyncProjectIntegrationsAction,
        build_initial_project_sync_state,
    )

    orch_lock_key = _project_sync_lock_key(project_id, "__orchestrator__")
    if not await acquire_task_lock(orch_lock_key, ttl=120):
        logger.info(
            f"Project integrations sync orchestrator already running for project {project_id}, skipping"
        )
        return

    engine = get_engine()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:

            class MockRequest:
                headers = {}

            svc = ProjectService(MockRequest(), session)
            try:
                model = await svc.get(project_id)
                sync_state = model.sync_state if isinstance(model.sync_state, dict) else {}
                if sync_state.get("status") in ("completed", "error"):
                    logger.info(
                        f"Project sync already finished ({sync_state.get('status')}) for project {project_id}"
                    )
                    return

                if not sync_state or not sync_state.get("tasks"):
                    model.sync_state = build_initial_project_sync_state()
                    flag_modified(model, "sync_state")
                    await session.commit()
                    sync_state = model.sync_state

                ns_status = sync_state.get("tasks", {}).get("namespace", {}).get("status")
                if ns_status != "completed":
                    await _update_project_sync_task_state(
                        session, project_id, "namespace", "running", logs=""
                    )
                    streamer = _ProjectSyncTaskLogStreamer(session, project_id, "namespace")
                    try:
                        action = SyncProjectIntegrationsAction(model, svc)
                        action.session = session
                        action.log_callback = streamer.write
                        msg = await run_with_lock_heartbeat(
                            orch_lock_key,
                            lambda: action.run_integration("namespace"),
                        )
                        await streamer.flush()
                        await _update_project_sync_task_state(
                            session,
                            project_id,
                            "namespace",
                            "completed",
                            message=msg,
                        )
                    except Exception as e:
                        await streamer.flush()
                        logger.error(
                            f"Error creating namespace during sync for project {project_id}: {e}",
                            exc_info=True,
                        )
                        await _update_project_sync_task_state(
                            session,
                            project_id,
                            "namespace",
                            "failed",
                            message=str(e) or type(e).__name__,
                            logs=traceback.format_exc(),
                            mark_remaining_failed_on_error=True,
                            append_logs=True,
                        )
                        return

                await session.refresh(model)
                latest_tasks = (
                    model.sync_state.get("tasks", {})
                    if isinstance(model.sync_state, dict)
                    else {}
                )

                dispatched = 0
                for key, _ in PROJECT_INTEGRATIONS:
                    if key == "namespace":
                        continue
                    task_status = latest_tasks.get(key, {}).get("status", "pending")
                    if task_status in ("completed", "failed"):
                        continue
                    if await is_task_locked(_project_sync_lock_key(project_id, key)):
                        continue
                    sync_project_integration_task.delay(project_id, key)
                    dispatched += 1

                if dispatched == 0 and isinstance(model.sync_state, dict):
                    reconciled = copy.deepcopy(model.sync_state)
                    if _reconcile_project_sync_state_totals(reconciled):
                        model.sync_state = reconciled
                        flag_modified(model, "sync_state")
                        await session.commit()

                logger.info(
                    f"Dispatched {dispatched} project integration sync subtasks for project {project_id}"
                )
            except Exception as e:
                logger.error(
                    f"Error orchestrating integrations sync for project {project_id}: {e}",
                    exc_info=True,
                )
    finally:
        await release_task_lock(orch_lock_key)


@app.task(acks_late=True, reject_on_worker_lost=True)
def sync_project_integration_task(project_id: int, integration_key: str):
    """Execute sync for a single project integration and update project sync_state."""
    logger.info(
        f"Syncing project integration '{integration_key}' for project {project_id}"
    )
    run_async(_sync_project_integration_task(project_id, integration_key))


async def _sync_project_integration_task(project_id: int, integration_key: str):
    """Async helper to run a single project integration sync and update persistent progress."""
    from citadel.service.project.actions import SyncProjectIntegrationsAction

    lock_key = _project_sync_lock_key(project_id, integration_key)
    if not await acquire_task_lock(lock_key, ttl=120):
        logger.info(
            f"Project integration '{integration_key}' already locked for project {project_id}, skipping"
        )
        return

    engine = get_engine()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:

            class MockRequest:
                headers = {}

            svc = ProjectService(MockRequest(), session)
            try:
                model = await svc.get(project_id)
                if isinstance(model.sync_state, dict):
                    if model.sync_state.get("status") in ("completed", "error"):
                        logger.info(
                            f"Sync already finished for project {project_id}, skipping '{integration_key}'"
                        )
                        return
                    current_task_status = (
                        model.sync_state.get("tasks", {})
                        .get(integration_key, {})
                        .get("status")
                    )
                    if current_task_status == "completed":
                        logger.info(
                            f"Integration '{integration_key}' already completed for project {project_id}, skipping"
                        )
                        return

                await _update_project_sync_task_state(
                    session, project_id, integration_key, "running", logs=""
                )
                streamer = _ProjectSyncTaskLogStreamer(session, project_id, integration_key)
                try:
                    action = SyncProjectIntegrationsAction(model, svc)
                    action.session = session
                    action.log_callback = streamer.write
                    msg = await run_with_lock_heartbeat(
                        lock_key,
                        lambda: action.run_integration(integration_key),
                    )
                    await streamer.flush()
                except Exception:
                    await streamer.flush()
                    raise

                await _update_project_sync_task_state(
                    session,
                    project_id,
                    integration_key,
                    "completed",
                    message=msg,
                )
                logger.info(
                    f"Completed project integration '{integration_key}' sync for project {project_id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed syncing project integration '{integration_key}' for project {project_id}: {e}",
                    exc_info=True,
                )
                await _update_project_sync_task_state(
                    session,
                    project_id,
                    integration_key,
                    "failed",
                    message=str(e) or type(e).__name__,
                    logs=traceback.format_exc(),
                    append_logs=True,
                )
    finally:
        await release_task_lock(lock_key)


@app.task(acks_late=True, reject_on_worker_lost=True)
def recover_stuck_project_sync_tasks(
    stale_seconds: int = 60, project_id: int | None = None
):
    """Scan projects with in_progress sync_state and re-dispatch stale, unlocked tasks."""
    run_async(_recover_stuck_project_sync_tasks(stale_seconds=stale_seconds, project_id=project_id))


async def _recover_stuck_project_sync_tasks(
    stale_seconds: int = 60, project_id: int | None = None
):
    """Inspect persisted Project.sync_state rows and re-dispatch incomplete, unlocked tasks."""
    from citadel.service.project.actions import PROJECT_INTEGRATIONS

    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        stmt = select(Project)
        if project_id is not None:
            stmt = stmt.where(Project.id == project_id)
        res = await session.exec(stmt)
        projects = res.all()

        for project in projects:
            sync_state = project.sync_state
            if not isinstance(sync_state, dict) or sync_state.get("status") != "in_progress":
                continue

            pid = project.id
            tasks = sync_state.get("tasks", {})
            ns_info = tasks.get("namespace", {})
            ns_status = ns_info.get("status", "pending")

            # 1. If Namespace failed, mark remaining pending/running tasks failed and finalize
            if ns_status == "failed":
                await _update_project_sync_task_state(
                    session,
                    pid,
                    "namespace",
                    "failed",
                    message=ns_info.get("message"),
                    logs=ns_info.get("logs"),
                    mark_remaining_failed_on_error=True,
                )
                continue

            # 2. If Namespace is not completed yet, resume via orchestrator if unlocked & stale
            if ns_status != "completed":
                orch_locked = await is_task_locked(_project_sync_lock_key(pid, "__orchestrator__"))
                if not orch_locked and _is_timestamp_stale(
                    ns_info.get("updated_at"), stale_seconds
                ):
                    updated = copy.deepcopy(sync_state)
                    updated.setdefault("tasks", {}).setdefault("namespace", {})[
                        "updated_at"
                    ] = ts_now().isoformat()
                    project.sync_state = updated
                    flag_modified(project, "sync_state")
                    await session.commit()
                    logger.info(
                        f"Resuming interrupted project sync orchestrator for project {pid}"
                    )
                    sync_project_integrations_task.delay(pid)
                continue

            # 3. Namespace is completed: reconcile if all tasks are already finished
            updated = copy.deepcopy(sync_state)
            if _reconcile_project_sync_state_totals(updated):
                project.sync_state = updated
                flag_modified(project, "sync_state")
                await session.commit()
                logger.info(f"Reconciled completed sync_state for project {pid}")
                continue

            # 4. Otherwise dispatch any incomplete, unlocked, stale subtasks
            now_iso = ts_now().isoformat()
            keys_to_dispatch: list[str] = []
            for key, _ in PROJECT_INTEGRATIONS:
                if key == "namespace":
                    continue
                t_info = updated.get("tasks", {}).get(key)
                if not t_info:
                    continue
                if t_info.get("status") in ("completed", "failed"):
                    continue
                if await is_task_locked(_project_sync_lock_key(pid, key)):
                    continue
                if not _is_timestamp_stale(t_info.get("updated_at"), stale_seconds):
                    continue
                t_info["updated_at"] = now_iso
                keys_to_dispatch.append(key)

            if keys_to_dispatch:
                updated["updated_at"] = now_iso
                project.sync_state = updated
                flag_modified(project, "sync_state")
                await session.commit()
                for key in keys_to_dispatch:
                    logger.info(
                        f"Resuming interrupted project sync subtask '{key}' for project {pid}"
                    )
                    sync_project_integration_task.delay(pid, key)


@app.task
def sync_trusted_certs_secret_task(project_id: int):
    """Trigger synchronization of the trusted-certs secret for a project."""
    logger.info(f"Triggering trusted-certs secret sync for project {project_id}")
    run_async(_sync_trusted_certs_secret_task(project_id))


async def _sync_trusted_certs_secret_task(project_id: int):
    """Synchronize only the trusted-certs secret to the project's Kubernetes cluster."""
    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        from citadel.service.k8s_cluster import K8sCluster
        from citadel.service.trusted_certs.model import TrustedCert

        try:
            project = await session.get(Project, project_id)
            if not project or not project.k8s_cluster_id:
                logger.warning(
                    f"Project {project_id} or cluster not configured, skipping trusted-certs secret sync"
                )
                return

            cluster = await session.get(K8sCluster, project.k8s_cluster_id)
            if not cluster:
                logger.warning(
                    f"Cluster {project.k8s_cluster_id} not found, skipping trusted-certs secret sync"
                )
                return

            namespace = project.k8s_namespace or project.name

            stmt_certs = select(TrustedCert).where(TrustedCert.project_id == project_id)
            res_certs = await session.exec(stmt_certs)
            certs = res_certs.all()

            trusted_certs = [
                {
                    "name": c.name,
                    "certificate": c.certificate,
                    "certificate_b64": base64.b64encode(c.certificate.encode("utf-8")).decode("utf-8"),
                }
                for c in certs
            ]

            from citadel.service.project.actions import _get_jinja_env, apply_manifest_to_cluster

            env = _get_jinja_env()
            template = env.get_template("03-trusted-certs.yml.j2")
            manifest = template.render(
                name=project.name,
                namespace=namespace,
                trusted_certs=trusted_certs,
            )

            await apply_manifest_to_cluster(cluster, manifest)
            logger.info(f"Successfully synced trusted-certs secret for project {project_id}")
        except Exception as e:
            logger.error(
                f"Error syncing trusted-certs secret for project {project_id}: {e}"
            )
