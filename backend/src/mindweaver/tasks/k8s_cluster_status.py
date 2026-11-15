# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import copy
import traceback
from mindweaver.celery_app import app
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from mindweaver.fw.model import get_engine, ts_now
from mindweaver.service.k8s_cluster import K8sClusterService, K8sClusterStatus
from mindweaver.platform_service.base import PlatformService
from mindweaver.config import logger, settings
from .base import run_async
from .poll_coordinator import acquire_poll_lock, release_poll_lock


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
            from mindweaver.service.k8s_cluster.actions import InstallArgoCDAction

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
            from mindweaver.service.k8s_cluster.actions import InstallCertManagerAction

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
            from mindweaver.service.k8s_cluster.actions import InstallCNPGAction

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
            from mindweaver.service.k8s_cluster.actions import InstallEnvoyGatewayAction

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
    from mindweaver.service.k8s_cluster.actions import build_initial_sync_state

    stmt = (
        select(K8sClusterStatus)
        .where(K8sClusterStatus.k8s_cluster_id == k8s_cluster_id)
        .with_for_update()
    )
    res = await session.exec(stmt)
    status_model = res.one_or_none()
    if not status_model:
        return False

    sync_state = copy.deepcopy(status_model.sync_state or build_initial_sync_state())
    tasks = sync_state.setdefault("tasks", {})
    if key in tasks:
        tasks[key]["status"] = task_status
        tasks[key]["message"] = message
        tasks[key]["logs"] = logs

    if installed_attr and task_status == "completed":
        setattr(status_model, installed_attr, True)

    if mark_remaining_failed_on_error and task_status == "failed":
        for other_key, other_info in tasks.items():
            if other_key != key and other_info.get("status") == "pending":
                other_info["status"] = "failed"
                other_info["message"] = f"Skipped: {key} failed"

    done_statuses = {"completed", "failed"}
    completed_count = sum(1 for t in tasks.values() if t.get("status") in done_statuses)
    total = sync_state.get("total", len(tasks))
    sync_state["completed"] = completed_count

    all_done = total > 0 and completed_count >= total
    if all_done:
        has_failure = any(t.get("status") == "failed" for t in tasks.values())
        sync_state["status"] = "error" if has_failure else "completed"
        sync_state["completed_at"] = ts_now().isoformat()
    else:
        sync_state["status"] = "in_progress"

    status_model.sync_state = sync_state
    flag_modified(status_model, "sync_state")
    await session.commit()
    return all_done


@app.task
def sync_core_integrations_task(k8s_cluster_id: int):
    """Trigger update/installation of configurations for all core integrations."""
    logger.info(f"Triggering core integrations sync for cluster {k8s_cluster_id}")
    run_async(_sync_core_integrations_task(k8s_cluster_id))


async def _sync_core_integrations_task(k8s_cluster_id: int):
    """Orchestrate core integrations sync: ensure ArgoCD first, then dispatch individual integration tasks."""
    from mindweaver.service.k8s_cluster.actions import (
        CORE_INTEGRATIONS,
        InstallArgoCDAction,
    )

    engine = get_engine()
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
            argocd_already_installed = bool(status_model and status_model.argocd_installed)

            if not argocd_already_installed:
                await _update_sync_task_state(
                    session, k8s_cluster_id, "argocd", "running"
                )
                try:
                    action = InstallArgoCDAction(model, svc)
                    action.session = session
                    await action.run()
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
            else:
                await _update_sync_task_state(
                    session,
                    k8s_cluster_id,
                    "argocd",
                    "completed",
                    message="Already installed",
                )

            for key, _, _ in CORE_INTEGRATIONS:
                if key == "argocd":
                    continue
                sync_core_integration_task.delay(k8s_cluster_id, key)

            logger.info(
                f"Dispatched core integration sync subtasks for cluster {k8s_cluster_id}"
            )
        except Exception as e:
            logger.error(
                f"Error orchestrating core integrations sync for cluster {k8s_cluster_id}: {e}"
            )


@app.task
def sync_core_integration_task(k8s_cluster_id: int, integration_key: str):
    """Execute sync for a single core integration and update cluster sync_state."""
    logger.info(
        f"Syncing core integration '{integration_key}' for cluster {k8s_cluster_id}"
    )
    run_async(_sync_core_integration_task(k8s_cluster_id, integration_key))


async def _sync_core_integration_task(k8s_cluster_id: int, integration_key: str):
    """Async helper to run a single core integration sync and update persistent progress."""
    from mindweaver.service.k8s_cluster.actions import (
        CORE_INTEGRATIONS,
        get_integration_action_class,
    )

    installed_attr = next(
        (attr for key, _, attr in CORE_INTEGRATIONS if key == integration_key),
        None,
    )
    action_cls = get_integration_action_class(integration_key)

    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:

        class MockRequest:
            headers = {}

        svc = K8sClusterService(MockRequest(), session)
        all_done = False
        try:
            model = await svc.get(k8s_cluster_id)
            await _update_sync_task_state(
                session, k8s_cluster_id, integration_key, "running"
            )
            action = action_cls(model, svc)
            action.session = session
            await action.run()
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
            from mindweaver.service.k8s_cluster.actions import InstallKafkaOperatorAction

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
            from mindweaver.service.k8s_cluster.actions import InstallNifikopAction

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
            from mindweaver.service.k8s_cluster.actions import InstallDorisOperatorAction

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






