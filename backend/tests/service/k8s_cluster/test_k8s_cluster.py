# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import pytest
from unittest.mock import MagicMock, patch, call
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from citadel.service.k8s_cluster.model import (
    K8sClusterStatus,
    K8sClusterType,
    K8sCluster,
)
from citadel.config import settings


@pytest.fixture
def mock_k8s():
    with patch(
        "citadel.service.k8s_cluster.service.config.load_incluster_config"
    ), patch(
        "citadel.service.k8s_cluster.service.client.CoreV1Api"
    ) as mock_core, patch(
        "citadel.service.k8s_cluster.service.client.VersionApi"
    ) as mock_version:

        # Mock Version
        mock_v = MagicMock()
        mock_v.git_version = "v1.27.0"
        mock_version.return_value.get_code.return_value = mock_v

        # Mock Nodes
        mock_node = MagicMock()
        mock_node.metadata.name = "node-1"
        mock_node.metadata.creation_timestamp = None
        mock_node.metadata.labels = {}
        mock_node.status.node_info.kubelet_version = "v1.27.0"
        mock_node.status.conditions = [MagicMock(type="Ready", status="True")]
        mock_node.status.capacity = {"cpu": "2", "memory": "4Gi"}

        mock_nodes_list = MagicMock()
        mock_nodes_list.items = [mock_node]
        mock_core.return_value.list_node.return_value = mock_nodes_list

        # Mock Services (ArgoCD)
        mock_svc = MagicMock()
        mock_svc.metadata.name = "argocd-server"
        mock_svc_list = MagicMock()
        mock_svc_list.items = [mock_svc]
        mock_core.return_value.list_service_for_all_namespaces.return_value = (
            mock_svc_list
        )

        # Mock Pods (ArgoCD version)
        mock_pod_argo = MagicMock()
        mock_pod_argo.metadata.labels = {"app.kubernetes.io/version": "v2.8.0"}
        mock_pod_argo.spec.containers = [MagicMock(image="argoproj/argocd:v2.8.0")]

        # Mock Pods (Cert Manager version)
        mock_pod_cm = MagicMock()
        mock_pod_cm.metadata.labels = {"app.kubernetes.io/version": "v1.20.0"}
        mock_pod_cm.spec.containers = [MagicMock(image="cert-manager:v1.20.0")]

        # Mock Pods (CNPG version - NO LABEL FALLBACK)
        mock_pod_cnpg = MagicMock()
        mock_pod_cnpg.metadata.labels = {}
        mock_pod_cnpg.spec.containers = [
            MagicMock(image="ghcr.io/cloudnative-pg/cloudnative-pg:1.28.1")
        ]

        # Mock Pods (Envoy Gateway version)
        mock_pod_eg = MagicMock()
        mock_pod_eg.metadata.labels = {"app.kubernetes.io/version": "v1.0.0"}
        mock_pod_eg.spec.containers = [MagicMock(image="envoyproxy/gateway:v1.0.0")]

        # Mock Pods (Kafka Operator version)
        mock_pod_kafka = MagicMock()
        mock_pod_kafka.metadata.labels = {"app.kubernetes.io/version": "v0.50.1"}
        mock_pod_kafka.spec.containers = [MagicMock(image="strimzi/operator:v0.50.1")]

        # Mock Pods (NiFiKop Operator version)
        mock_pod_nifikop = MagicMock()
        mock_pod_nifikop.metadata.labels = {"app.kubernetes.io/version": "v1.17.0"}
        mock_pod_nifikop.spec.containers = [MagicMock(image="konpyutaika/nifikop:v1.17.0")]

        # Mock Pods (Doris Operator version)
        mock_pod_doris = MagicMock()
        mock_pod_doris.metadata.labels = {"app.kubernetes.io/version": "v25.8.0"}
        mock_pod_doris.spec.containers = [MagicMock(image="doris-operator:v25.8.0")]

        # Mock Pods (kube-prometheus-stack version)
        mock_pod_prom = MagicMock()
        mock_pod_prom.metadata.labels = {"app.kubernetes.io/version": "v3.16.0-distroless"}
        mock_pod_prom.spec.containers = [MagicMock(image="quay.io/prometheus/prometheus:v3.16.0-distroless")]

        def _mock_list_pod_for_all_namespaces(label_selector=None):
            m_list = MagicMock()
            if not label_selector:
                m_list.items = []
            elif "argocd-server" in label_selector:
                m_list.items = [mock_pod_argo]
            elif "cert-manager" in label_selector:
                m_list.items = [mock_pod_cm]
            elif "cloudnative-pg" in label_selector:
                m_list.items = [mock_pod_cnpg]
            elif "envoy-gateway" in label_selector:
                m_list.items = [mock_pod_eg]
            elif "strimzi-kafka-operator" in label_selector or "kafka-operator" in label_selector or "name=strimzi-cluster-operator" in label_selector or "strimzi.io/kind=cluster-operator" in label_selector:
                m_list.items = [mock_pod_kafka]
            elif "nifikop" in label_selector:
                m_list.items = [mock_pod_nifikop]
            elif "doris-operator" in label_selector:
                m_list.items = [mock_pod_doris]
            elif "prometheus" in label_selector:
                m_list.items = [mock_pod_prom]
            else:
                m_list.items = []
            return m_list

        mock_core.return_value.list_pod_for_all_namespaces.side_effect = (
            _mock_list_pod_for_all_namespaces
        )

        # Mock Secrets (Helm Release)
        mock_secret_argo = MagicMock()
        mock_secret_argo.metadata.name = "sh.helm.release.v1.argocd.v1"
        mock_secret_cm = MagicMock()
        mock_secret_cm.metadata.name = "sh.helm.release.v1.cert-manager.v1"
        mock_secret_cnpg = MagicMock()
        mock_secret_cnpg.metadata.name = "sh.helm.release.v1.cnpg.v1"
        mock_secret_eg = MagicMock()
        mock_secret_eg.metadata.name = "sh.helm.release.v1.eg.v1"
        mock_secret_kafka = MagicMock()
        mock_secret_kafka.metadata.name = "sh.helm.release.v1.strimzi-kafka-operator.v1"
        mock_secret_nifikop = MagicMock()
        mock_secret_nifikop.metadata.name = "sh.helm.release.v1.nifikop.v1"
        mock_secret_doris = MagicMock()
        mock_secret_doris.metadata.name = "sh.helm.release.v1.doris-operator.v1"
        mock_secret_prom = MagicMock()
        mock_secret_prom.metadata.name = "sh.helm.release.v1.kube-prometheus-stack.v1"

        mock_secret_list = MagicMock()
        mock_secret_list.items = [
            mock_secret_argo,
            mock_secret_cm,
            mock_secret_cnpg,
            mock_secret_eg,
            mock_secret_nifikop,
            mock_secret_doris,
            mock_secret_prom,
        ]
        mock_core.return_value.list_secret_for_all_namespaces.return_value = (
            mock_secret_list
        )

        yield {"core": mock_core, "version": mock_version}


@pytest.fixture(autouse=True)
def mock_get_kubernetes_clients():
    with patch(
        "citadel.service.k8s_cluster.actions.InstallArgoCDAction._get_kubernetes_clients"
    ) as mock_clients:
        mock_core = MagicMock()
        mock_ext = MagicMock()
        mock_clients.return_value = (mock_core, mock_ext)
        yield mock_clients


def test_poll_k8s_cluster_status(client: TestClient, mock_k8s):
    # Create cluster
    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "poll-test",
            "title": "Poll Test",
            "type": "in-cluster",
        },
    ).json()["data"]

    # Trigger refresh
    resp = client.post(f"/api/v1/k8s_clusters/{p1['id']}/_refresh")
    assert resp.status_code == 200

    # Check state
    resp_state = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state")
    assert resp_state.status_code == 200
    data = resp_state.json()

    assert data["status"] == "online"
    assert data["k8s_version"] == "v1.27.0"
    assert data["node_count"] == 1
    assert data["cpu_total"] == 2.0
    assert data["ram_total"] == 4.0
    assert data["argocd_installed"] is True
    assert data["argocd_version"] == "v2.8.0"
    assert data["cert_manager_installed"] is True
    assert data["cert_manager_version"] == "v1.20.0"
    assert data["cnpg_installed"] is True
    assert data["cnpg_version"] == "1.28.1"
    assert data["envoy_gateway_installed"] is True
    assert data["envoy_gateway_version"] == "v1.0.0"
    assert data["kafka_operator_installed"] is True
    assert data["kafka_operator_version"] == "v0.50.1"
    assert data["nifikop_installed"] is True
    assert data["nifikop_version"] == "v1.17.0"
    assert data["kube_prometheus_stack_installed"] is True
    assert data["kube_prometheus_stack_version"] == "v3.16.0-distroless"


def test_poll_k8s_cluster_unreachable_cascades_to_services(client: TestClient, test_project):
    """Test that when a cluster is unreachable, cluster state and its active platform services are marked error."""
    cluster_id = test_project["k8s_cluster_id"]
    project_id = test_project["id"]

    # Create an active platform service under this project
    resp_plat = client.post(
        "/api/v1/platform/pgsql",
        json={
            "name": "test-pg-cascade",
            "title": "Test PG Cascade",
            "project_id": project_id,
            "instances": 1,
            "storage_size": "1Gi",
        },
        headers={"X-Project-Id": str(project_id)},
    )
    assert resp_plat.status_code == 200, resp_plat.json()
    platform_id = resp_plat.json()["data"]["id"]

    valid_kubeconfig = (
        "apiVersion: v1\n"
        "clusters:\n"
        "- cluster:\n"
        "    server: https://127.0.0.1:6443\n"
        "  name: default-cluster\n"
        "contexts:\n"
        "- context:\n"
        "    cluster: default-cluster\n"
        "    user: default-user\n"
        "  name: default-context\n"
        "current-context: default-context\n"
        "kind: Config\n"
        "preferences: {}\n"
        "users:\n"
        "- name: default-user\n"
        "  user:\n"
        "    token: fake-token\n"
    )
    client.put(
        f"/api/v1/k8s_clusters/{cluster_id}",
        json={"kubeconfig": valid_kubeconfig},
    )

    # Set initial state to active online with deploy and poll_status mocked
    with patch("citadel.platform_service.base.PlatformService.deploy", return_value=None), \
         patch("citadel.platform_service.base.PlatformService.poll_status", return_value=None):
        resp_init = client.post(
            f"/api/v1/platform/pgsql/{platform_id}/_state",
            json={"status": "online", "active": True, "message": "Cluster is running"},
            headers={"X-Project-Id": str(project_id)},
        )
        assert resp_init.status_code == 200
        assert resp_init.json()["status"] == "online"

    # Mock unreachable Kubernetes cluster
    with patch("kubernetes.client.VersionApi") as mock_ver, \
         patch("kubernetes.client.CoreV1Api") as mock_core:
        mock_ver.return_value.get_code.side_effect = Exception("Connection refused: cluster is down")

        # Trigger refresh on cluster
        resp = client.post(f"/api/v1/k8s_clusters/{cluster_id}/_refresh")
        assert resp.status_code == 200

    # Verify cluster state is error with unreachable message and cleared node count
    resp_state = client.get(f"/api/v1/k8s_clusters/{cluster_id}/_state")
    assert resp_state.status_code == 200
    cluster_state = resp_state.json()
    assert cluster_state["status"] == "error"
    assert "unreachable" in cluster_state["message"].lower()
    assert cluster_state["node_count"] == 0

    # Verify platform service state was cascaded to error with unreachable message
    resp_pstate2 = client.get(
        f"/api/v1/platform/pgsql/{platform_id}/_state",
        headers={"X-Project-Id": str(project_id)},
    )
    assert resp_pstate2.status_code == 200
    pstate2 = resp_pstate2.json()
    assert pstate2["status"] == "error"
    assert "unreachable" in pstate2["message"].lower()


@pytest.mark.asyncio
async def test_install_argocd():
    from citadel.service.k8s_cluster.service import K8sClusterService

    cluster = K8sCluster(
        name="test-cluster-argo",
        title="Test Cluster Argo",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )

    mock_svc = MagicMock()
    mock_svc.kubeconfig = pytest.importorskip("unittest.mock").AsyncMock(
        return_value="fake-kubeconfig"
    )

    from citadel.service.k8s_cluster.actions import InstallArgoCDAction

    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = pytest.importorskip("unittest.mock").AsyncMock(
            return_value=(b"success", b"")
        )
        mock_exec.return_value = mock_proc

        action = InstallArgoCDAction(cluster, mock_svc)
        await action.run()

        # Verify helm repo add
        # Verify helm upgrade --install
        assert mock_exec.call_count >= 3  # add, update, upgrade

        calls = [call[0] for call in mock_exec.call_args_list]
        found_upgrade = False
        for call_args in calls:
            if "upgrade" in call_args and "--install" in call_args:
                found_upgrade = True
                assert "argo/argo-cd" in call_args
                assert "--kubeconfig" in call_args

        assert found_upgrade


@pytest.mark.asyncio
async def test_install_cert_manager():
    from citadel.service.k8s_cluster.model import K8sCluster, K8sClusterType
    import os

    cluster = K8sCluster(
        name="test-cluster-cm",
        title="Test Cluster CM",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )

    mock_svc = MagicMock()
    mock_svc.kubeconfig = pytest.importorskip("unittest.mock").AsyncMock(
        return_value="fake-kubeconfig"
    )

    from citadel.service.k8s_cluster.actions import InstallCertManagerAction

    applied_manifests = []

    def mock_subprocess(*args, **kwargs):
        cmd = args
        if len(cmd) > 0 and "kubectl" in cmd:
            path = cmd[-1]
            if os.path.exists(path):
                with open(path, "r") as f:
                    applied_manifests.append(f.read())
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = pytest.importorskip("unittest.mock").AsyncMock(
            return_value=(b"success", b"")
        )
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess) as mock_exec:
        action = InstallCertManagerAction(cluster, mock_svc)
        await action.run()

        assert len(applied_manifests) == 1
        manifest = applied_manifests[0]
        assert "kind: Application" in manifest
        assert "name: cert-manager" in manifest
        assert "repoURL: https://charts.jetstack.io" in manifest
        assert "chart: cert-manager" in manifest
        assert "targetRevision: v1.20.0" in manifest
        assert "installCRDs: true" in manifest


@pytest.mark.asyncio
async def test_install_cnpg():
    from citadel.service.k8s_cluster.model import K8sCluster, K8sClusterType
    import os

    cluster = K8sCluster(
        name="test-cluster-cnpg",
        title="Test Cluster CNPG",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )

    mock_svc = MagicMock()
    mock_svc.kubeconfig = pytest.importorskip("unittest.mock").AsyncMock(
        return_value="fake-kubeconfig"
    )

    from citadel.service.k8s_cluster.actions import InstallCNPGAction

    applied_manifests = []

    def mock_subprocess(*args, **kwargs):
        cmd = args
        if len(cmd) > 0 and "kubectl" in cmd:
            path = cmd[-1]
            if os.path.exists(path):
                with open(path, "r") as f:
                    applied_manifests.append(f.read())
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = pytest.importorskip("unittest.mock").AsyncMock(
            return_value=(b"success", b"")
        )
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess) as mock_exec:
        action = InstallCNPGAction(cluster, mock_svc)
        await action.run()

        assert len(applied_manifests) == 1
        manifest = applied_manifests[0]
        assert "kind: Application" in manifest
        assert "name: cnpg" in manifest
        assert "repoURL: https://cloudnative-pg.github.io/charts" in manifest
        assert "chart: cloudnative-pg" in manifest
        assert "targetRevision: 0.27.1" in manifest


def test_poll_k8s_cluster_error(client: TestClient):

    with patch(
        "citadel.service.k8s_cluster.service.config.load_incluster_config",
        side_effect=Exception("K8S Error"),
    ):
        # Create cluster
        p1 = client.post(
            "/api/v1/k8s_clusters",
            json={
                "name": "error-test",
                "title": "Error Test",
                "type": "in-cluster",
            },
        ).json()["data"]

        # Trigger refresh
        client.post(f"/api/v1/k8s_clusters/{p1['id']}/_refresh")

        # Check state
        resp_state = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state")
        data = resp_state.json()
        assert data["status"] == "error"
        assert data["message"] == "Cluster is unreachable: K8S Error"


def test_install_argocd_action_triggers_task(client: TestClient):
    # Create cluster
    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "task-test",
            "title": "Task Test",
            "type": "in-cluster",
        },
    ).json()["data"]

    with patch(
        "citadel.tasks.k8s_cluster_status.install_argocd_task.delay"
    ) as mock_delay:
        resp = client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "install_argocd"},
        )
        assert resp.status_code == 200
        assert (
            resp.json()["message"]
            == "ArgoCD installation triggered and status being refreshed."
        )
        mock_delay.assert_called_once_with(p1["id"])

        # Verify status updated immediately in DB
        resp_state = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state")
        assert resp_state.json()["argocd_installed"] is True


@pytest.mark.asyncio
async def test_install_envoy_gateway():
    from citadel.service.k8s_cluster.model import K8sCluster, K8sClusterType
    import os

    cluster = K8sCluster(
        name="test-cluster-eg",
        title="Test Cluster EG",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )

    mock_svc = MagicMock()
    mock_svc.kubeconfig = pytest.importorskip("unittest.mock").AsyncMock(
        return_value="fake-kubeconfig"
    )

    from citadel.service.k8s_cluster.actions import InstallEnvoyGatewayAction

    applied_manifests = []

    def mock_subprocess(*args, **kwargs):
        cmd = args
        if len(cmd) > 0 and "kubectl" in cmd:
            path = cmd[-1]
            if os.path.exists(path):
                with open(path, "r") as f:
                    applied_manifests.append(f.read())
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = pytest.importorskip("unittest.mock").AsyncMock(
            return_value=(b"success", b"")
        )
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess) as mock_exec:
        action = InstallEnvoyGatewayAction(cluster, mock_svc)
        await action.run()

        # Verify that kubectl apply applied the Envoy Gateway Application and the global GatewayClass/EnvoyProxy config
        assert len(applied_manifests) == 2

        # Manifest 1: ArgoCD Application
        app_manifest = applied_manifests[0]
        assert "kind: Application" in app_manifest
        assert "name: envoy-gateway" in app_manifest
        assert "repoURL: docker.io/envoyproxy" in app_manifest
        assert "chart: gateway-helm" in app_manifest
        assert "targetRevision: 1.8.1" in app_manifest

        # Manifest 2: Envoy Gateway configuration
        config_manifest = applied_manifests[1]
        assert "kind: GatewayClass" in config_manifest
        assert "kind: EnvoyProxy" in config_manifest


def test_install_envoy_gateway_action_triggers_task(client: TestClient):
    # Create cluster
    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "task-test-eg",
            "title": "Task Test EG",
            "type": "in-cluster",
        },
    ).json()["data"]

    with patch(
        "citadel.tasks.k8s_cluster_status.install_envoy_gateway_task.delay"
    ) as mock_delay:
        resp = client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "install_envoy_gateway"},
        )
        assert resp.status_code == 200
        assert (
            resp.json()["message"]
            == "Envoy Gateway installation triggered and status being refreshed."
        )
        mock_delay.assert_called_once_with(p1["id"])

        # Verify status updated immediately in DB
        resp_state = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state")
        assert resp_state.json()["envoy_gateway_installed"] is True


def test_sync_core_integrations_action_triggers_task(client: TestClient):
    # Create cluster
    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "task-test-sync",
            "title": "Task Test Sync",
            "type": "in-cluster",
        },
    ).json()["data"]

    with patch(
        "citadel.tasks.k8s_cluster_status.sync_core_integrations_task.delay"
    ) as mock_delay:
        resp = client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "sync_core_integrations"},
        )
        assert resp.status_code == 200
        assert (
            resp.json()["message"]
            == "Core integrations synchronization triggered."
        )
        mock_delay.assert_called_once_with(p1["id"])


@pytest.mark.asyncio
async def test_install_envoy_gateway_with_loadbalancer():
    from citadel.service.k8s_cluster.model import K8sCluster, K8sClusterType
    import os

    cluster = K8sCluster(
        name="test-cluster-eg-lb",
        title="Test Cluster EG LB",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )

    mock_svc = MagicMock()
    mock_svc.kubeconfig = pytest.importorskip("unittest.mock").AsyncMock(
        return_value="fake-kubeconfig"
    )

    from citadel.service.k8s_cluster.actions import InstallEnvoyGatewayAction

    applied_manifests = []

    def mock_subprocess(*args, **kwargs):
        cmd = args
        if len(cmd) > 0 and "kubectl" in cmd:
            path = cmd[-1]
            if os.path.exists(path):
                with open(path, "r") as f:
                    applied_manifests.append(f.read())
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = pytest.importorskip("unittest.mock").AsyncMock(
            return_value=(b"success", b"")
        )
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess) as mock_exec:
        action = InstallEnvoyGatewayAction(cluster, mock_svc)
        await action.run()

        # Verify that kubectl apply applied both the Application and EnvoyProxy LoadBalancer type
        assert len(applied_manifests) == 2
        config_manifest = applied_manifests[1]
        assert "type: LoadBalancer" in config_manifest


@pytest.mark.asyncio
async def test_install_kafka_operator():
    from citadel.service.k8s_cluster.model import K8sCluster, K8sClusterType
    import os

    cluster = K8sCluster(
        name="test-cluster-kafka-op",
        title="Test Cluster Kafka Op",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )

    mock_svc = MagicMock()
    mock_svc.kubeconfig = pytest.importorskip("unittest.mock").AsyncMock(
        return_value="fake-kubeconfig"
    )

    from citadel.service.k8s_cluster.actions import InstallKafkaOperatorAction

    applied_manifests = []

    def mock_subprocess(*args, **kwargs):
        cmd = args
        if len(cmd) > 0 and "kubectl" in cmd:
            path = cmd[-1]
            if os.path.exists(path):
                with open(path, "r") as f:
                    applied_manifests.append(f.read())
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = pytest.importorskip("unittest.mock").AsyncMock(
            return_value=(b"success", b"")
        )
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess) as mock_exec:
        action = InstallKafkaOperatorAction(cluster, mock_svc)
        await action.run()

        assert len(applied_manifests) == 1
        manifest = applied_manifests[0]
        assert "kind: Application" in manifest
        assert "name: kafka-operator" in manifest
        assert "repoURL: https://strimzi.io/charts/" in manifest
        assert "chart: strimzi-kafka-operator" in manifest
        assert "targetRevision: 0.50.1" in manifest


@pytest.mark.asyncio
async def test_install_nifikop():
    from citadel.service.k8s_cluster.model import K8sCluster, K8sClusterType
    import os

    cluster = K8sCluster(
        name="test-cluster-nifikop-op",
        title="Test Cluster NiFiKop Op",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )

    mock_svc = MagicMock()
    mock_svc.kubeconfig = pytest.importorskip("unittest.mock").AsyncMock(
        return_value="fake-kubeconfig"
    )

    from citadel.service.k8s_cluster.actions import InstallNifikopAction

    applied_manifests = []

    def mock_subprocess(*args, **kwargs):
        cmd = args
        if len(cmd) > 0 and "kubectl" in cmd:
            path = cmd[-1]
            if os.path.exists(path):
                with open(path, "r") as f:
                    applied_manifests.append(f.read())
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = pytest.importorskip("unittest.mock").AsyncMock(
            return_value=(b"success", b"")
        )
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess) as mock_exec:
        action = InstallNifikopAction(cluster, mock_svc)
        await action.run()

        assert len(applied_manifests) == 1
        manifest = applied_manifests[0]
        assert "kind: Application" in manifest
        assert "name: nifikop-operator" in manifest
        assert "repoURL: ghcr.io/konpyutaika/helm-charts" in manifest
        assert "chart: nifikop" in manifest
        assert "targetRevision: 1.17.0" in manifest
        assert "namespaces:\n          - \"\"" in manifest
        assert "ignoreDifferences:" in manifest
        assert "/status/terminatingReplicas" in manifest
        assert "kind: ClusterRole" in manifest
        assert "name: nifikop-cluster-role" in manifest
        assert "kind: ClusterRoleBinding" in manifest
        assert "name: nifikop-cluster-role-binding" in manifest
        assert "nifi.konpyutaika.com" in manifest


def test_install_nifikop_action_triggers_task(client: TestClient):
    # Create cluster
    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "task-test-nifikop",
            "title": "Task Test NiFiKop",
            "type": "in-cluster",
        },
    ).json()["data"]

    with patch(
        "citadel.tasks.k8s_cluster_status.install_nifikop_task.delay"
    ) as mock_delay:
        resp = client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "install_nifikop"},
        )
        assert resp.status_code == 200
        assert (
            resp.json()["message"]
            == "NiFiKop Operator installation triggered and status being refreshed."
        )
        mock_delay.assert_called_once_with(p1["id"])

        # Verify status updated immediately in DB
        resp_state = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state")
        assert resp_state.json()["nifikop_installed"] is True


@pytest.mark.asyncio
async def test_install_doris_operator():
    from citadel.service.k8s_cluster.model import K8sCluster, K8sClusterType
    import os

    cluster = K8sCluster(
        name="test-cluster-doris-op",
        title="Test Cluster Doris Op",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )

    mock_svc = MagicMock()
    mock_svc.kubeconfig = pytest.importorskip("unittest.mock").AsyncMock(
        return_value="fake-kubeconfig"
    )

    from citadel.service.k8s_cluster.actions import InstallDorisOperatorAction

    applied_manifests = []

    def mock_subprocess(*args, **kwargs):
        cmd = args
        if len(cmd) > 0 and "kubectl" in cmd:
            path = cmd[-1]
            if os.path.exists(path):
                with open(path, "r") as f:
                    applied_manifests.append(f.read())
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = pytest.importorskip("unittest.mock").AsyncMock(
            return_value=(b"success", b"")
        )
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess) as mock_exec:
        action = InstallDorisOperatorAction(cluster, mock_svc)
        await action.run()

        assert len(applied_manifests) == 1
        manifest = applied_manifests[0]
        assert "kind: Application" in manifest
        assert "name: doris-operator" in manifest
        assert "repoURL: https://charts.selectdb.com" in manifest
        assert "chart: doris-operator" in manifest
        assert "targetRevision: 25.8.0" in manifest


def test_install_doris_operator_action_triggers_task(client: TestClient):
    # Create cluster
    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "task-test-doris",
            "title": "Task Test Doris",
            "type": "in-cluster",
        },
    ).json()["data"]

    with patch(
        "citadel.tasks.k8s_cluster_status.install_doris_operator_task.delay"
    ) as mock_delay:
        resp = client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "install_doris_operator"},
        )
        assert resp.status_code == 200
        assert (
            resp.json()["message"]
            == "Doris Operator installation triggered and status being refreshed."
        )
        mock_delay.assert_called_once_with(p1["id"])

        # Verify status updated immediately in DB
        resp_state = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state")
        assert resp_state.json()["doris_operator_installed"] is True


@pytest.mark.asyncio
async def test_install_doris_operator_locks_image(test_stack):
    """Verify InstallDorisOperatorAction renders dorisOperator image repository and tag from test_stack."""
    from unittest.mock import AsyncMock
    from citadel.service.k8s_cluster.model import K8sCluster, K8sClusterType
    from citadel.service.k8s_cluster.actions import InstallDorisOperatorAction
    import os

    cluster = K8sCluster(
        name="test-cluster-doris",
        title="Test Cluster Doris",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )

    mock_svc = MagicMock()
    mock_svc.kubeconfig = AsyncMock(return_value="fake-kubeconfig")

    applied_manifests = []

    def mock_subprocess(*args, **kwargs):
        cmd = args
        if len(cmd) > 0 and "kubectl" in cmd:
            path = cmd[-1]
            if os.path.exists(path):
                with open(path, "r") as f:
                    applied_manifests.append(f.read())
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"success", b""))
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
        action = InstallDorisOperatorAction(cluster, mock_svc)
        action._resolve_stack = AsyncMock(return_value=test_stack)
        await action.run()

    assert len(applied_manifests) == 1
    manifest = applied_manifests[0]
    assert "repository: test.registry/apache/doris" in manifest
    assert 'tag: "operator-26.99.1"' in manifest


@pytest.mark.asyncio
async def test_install_cert_manager_locks_images(test_stack):
    """Verify InstallCertManagerAction renders image tags and repos from test_stack."""
    from unittest.mock import AsyncMock
    from citadel.service.k8s_cluster.model import K8sCluster, K8sClusterType
    from citadel.service.k8s_cluster.actions import InstallCertManagerAction
    import os

    cluster = K8sCluster(
        name="test-cluster-cm-tags",
        title="Test Cluster CM Tags",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )

    mock_svc = MagicMock()
    mock_svc.kubeconfig = AsyncMock(return_value="fake-kubeconfig")

    applied_manifests = []

    def mock_subprocess(*args, **kwargs):
        cmd = args
        if len(cmd) > 0 and "kubectl" in cmd:
            path = cmd[-1]
            if os.path.exists(path):
                with open(path, "r") as f:
                    applied_manifests.append(f.read())
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"success", b""))
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
        action = InstallCertManagerAction(cluster, mock_svc)
        action._resolve_stack = AsyncMock(return_value=test_stack)
        await action.run()

    assert len(applied_manifests) == 1
    manifest = applied_manifests[0]
    assert 'tag: "v1.99.0"' in manifest
    assert "repository: test.registry/jetstack/cert-manager-controller" in manifest
    assert "cainjector:" in manifest
    assert "repository: test.registry/jetstack/cert-manager-cainjector" in manifest
    assert "webhook:" in manifest
    assert "repository: test.registry/jetstack/cert-manager-webhook" in manifest


@pytest.mark.asyncio
async def test_install_argocd_locks_images_and_chart(test_stack):
    """Verify InstallArgoCDAction passes stack chart version and image overrides from test_stack."""
    from unittest.mock import AsyncMock
    from citadel.service.k8s_cluster.model import K8sCluster, K8sClusterType
    from citadel.service.k8s_cluster.actions import InstallArgoCDAction

    cluster = K8sCluster(
        name="test-cluster-argo",
        title="Test Cluster Argo",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )
    mock_svc = MagicMock()
    action = InstallArgoCDAction(cluster, mock_svc)
    action._resolve_stack = AsyncMock(return_value=test_stack)
    action._install_helm_chart = AsyncMock()
    action._apply_template = AsyncMock()

    await action.run()
    action._apply_template.assert_called_once_with("argocd-lb.yml.j2", namespace="argocd")

    action._install_helm_chart.assert_awaited_once()
    kwargs = action._install_helm_chart.call_args.kwargs
    assert kwargs["version"] == "9.99.4"
    set_vals = kwargs["set_vals"]
    assert set_vals["global.image.repository"] == "test.registry/argoproj/argocd"
    assert set_vals["global.image.tag"] == "v2.99.2"
    assert set_vals["dex.image.repository"] == "test.registry/dexidp/dex"
    assert set_vals["dex.image.tag"] == "v2.99.1"
    assert set_vals["redis.image.repository"] == "test.registry/library/redis"
    assert set_vals["redis.image.tag"] == "7.99.2-alpine"


@pytest.mark.asyncio
async def test_install_other_integrations_lock_images(test_stack):
    """Verify CNPG, Envoy Gateway, Kafka Operator, and NiFiKop render images from test_stack."""
    from unittest.mock import AsyncMock
    from citadel.service.k8s_cluster.model import K8sCluster, K8sClusterType
    from citadel.service.k8s_cluster.actions import (
        InstallCNPGAction,
        InstallEnvoyGatewayAction,
        InstallKafkaOperatorAction,
        InstallNifikopAction,
    )
    import os

    cluster = K8sCluster(
        name="test-cluster-integrations",
        title="Test Cluster Integrations",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )
    mock_svc = MagicMock()
    mock_svc.kubeconfig = AsyncMock(return_value="fake-kubeconfig")

    applied_manifests = []

    def mock_subprocess(*args, **kwargs):
        cmd = args
        if len(cmd) > 0 and "kubectl" in cmd:
            path = cmd[-1]
            if os.path.exists(path):
                with open(path, "r") as f:
                    applied_manifests.append(f.read())
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"success", b""))
        return mock_proc

    with patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
        cnpg_action = InstallCNPGAction(cluster, mock_svc)
        cnpg_action._resolve_stack = AsyncMock(return_value=test_stack)
        await cnpg_action.run()

        envoy_action = InstallEnvoyGatewayAction(cluster, mock_svc)
        envoy_action._resolve_stack = AsyncMock(return_value=test_stack)
        envoy_action._wait_for_crd_and_namespace = AsyncMock()
        await envoy_action.run()

        kafka_action = InstallKafkaOperatorAction(cluster, mock_svc)
        kafka_action._resolve_stack = AsyncMock(return_value=test_stack)
        await kafka_action.run()

        nifikop_action = InstallNifikopAction(cluster, mock_svc)
        nifikop_action._resolve_stack = AsyncMock(return_value=test_stack)
        await nifikop_action.run()

    assert len(applied_manifests) == 5
    cnpg_manifest, eg_manifest, eg_cfg_manifest, kafka_manifest, nifikop_manifest = applied_manifests

    assert "repository: test.registry/cloudnative-pg/cloudnative-pg" in cnpg_manifest
    assert 'tag: "1.99.1"' in cnpg_manifest

    assert "repository: test.registry/envoyproxy/gateway" in eg_manifest
    assert 'tag: "v1.99.1"' in eg_manifest
    assert "image: test.registry/envoyproxy/envoy:distroless-v1.99.1" in eg_cfg_manifest

    assert "registry: test.registry" in kafka_manifest
    assert "repository: strimzi" in kafka_manifest
    assert "name: operator" in kafka_manifest
    assert 'tag: "0.99.1"' in kafka_manifest

    assert "repository: test.registry/konpyutaika/nifikop" in nifikop_manifest
    assert 'tag: "v1.99.0-test"' in nifikop_manifest


def test_sync_core_integrations_initializes_sync_state(client: TestClient):
    """Triggering sync_core_integrations should persist initial sync_state in DB so progress survives refresh."""
    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "sync-state-init",
            "title": "Sync State Init",
            "type": "in-cluster",
        },
    ).json()["data"]

    with patch(
        "citadel.tasks.k8s_cluster_status.sync_core_integrations_task.delay"
    ) as mock_delay:
        resp = client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "sync_core_integrations"},
        )
        assert resp.status_code == 200
        mock_delay.assert_called_once_with(p1["id"])

    resp_state = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state")
    assert resp_state.status_code == 200
    sync_state = resp_state.json().get("sync_state")
    assert sync_state is not None
    assert sync_state["status"] == "in_progress"
    assert sync_state["total"] == 8
    assert sync_state["completed"] == 0
    for key in [
        "argocd",
        "cert_manager",
        "cnpg",
        "envoy_gateway",
        "kafka_operator",
        "nifikop",
        "doris_operator",
        "kube_prometheus_stack",
    ]:
        assert key in sync_state["tasks"]
        assert sync_state["tasks"][key]["status"] == "pending"


@pytest.mark.asyncio
async def test_sync_core_integrations_orchestration_dispatches_tasks(client: TestClient):
    """_sync_core_integrations_task runs ArgoCD first then dispatches individual integration tasks."""
    from unittest.mock import AsyncMock
    from citadel.tasks.k8s_cluster_status import _sync_core_integrations_task

    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "sync-orch-test",
            "title": "Sync Orch Test",
            "type": "in-cluster",
        },
    ).json()["data"]

    with patch(
        "citadel.tasks.k8s_cluster_status.sync_core_integrations_task.delay"
    ):
        client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "sync_core_integrations"},
        )

    with patch(
        "citadel.service.k8s_cluster.actions.InstallArgoCDAction.run",
        new_callable=AsyncMock,
    ) as mock_argo_run, patch(
        "citadel.tasks.k8s_cluster_status.sync_core_integration_task.delay"
    ) as mock_sub_delay:
        await _sync_core_integrations_task(p1["id"])

        mock_argo_run.assert_awaited_once()
        expected_keys = [
            "cert_manager",
            "cnpg",
            "envoy_gateway",
            "kafka_operator",
            "nifikop",
            "doris_operator",
            "kube_prometheus_stack",
        ]
        assert mock_sub_delay.call_count == len(expected_keys)
        called_keys = [c.args[1] for c in mock_sub_delay.call_args_list]
        assert called_keys == expected_keys

    resp_state = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state")
    sync_state = resp_state.json()["sync_state"]
    assert sync_state["tasks"]["argocd"]["status"] == "completed"
    assert sync_state["completed"] == 1
    assert sync_state["status"] == "in_progress"


@pytest.mark.asyncio
async def test_sync_core_integrations_argocd_failure_marks_error(client: TestClient):
    """If ArgoCD installation fails during sync, remaining tasks are skipped and sync_state is error."""
    from unittest.mock import AsyncMock
    from citadel.tasks.k8s_cluster_status import _sync_core_integrations_task

    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "sync-argo-fail",
            "title": "Sync Argo Fail",
            "type": "in-cluster",
        },
    ).json()["data"]

    with patch(
        "citadel.tasks.k8s_cluster_status.sync_core_integrations_task.delay"
    ):
        client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "sync_core_integrations"},
        )

    with patch(
        "citadel.service.k8s_cluster.actions.InstallArgoCDAction.run",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Helm failed"),
    ), patch(
        "citadel.tasks.k8s_cluster_status.sync_core_integration_task.delay"
    ) as mock_sub_delay:
        await _sync_core_integrations_task(p1["id"])
        mock_sub_delay.assert_not_called()

    resp_state = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state")
    sync_state = resp_state.json()["sync_state"]
    assert sync_state["status"] == "error"
    assert sync_state["tasks"]["argocd"]["status"] == "failed"
    assert "Helm failed" in sync_state["tasks"]["argocd"]["message"]
    assert sync_state["tasks"]["cert_manager"]["status"] == "failed"


@pytest.mark.asyncio
async def test_sync_core_integration_task_updates_progress_and_completes(client: TestClient):
    """Each individual integration task updates sync_state and the final one marks sync completed."""
    from unittest.mock import AsyncMock
    from citadel.tasks.k8s_cluster_status import (
        _sync_core_integrations_task,
        _sync_core_integration_task,
    )

    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "sync-single-task",
            "title": "Sync Single Task",
            "type": "in-cluster",
        },
    ).json()["data"]

    with patch(
        "citadel.tasks.k8s_cluster_status.sync_core_integrations_task.delay"
    ):
        client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "sync_core_integrations"},
        )

    with patch(
        "citadel.service.k8s_cluster.actions.InstallArgoCDAction.run",
        new_callable=AsyncMock,
    ), patch(
        "citadel.tasks.k8s_cluster_status.sync_core_integration_task.delay"
    ):
        await _sync_core_integrations_task(p1["id"])

    with patch(
        "citadel.service.k8s_cluster.actions.InstallCertManagerAction.run",
        new_callable=AsyncMock,
    ), patch(
        "citadel.service.k8s_cluster.actions.InstallCNPGAction.run",
        new_callable=AsyncMock,
    ), patch(
        "citadel.service.k8s_cluster.actions.InstallEnvoyGatewayAction.run",
        new_callable=AsyncMock,
    ), patch(
        "citadel.service.k8s_cluster.actions.InstallKafkaOperatorAction.run",
        new_callable=AsyncMock,
    ), patch(
        "citadel.service.k8s_cluster.actions.InstallNifikopAction.run",
        new_callable=AsyncMock,
    ), patch(
        "citadel.service.k8s_cluster.actions.InstallDorisOperatorAction.run",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Doris apply error"),
    ), patch(
        "citadel.service.k8s_cluster.actions.InstallKubePrometheusStackAction.run",
        new_callable=AsyncMock,
    ), patch(
        "citadel.tasks.k8s_cluster_status.poll_k8s_cluster_status.delay"
    ) as mock_poll_delay:
        await _sync_core_integration_task(p1["id"], "cert_manager")
        state_mid = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state").json()["sync_state"]
        assert state_mid["completed"] == 2
        assert state_mid["status"] == "in_progress"
        assert state_mid["tasks"]["cert_manager"]["status"] == "completed"

        for key in ["cnpg", "envoy_gateway", "kafka_operator", "nifikop", "doris_operator", "kube_prometheus_stack"]:
            await _sync_core_integration_task(p1["id"], key)

        mock_poll_delay.assert_called_once_with(p1["id"])

    state_end = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state").json()["sync_state"]
    assert state_end["completed"] == 8
    assert state_end["status"] == "error"
    assert state_end["completed_at"] is not None
    assert state_end["tasks"]["doris_operator"]["status"] == "failed"
    assert "Doris apply error" in state_end["tasks"]["doris_operator"]["message"]
    assert "RuntimeError: Doris apply error" in state_end["tasks"]["doris_operator"]["logs"]


@pytest.mark.asyncio
async def test_sync_core_integration_task_model_not_expired_after_commit(client: TestClient):
    """Regression test: accessing self.model attributes in action.run() after _update_sync_task_state commit must not raise MissingGreenlet."""
    from citadel.tasks.k8s_cluster_status import _sync_core_integration_task
    from citadel.service.k8s_cluster.actions import InstallCertManagerAction

    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "sync-no-expire",
            "title": "Sync No Expire",
            "type": "in-cluster",
        },
    ).json()["data"]

    with patch(
        "citadel.tasks.k8s_cluster_status.sync_core_integrations_task.delay"
    ):
        client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "sync_core_integrations"},
        )

    observed_names = []

    async def _run_accessing_model(self):
        observed_names.append(self.model.name)
        observed_names.append(self.model.type)

    with patch.object(InstallCertManagerAction, "run", _run_accessing_model), patch(
        "citadel.tasks.k8s_cluster_status.poll_k8s_cluster_status.delay"
    ):
        await _sync_core_integration_task(p1["id"], "cert_manager")

    assert observed_names == ["sync-no-expire", K8sClusterType.IN_CLUSTER]
    state = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state").json()["sync_state"]
    assert state["tasks"]["cert_manager"]["status"] == "completed"


def test_poll_k8s_cluster_integrations_status(client: TestClient, mock_k8s):
    """poll_status should populate integrations_status with status, version, and message."""
    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "poll-int-status",
            "title": "Poll Int Status",
            "type": "in-cluster",
        },
    ).json()["data"]

    # Ensure pods in mock_k8s have Running phase and ready container_statuses
    for pod_attr in mock_k8s["core"].return_value.list_pod_for_all_namespaces.side_effect("argocd-server").items:
        pod_attr.status.phase = "Running"
        pod_attr.status.container_statuses = [MagicMock(ready=True)]

    def _mock_list_pods(label_selector=None):
        res = MagicMock()
        pod = MagicMock()
        pod.metadata.labels = {"app.kubernetes.io/version": "v1.0.0"}
        pod.spec.containers = [MagicMock(image="test:v1.0.0")]
        pod.status.phase = "Running"
        pod.status.container_statuses = [MagicMock(ready=True)]
        res.items = [pod]
        return res

    mock_k8s["core"].return_value.list_pod_for_all_namespaces.side_effect = _mock_list_pods

    with patch("citadel.service.k8s_cluster.service.client.CustomObjectsApi") as mock_custom:
        mock_custom.return_value.list_namespaced_custom_object.return_value = {
            "items": [
                {
                    "metadata": {"name": "cert-manager"},
                    "status": {
                        "sync": {"status": "Synced"},
                        "health": {"status": "Healthy"},
                    },
                },
                {
                    "metadata": {"name": "cnpg-operator"},
                    "status": {
                        "sync": {"status": "OutOfSync"},
                        "health": {"status": "Progressing"},
                    },
                },
                {
                    "metadata": {"name": "doris-operator"},
                    "status": {
                        "sync": {"status": "Synced"},
                        "health": {"status": "Degraded"},
                    },
                },
            ]
        }

        resp = client.post(f"/api/v1/k8s_clusters/{p1['id']}/_refresh")
        assert resp.status_code == 200

    data = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state").json()
    int_status = data.get("integrations_status")
    assert int_status is not None
    assert int_status["argocd"]["status"] == "online"
    assert int_status["cert_manager"]["status"] == "online"
    assert "Healthy" in int_status["cert_manager"]["message"]
    assert int_status["cnpg"]["status"] == "pending"
    assert "Progressing" in int_status["cnpg"]["message"]
    assert int_status["doris_operator"]["status"] == "error"
    assert "Degraded" in int_status["doris_operator"]["message"]


@pytest.mark.asyncio
async def test_sync_core_integrations_resume_skips_completed_tasks(client: TestClient):
    """Recovery resumes interrupted sync by dispatching only incomplete, unlocked tasks."""
    from datetime import timedelta
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession
    from sqlalchemy.orm.attributes import flag_modified
    from citadel.fw.model import get_engine, ts_now
    from citadel.service.k8s_cluster.model import K8sClusterStatus
    from citadel.tasks.k8s_cluster_status import _recover_stuck_sync_tasks
    from citadel.tasks.resiliency import clear_memory_locks

    clear_memory_locks()

    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "sync-resume-skip",
            "title": "Sync Resume Skip",
            "type": "in-cluster",
        },
    ).json()["data"]

    with patch("citadel.tasks.k8s_cluster_status.sync_core_integrations_task.delay"):
        client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "sync_core_integrations"},
        )

    stale_ts = (ts_now() - timedelta(minutes=5)).isoformat()
    async with AsyncSession(get_engine()) as session:
        res = await session.exec(
            select(K8sClusterStatus).where(K8sClusterStatus.k8s_cluster_id == p1["id"])
        )
        st = res.one()
        st.argocd_installed = True
        st.sync_state["tasks"]["argocd"]["status"] = "completed"
        st.sync_state["tasks"]["cert_manager"]["status"] = "completed"
        st.sync_state["tasks"]["cnpg"]["status"] = "running"
        st.sync_state["tasks"]["cnpg"]["updated_at"] = stale_ts
        st.sync_state["completed"] = 2
        flag_modified(st, "sync_state")
        await session.commit()

    with patch(
        "citadel.tasks.k8s_cluster_status.sync_core_integration_task.delay"
    ) as mock_sub_delay, patch(
        "citadel.tasks.k8s_cluster_status.sync_core_integrations_task.delay"
    ) as mock_orch_delay:
        await _recover_stuck_sync_tasks(stale_seconds=0)

        mock_orch_delay.assert_not_called()
        called_keys = [c.args[1] for c in mock_sub_delay.call_args_list]
        assert "argocd" not in called_keys
        assert "cert_manager" not in called_keys
        assert called_keys == [
            "cnpg",
            "envoy_gateway",
            "kafka_operator",
            "nifikop",
            "doris_operator",
            "kube_prometheus_stack",
        ]


@pytest.mark.asyncio
async def test_sync_core_integrations_resume_restarts_interrupted_argocd(client: TestClient):
    """If ArgoCD was interrupted mid-install, recovery re-dispatches the orchestrator task."""
    from citadel.tasks.k8s_cluster_status import _recover_stuck_sync_tasks
    from citadel.tasks.resiliency import clear_memory_locks

    clear_memory_locks()

    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "sync-resume-argo",
            "title": "Sync Resume Argo",
            "type": "in-cluster",
        },
    ).json()["data"]

    with patch("citadel.tasks.k8s_cluster_status.sync_core_integrations_task.delay"):
        client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "sync_core_integrations"},
        )

    with patch(
        "citadel.tasks.k8s_cluster_status.sync_core_integrations_task.delay"
    ) as mock_orch_delay, patch(
        "citadel.tasks.k8s_cluster_status.sync_core_integration_task.delay"
    ) as mock_sub_delay:
        await _recover_stuck_sync_tasks(stale_seconds=0)
        mock_orch_delay.assert_called_once_with(p1["id"])
        mock_sub_delay.assert_not_called()


@pytest.mark.asyncio
async def test_sync_core_integrations_resume_skips_actively_locked_task(client: TestClient):
    """Recovery must not duplicate a task whose lock is actively held by a live worker."""
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession
    from sqlalchemy.orm.attributes import flag_modified
    from citadel.fw.model import get_engine
    from citadel.service.k8s_cluster.model import K8sClusterStatus
    from citadel.tasks.k8s_cluster_status import _recover_stuck_sync_tasks
    from citadel.tasks.resiliency import (
        acquire_task_lock,
        clear_memory_locks,
        release_task_lock,
    )

    clear_memory_locks()

    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "sync-resume-locked",
            "title": "Sync Resume Locked",
            "type": "in-cluster",
        },
    ).json()["data"]

    with patch("citadel.tasks.k8s_cluster_status.sync_core_integrations_task.delay"):
        client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "sync_core_integrations"},
        )

    async with AsyncSession(get_engine()) as session:
        res = await session.exec(
            select(K8sClusterStatus).where(K8sClusterStatus.k8s_cluster_id == p1["id"])
        )
        st = res.one()
        st.argocd_installed = True
        st.sync_state["tasks"]["argocd"]["status"] = "completed"
        st.sync_state["tasks"]["cnpg"]["status"] = "running"
        flag_modified(st, "sync_state")
        await session.commit()

    lock_key = f"k8s_cluster:{p1['id']}:cnpg"
    assert await acquire_task_lock(lock_key, ttl=60)
    try:
        with patch(
            "citadel.tasks.k8s_cluster_status.sync_core_integration_task.delay"
        ) as mock_sub_delay:
            await _recover_stuck_sync_tasks(stale_seconds=0)
            called_keys = [c.args[1] for c in mock_sub_delay.call_args_list]
            assert "cnpg" not in called_keys
            assert "cert_manager" in called_keys
    finally:
        await release_task_lock(lock_key)


@pytest.mark.asyncio
async def test_sync_core_integration_task_skips_already_completed_or_locked(client: TestClient):
    """Duplicate delivery of an already-completed or locked subtask must be a no-op."""
    from unittest.mock import AsyncMock
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession
    from sqlalchemy.orm.attributes import flag_modified
    from citadel.fw.model import get_engine
    from citadel.service.k8s_cluster.model import K8sClusterStatus
    from citadel.tasks.k8s_cluster_status import _sync_core_integration_task
    from citadel.tasks.resiliency import (
        acquire_task_lock,
        clear_memory_locks,
        release_task_lock,
    )

    clear_memory_locks()

    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "sync-idempotent",
            "title": "Sync Idempotent",
            "type": "in-cluster",
        },
    ).json()["data"]

    with patch("citadel.tasks.k8s_cluster_status.sync_core_integrations_task.delay"):
        client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "sync_core_integrations"},
        )

    async with AsyncSession(get_engine()) as session:
        res = await session.exec(
            select(K8sClusterStatus).where(K8sClusterStatus.k8s_cluster_id == p1["id"])
        )
        st = res.one()
        st.sync_state["tasks"]["cert_manager"]["status"] = "completed"
        flag_modified(st, "sync_state")
        await session.commit()

    with patch(
        "citadel.service.k8s_cluster.actions.InstallCertManagerAction.run",
        new_callable=AsyncMock,
    ) as mock_cm_run:
        await _sync_core_integration_task(p1["id"], "cert_manager")
        mock_cm_run.assert_not_awaited()

    lock_key = f"k8s_cluster:{p1['id']}:cnpg"
    assert await acquire_task_lock(lock_key, ttl=60)
    try:
        with patch(
            "citadel.service.k8s_cluster.actions.InstallCNPGAction.run",
            new_callable=AsyncMock,
        ) as mock_cnpg_run:
            await _sync_core_integration_task(p1["id"], "cnpg")
            mock_cnpg_run.assert_not_awaited()
    finally:
        await release_task_lock(lock_key)


@pytest.mark.asyncio
async def test_sync_core_integrations_resume_reconciles_all_done_state(client: TestClient):
    """If all tasks are done but top-level status remained in_progress, recovery finalizes it."""
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession
    from sqlalchemy.orm.attributes import flag_modified
    from citadel.fw.model import get_engine
    from citadel.service.k8s_cluster.model import K8sClusterStatus
    from citadel.tasks.k8s_cluster_status import _recover_stuck_sync_tasks
    from citadel.tasks.resiliency import clear_memory_locks

    clear_memory_locks()

    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "sync-reconcile",
            "title": "Sync Reconcile",
            "type": "in-cluster",
        },
    ).json()["data"]

    with patch("citadel.tasks.k8s_cluster_status.sync_core_integrations_task.delay"):
        client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "sync_core_integrations"},
        )

    async with AsyncSession(get_engine()) as session:
        res = await session.exec(
            select(K8sClusterStatus).where(K8sClusterStatus.k8s_cluster_id == p1["id"])
        )
        st = res.one()
        for task_info in st.sync_state["tasks"].values():
            task_info["status"] = "completed"
        flag_modified(st, "sync_state")
        await session.commit()

    with patch("citadel.tasks.k8s_cluster_status.poll_k8s_cluster_status.delay") as mock_poll:
        await _recover_stuck_sync_tasks(stale_seconds=0)
        mock_poll.assert_called_once_with(p1["id"])

    state = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state").json()["sync_state"]
    assert state["status"] == "completed"
    assert state["completed"] == 8
    assert state["completed_at"] is not None


def test_resume_sync_core_integrations_action(client: TestClient):
    """resume_sync_core_integrations action is available only when sync is in_progress."""
    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "sync-resume-action",
            "title": "Sync Resume Action",
            "type": "in-cluster",
        },
    ).json()["data"]

    # Initially not in_progress -> action should fail
    resp_unavail = client.post(
        f"/api/v1/k8s_clusters/{p1['id']}/_actions",
        json={"action": "resume_sync_core_integrations"},
    )
    assert resp_unavail.status_code != 200

    with patch("citadel.tasks.k8s_cluster_status.sync_core_integrations_task.delay"):
        resp_start = client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "sync_core_integrations"},
        )
        assert resp_start.status_code == 200

    with patch(
        "citadel.tasks.k8s_cluster_status.recover_stuck_sync_tasks.delay"
    ) as mock_recover:
        resp_resume = client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "resume_sync_core_integrations"},
        )
        assert resp_resume.status_code == 200
        mock_recover.assert_called_once_with(stale_seconds=0, k8s_cluster_id=p1["id"])


@pytest.mark.asyncio
async def test_install_argocd_deploys_load_balancer_service():
    """InstallArgoCDAction.run deploys a LoadBalancer Service for ArgoCD after Helm install."""
    from unittest.mock import AsyncMock
    import yaml
    from citadel.service.k8s_cluster.actions import InstallArgoCDAction

    cluster = K8sCluster(
        name="test-cluster-argo-lb",
        title="Test Cluster Argo LB",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )

    mock_svc = MagicMock()
    mock_svc.kubeconfig = AsyncMock(return_value="fake-kubeconfig")

    applied_manifests = []

    async def capture_apply_yaml(self, manifest: str):
        applied_manifests.append(manifest)
        return "service/argocd-server-lb created"

    with patch("asyncio.create_subprocess_exec") as mock_exec, patch.object(
        InstallArgoCDAction, "_apply_yaml", new=capture_apply_yaml
    ):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"success", b""))
        mock_exec.return_value = mock_proc

        action = InstallArgoCDAction(cluster, mock_svc)
        await action.run()

    assert len(applied_manifests) == 1
    manifest = yaml.safe_load(applied_manifests[0])
    assert manifest["kind"] == "Service"
    assert manifest["metadata"]["name"] == "argocd-server-lb"
    assert manifest["metadata"]["namespace"] == "argocd"
    assert manifest["spec"]["type"] == "LoadBalancer"
    assert manifest["spec"]["selector"]["app.kubernetes.io/name"] == "argocd-server"


def test_poll_k8s_cluster_argocd_access_details(client: TestClient):
    """Polling fetches ArgoCD LoadBalancer URL, login, and decrypted initial admin password."""
    import base64
    from datetime import datetime, timezone

    with patch(
        "citadel.service.k8s_cluster.service.config.load_incluster_config"
    ), patch(
        "citadel.service.k8s_cluster.service.client.CoreV1Api"
    ) as mock_core_cls, patch(
        "citadel.service.k8s_cluster.service.client.VersionApi"
    ) as mock_ver_cls, patch(
        "citadel.service.k8s_cluster.service.client.CustomObjectsApi"
    ) as mock_custom_cls:
        mock_ver_cls.return_value.get_code.return_value = MagicMock(git_version="v1.30.0")
        mock_custom_cls.return_value.list_namespaced_custom_object.return_value = {"items": []}

        mock_node = MagicMock()
        mock_node.metadata.name = "node-1"
        mock_node.metadata.labels = {}
        mock_node.metadata.creation_timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        mock_node.status.conditions = [MagicMock(type="Ready", status="True")]
        mock_node.status.capacity = {"cpu": "2", "memory": "4Gi", "ephemeral-storage": "20Gi"}
        mock_node.status.allocatable = {"cpu": "2", "memory": "4Gi", "ephemeral-storage": "20Gi"}
        mock_node.status.addresses = [MagicMock(type="InternalIP", address="10.0.0.10")]
        mock_node.status.node_info.kubelet_version = "v1.30.0"

        mock_argo_pod = MagicMock()
        mock_argo_pod.metadata.labels = {}
        mock_argo_pod.spec.containers = [MagicMock(image="quay.io/argoproj/argocd:v2.14.2")]
        mock_argo_pod.status.phase = "Running"
        mock_argo_pod.status.conditions = [MagicMock(type="Ready", status="True")]

        mock_core = mock_core_cls.return_value
        mock_core.list_node.return_value = MagicMock(items=[mock_node])
        mock_core.list_pod_for_all_namespaces.side_effect = lambda label_selector="": MagicMock(
            items=[mock_argo_pod]
            if "argocd-server" in label_selector
            else []
        )

        mock_helm_secret = MagicMock()
        mock_helm_secret.metadata.name = "sh.helm.release.v1.argocd.v1"
        mock_core.list_secret_for_all_namespaces.return_value = MagicMock(items=[mock_helm_secret])

        mock_lb_svc = MagicMock()
        mock_lb_svc.metadata.name = "argocd-server-lb"
        mock_lb_svc.spec.type = "LoadBalancer"
        mock_lb_svc.spec.ports = [MagicMock(port=443), MagicMock(port=80)]
        mock_lb_svc.status.load_balancer.ingress = [MagicMock(ip="192.168.1.50", hostname=None)]

        mock_core.list_namespaced_service.return_value = MagicMock(items=[mock_lb_svc])
        mock_core.list_service_for_all_namespaces.return_value = MagicMock(items=[])

        encoded_pw = base64.b64encode(b"argo-init-secret-123").decode("utf-8")
        mock_core.read_namespaced_secret.return_value = MagicMock(data={"password": encoded_pw})

        p1 = client.post(
            "/api/v1/k8s_clusters",
            json={
                "name": "poll-argo-details",
                "title": "Poll Argo Details",
                "type": "in-cluster",
            },
        ).json()["data"]

        resp = client.post(f"/api/v1/k8s_clusters/{p1['id']}/_refresh")
        assert resp.status_code == 200

        state = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state").json()
        argo_info = state["integrations_status"]["argocd"]
        assert argo_info["url"] == "https://192.168.1.50"
        assert argo_info["username"] == "admin"
        assert argo_info["initial_admin_password"] == "argo-init-secret-123"


def test_poll_k8s_cluster_argocd_access_details_missing(client: TestClient):
    """Polling handles missing LoadBalancer IP and missing argocd-initial-admin-secret gracefully."""
    from datetime import datetime, timezone
    from kubernetes.client.rest import ApiException

    with patch(
        "citadel.service.k8s_cluster.service.config.load_incluster_config"
    ), patch(
        "citadel.service.k8s_cluster.service.client.CoreV1Api"
    ) as mock_core_cls, patch(
        "citadel.service.k8s_cluster.service.client.VersionApi"
    ) as mock_ver_cls, patch(
        "citadel.service.k8s_cluster.service.client.CustomObjectsApi"
    ) as mock_custom_cls:
        mock_ver_cls.return_value.get_code.return_value = MagicMock(git_version="v1.30.0")
        mock_custom_cls.return_value.list_namespaced_custom_object.return_value = {"items": []}

        mock_node = MagicMock()
        mock_node.metadata.name = "node-1"
        mock_node.metadata.labels = {}
        mock_node.metadata.creation_timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        mock_node.status.conditions = [MagicMock(type="Ready", status="True")]
        mock_node.status.capacity = {"cpu": "2", "memory": "4Gi", "ephemeral-storage": "20Gi"}
        mock_node.status.allocatable = {"cpu": "2", "memory": "4Gi", "ephemeral-storage": "20Gi"}
        mock_node.status.addresses = [MagicMock(type="InternalIP", address="10.0.0.10")]
        mock_node.status.node_info.kubelet_version = "v1.30.0"

        mock_core = mock_core_cls.return_value
        mock_core.list_node.return_value = MagicMock(items=[mock_node])
        mock_core.list_pod_for_all_namespaces.side_effect = lambda label_selector="": MagicMock(
            items=[]
        )

        mock_helm_secret = MagicMock()
        mock_helm_secret.metadata.name = "sh.helm.release.v1.argocd.v1"
        mock_core.list_secret_for_all_namespaces.return_value = MagicMock(items=[mock_helm_secret])

        mock_core.list_namespaced_service.return_value = MagicMock(items=[])
        mock_core.list_service_for_all_namespaces.return_value = MagicMock(items=[])
        mock_core.read_namespaced_secret.side_effect = ApiException(status=404, reason="Not Found")

        p1 = client.post(
            "/api/v1/k8s_clusters",
            json={
                "name": "poll-argo-missing",
                "title": "Poll Argo Missing",
                "type": "in-cluster",
            },
        ).json()["data"]

        resp = client.post(f"/api/v1/k8s_clusters/{p1['id']}/_refresh")
        assert resp.status_code == 200

        state = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state").json()
        argo_info = state["integrations_status"]["argocd"]
        assert argo_info["url"] is None
        assert argo_info["username"] == "admin"
        assert argo_info["initial_admin_password"] is None


@pytest.mark.asyncio
async def test_sync_core_integrations_ensures_argocd_load_balancer_when_already_installed(
    client: TestClient,
):
    """Syncing core integrations ensures ArgoCD LoadBalancer service even if ArgoCD is already installed."""
    from unittest.mock import AsyncMock
    from citadel.service.k8s_cluster.actions import build_initial_sync_state
    from citadel.tasks.k8s_cluster_status import _sync_core_integrations_task
    from citadel.fw.model import get_engine

    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "sync-argo-lb-existing",
            "title": "Sync Argo LB Existing",
            "type": "in-cluster",
        },
    ).json()["data"]

    engine = get_engine()
    async with AsyncSession(engine) as session:
        st = K8sClusterStatus(
            k8s_cluster_id=p1["id"],
            status="online",
            argocd_installed=True,
            sync_state=build_initial_sync_state(),
        )
        session.add(st)
        await session.commit()

    with patch(
        "citadel.tasks.k8s_cluster_status.acquire_task_lock",
        new=AsyncMock(return_value=True),
    ), patch(
        "citadel.tasks.k8s_cluster_status.release_task_lock",
        new=AsyncMock(),
    ), patch(
        "citadel.tasks.k8s_cluster_status.is_task_locked",
        new=AsyncMock(return_value=False),
    ), patch(
        "citadel.tasks.k8s_cluster_status.sync_core_integration_task.delay",
    ), patch(
        "citadel.service.k8s_cluster.actions.InstallArgoCDAction.run",
        new=AsyncMock(),
    ) as mock_run, patch(
        "citadel.service.k8s_cluster.actions.InstallArgoCDAction.ensure_load_balancer",
        new=AsyncMock(),
    ) as mock_ensure_lb:
        await _sync_core_integrations_task(p1["id"])

    mock_run.assert_not_called()
    mock_ensure_lb.assert_awaited_once()


@pytest.mark.asyncio
async def test_install_kube_prometheus_stack():
    """Verify InstallKubePrometheusStackAction renders ArgoCD Application with K3s defaults."""
    import os
    from unittest.mock import AsyncMock
    from citadel.service.k8s_cluster.actions import InstallKubePrometheusStackAction

    cluster = K8sCluster(
        name="test-cluster-prom",
        title="Test Cluster Prom",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )

    mock_svc = MagicMock()
    mock_svc.kubeconfig = AsyncMock(return_value="fake-kubeconfig")

    applied_manifests = []

    def mock_subprocess(*args, **kwargs):
        cmd = args
        if len(cmd) > 0 and "kubectl" in cmd:
            path = cmd[-1]
            if os.path.exists(path):
                with open(path, "r") as f:
                    applied_manifests.append(f.read())
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"success", b""))
        return mock_proc

    with patch.object(
        InstallKubePrometheusStackAction, "_is_already_available", new=AsyncMock(return_value=False)
    ), patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
        action = InstallKubePrometheusStackAction(cluster, mock_svc)
        await action.run()

    assert len(applied_manifests) == 1
    manifest = applied_manifests[0]
    assert "kind: Application" in manifest
    assert "name: kube-prometheus-stack" in manifest
    assert "namespace: monitoring" in manifest
    assert "repoURL: https://prometheus-community.github.io/helm-charts" in manifest
    assert "chart: kube-prometheus-stack" in manifest
    assert "targetRevision: 93.3.0" in manifest
    assert "ServerSideApply=true" in manifest
    assert "grafana:\n          enabled: false" in manifest
    assert "alertmanager:\n          enabled: false" in manifest
    assert "kubeControllerManager:\n          enabled: false" in manifest
    assert "kubeScheduler:\n          enabled: false" in manifest
    assert "kubeEtcd:\n          enabled: false" in manifest
    assert "kubeProxy:\n          enabled: false" in manifest
    assert "distroless: false" in manifest


@pytest.mark.asyncio
async def test_install_kube_prometheus_stack_skips_when_already_available():
    """Verify InstallKubePrometheusStackAction skips installation when Prometheus CRD or pods already exist."""
    from unittest.mock import AsyncMock
    from citadel.service.k8s_cluster.actions import InstallKubePrometheusStackAction

    cluster = K8sCluster(
        name="test-cluster-prom-exists",
        title="Test Cluster Prom Exists",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )
    mock_svc = MagicMock()

    with patch(
        "citadel.service.k8s_cluster.actions.client.CustomObjectsApi"
    ) as mock_custom, patch(
        "citadel.service.k8s_cluster.actions.InstallArgoCDAction._get_kubernetes_clients"
    ) as mock_clients, patch(
        "asyncio.create_subprocess_exec", new_callable=AsyncMock
    ) as mock_exec:
        mock_custom.return_value.get_namespaced_custom_object.side_effect = Exception("NotFound")
        mock_core = MagicMock()
        mock_ext = MagicMock()
        mock_ext.read_custom_resource_definition.return_value = MagicMock()
        mock_clients.return_value = (mock_core, mock_ext)

        action = InstallKubePrometheusStackAction(cluster, mock_svc)
        await action.run()

        mock_exec.assert_not_called()


@pytest.mark.asyncio
async def test_install_kube_prometheus_stack_reconciles_when_argocd_managed():
    """Verify InstallKubePrometheusStackAction reconciles when Citadel ArgoCD Application already exists."""
    from unittest.mock import AsyncMock
    from citadel.service.k8s_cluster.actions import InstallKubePrometheusStackAction

    cluster = K8sCluster(
        name="test-cluster-prom-argo",
        title="Test Cluster Prom Argo",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )
    mock_svc = MagicMock()

    with patch(
        "citadel.service.k8s_cluster.actions.client.CustomObjectsApi"
    ) as mock_custom, patch(
        "citadel.service.k8s_cluster.actions.InstallArgoCDAction._get_kubernetes_clients"
    ) as mock_clients, patch.object(
        InstallKubePrometheusStackAction, "_apply_template", new=AsyncMock()
    ) as mock_apply:
        mock_custom.return_value.get_namespaced_custom_object.return_value = {"metadata": {"name": "kube-prometheus-stack"}}
        mock_clients.return_value = (MagicMock(), MagicMock())

        action = InstallKubePrometheusStackAction(cluster, mock_svc)
        await action.run()

        mock_apply.assert_awaited_once()


def test_install_kube_prometheus_stack_action_triggers_task(client: TestClient):
    """Verify install_kube_prometheus_stack action queues Celery task and updates DB status."""
    p1 = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "task-test-prom",
            "title": "Task Test Prom",
            "type": "in-cluster",
        },
    ).json()["data"]

    with patch(
        "citadel.tasks.k8s_cluster_status.install_kube_prometheus_stack_task.delay"
    ) as mock_delay:
        resp = client.post(
            f"/api/v1/k8s_clusters/{p1['id']}/_actions",
            json={"action": "install_kube_prometheus_stack"},
        )
        assert resp.status_code == 200
        assert (
            resp.json()["message"]
            == "Kube Prometheus Stack installation triggered and status being refreshed."
        )
        mock_delay.assert_called_once_with(p1["id"])

        resp_state = client.get(f"/api/v1/k8s_clusters/{p1['id']}/_state")
        assert resp_state.json()["kube_prometheus_stack_installed"] is True


@pytest.mark.asyncio
async def test_install_kube_prometheus_stack_locks_images(test_stack):
    """Verify InstallKubePrometheusStackAction resolves chart and all 6 image roles from test_stack."""
    import os
    from unittest.mock import AsyncMock
    from citadel.service.k8s_cluster.actions import InstallKubePrometheusStackAction

    cluster = K8sCluster(
        name="test-cluster-prom-lock",
        title="Test Cluster Prom Lock",
        type=K8sClusterType.REMOTE,
        kubeconfig="fake-kubeconfig",
    )

    mock_svc = MagicMock()
    mock_svc.kubeconfig = AsyncMock(return_value="fake-kubeconfig")

    applied_manifests = []

    def mock_subprocess(*args, **kwargs):
        cmd = args
        if len(cmd) > 0 and "kubectl" in cmd:
            path = cmd[-1]
            if os.path.exists(path):
                with open(path, "r") as f:
                    applied_manifests.append(f.read())
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"success", b""))
        return mock_proc

    with patch.object(
        InstallKubePrometheusStackAction, "_is_already_available", new=AsyncMock(return_value=False)
    ), patch.object(
        InstallKubePrometheusStackAction, "_resolve_stack", new=AsyncMock(return_value=test_stack)
    ), patch("asyncio.create_subprocess_exec", side_effect=mock_subprocess):
        action = InstallKubePrometheusStackAction(cluster, mock_svc)
        await action.run()

    assert len(applied_manifests) == 1
    manifest = applied_manifests[0]
    assert "repoURL: https://test.example.com/prometheus-community" in manifest
    assert "targetRevision: 93.99.0" in manifest
    assert "repository: prometheus/prometheus" in manifest
    assert 'tag: "v3.99.0-distroless"' in manifest
    assert "repository: prometheus-operator/prometheus-operator" in manifest
    assert 'tag: "v0.99.2"' in manifest
    assert "repository: prometheus-operator/prometheus-config-reloader" in manifest
    assert "repository: kube-state-metrics/kube-state-metrics" in manifest
    assert 'tag: "v2.99.0"' in manifest
    assert "repository: prometheus/node-exporter" in manifest
    assert 'tag: "v1.99.1-distroless"' in manifest
    assert "repository: jkroepke/kube-webhook-certgen" in manifest
    assert 'tag: "1.99.1"' in manifest












