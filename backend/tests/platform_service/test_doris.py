# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import Request
from pydantic import ValidationError
from citadel.config import settings
from citadel.crypto import encrypt_password
from citadel.platform_service.doris import DorisPlatform, DorisPlatformService, DorisPlatformState
from citadel.platform_service.doris.poller import DorisPoller
from citadel.fw.model import AsyncSession

# Ensure encryption key is configured for tests
settings.fernet_key = "EFw4cCjDgHhGuZAGlwXmQhXg134ZdHjb9SeqcszWeSU="


@pytest.fixture
def mock_service_dependencies():
    """Provides mock request and session objects for service tests."""
    request = MagicMock(spec=Request)
    session = MagicMock(spec=AsyncSession)
    mock_exec_result = MagicMock()
    mock_exec_result.all.return_value = []
    mock_exec_result.first.return_value = None
    session.exec = AsyncMock(return_value=mock_exec_result)
    session.flush = AsyncMock()
    session.add = MagicMock()
    return request, session


def test_doris_resource_defaults():
    """Test default values for Doris platform model."""
    model = DorisPlatform(name="test-doris", title="Test Doris", project_id=1)
    assert model.fe_replicas == 3
    assert model.be_replicas == 3
    assert model.fe_storage_size == "10Gi"
    assert model.be_storage_size == "50Gi"
    assert model.fe_cpu_request == 0.5
    assert model.fe_cpu_limit == 2.0
    assert model.fe_mem_request == 2.0
    assert model.fe_mem_limit == 4.0
    assert model.be_cpu_request == 0.5
    assert model.be_cpu_limit == 2.0
    assert model.be_mem_request == 2.0
    assert model.be_mem_limit == 4.0
    assert model.admin_password is not None
    assert len(model.admin_password) >= 16
    assert model.operator_password is not None
    assert len(model.operator_password) >= 16


def test_doris_cpu_validation():
    """Test that FE and BE CPU request cannot exceed limits."""
    # Invalid FE CPU
    with pytest.raises(ValidationError) as excinfo:
        DorisPlatform.model_validate(
            {
                "name": "test-doris",
                "title": "Test Doris",
                "project_id": 1,
                "fe_cpu_request": 4.0,
                "fe_cpu_limit": 2.0,
            }
        )
    assert "FE CPU request cannot be greater than FE CPU limit" in str(excinfo.value)

    # Invalid BE CPU
    with pytest.raises(ValidationError) as excinfo:
        DorisPlatform.model_validate(
            {
                "name": "test-doris",
                "title": "Test Doris",
                "project_id": 1,
                "be_cpu_request": 4.0,
                "be_cpu_limit": 2.0,
            }
        )
    assert "BE CPU request cannot be greater than BE CPU limit" in str(excinfo.value)


def test_doris_mem_validation():
    """Test that FE and BE Memory request cannot exceed limits."""
    # Invalid FE Memory
    with pytest.raises(ValidationError) as excinfo:
        DorisPlatform.model_validate(
            {
                "name": "test-doris",
                "title": "Test Doris",
                "project_id": 1,
                "fe_mem_request": 8.0,
                "fe_mem_limit": 4.0,
            }
        )
    assert "FE Memory request cannot be greater than FE Memory limit" in str(excinfo.value)

    # Invalid BE Memory
    with pytest.raises(ValidationError) as excinfo:
        DorisPlatform.model_validate(
            {
                "name": "test-doris",
                "title": "Test Doris",
                "project_id": 1,
                "be_mem_request": 8.0,
                "be_mem_limit": 4.0,
            }
        )
    assert "BE Memory request cannot be greater than BE Memory limit" in str(excinfo.value)


def test_doris_replica_count_validation():
    """Test that FE and BE replica counts are validated properly."""
    # FE replicas must be odd positive numbers
    for valid_fe in [1, 3, 5, 7]:
        model = DorisPlatform.model_validate(
            {
                "name": "test-doris",
                "title": "Test Doris",
                "project_id": 1,
                "fe_replicas": valid_fe,
            }
        )
        assert model.fe_replicas == valid_fe

    for invalid_fe in [0, 2, 4, -1]:
        with pytest.raises(ValidationError) as excinfo:
            DorisPlatform.model_validate(
                {
                    "name": "test-doris",
                    "title": "Test Doris",
                    "project_id": 1,
                    "fe_replicas": invalid_fe,
                }
            )
        assert "FE replicas must be an odd positive number" in str(excinfo.value)

    # BE replicas must be positive
    for valid_be in [1, 2, 3, 5]:
        model = DorisPlatform.model_validate(
            {
                "name": "test-doris",
                "title": "Test Doris",
                "project_id": 1,
                "be_replicas": valid_be,
            }
        )
        assert model.be_replicas == valid_be

    for invalid_be in [0, -1]:
        with pytest.raises(ValidationError) as excinfo:
            DorisPlatform.model_validate(
                {
                    "name": "test-doris",
                    "title": "Test Doris",
                    "project_id": 1,
                    "be_replicas": invalid_be,
                }
            )
        assert "BE replicas must be at least 1" in str(excinfo.value)


@pytest.mark.asyncio
async def test_doris_template_vars(mock_service_dependencies):
    """Test that template_vars generates expected template values."""
    request, session = mock_service_dependencies
    svc = DorisPlatformService(request, session)

    model = DorisPlatform(
        name="doris-cluster",
        title="Doris Analytics",
        project_id=1,
        fe_replicas=3,
        be_replicas=3,
        fe_storage_size="10Gi",
        be_storage_size="50Gi",
    )

    svc._resolve_namespace = AsyncMock(return_value="test-ns")
    mock_project = MagicMock(
        name="default",
        title="Default Project",
        ingress_domain="apps.example.com",
        stack_id=None,
    )
    svc.project = AsyncMock(return_value=mock_project)

    vars_dict = await svc.template_vars(model)

    assert vars_dict["name"] == "doris-cluster"
    assert vars_dict["fe_replicas"] == 3
    assert vars_dict["be_replicas"] == 3
    assert vars_dict["fe_storage_size"] == "10Gi"
    assert vars_dict["be_storage_size"] == "50Gi"
    assert vars_dict["fe_image"] == "selectdb/doris.fe-ubuntu"
    assert vars_dict["fe_image_tag"] == "2.1.8"
    assert vars_dict["be_image"] == "selectdb/doris.be-ubuntu"
    assert vars_dict["be_image_tag"] == "2.1.8"
    assert vars_dict["ingress_domain"] == "apps.example.com"
    assert vars_dict["namespace"] == "test-ns"
    assert vars_dict["operator_username"] == "doris_operator"
    assert vars_dict["operator_password"] is not None


@pytest.mark.asyncio
async def test_doris_render_manifests(mock_service_dependencies):
    """Test rendering Kubernetes manifests from templates."""
    request, session = mock_service_dependencies
    svc = DorisPlatformService(request, session)

    model = DorisPlatform(
        name="doris-main",
        title="Doris Main",
        project_id=1,
    )

    svc._resolve_namespace = AsyncMock(return_value="proj1")
    mock_project = MagicMock(
        name="proj1",
        title="Project One",
        ingress_domain="apps.example.com",
        stack_id=None,
    )
    svc.project = AsyncMock(return_value=mock_project)

    manifests = await svc.render_manifests(model)
    assert "kind: Application" in manifests
    assert "kind: Secret" in manifests
    assert "kind: Service" in manifests
    assert "kind: HTTPRoute" in manifests
    assert "kind: Job" in manifests
    assert "doris-main" in manifests
    assert "doris-main-mysql-lb" in manifests
    assert "doris_operator" in manifests
    assert "type: ClusterIP" in manifests
    assert "type: LoadBalancer" in manifests
    assert "port: 3306" in manifests
    assert "targetPort: 9030" in manifests
    assert "type: NodePort" not in manifests


@pytest.mark.asyncio
async def test_doris_poller(mock_service_dependencies):
    """Test DorisPoller updating state from cluster info."""
    request, session = mock_service_dependencies
    svc = DorisPlatformService(request, session)

    model = DorisPlatform(
        id=10,
        name="doris-test",
        title="Doris Test",
        project_id=1,
        admin_password=encrypt_password("supersecret123"),
    )

    state = DorisPlatformState(platform_id=10, active=True)
    svc.platform_state = AsyncMock(return_value=state)
    svc.kubeconfig = AsyncMock(return_value=None)
    svc._resolve_namespace = AsyncMock(return_value="default")
    svc.project = AsyncMock(return_value=MagicMock(ingress_domain="example.com"))

    with patch("asyncio.to_thread") as mock_thread:
        mock_thread.return_value = (
            "online",
            "Sync: Synced, Health: Healthy | Pods: FE 3/3, BE 3/3",
            {
                "sync": {"status": "Synced"},
                "health": {"status": "Healthy"},
                "load_balancer_ips": ["10.20.30.40"],
            },
            [],
            [{"hostname": "node1", "ipv4": "192.168.1.100", "ipv6": None}],
        )

        poller = DorisPoller(svc, model)
        await poller.poll()

        assert state.status == "online"
        assert state.node_ports == []
        assert state.extra_data["load_balancer_ips"] == ["10.20.30.40"]
        assert state.query_uri == "mysql://root:supersecret123@10.20.30.40:3306"
        assert state.admin_password == "supersecret123"
        assert state.operator_user == "doris_operator"
        assert state.fe_http_uri == "https://doris-test.example.com"

        # Fallback to internal service when LoadBalancer IP is not yet assigned
        mock_thread.return_value = (
            "online",
            "Sync: Synced, Health: Healthy | Pods: FE 3/3, BE 3/3",
            {"sync": {"status": "Synced"}, "health": {"status": "Healthy"}},
            [],
            [{"hostname": "node1", "ipv4": "192.168.1.100", "ipv6": None}],
        )
        await poller.poll()
        assert state.query_uri == "mysql://root:supersecret123@doris-test-fe-service.default.svc.cluster.local:9030"


def _make_mock_pod(name: str, phase: str = "Running", ready: bool = True) -> MagicMock:
    """Create a mock Kubernetes pod object for Doris poller tests."""
    pod = MagicMock()
    pod.metadata.name = name
    pod.status.phase = phase
    container_status = MagicMock()
    container_status.ready = ready
    pod.status.container_statuses = [container_status]
    return pod


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "argo_health,fe_replicas,be_replicas,fe_ready_count,be_ready_count,expected_status",
    [
        # ArgoCD says Healthy, but 0/3 pods are up -> must be pending
        ("Healthy", 3, 3, 0, 0, "pending"),
        # ArgoCD says Healthy, FE is 3/3 but BE is 2/3 -> must be pending
        ("Healthy", 3, 3, 3, 2, "pending"),
        # ArgoCD says Healthy, FE is 2/3 and BE is 3/3 -> must be pending
        ("Healthy", 3, 3, 2, 3, "pending"),
        # ArgoCD says Healthy, FE is 3/3 and BE is 3/3 -> online
        ("Healthy", 3, 3, 3, 3, "online"),
        # Custom replica configuration (1 FE, 2 BE) all ready -> online
        ("Healthy", 1, 2, 1, 2, "online"),
        # ArgoCD says Degraded even when pods are ready -> error
        ("Degraded", 3, 3, 3, 3, "error"),
    ],
)
async def test_doris_poller_instance_counts(
    mock_service_dependencies,
    argo_health,
    fe_replicas,
    be_replicas,
    fe_ready_count,
    be_ready_count,
    expected_status,
):
    """Test DorisPoller compares running FE/BE pods against configured replicas."""
    request, session = mock_service_dependencies
    svc = DorisPlatformService(request, session)

    model = DorisPlatform(
        id=11,
        name="doris-test",
        title="Doris Test",
        project_id=1,
        fe_replicas=fe_replicas,
        be_replicas=be_replicas,
        admin_password=encrypt_password("supersecret123"),
    )

    state = DorisPlatformState(platform_id=11, active=True)
    svc.platform_state = AsyncMock(return_value=state)
    svc.kubeconfig = AsyncMock(return_value=None)
    svc._resolve_namespace = AsyncMock(return_value="default")
    svc.project = AsyncMock(return_value=MagicMock(ingress_domain="example.com"))

    fe_pods = [
        _make_mock_pod(f"doris-test-fe-{i}", phase="Running", ready=(i < fe_ready_count))
        for i in range(fe_replicas)
    ]
    be_pods = [
        _make_mock_pod(f"doris-test-be-{i}", phase="Running", ready=(i < be_ready_count))
        for i in range(be_replicas)
    ]

    mock_custom_api = MagicMock()
    mock_custom_api.get_namespaced_custom_object.return_value = {
        "status": {
            "sync": {"status": "Synced"},
            "health": {"status": argo_health},
        }
    }

    mock_core_v1 = MagicMock()
    mock_pod_list = MagicMock()
    mock_pod_list.items = fe_pods + be_pods
    mock_core_v1.list_namespaced_pod.return_value = mock_pod_list
    mock_core_v1.read_namespaced_service.side_effect = Exception("not found")
    mock_node_list = MagicMock()
    mock_node_list.items = []
    mock_core_v1.list_node.return_value = mock_node_list

    with (
        patch("citadel.platform_service.doris.poller.config.load_incluster_config"),
        patch("citadel.platform_service.doris.poller.client.ApiClient"),
        patch(
            "citadel.platform_service.doris.poller.client.CustomObjectsApi",
            return_value=mock_custom_api,
        ),
        patch(
            "citadel.platform_service.doris.poller.client.CoreV1Api",
            return_value=mock_core_v1,
        ),
    ):
        poller = DorisPoller(svc, model)
        await poller.poll()

    assert state.status == expected_status
    if expected_status != "error":
        assert f"FE {fe_ready_count}/{fe_replicas}" in state.message
        assert f"BE {be_ready_count}/{be_replicas}" in state.message
