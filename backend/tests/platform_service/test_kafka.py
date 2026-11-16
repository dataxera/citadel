# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import Request
from pydantic import ValidationError
from citadel.platform_service.kafka import KafkaPlatform, KafkaPlatformService
from citadel.fw.model import AsyncSession


@pytest.fixture
def mock_service_dependencies():
    request = MagicMock(spec=Request)
    session = MagicMock(spec=AsyncSession)
    mock_exec_result = MagicMock()
    mock_exec_result.all.return_value = []
    mock_exec_result.first.return_value = None
    session.exec = AsyncMock(return_value=mock_exec_result)
    session.flush = AsyncMock()
    return request, session


def test_kafka_resource_defaults():
    """Test default values for Kafka resource limits and replicas."""
    model = KafkaPlatform(name="test-kafka", title="Test Kafka", project_id=1)
    assert model.replica_count == 3
    assert model.storage_size == "20Gi"
    assert model.cpu_request == 0.5
    assert model.cpu_limit == 1.0
    assert model.mem_request == 1.0
    assert model.mem_limit == 2.0
    assert model.enable_loadbalancer is False


def test_kafka_cpu_validation():
    """Test that CPU request cannot exceed CPU limit."""
    with pytest.raises(ValidationError) as excinfo:
        KafkaPlatform.model_validate(
            {
                "name": "test-kafka",
                "title": "Test Kafka",
                "project_id": 1,
                "cpu_request": 4.0,
                "cpu_limit": 2.0,
            }
        )
    assert "CPU request cannot be greater than CPU limit" in str(excinfo.value)


def test_kafka_mem_validation():
    """Test that memory request cannot exceed memory limit."""
    with pytest.raises(ValidationError) as excinfo:
        KafkaPlatform.model_validate(
            {
                "name": "test-kafka",
                "title": "Test Kafka",
                "project_id": 1,
                "mem_request": 8.0,
                "mem_limit": 4.0,
            }
        )
    assert "Memory request cannot be greater than Memory limit" in str(excinfo.value)


def test_kafka_replica_count_validation():
    """Test that replica count is validated between 1 and 9."""
    # Valid replica counts
    for valid_replicas in [1, 3, 5, 9]:
        model = KafkaPlatform.model_validate(
            {
                "name": "test-kafka",
                "title": "Test Kafka",
                "project_id": 1,
                "replica_count": valid_replicas,
            }
        )
        assert model.replica_count == valid_replicas

    # Invalid replica counts
    for invalid_replicas in [0, 10]:
        with pytest.raises(ValidationError) as excinfo:
            KafkaPlatform.model_validate(
                {
                    "name": "test-kafka",
                    "title": "Test Kafka",
                    "project_id": 1,
                    "replica_count": invalid_replicas,
                }
            )
        assert "Replica count must be between 1 and 9" in str(excinfo.value)


@pytest.mark.asyncio
async def test_kafka_template_vars(mock_service_dependencies):
    """Test that template_vars returns expected template variable mappings."""
    request, session = mock_service_dependencies
    svc = KafkaPlatformService(request, session)

    model = KafkaPlatform(
        name="test-kafka",
        project_id=1,
        replica_count=3,
        storage_size="20Gi",
    )

    svc._resolve_namespace = AsyncMock(return_value="test-ns")
    svc.project = AsyncMock(return_value=MagicMock(ingress_domain=None))

    vars = await svc.template_vars(model)

    assert vars["name"] == "test-kafka"
    assert vars["namespace"] == "test-ns"
    assert vars["replica_count"] == 3
    assert vars["storage_size"] == "20Gi"


@pytest.mark.asyncio
async def test_kafka_render_manifests(mock_service_dependencies):
    """Test that the ArgoCD Application manifests render correctly."""
    request, session = mock_service_dependencies
    svc = KafkaPlatformService(request, session)

    model = KafkaPlatform(
        name="test-kafka",
        project_id=1,
        replica_count=3,
        storage_size="20Gi",
    )

    svc._resolve_namespace = AsyncMock(return_value="test-ns")
    svc.project = AsyncMock(return_value=MagicMock(ingress_domain=None))

    manifests = await svc.render_manifests(model)

    assert "name: test-kafka" in manifests
    assert "replicaCount: 3" in manifests
    assert "chart: kafka" in manifests
    assert "ghcr.io/kagesenshi/citadel/charts" in manifests
    assert "size: \"20Gi\"" in manifests
    assert "namespace: test-ns" in manifests
    assert "enableLoadBalancer: false" in manifests


@pytest.mark.asyncio
async def test_kafka_render_manifests_image_override(mock_service_dependencies):
    """Test that image override is rendered correctly when enabled."""
    request, session = mock_service_dependencies
    svc = KafkaPlatformService(request, session)

    model = KafkaPlatform(
        name="test-kafka",
        project_id=1,
        replica_count=3,
        storage_size="20Gi",
    )

    svc._resolve_namespace = AsyncMock(return_value="test-ns")
    svc.project = AsyncMock(return_value=MagicMock(ingress_domain=None))
    svc.resolve_image = AsyncMock(return_value=("my-custom/kafka", "custom-1.0"))

    manifests = await svc.render_manifests(model)

    assert "my-custom/kafka" in manifests
    assert "custom-1.0" in manifests


@pytest.mark.asyncio
async def test_kafka_poll_status(mock_service_dependencies):
    """Test that kafka_url is derived correctly in poll_status."""
    from citadel.platform_service.kafka.model import KafkaPlatformState
    request, session = mock_service_dependencies
    svc = KafkaPlatformService(request, session)

    model = KafkaPlatform(
        name="test-kafka",
        project_id=1,
    )

    mock_state = MagicMock(spec=KafkaPlatformState)
    mock_state.active = True

    with patch.object(svc, "platform_state", AsyncMock(return_value=mock_state)), \
         patch.object(svc, "kubeconfig", AsyncMock(return_value="mock-kubeconfig")), \
         patch.object(svc, "_resolve_namespace", AsyncMock(return_value="test-ns")):

        node_ports = []
        cluster_nodes = [{"hostname": "node1", "ipv4": "1.2.3.4", "ipv6": None}]

        async def mock_poll(*args):
            return "online", "Healthy", {}, node_ports, cluster_nodes, "test-kafka"

        with patch("citadel.platform_service.kafka.service.asyncio.to_thread", side_effect=mock_poll):
            mock_project = MagicMock()
            mock_project.ingress_domain = None
            svc.project = AsyncMock(return_value=mock_project)

            await svc.poll_status(model)

            # Kafka URL should be derived as <service>.<namespace>.svc.cluster.local:9092
            assert mock_state.kafka_url == "test-kafka.test-ns.svc.cluster.local:9092"


@pytest.mark.asyncio
async def test_kafka_ssl_certificate_rendering(mock_service_dependencies):
    """Test that the cert-manager Certificate is generated and contains the self-signed issuer."""
    request, session = mock_service_dependencies
    svc = KafkaPlatformService(request, session)

    model = KafkaPlatform(
        name="my-kafka",
        project_id=1,
    )

    svc._resolve_namespace = AsyncMock(return_value="custom-ns")
    mock_project = MagicMock(ingress_domain=None)
    mock_project.name = "mock-project"
    svc.project = AsyncMock(return_value=mock_project)

    manifests = await svc.render_manifests(model)

    assert "kind: Certificate" in manifests
    assert "name: my-kafka-tls" in manifests
    assert "secretName: my-kafka-tls" in manifests
    assert "name: mock-project-selfsigned-issuer" in manifests
    assert "kind: Issuer" in manifests
    assert "my-kafka-kafka-bootstrap" in manifests
    assert "my-kafka-kafka-external-bootstrap" not in manifests


@pytest.mark.asyncio
async def test_kafka_poll_status_with_nodeports(mock_service_dependencies):
    """Test that nodeports are populated correctly in poll_status."""
    from citadel.platform_service.kafka.model import KafkaPlatformState
    request, session = mock_service_dependencies
    svc = KafkaPlatformService(request, session)

    model = KafkaPlatform(
        name="test-kafka",
        project_id=1,
    )

    mock_state = MagicMock(spec=KafkaPlatformState)
    mock_state.active = True

    with patch.object(svc, "platform_state", AsyncMock(return_value=mock_state)), \
         patch.object(svc, "kubeconfig", AsyncMock(return_value="mock-kubeconfig")), \
         patch.object(svc, "_resolve_namespace", AsyncMock(return_value="test-ns")):

        node_ports = [{"name": "test-kafka-kafka-external-bootstrap", "port": 9094, "node_port": 32094}]
        cluster_nodes = [{"hostname": "node1", "ipv4": "1.2.3.4", "ipv6": None}]

        async def mock_poll(*args):
            return "online", "Healthy", {}, node_ports, cluster_nodes, "test-kafka-kafka-external-bootstrap"

        with patch("citadel.platform_service.kafka.service.asyncio.to_thread", side_effect=mock_poll):
            mock_project = MagicMock()
            mock_project.ingress_domain = None
            svc.project = AsyncMock(return_value=mock_project)

            await svc.poll_status(model)

            assert mock_state.node_ports == node_ports
            assert mock_state.cluster_nodes == cluster_nodes


@pytest.mark.asyncio
async def test_kafka_render_manifests_with_loadbalancer(mock_service_dependencies):
    """Test that manifests include enableLoadBalancer: true and certificate includes external bootstrap when enabled."""
    request, session = mock_service_dependencies
    svc = KafkaPlatformService(request, session)

    model = KafkaPlatform(
        name="lb-kafka",
        project_id=1,
        replica_count=3,
        storage_size="20Gi",
        enable_loadbalancer=True,
    )

    svc._resolve_namespace = AsyncMock(return_value="test-ns")
    mock_project = MagicMock(ingress_domain=None)
    mock_project.name = "mock-project"
    svc.project = AsyncMock(return_value=mock_project)

    manifests = await svc.render_manifests(model)

    assert "enableLoadBalancer: true" in manifests
    assert "lb-kafka-kafka-bootstrap" in manifests
    assert "lb-kafka-kafka-external-bootstrap" in manifests


@pytest.mark.asyncio
async def test_kafka_poll_status_with_loadbalancer(mock_service_dependencies):
    """Test that load balancer ingress IP is discovered and kafka_external_url is populated."""
    from citadel.platform_service.kafka.model import KafkaPlatformState
    request, session = mock_service_dependencies
    svc = KafkaPlatformService(request, session)

    model = KafkaPlatform(
        name="test-kafka",
        project_id=1,
        enable_loadbalancer=True,
    )

    mock_state = MagicMock(spec=KafkaPlatformState)
    mock_state.active = True

    with patch.object(svc, "platform_state", AsyncMock(return_value=mock_state)), \
         patch.object(svc, "kubeconfig", AsyncMock(return_value="mock-kubeconfig")), \
         patch.object(svc, "_resolve_namespace", AsyncMock(return_value="test-ns")):

        node_ports = []
        cluster_nodes = [{"hostname": "node1", "ipv4": "1.2.3.4", "ipv6": None}]
        load_balancer_ips = ["198.51.100.50"]

        async def mock_poll(*args):
            return "online", "Healthy", {"load_balancer_ips": load_balancer_ips}, node_ports, cluster_nodes, "test-kafka-kafka-bootstrap"

        with patch("citadel.platform_service.kafka.service.asyncio.to_thread", side_effect=mock_poll):
            mock_project = MagicMock()
            mock_project.ingress_domain = None
            svc.project = AsyncMock(return_value=mock_project)

            await svc.poll_status(model)

            assert mock_state.kafka_external_url == "198.51.100.50:9094"
            assert mock_state.extra_data.get("load_balancer_ips") == ["198.51.100.50"]


@pytest.mark.asyncio
async def test_kafka_rbac_rendering(mock_service_dependencies):
    """Test that ClusterRole and ClusterRoleBinding for node access are generated."""
    request, session = mock_service_dependencies
    svc = KafkaPlatformService(request, session)

    model = KafkaPlatform(
        name="my-kafka",
        project_id=1,
    )

    svc._resolve_namespace = AsyncMock(return_value="custom-ns")
    mock_project = MagicMock(ingress_domain=None)
    mock_project.name = "mock-project"
    svc.project = AsyncMock(return_value=mock_project)

    manifests = await svc.render_manifests(model)

    assert "kind: ClusterRole" in manifests
    assert "name: my-kafka-custom-ns-node-reader" in manifests
    assert "kind: ClusterRoleBinding" in manifests
    assert "name: my-kafka-custom-ns-node-reader-binding" in manifests
    assert "name: my-kafka-kafka" in manifests


def test_register_poller_invalid_frequency():
    """Verify that register_poller raises ValueError for frequency not multiple of 15."""
    with pytest.raises(ValueError, match="Polling frequency must be set at blocks of 15 seconds"):
        @KafkaPlatformService.register_poller(frequency=25)
        class InvalidPoller:
            pass


@pytest.mark.asyncio
async def test_kafka_default_image_and_chart_locked(test_stack_session):
    """Test that Kafka resolves image and chart versions from test_stack."""
    request = MagicMock(spec=Request)
    svc = KafkaPlatformService(request, test_stack_session)
    model = KafkaPlatform(name="my-kafka", project_id=1)

    svc._resolve_namespace = AsyncMock(return_value="ns")
    mock_project = MagicMock(ingress_domain=None)
    mock_project.name = "mock-project"
    mock_project.stack_id = 1
    svc.project = AsyncMock(return_value=mock_project)

    vars = await svc.template_vars(model)
    assert vars["image"] == "test.registry/citadel/kafka"
    assert vars["image_tag"] == "4.99.0"
    assert vars["chart_repo"] == "https://test.example.com/kafka"
    assert vars["chart_name"] == "kafka"
    assert vars["chart_version"] == "0.99.3"

