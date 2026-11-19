# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from kubernetes.client.rest import ApiException

from citadel.fw.model import get_engine
from citadel.service.k8s_cluster.model import K8sCluster, K8sClusterStatus, K8sClusterType
from citadel.service.project.model import Project
from sqlmodel.ext.asyncio.session import AsyncSession
import pytest


def _make_project_and_cluster_sync(client: TestClient, suffix: str, ingress_domain: str = "apps.example.com"):
    """Helper to create a cluster and project via API."""
    c_resp = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": f"integ-cluster-{suffix}",
            "title": f"Integ Cluster {suffix}",
            "type": "in-cluster",
        },
    )
    assert c_resp.status_code == 200
    cluster = c_resp.json()["data"]

    p_resp = client.post(
        "/api/v1/projects",
        json={
            "name": f"integ-proj-{suffix}",
            "title": f"Integ Proj {suffix}",
            "k8s_cluster_id": cluster["id"],
            "k8s_namespace": f"integ-proj-{suffix}",
            "ingress_domain": ingress_domain,
        },
    )
    assert p_resp.status_code == 200
    project = p_resp.json()["data"]
    return cluster, project


@pytest.mark.asyncio
async def test_project_state_integrations_all_online(client: TestClient):
    """Project _state reports all project integrations as online when present and ready."""
    cluster, project = _make_project_and_cluster_sync(client, "online")

    engine = get_engine()
    async with AsyncSession(engine) as session:
        status_row = K8sClusterStatus(k8s_cluster_id=cluster["id"], status="online")
        session.add(status_row)
        await session.commit()

    mock_core_v1 = MagicMock()
    mock_core_v1.read_namespace.return_value = SimpleNamespace(
        status=SimpleNamespace(phase="Active")
    )
    mock_core_v1.list_namespaced_service.return_value = SimpleNamespace(items=[])
    mock_core_v1.list_namespaced_secret.return_value = SimpleNamespace(
        items=[SimpleNamespace(metadata=SimpleNamespace(name="trusted-certs"))]
    )

    def _get_custom_object(group, version, namespace, plural, name):
        if plural == "appprojects":
            return {"metadata": {"name": name}}
        if plural == "issuers":
            return {"status": {"conditions": [{"type": "Ready", "status": "True"}]}}
        if plural == "gateways":
            return {"status": {"conditions": [{"type": "Programmed", "status": "True"}]}}
        if plural == "certificates":
            return {"status": {"conditions": [{"type": "Ready", "status": "True"}]}}
        raise ApiException(status=404)

    mock_custom_api = MagicMock()
    mock_custom_api.get_namespaced_custom_object.side_effect = _get_custom_object

    with (
        patch("kubernetes.config.load_incluster_config"),
        patch("kubernetes.client.ApiClient"),
        patch("kubernetes.client.CoreV1Api", return_value=mock_core_v1),
        patch("kubernetes.client.CustomObjectsApi", return_value=mock_custom_api),
    ):
        resp = client.get(f"/api/v1/projects/{project['id']}/_state")

    assert resp.status_code == 200
    data = resp.json()
    integrations = data["integrations_status"]
    for key in (
        "namespace",
        "argocd_project",
        "self_signed_issuer",
        "trusted_certs",
        "envoy_gateway",
        "wildcard_certificate",
    ):
        assert integrations[key]["status"] == "online", f"Expected {key} online, got {integrations[key]}"


@pytest.mark.asyncio
async def test_project_state_integrations_missing_are_offline(client: TestClient):
    """Project _state reports missing integrations as offline when k8s resources return 404."""
    cluster, project = _make_project_and_cluster_sync(client, "offline")

    engine = get_engine()
    async with AsyncSession(engine) as session:
        status_row = K8sClusterStatus(k8s_cluster_id=cluster["id"], status="online")
        session.add(status_row)
        await session.commit()

    mock_core_v1 = MagicMock()
    mock_core_v1.read_namespace.side_effect = ApiException(status=404)
    mock_core_v1.list_namespaced_service.side_effect = ApiException(status=404)
    mock_core_v1.list_namespaced_secret.side_effect = ApiException(status=404)

    mock_custom_api = MagicMock()
    mock_custom_api.get_namespaced_custom_object.side_effect = ApiException(status=404)

    with (
        patch("kubernetes.config.load_incluster_config"),
        patch("kubernetes.client.ApiClient"),
        patch("kubernetes.client.CoreV1Api", return_value=mock_core_v1),
        patch("kubernetes.client.CustomObjectsApi", return_value=mock_custom_api),
    ):
        resp = client.get(f"/api/v1/projects/{project['id']}/_state")

    assert resp.status_code == 200
    data = resp.json()
    integrations = data["integrations_status"]
    for key in (
        "namespace",
        "argocd_project",
        "self_signed_issuer",
        "trusted_certs",
        "envoy_gateway",
        "wildcard_certificate",
    ):
        assert integrations[key]["status"] == "offline", f"Expected {key} offline, got {integrations[key]}"


@pytest.mark.asyncio
async def test_project_state_integrations_pending_states(client: TestClient):
    """Project _state reports provisioning issuer/gateway/certificate as pending."""
    cluster, project = _make_project_and_cluster_sync(client, "pending")

    engine = get_engine()
    async with AsyncSession(engine) as session:
        status_row = K8sClusterStatus(k8s_cluster_id=cluster["id"], status="online")
        session.add(status_row)
        await session.commit()

    mock_core_v1 = MagicMock()
    mock_core_v1.read_namespace.return_value = SimpleNamespace(
        status=SimpleNamespace(phase="Active")
    )
    mock_core_v1.list_namespaced_service.return_value = SimpleNamespace(items=[])
    mock_core_v1.list_namespaced_secret.return_value = SimpleNamespace(
        items=[SimpleNamespace(metadata=SimpleNamespace(name="trusted-certs"))]
    )

    def _get_custom_object(group, version, namespace, plural, name):
        if plural == "appprojects":
            return {"metadata": {"name": name}}
        if plural == "issuers":
            return {"status": {"conditions": [{"type": "Ready", "status": "False", "reason": "Pending"}]}}
        if plural == "gateways":
            return {"status": {"conditions": [{"type": "Accepted", "status": "True"}]}}
        if plural == "certificates":
            return {"status": {"conditions": [{"type": "Ready", "status": "False", "message": "Issuing"}]}}
        raise ApiException(status=404)

    mock_custom_api = MagicMock()
    mock_custom_api.get_namespaced_custom_object.side_effect = _get_custom_object

    with (
        patch("kubernetes.config.load_incluster_config"),
        patch("kubernetes.client.ApiClient"),
        patch("kubernetes.client.CoreV1Api", return_value=mock_core_v1),
        patch("kubernetes.client.CustomObjectsApi", return_value=mock_custom_api),
    ):
        resp = client.get(f"/api/v1/projects/{project['id']}/_state")

    assert resp.status_code == 200
    integrations = resp.json()["integrations_status"]
    assert integrations["namespace"]["status"] == "online"
    assert integrations["argocd_project"]["status"] == "online"
    assert integrations["trusted_certs"]["status"] == "online"
    assert integrations["self_signed_issuer"]["status"] == "pending"
    assert integrations["envoy_gateway"]["status"] == "pending"
    assert integrations["wildcard_certificate"]["status"] == "pending"


def test_project_sync_action_initializes_sync_state(client: TestClient):
    """Triggering sync_project_integrations persists initial sync_state and exposes it via _state."""
    _, project = _make_project_and_cluster_sync(client, "syncinit")

    with patch("citadel.tasks.project_tasks.sync_project_integrations_task.delay") as mock_delay:
        resp = client.post(
            f"/api/v1/projects/{project['id']}/_actions",
            json={"action": "sync_project_integrations"},
        )
    assert resp.status_code == 200
    mock_delay.assert_called_once_with(project["id"])

    state_resp = client.get(f"/api/v1/projects/{project['id']}/_state")
    assert state_resp.status_code == 200
    sync_state = state_resp.json()["sync_state"]
    assert sync_state["status"] == "in_progress"
    assert sync_state["total"] == 6
    assert sync_state["completed"] == 0
    for key in (
        "namespace",
        "argocd_project",
        "self_signed_issuer",
        "trusted_certs",
        "envoy_gateway",
        "wildcard_certificate",
    ):
        assert sync_state["tasks"][key]["status"] == "pending"


@pytest.mark.asyncio
async def test_project_sync_action_run_completes_all_steps(client: TestClient):
    """Running SyncProjectIntegrationsAction updates sync_state to completed with logs."""
    from citadel.service.project.actions import SyncProjectIntegrationsAction

    _, project_data = _make_project_and_cluster_sync(client, "syncok")

    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        project = await session.get(Project, project_data["id"])
        mock_svc = MagicMock()
        mock_svc.session = session
        mock_svc.request = MagicMock()

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.communicate = pytest.importorskip("unittest.mock").AsyncMock(
                return_value=(b"configured\n", b"")
            )
            mock_exec.return_value = mock_proc

            action = SyncProjectIntegrationsAction(project, mock_svc)
            action.session = session
            await action.run()

    state_resp = client.get(f"/api/v1/projects/{project_data['id']}/_state")
    assert state_resp.status_code == 200
    sync_state = state_resp.json()["sync_state"]
    assert sync_state["status"] == "completed"
    assert sync_state["completed"] == 6
    for key in (
        "namespace",
        "argocd_project",
        "self_signed_issuer",
        "trusted_certs",
        "envoy_gateway",
        "wildcard_certificate",
    ):
        assert sync_state["tasks"][key]["status"] == "completed"
        assert "configured" in (sync_state["tasks"][key]["logs"] or "")


@pytest.mark.asyncio
async def test_project_sync_action_run_marks_remaining_failed_on_error(client: TestClient):
    """If a sync step fails, sync_state transitions to error and remaining pending tasks are failed."""
    from citadel.service.project.actions import SyncProjectIntegrationsAction

    _, project_data = _make_project_and_cluster_sync(client, "syncerr")

    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        project = await session.get(Project, project_data["id"])
        mock_svc = MagicMock()
        mock_svc.session = session
        mock_svc.request = MagicMock()

        call_count = 0

        async def _communicate():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (b"namespace created\n", b"")
            return (b"", b"error: argocd CRD missing")

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            def _make_proc(*args, **kwargs):
                proc = MagicMock()
                proc.returncode = 0 if call_count == 0 else 1
                proc.communicate = _communicate
                return proc

            mock_exec.side_effect = _make_proc

            action = SyncProjectIntegrationsAction(project, mock_svc)
            action.session = session
            with pytest.raises(RuntimeError, match="argocd CRD missing"):
                await action.run()

    state_resp = client.get(f"/api/v1/projects/{project_data['id']}/_state")
    assert state_resp.status_code == 200
    sync_state = state_resp.json()["sync_state"]
    assert sync_state["status"] == "error"
    assert sync_state["completed"] == 1
    assert sync_state["tasks"]["namespace"]["status"] == "completed"
    assert sync_state["tasks"]["argocd_project"]["status"] == "failed"
    assert "argocd CRD missing" in (sync_state["tasks"]["argocd_project"]["message"] or "")
    assert sync_state["tasks"]["self_signed_issuer"]["status"] == "failed"
    assert sync_state["tasks"]["self_signed_issuer"]["message"] == "Skipped due to earlier error"


@pytest.mark.asyncio
async def test_sync_project_integrations_task_marks_error_on_crash(client: TestClient):
    """_sync_project_integrations_task marks sync_state as error if namespace step fails."""
    from citadel.tasks.project_tasks import _sync_project_integrations_task

    _, project_data = _make_project_and_cluster_sync(client, "taskcrash")

    with patch("citadel.tasks.project_tasks.sync_project_integrations_task.delay"):
        resp = client.post(
            f"/api/v1/projects/{project_data['id']}/_actions",
            json={"action": "sync_project_integrations"},
        )
    assert resp.status_code == 200

    with (
        patch("citadel.tasks.project_tasks.acquire_task_lock", return_value=True),
        patch("citadel.tasks.project_tasks.release_task_lock"),
        patch(
            "citadel.tasks.project_tasks.run_with_lock_heartbeat",
            side_effect=RuntimeError("worker crash"),
        ),
    ):
        await _sync_project_integrations_task(project_data["id"])

    state_resp = client.get(f"/api/v1/projects/{project_data['id']}/_state")
    assert state_resp.status_code == 200
    sync_state = state_resp.json()["sync_state"]
    assert sync_state["status"] == "error"
    assert sync_state["tasks"]["namespace"]["status"] == "failed"
    assert "worker crash" in (sync_state["tasks"]["namespace"]["message"] or "")
    assert sync_state["tasks"]["argocd_project"]["status"] == "failed"


def test_project_resume_sync_action(client: TestClient):
    """resume_sync_project_integrations is available when in_progress and triggers recovery."""
    _, project = _make_project_and_cluster_sync(client, "resume")

    # Initially not in_progress, so resume action should not be available
    actions_before = client.get(f"/api/v1/projects/{project['id']}/_actions").json()["actions"]
    assert "resume_sync_project_integrations" not in actions_before

    # Trigger initial sync
    with patch("citadel.tasks.project_tasks.sync_project_integrations_task.delay"):
        resp = client.post(
            f"/api/v1/projects/{project['id']}/_actions",
            json={"action": "sync_project_integrations"},
        )
    assert resp.status_code == 200

    # Now resume action should be available and trigger recover_stuck_project_sync_tasks
    actions_during = client.get(f"/api/v1/projects/{project['id']}/_actions").json()["actions"]
    assert "resume_sync_project_integrations" in actions_during

    with patch("citadel.tasks.project_tasks.recover_stuck_project_sync_tasks.delay") as mock_recover:
        resume_resp = client.post(
            f"/api/v1/projects/{project['id']}/_actions",
            json={"action": "resume_sync_project_integrations"},
        )
    assert resume_resp.status_code == 200
    assert resume_resp.json()["message"] == "Project integrations synchronization resumed."
    mock_recover.assert_called_once_with(stale_seconds=0, project_id=project["id"])


@pytest.mark.asyncio
async def test_project_sync_orchestrator_and_subtasks_flow(client: TestClient):
    """Orchestrator runs namespace first, dispatches subtasks, and subtasks complete sync_state."""
    from citadel.tasks.project_tasks import (
        _sync_project_integration_task,
        _sync_project_integrations_task,
    )

    _, project_data = _make_project_and_cluster_sync(client, "orchflow")
    pid = project_data["id"]

    with patch("citadel.tasks.project_tasks.sync_project_integrations_task.delay"):
        resp = client.post(
            f"/api/v1/projects/{pid}/_actions",
            json={"action": "sync_project_integrations"},
        )
    assert resp.status_code == 200

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = pytest.importorskip("unittest.mock").AsyncMock(
        return_value=(b"configured\n", b"")
    )

    dispatched_keys = []

    with (
        patch("citadel.tasks.project_tasks.acquire_task_lock", return_value=True),
        patch("citadel.tasks.project_tasks.release_task_lock"),
        patch("citadel.tasks.project_tasks.is_task_locked", return_value=False),
        patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        patch(
            "citadel.tasks.project_tasks.sync_project_integration_task.delay",
            side_effect=lambda p, k: dispatched_keys.append(k),
        ),
    ):
        await _sync_project_integrations_task(pid)

        assert dispatched_keys == [
            "argocd_project",
            "self_signed_issuer",
            "trusted_certs",
            "envoy_gateway",
            "wildcard_certificate",
        ]

        mid_state = client.get(f"/api/v1/projects/{pid}/_state").json()["sync_state"]
        assert mid_state["status"] == "in_progress"
        assert mid_state["completed"] == 1
        assert mid_state["tasks"]["namespace"]["status"] == "completed"

        for key in dispatched_keys:
            await _sync_project_integration_task(pid, key)

    final_state = client.get(f"/api/v1/projects/{pid}/_state").json()["sync_state"]
    assert final_state["status"] == "completed"
    assert final_state["completed"] == 6
    for key in ("namespace", *dispatched_keys):
        assert final_state["tasks"][key]["status"] == "completed"
        assert "configured" in (final_state["tasks"][key]["logs"] or "")
