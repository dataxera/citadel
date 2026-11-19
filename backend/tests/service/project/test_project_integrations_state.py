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
