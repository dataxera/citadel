# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from citadel.service.k8s_cluster.model import K8sCluster, K8sClusterType
from citadel.service.project.model import Project
from citadel.service.project_user.model import ProjectLocalUser
from citadel.service.ldap_config.model import LdapConfig
from citadel.fw.model import get_engine
from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.mark.asyncio
async def test_project_deploy_gateway(client):
    from citadel.service.project.actions import SyncProjectIntegrationsAction as DeployGatewayAction

    cluster = K8sCluster(
        name="test-cluster-gw",
        title="Test Cluster GW",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )

    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(cluster)
        await session.commit()
        await session.refresh(cluster)

        project = Project(
            name="test-proj-gw",
            title="Test Proj GW",
            k8s_cluster_id=cluster.id,
            k8s_namespace="test-proj-gw",
            ingress_domain="gw.test.local",
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)

        mock_svc = MagicMock()
        mock_svc.session = session
        mock_svc.request = MagicMock()

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.communicate = pytest.importorskip("unittest.mock").AsyncMock(
                return_value=(b"success", b"")
            )
            mock_exec.return_value = mock_proc

            action = DeployGatewayAction(project, mock_svc)
            action.session = session
            await action.run()

            # Verify kubectl was executed to apply gateway resources
            assert mock_exec.call_count >= 1
            calls = [call[0] for call in mock_exec.call_args_list]
            found_kubectl = False
            for call_args in calls:
                if "kubectl" in call_args and "apply" in call_args:
                    found_kubectl = True
            assert found_kubectl


def test_project_deploy_gateway_action_triggers_task(client: TestClient):
    # Create cluster and project with ingress_domain
    cluster_data = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "gw-cluster-test",
            "title": "GW Cluster Test",
            "type": "in-cluster",
        },
    ).json()["data"]

    project_data = client.post(
        "/api/v1/projects",
        json={
            "name": "gw-project-test",
            "title": "GW Project Test",
            "k8s_cluster_id": cluster_data["id"],
            "k8s_namespace": "gw-project-test",
            "ingress_domain": "gw-test.domain",
        },
    ).json()["data"]

    with patch(
        "citadel.tasks.project_tasks.sync_project_integrations_task.delay"
    ) as mock_delay:
        resp = client.post(
            f"/api/v1/projects/{project_data['id']}/_actions",
            json={"action": "sync_project_integrations"},
        )
        assert resp.status_code == 200
        assert (
            resp.json()["message"]
            == "Project integrations synchronization triggered."
        )
        mock_delay.assert_called_once_with(project_data["id"])


@pytest.mark.asyncio
async def test_project_deploy_gateway_with_nodeport(client):
    from citadel.service.project.actions import SyncProjectIntegrationsAction as DeployGatewayAction

    cluster = K8sCluster(
        name="test-cluster-gw-np",
        title="Test Cluster GW NP",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )

    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(cluster)
        await session.commit()
        await session.refresh(cluster)

        project = Project(
            name="test-proj-gw-np",
            title="Test Proj GW NP",
            k8s_cluster_id=cluster.id,
            k8s_namespace="test-proj-gw-np",
            ingress_domain="gw-np.test.local",
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)

        mock_svc = MagicMock()
        mock_svc.session = session
        mock_svc.request = MagicMock()

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.communicate = pytest.importorskip("unittest.mock").AsyncMock(
                return_value=(b"success", b"")
            )
            mock_exec.return_value = mock_proc

            action = DeployGatewayAction(project, mock_svc)
            action.session = session
            await action.run()

            # Verify that the generated manifest includes EnvoyProxy and references it in the Gateway
            assert mock_exec.call_count >= 1

            # Let's test the helper directly to be extremely clean and robust
            from citadel.service.project.actions import _render_gateway_manifests
            manifest = _render_gateway_manifests(project, "test-proj-gw-np")
            assert "EnvoyProxy" in manifest
            assert "project-envoy-proxy-config" in manifest
            assert "type: LoadBalancer" in manifest
            assert "externalTrafficPolicy: Cluster" in manifest
            assert "nodePort" not in manifest
            assert "NodePort" not in manifest
            assert "infrastructure:" in manifest
            assert "parametersRef:" in manifest
            assert "backendTLS:" in manifest
            assert "clientCertificateRef:" in manifest
            assert "name: envoy-test-proj-gw-np" in manifest


def test_download_haproxy_cert_view(client: TestClient):

    # Create cluster and project
    cluster_data = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "cert-cluster-test",
            "title": "Cert Cluster Test",
            "type": "in-cluster",
        },
    ).json()["data"]

    project_data = client.post(
        "/api/v1/projects",
        json={
            "name": "cert-project-test",
            "title": "Cert Project Test",
            "k8s_cluster_id": cluster_data["id"],
            "k8s_namespace": "cert-project-test",
            "ingress_domain": "cert-test.domain",
        },
    ).json()["data"]

    # Test secret not found (returns 404)
    with patch("kubernetes.config.load_incluster_config"), \
         patch("kubernetes.config.load_kube_config"), \
         patch("kubernetes.client.CoreV1Api.read_namespaced_secret", side_effect=Exception("Not found")):
        resp = client.get(f"/api/v1/projects/{project_data['id']}/_download-haproxy-cert")
        assert resp.status_code == 404

    # Test successful download
    import base64
    mock_secret = MagicMock()
    mock_secret.data = {
        "tls.crt": base64.b64encode(b"MOCK CERTIFICATE CONTENT").decode("utf-8"),
        "tls.key": base64.b64encode(b"MOCK PRIVATE KEY CONTENT").decode("utf-8"),
    }
    with patch("kubernetes.config.load_incluster_config"), \
         patch("kubernetes.config.load_kube_config"), \
         patch("kubernetes.client.CoreV1Api.read_namespaced_secret", return_value=mock_secret):
        resp = client.get(f"/api/v1/projects/{project_data['id']}/_download-haproxy-cert")
        assert resp.status_code == 200
        assert resp.headers["Content-Disposition"] == f"attachment; filename=envoy-{project_data['name']}.pem"
        assert b"MOCK CERTIFICATE CONTENT" in resp.content
        assert b"MOCK PRIVATE KEY CONTENT" in resp.content


@pytest.mark.asyncio
async def test_sync_project_integrations_excludes_dex(client):
    """Ensure Dex manifests (certificate, route, gateway listener, app) are not rendered or applied during project sync integration."""
    from citadel.service.project.actions import (
        SyncProjectIntegrationsAction,
        _render_gateway_manifests,
    )

    cluster = K8sCluster(
        name="test-cluster-no-dex",
        title="Test Cluster No Dex",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )

    engine = get_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(cluster)
        await session.commit()
        await session.refresh(cluster)

        project = Project(
            name="test-proj-no-dex",
            title="Test Proj No Dex",
            k8s_cluster_id=cluster.id,
            k8s_namespace="test-proj-no-dex",
            ingress_domain="no-dex.test.local",
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)

        manifest = _render_gateway_manifests(project, "test-proj-no-dex")
        assert "dex-tls" not in manifest
        assert "dex-route" not in manifest
        assert "dex.no-dex.test.local" not in manifest
        assert "test-proj-no-dex-dex" not in manifest
        assert "wildcard-https" in manifest
        assert "envoy-test-proj-no-dex" in manifest

        mock_svc = MagicMock()
        mock_svc.session = session
        mock_svc.request = MagicMock()

        applied_manifests = []

        async def _capture_apply(target_cluster, rendered_manifest):
            applied_manifests.append(rendered_manifest)

        with patch(
            "citadel.service.project.actions.apply_manifest_to_cluster",
            side_effect=_capture_apply,
        ):
            action = SyncProjectIntegrationsAction(project, mock_svc)
            action.session = session
            await action.run()

        combined = "\n---\n".join(applied_manifests)
        assert "dex-tls" not in combined
        assert "dex-route" not in combined
        assert "dex.no-dex.test.local" not in combined
        assert "test-proj-no-dex-dex" not in combined
        assert "wildcard-https" in combined
        assert "envoy-test-proj-no-dex" in combined



