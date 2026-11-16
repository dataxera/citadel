# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import copy
from datetime import datetime, timezone
import traceback
from citadel.celery_app import app
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from citadel.fw.model import get_engine, ts_now
from citadel.service.k8s_cluster import K8sClusterService, K8sClusterStatus
from citadel.platform_service.base import PlatformService
from citadel.config import logger, settings
from .base import run_async
from .poll_coordinator import acquire_poll_lock, release_poll_lock
from .resiliency import (
    acquire_task_lock,
    is_task_locked,
    release_task_lock,
    run_with_lock_heartbeat,
)


@app.task
def poll_all_k8s_clusters():
    """Poll all clusters for status"""
    logger.info("Starting polling of all k8s clusters")
    run_async(_poll_all_k8s_clusters())


async def _poll_all_k8s_clusters():
    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:

        class MockRequest:
            headers = {}

        svc = K8sClusterService(MockRequest(), session)
        clusters = await svc.all()

        for cluster in clusters:
            poll_k8s_cluster_status.apply_async(args=[cluster.id], expires=settings.status_polling_expiry)


@app.task
def poll_k8s_cluster_status(k8s_cluster_id: int):
    """Poll status for a specific cluster instance."""
    logger.info(f"Polling status for k8s cluster {k8s_cluster_id}")
    run_async(_poll_k8s_cluster_status(k8s_cluster_id))


async def _poll_k8s_cluster_status(k8s_cluster_id: int):
    resource_key = f"k8s_cluster:{k8s_cluster_id}"
    if not await acquire_poll_lock(resource_key):
        logger.debug(f"Skipping poll for {resource_key}; already in flight")
        return

    engine = get_engine()
    try:
        async with AsyncSession(engine) as session:

            class MockRequest:
                headers = {}

            svc = K8sClusterService(MockRequest(), session)
            try:
                model = await svc.get(k8s_cluster_id)
                await svc.poll_status(model)
                await session.commit()
                logger.info(f"Successfully polled cluster {k8s_cluster_id}")
            except Exception as e:
                logger.error(f"Error polling cluster {k8s_cluster_id}: {e}")
                try:
                    stmt = select(K8sClusterStatus).where(
                        K8sClusterStatus.k8s_cluster_id == k8s_cluster_id
                    )
                    res = await session.exec(stmt)
                    status_model = res.one_or_none()
                    if not status_model:
                        status_model = K8sClusterStatus(k8s_cluster_id=k8s_cluster_id)
                        session.add(status_model)
                    status_model.status = "error"
                    status_model.message = f"Cluster is unreachable: {str(e)}"
                    status_model.last_update = ts_now()
                    cluster_name = getattr(model, "name", str(k8s_cluster_id)) if "model" in locals() and model else str(k8s_cluster_id)
                    await PlatformService.mark_cluster_services_unreachable(
                        session, k8s_cluster_id, cluster_name, str(e)
                    )
                    await session.commit()
                except Exception as se:
                    logger.error(f"Failed to record cluster error state for {k8s_cluster_id}: {se}")
    finally:
        await release_poll_lock(resource_key)


@app.task
def install_argocd_task(k8s_cluster_id: int):
    """Trigger ArgoCD installation for a cluster."""
    logger.info(f"Triggering ArgoCD installation for cluster {k8s_cluster_id}")
    run_async(_install_argocd_task(k8s_cluster_id))


async def _install_argocd_task(k8s_cluster_id: int):
    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:

        class MockRequest:
            headers = {}

        svc = K8sClusterService(MockRequest(), session)
        try:
            model = await svc.get(k8s_cluster_id)
            from citadel.service.k8s_cluster.actions import InstallArgoCDAction

            action = InstallArgoCDAction(model, svc)
            await action.run()
            await svc.poll_status(model)
            await session.commit()
            logger.info(f"Successfully installed ArgoCD for cluster {k8s_cluster_id}")
        except Exception as e:
            logger.error(f"Error installing ArgoCD for cluster {k8s_cluster_id}: {e}")


@app.task
def install_cert_manager_task(k8s_cluster_id: int):
    """Trigger Cert Manager installation for a cluster."""
    logger.info(f"Triggering Cert Manager installation for cluster {k8s_cluster_id}")
    run_async(_install_cert_manager_task(k8s_cluster_id))


async def _install_cert_manager_task(k8s_cluster_id: int):
    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:

        class MockRequest:
            headers = {}

        svc = K8sClusterService(MockRequest(), session)
        try:
            model = await svc.get(k8s_cluster_id)
            from citadel.service.k8s_cluster.actions import InstallCertManagerAction

            action = InstallCertManagerAction(model, svc)
            await action.run()
            await svc.poll_status(model)
            await session.commit()
            logger.info(
                f"Successfully installed Cert Manager for cluster {k8s_cluster_id}"
            )
        except Exception as e:
            logger.error(
                f"Error installing Cert Manager for cluster {k8s_cluster_id}: {e}"
            )


@app.task
def install_cnpg_operator_task(k8s_cluster_id: int):
    """Trigger CNPG Operator installation for a cluster."""
    logger.info(f"Triggering CNPG Operator installation for cluster {k8s_cluster_id}")
    run_async(_install_cnpg_operator_task(k8s_cluster_id))


async def _install_cnpg_operator_task(k8s_cluster_id: int):
    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:

        class MockRequest:
            headers = {}

        svc = K8sClusterService(MockRequest(), session)
        try:
            model = await svc.get(k8s_cluster_id)
            from citadel.service.k8s_cluster.actions import InstallCNPGAction

            action = InstallCNPGAction(model, svc)
            await action.run()
            await svc.poll_status(model)
            await session.commit()
            logger.info(
                f"Successfully installed CNPG Operator for cluster {k8s_cluster_id}"
            )
        except Exception as e:
            logger.error(
                f"Error installing CNPG Operator for cluster {k8s_cluster_id}: {e}"
            )




@app.task
def install_envoy_gateway_task(k8s_cluster_id: int):
    """Trigger Envoy Gateway installation for a cluster."""
    logger.info(f"Triggering Envoy Gateway installation for cluster {k8s_cluster_id}")
    run_async(_install_envoy_gateway_task(k8s_cluster_id))


async def _install_envoy_gateway_task(k8s_cluster_id: int):
    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:

        class MockRequest:
            headers = {}

        svc = K8sClusterService(MockRequest(), session)
        try:
            model = await svc.get(k8s_cluster_id)
            from citadel.service.k8s_cluster.actions import InstallEnvoyGatewayAction

            action = InstallEnvoyGatewayAction(model, svc)
            await action.run()
            await svc.poll_status(model)
            await session.commit()
            logger.info(
                f"Successfully installed Envoy Gateway for cluster {k8s_cluster_id}"
            )
        except Exception as e:
            logger.error(
                f"Error installing Envoy Gateway for cluster {k8s_cluster_id}: {e}"
            )


def _sync_lock_key(k8s_cluster_id: int, key: str) -> str:
    """Return the distributed lock key for a cluster sync task."""
    return f"k8s_cluster:{k8s_cluster_id}:{key}"


def _is_timestamp_stale(updated_at_str: str | None, stale_seconds: int) -> bool:
    """Return True if an ISO timestamp is missing or older than stale_seconds."""
    if stale_seconds <= 0:
        return True
    if not updated_at_str:
        return True
    try:
        dt = datetime.fromisoformat(updated_at_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (ts_now() - dt).total_seconds()
        return age >= stale_seconds
    except Exception:
        return True


def _reconcile_sync_state_totals(sync_state: dict) -> bool:
    """Recompute completed count and overall status for sync_state. Returns True if all tasks finished."""
    tasks = sync_state.setdefault("tasks", {})
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


async def _update_sync_task_state(
    session: AsyncSession,
    k8s_cluster_id: int,
    key: str,
    task_status: str,
    message: str | None = None,
    logs: str | None = None,
    installed_attr: str | None = None,
    mark_remaining_failed_on_error: bool = False,
) -> bool:
    """Update a single integration's sync_state entry under a row lock. Returns True if all tasks finished."""
    from citadel.service.k8s_cluster.actions import build_initial_sync_state

    stmt = (
        select(K8sClusterStatus)
        .where(K8sClusterStatus.k8s_cluster_id == k8s_cluster_id)
        .with_for_update()
    )
    res = await session.exec(stmt)
    status_model = res.one_or_none()
    if not status_model:
        return False

    now_iso = ts_now().isoformat()
    sync_state = copy.deepcopy(status_model.sync_state or build_initial_sync_state())
    tasks = sync_state.setdefault("tasks", {})
    if key in tasks:
        tasks[key]["status"] = task_status
        tasks[key]["message"] = message
        tasks[key]["logs"] = logs
        tasks[key]["updated_at"] = now_iso
        if task_status == "running":
            tasks[key]["attempts"] = tasks[key].get("attempts", 0) + 1

    if installed_attr and task_status == "completed":
        setattr(status_model, installed_attr, True)

    if mark_remaining_failed_on_error and task_status == "failed":
        for other_key, other_info in tasks.items():
            if other_key != key and other_info.get("status") in ("pending", "running"):
                other_info["status"] = "failed"
                other_info["message"] = f"Skipped: {key} failed"
                other_info["updated_at"] = now_iso

    all_done = _reconcile_sync_state_totals(sync_state)

    status_model.sync_state = sync_state
    flag_modified(status_model, "sync_state")
    await session.commit()
    return all_done


@app.task(acks_late=True, reject_on_worker_lost=True)
def sync_core_integrations_task(k8s_cluster_id: int):
    """Trigger update/installation of configurations for all core integrations."""
    logger.info(f"Triggering core integrations sync for cluster {k8s_cluster_id}")
    run_async(_sync_core_integrations_task(k8s_cluster_id))


async def _sync_core_integrations_task(k8s_cluster_id: int):
    """Orchestrate core integrations sync: ensure ArgoCD first, then dispatch incomplete integration tasks."""
    from citadel.service.k8s_cluster.actions import (
        CORE_INTEGRATIONS,
        InstallArgoCDAction,
    )

    orch_lock_key = _sync_lock_key(k8s_cluster_id, "__orchestrator__")
    if not await acquire_task_lock(orch_lock_key, ttl=120):
        logger.info(
            f"Core integrations sync orchestrator already running for cluster {k8s_cluster_id}, skipping"
        )
        return

    engine = get_engine()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:

            class MockRequest:
                headers = {}

            svc = K8sClusterService(MockRequest(), session)
            try:
                model = await svc.get(k8s_cluster_id)
                stmt = select(K8sClusterStatus).where(
                    K8sClusterStatus.k8s_cluster_id == k8s_cluster_id
                )
                res = await session.exec(stmt)
                status_model = res.one_or_none()
                sync_state = status_model.sync_state if status_model else {}
                if isinstance(sync_state, dict) and sync_state.get("status") in (
                    "completed",
                    "error",
                ):
                    logger.info(
                        f"Sync already finished ({sync_state.get('status')}) for cluster {k8s_cluster_id}"
                    )
                    return

                argocd_task_status = (
                    sync_state.get("tasks", {}).get("argocd", {}).get("status")
                    if isinstance(sync_state, dict)
                    else None
                )
                argocd_already_done = argocd_task_status == "completed" or bool(
                    status_model and status_model.argocd_installed
                )

                if not argocd_already_done:
                    await _update_sync_task_state(
                        session, k8s_cluster_id, "argocd", "running"
                    )
                    try:
                        action = InstallArgoCDAction(model, svc)
                        action.session = session
                        await run_with_lock_heartbeat(orch_lock_key, action.run)
                        await _update_sync_task_state(
                            session,
                            k8s_cluster_id,
                            "argocd",
                            "completed",
                            installed_attr="argocd_installed",
                        )
                    except Exception as e:
                        logger.error(
                            f"Error installing ArgoCD during sync for cluster {k8s_cluster_id}: {e}"
                        )
                        await _update_sync_task_state(
                            session,
                            k8s_cluster_id,
                            "argocd",
                            "failed",
                            message=str(e) or type(e).__name__,
                            logs=traceback.format_exc(),
                            mark_remaining_failed_on_error=True,
                        )
                        return
                elif argocd_task_status != "completed":
                    try:
                        action = InstallArgoCDAction(model, svc)
                        action.session = session
                        await action.ensure_load_balancer()
                    except Exception as e:
                        logger.warning(
                            f"Failed to ensure ArgoCD LoadBalancer service during sync for cluster {k8s_cluster_id}: {e}"
                        )
                    await _update_sync_task_state(
                        session,
                        k8s_cluster_id,
                        "argocd",
                        "completed",
                        message="Already installed",
                    )

                # Refresh status_model to read latest sync_state before dispatching remaining tasks
                await session.refresh(status_model)
                latest_tasks = (
                    status_model.sync_state.get("tasks", {})
                    if isinstance(status_model.sync_state, dict)
                    else {}
                )

                dispatched = 0
                for key, _, _ in CORE_INTEGRATIONS:
                    if key == "argocd":
                        continue
                    task_status = latest_tasks.get(key, {}).get("status", "pending")
                    if task_status in ("completed", "failed"):
                        continue
                    if await is_task_locked(_sync_lock_key(k8s_cluster_id, key)):
                        continue
                    sync_core_integration_task.delay(k8s_cluster_id, key)
                    dispatched += 1

                if dispatched == 0 and isinstance(status_model.sync_state, dict):
                    reconciled = copy.deepcopy(status_model.sync_state)
                    if _reconcile_sync_state_totals(reconciled):
                        status_model.sync_state = reconciled
                        flag_modified(status_model, "sync_state")
                        await session.commit()
                        poll_k8s_cluster_status.delay(k8s_cluster_id)

                logger.info(
                    f"Dispatched {dispatched} core integration sync subtasks for cluster {k8s_cluster_id}"
                )
            except Exception as e:
                logger.error(
                    f"Error orchestrating core integrations sync for cluster {k8s_cluster_id}: {e}"
                )
    finally:
        await release_task_lock(orch_lock_key)


@app.task(acks_late=True, reject_on_worker_lost=True)
def sync_core_integration_task(k8s_cluster_id: int, integration_key: str):
    """Execute sync for a single core integration and update cluster sync_state."""
    logger.info(
        f"Syncing core integration '{integration_key}' for cluster {k8s_cluster_id}"
    )
    run_async(_sync_core_integration_task(k8s_cluster_id, integration_key))


async def _sync_core_integration_task(k8s_cluster_id: int, integration_key: str):
    """Async helper to run a single core integration sync and update persistent progress."""
    from citadel.service.k8s_cluster.actions import (
        CORE_INTEGRATIONS,
        get_integration_action_class,
    )

    installed_attr = next(
        (attr for key, _, attr in CORE_INTEGRATIONS if key == integration_key),
        None,
    )
    action_cls = get_integration_action_class(integration_key)
    lock_key = _sync_lock_key(k8s_cluster_id, integration_key)

    if not await acquire_task_lock(lock_key, ttl=120):
        logger.info(
            f"Core integration '{integration_key}' already locked for cluster {k8s_cluster_id}, skipping"
        )
        return

    engine = get_engine()
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:

            class MockRequest:
                headers = {}

            svc = K8sClusterService(MockRequest(), session)
            all_done = False
            try:
                stmt = select(K8sClusterStatus).where(
                    K8sClusterStatus.k8s_cluster_id == k8s_cluster_id
                )
                res = await session.exec(stmt)
                status_model = res.one_or_none()
                if status_model and isinstance(status_model.sync_state, dict):
                    if status_model.sync_state.get("status") in ("completed", "error"):
                        logger.info(
                            f"Sync already finished for cluster {k8s_cluster_id}, skipping '{integration_key}'"
                        )
                        return
                    current_task_status = (
                        status_model.sync_state.get("tasks", {})
                        .get(integration_key, {})
                        .get("status")
                    )
                    if current_task_status == "completed":
                        logger.info(
                            f"Integration '{integration_key}' already completed for cluster {k8s_cluster_id}, skipping"
                        )
                        return

                model = await svc.get(k8s_cluster_id)
                await _update_sync_task_state(
                    session, k8s_cluster_id, integration_key, "running"
                )
                action = action_cls(model, svc)
                action.session = session
                await run_with_lock_heartbeat(lock_key, action.run)
                all_done = await _update_sync_task_state(
                    session,
                    k8s_cluster_id,
                    integration_key,
                    "completed",
                    installed_attr=installed_attr,
                )
                logger.info(
                    f"Successfully synced '{integration_key}' for cluster {k8s_cluster_id}"
                )
            except Exception as e:
                logger.error(
                    f"Error syncing '{integration_key}' for cluster {k8s_cluster_id}: {e}"
                )
                all_done = await _update_sync_task_state(
                    session,
                    k8s_cluster_id,
                    integration_key,
                    "failed",
                    message=str(e) or type(e).__name__,
                    logs=traceback.format_exc(),
                )

            if all_done:
                poll_k8s_cluster_status.delay(k8s_cluster_id)
    finally:
        await release_task_lock(lock_key)


@app.task(acks_late=True, reject_on_worker_lost=True)
def recover_stuck_sync_tasks(
    stale_seconds: int = 60, k8s_cluster_id: int | None = None
):
    """Recover and resume any k8s cluster core integration syncs stuck in 'in_progress'."""
    run_async(
        _recover_stuck_sync_tasks(
            stale_seconds=stale_seconds, k8s_cluster_id=k8s_cluster_id
        )
    )


async def _recover_stuck_sync_tasks(
    stale_seconds: int = 60, k8s_cluster_id: int | None = None
):
    """Inspect persisted sync_state rows and re-dispatch incomplete, unlocked tasks."""
    from citadel.service.k8s_cluster.actions import CORE_INTEGRATIONS

    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        stmt = select(K8sClusterStatus)
        if k8s_cluster_id is not None:
            stmt = stmt.where(K8sClusterStatus.k8s_cluster_id == k8s_cluster_id)
        res = await session.exec(stmt)
        status_rows = res.all()

        for status_model in status_rows:
            sync_state = status_model.sync_state
            if not isinstance(sync_state, dict) or sync_state.get("status") != "in_progress":
                continue

            cid = status_model.k8s_cluster_id
            tasks = sync_state.get("tasks", {})
            argocd_info = tasks.get("argocd", {})
            argocd_status = argocd_info.get("status", "pending")

            # 1. If ArgoCD failed, ensure remaining pending/running tasks are marked failed and finalize
            if argocd_status == "failed":
                await _update_sync_task_state(
                    session,
                    cid,
                    "argocd",
                    "failed",
                    message=argocd_info.get("message"),
                    logs=argocd_info.get("logs"),
                    mark_remaining_failed_on_error=True,
                )
                continue

            # 2. If ArgoCD is not completed yet, resume via orchestrator task if unlocked & stale
            if argocd_status != "completed":
                orch_locked = await is_task_locked(_sync_lock_key(cid, "__orchestrator__"))
                argo_locked = await is_task_locked(_sync_lock_key(cid, "argocd"))
                if (
                    not orch_locked
                    and not argo_locked
                    and _is_timestamp_stale(argocd_info.get("updated_at"), stale_seconds)
                ):
                    updated = copy.deepcopy(sync_state)
                    updated.setdefault("tasks", {}).setdefault("argocd", {})[
                        "updated_at"
                    ] = ts_now().isoformat()
                    status_model.sync_state = updated
                    flag_modified(status_model, "sync_state")
                    await session.commit()
                    logger.info(
                        f"Resuming interrupted ArgoCD/core sync orchestrator for cluster {cid}"
                    )
                    sync_core_integrations_task.delay(cid)
                continue

            # 3. ArgoCD is completed: reconcile if all tasks are already finished
            updated = copy.deepcopy(sync_state)
            if _reconcile_sync_state_totals(updated):
                status_model.sync_state = updated
                flag_modified(status_model, "sync_state")
                await session.commit()
                logger.info(f"Reconciled completed sync_state for cluster {cid}")
                poll_k8s_cluster_status.delay(cid)
                continue

            # 4. Otherwise dispatch any incomplete, unlocked, stale tasks
            now_iso = ts_now().isoformat()
            keys_to_dispatch: list[str] = []
            for key, _, _ in CORE_INTEGRATIONS:
                if key == "argocd":
                    continue
                t_info = updated.get("tasks", {}).get(key)
                if not t_info:
                    continue
                if t_info.get("status") in ("completed", "failed"):
                    continue
                if await is_task_locked(_sync_lock_key(cid, key)):
                    continue
                if not _is_timestamp_stale(t_info.get("updated_at"), stale_seconds):
                    continue
                t_info["updated_at"] = now_iso
                keys_to_dispatch.append(key)

            if keys_to_dispatch:
                updated["updated_at"] = now_iso
                status_model.sync_state = updated
                flag_modified(status_model, "sync_state")
                await session.commit()
                for key in keys_to_dispatch:
                    logger.info(
                        f"Resuming interrupted sync subtask '{key}' for cluster {cid}"
                    )
                    sync_core_integration_task.delay(cid, key)


@app.task
def install_kafka_operator_task(k8s_cluster_id: int):
    """Trigger Kafka Operator installation for a cluster."""
    logger.info(f"Triggering Kafka Operator installation for cluster {k8s_cluster_id}")
    run_async(_install_kafka_operator_task(k8s_cluster_id))


async def _install_kafka_operator_task(k8s_cluster_id: int):
    """Async task implementation to deploy the Kafka Operator via its install action."""
    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:

        class MockRequest:
            headers = {}

        svc = K8sClusterService(MockRequest(), session)
        try:
            model = await svc.get(k8s_cluster_id)
            from citadel.service.k8s_cluster.actions import InstallKafkaOperatorAction

            action = InstallKafkaOperatorAction(model, svc)
            await action.run()
            await svc.poll_status(model)
            await session.commit()
            logger.info(
                f"Successfully installed Kafka Operator for cluster {k8s_cluster_id}"
            )
        except Exception as e:
            logger.error(
                f"Error installing Kafka Operator for cluster {k8s_cluster_id}: {e}"
            )


@app.task
def install_nifikop_task(k8s_cluster_id: int):
    """Trigger NiFiKop Operator installation for a cluster."""
    logger.info(f"Triggering NiFiKop Operator installation for cluster {k8s_cluster_id}")
    run_async(_install_nifikop_task(k8s_cluster_id))


async def _install_nifikop_task(k8s_cluster_id: int):
    """Async task implementation to deploy the NiFiKop Operator via its install action."""
    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:

        class MockRequest:
            headers = {}

        svc = K8sClusterService(MockRequest(), session)
        try:
            model = await svc.get(k8s_cluster_id)
            from citadel.service.k8s_cluster.actions import InstallNifikopAction

            action = InstallNifikopAction(model, svc)
            await action.run()
            await svc.poll_status(model)
            await session.commit()
            logger.info(
                f"Successfully installed NiFiKop Operator for cluster {k8s_cluster_id}"
            )
        except Exception as e:
            logger.error(
                f"Error installing NiFiKop Operator for cluster {k8s_cluster_id}: {e}"
            )


@app.task
def install_doris_operator_task(k8s_cluster_id: int):
    """Trigger Doris Operator installation for a cluster."""
    logger.info(f"Triggering Doris Operator installation for cluster {k8s_cluster_id}")
    run_async(_install_doris_operator_task(k8s_cluster_id))


async def _install_doris_operator_task(k8s_cluster_id: int):
    """Async task implementation to deploy the Doris Operator via its install action."""
    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:

        class MockRequest:
            headers = {}

        svc = K8sClusterService(MockRequest(), session)
        try:
            model = await svc.get(k8s_cluster_id)
            from citadel.service.k8s_cluster.actions import InstallDorisOperatorAction

            action = InstallDorisOperatorAction(model, svc)
            await action.run()
            await svc.poll_status(model)
            await session.commit()
            logger.info(
                f"Successfully installed Doris Operator for cluster {k8s_cluster_id}"
            )
        except Exception as e:
            logger.error(
                f"Error installing Doris Operator for cluster {k8s_cluster_id}: {e}"
            )


@app.task
def install_kube_prometheus_stack_task(k8s_cluster_id: int):
    """Trigger kube-prometheus-stack installation for a cluster."""
    logger.info(f"Triggering kube-prometheus-stack installation for cluster {k8s_cluster_id}")
    run_async(_install_kube_prometheus_stack_task(k8s_cluster_id))


async def _install_kube_prometheus_stack_task(k8s_cluster_id: int):
    """Async task implementation to deploy kube-prometheus-stack via its install action."""
    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:

        class MockRequest:
            headers = {}

        svc = K8sClusterService(MockRequest(), session)
        try:
            model = await svc.get(k8s_cluster_id)
            from citadel.service.k8s_cluster.actions import InstallKubePrometheusStackAction

            action = InstallKubePrometheusStackAction(model, svc)
            await action.run()
            await svc.poll_status(model)
            await session.commit()
            logger.info(
                f"Successfully installed kube-prometheus-stack for cluster {k8s_cluster_id}"
            )
        except Exception as e:
            logger.error(
                f"Error installing kube-prometheus-stack for cluster {k8s_cluster_id}: {e}"
            )






