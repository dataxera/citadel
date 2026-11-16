# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from mindweaver.config import settings
from mindweaver.service.k8s_cluster.model import K8sCluster, K8sClusterStatus, K8sClusterType
from mindweaver.service.k8s_cluster.service import (
    K8sClusterService,
    build_nodes_details,
    compute_pod_requests,
    parse_k8s_bytes_to_gib,
    parse_k8s_cpu,
)


def _make_node(
    name: str,
    ready: str = "True",
    internal_ip: str | None = "10.0.0.10",
    external_ip: str | None = None,
    version: str = "v1.36.3+k3s1",
    created_at: datetime | None = None,
    cpu: str = "4",
    memory: str = "16Gi",
    ephemeral_storage: str | None = "100Gi",
    labels: dict[str, str] | None = None,
):
    """Build a mock Kubernetes V1Node object for testing."""
    addresses = []
    if internal_ip is not None:
        addresses.append(SimpleNamespace(type="InternalIP", address=internal_ip))
    if external_ip is not None:
        addresses.append(SimpleNamespace(type="ExternalIP", address=external_ip))

    capacity = {"cpu": cpu, "memory": memory}
    if ephemeral_storage is not None:
        capacity["ephemeral-storage"] = ephemeral_storage

    conditions = []
    if ready is not None:
        conditions.append(SimpleNamespace(type="Ready", status=ready))

    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            creation_timestamp=created_at or datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
            labels=labels if labels is not None else {},
        ),
        status=SimpleNamespace(
            conditions=conditions,
            addresses=addresses,
            capacity=capacity,
            node_info=SimpleNamespace(kubelet_version=version),
        ),
    )


def _make_pod(
    node_name: str | None,
    phase: str = "Running",
    containers: list[dict[str, str]] | None = None,
    init_containers: list[tuple[dict[str, str], str | None]] | None = None,
):
    """Build a mock Kubernetes V1Pod object for testing."""
    c_objs = []
    for req in containers or []:
        c_objs.append(
            SimpleNamespace(resources=SimpleNamespace(requests=req))
        )

    ic_objs = []
    for req, restart_policy in init_containers or []:
        ic_objs.append(
            SimpleNamespace(
                resources=SimpleNamespace(requests=req),
                restart_policy=restart_policy,
            )
        )

    return SimpleNamespace(
        spec=SimpleNamespace(
            node_name=node_name,
            containers=c_objs,
            init_containers=ic_objs,
        ),
        status=SimpleNamespace(phase=phase),
    )


def test_parse_k8s_cpu():
    """parse_k8s_cpu converts cores, millicores, nanocores, and invalid values."""
    assert parse_k8s_cpu("4") == pytest.approx(4.0)
    assert parse_k8s_cpu("500m") == pytest.approx(0.5)
    assert parse_k8s_cpu("2500m") == pytest.approx(2.5)
    assert parse_k8s_cpu("100000000n") == pytest.approx(0.1)
    assert parse_k8s_cpu(None) == 0.0
    assert parse_k8s_cpu("") == 0.0
    assert parse_k8s_cpu("invalid") == 0.0


def test_parse_k8s_bytes_to_gib():
    """parse_k8s_bytes_to_gib converts binary/decimal SI units and plain bytes to GiB."""
    assert parse_k8s_bytes_to_gib("1Gi") == pytest.approx(1.0)
    assert parse_k8s_bytes_to_gib("512Mi") == pytest.approx(0.5)
    assert parse_k8s_bytes_to_gib("1048576Ki") == pytest.approx(1.0)
    assert parse_k8s_bytes_to_gib("1Ti") == pytest.approx(1024.0)
    assert parse_k8s_bytes_to_gib(str(10 * 1024**3)) == pytest.approx(10.0)
    assert parse_k8s_bytes_to_gib("1073741824") == pytest.approx(1.0)
    assert parse_k8s_bytes_to_gib("1G") == pytest.approx(1_000_000_000 / (1024**3))
    assert parse_k8s_bytes_to_gib(None) == 0.0
    assert parse_k8s_bytes_to_gib("") == 0.0
    assert parse_k8s_bytes_to_gib("bad") == 0.0


def test_compute_pod_requests_with_init_and_sidecar():
    """compute_pod_requests sums regular + sidecar containers and takes max with standard init containers."""
    pod = _make_pod(
        node_name="worker-1",
        containers=[
            {"cpu": "500m", "memory": "1Gi", "ephemeral-storage": "512Mi"},
            {"cpu": "250m", "memory": "512Mi", "ephemeral-storage": "512Mi"},
        ],
        init_containers=[
            ({"cpu": "1", "memory": "2Gi", "ephemeral-storage": "2Gi"}, None),
            ({"cpu": "250m", "memory": "256Mi", "ephemeral-storage": "128Mi"}, "Always"),
        ],
    )
    cpu, ram, eph = compute_pod_requests(pod)
    # Regular + Always sidecar = 1.0 CPU, 1.75 GiB RAM, 1.125 GiB eph
    # Standard init = 1.0 CPU, 2.0 GiB RAM, 2.0 GiB eph
    assert cpu == pytest.approx(1.0)
    assert ram == pytest.approx(2.0)
    assert eph == pytest.approx(2.0)


def test_build_nodes_details_aggregates_node_and_pod_metrics():
    """build_nodes_details extracts all node fields and sums non-terminated pod requests per node."""
    created = datetime(2026, 8, 21, 10, 0, 0, tzinfo=timezone.utc)
    nodes = [
        _make_node(
            name="cp-1.home.kagesenshi.org",
            ready="True",
            internal_ip="192.168.1.10",
            version="v1.36.3+k3s1",
            created_at=created,
            cpu="8",
            memory="32Gi",
            ephemeral_storage="200Gi",
            labels={
                "node-role.kubernetes.io/etcd": "true",
                "node-role.kubernetes.io/control-plane": "true",
                "kubernetes.io/os": "linux",
            },
        ),
        _make_node(
            name="worker-1.home.kagesenshi.org",
            ready="False",
            internal_ip=None,
            external_ip="203.0.113.5",
            version="v1.36.3+k3s1",
            created_at=created,
            cpu="16",
            memory="64Gi",
            ephemeral_storage=None,
            labels=None,
        ),
    ]
    pods = [
        _make_pod(
            node_name="cp-1.home.kagesenshi.org",
            phase="Running",
            containers=[{"cpu": "1500m", "memory": "4Gi", "ephemeral-storage": "10Gi"}],
        ),
        # Terminated pod should be ignored
        _make_pod(
            node_name="cp-1.home.kagesenshi.org",
            phase="Succeeded",
            containers=[{"cpu": "4", "memory": "16Gi", "ephemeral-storage": "50Gi"}],
        ),
        # Failed pod should be ignored
        _make_pod(
            node_name="worker-1.home.kagesenshi.org",
            phase="Failed",
            containers=[{"cpu": "2", "memory": "8Gi", "ephemeral-storage": "5Gi"}],
        ),
        # Unscheduled pod should be ignored
        _make_pod(
            node_name=None,
            phase="Pending",
            containers=[{"cpu": "2", "memory": "8Gi"}],
        ),
    ]

    nodes_status, node_ips, cpu_total, ram_total, cpu_allocated, ram_allocated, details = build_nodes_details(
        nodes, pods
    )

    assert nodes_status == {
        "cp-1.home.kagesenshi.org": "Ready",
        "worker-1.home.kagesenshi.org": "NotReady",
    }
    assert node_ips == ["192.168.1.10", "203.0.113.5"]
    assert cpu_total == pytest.approx(24.0)
    assert ram_total == pytest.approx(96.0)
    assert cpu_allocated == pytest.approx(1.5)
    assert ram_allocated == pytest.approx(4.0)

    assert len(details) == 2
    cp1 = details[0]
    assert cp1["hostname"] == "cp-1.home.kagesenshi.org"
    assert cp1["ip"] == "192.168.1.10"
    assert cp1["status"] == "Ready"
    assert cp1["roles"] == ["control-plane", "etcd"]
    assert cp1["creation_timestamp"] == created.isoformat()
    assert cp1["version"] == "v1.36.3+k3s1"
    assert cp1["cpu_total"] == pytest.approx(8.0)
    assert cp1["cpu_requested"] == pytest.approx(1.5)
    assert cp1["ram_total"] == pytest.approx(32.0)
    assert cp1["ram_requested"] == pytest.approx(4.0)
    assert cp1["ephemeral_storage_total"] == pytest.approx(200.0)
    assert cp1["ephemeral_storage_requested"] == pytest.approx(10.0)

    w1 = details[1]
    assert w1["hostname"] == "worker-1.home.kagesenshi.org"
    assert w1["ip"] == "203.0.113.5"
    assert w1["status"] == "NotReady"
    assert w1["roles"] == []
    assert w1["ephemeral_storage_total"] == 0.0
    assert w1["ephemeral_storage_requested"] == 0.0


@pytest.mark.asyncio
async def test_poll_status_stores_nodes_details_and_state_exposes_it(
    postgresql_proc, client
):
    """poll_status persists nodes_details and /_state returns it."""
    settings.db_host = postgresql_proc.host
    settings.db_port = postgresql_proc.port
    settings.db_name = postgresql_proc.dbname
    settings.db_user = postgresql_proc.user
    settings.db_pass = postgresql_proc.password

    engine = create_async_engine(settings.db_async_uri)
    async with AsyncSession(engine) as session:
        cluster = K8sCluster(
            name="node-details-cluster",
            title="Node Details Cluster",
            type=K8sClusterType.REMOTE,
            kubeconfig="apiVersion: v1\nkind: Config",
        )
        session.add(cluster)
        await session.commit()
        await session.refresh(cluster)
        cluster_id = cluster.id

        mock_nodes = SimpleNamespace(
            items=[
                _make_node(
                    name="cp-1.home.kagesenshi.org",
                    internal_ip="10.0.0.1",
                    cpu="4",
                    memory="16Gi",
                    ephemeral_storage="80Gi",
                )
            ]
        )
        mock_pods = SimpleNamespace(
            items=[
                _make_pod(
                    node_name="cp-1.home.kagesenshi.org",
                    phase="Running",
                    containers=[{"cpu": "500m", "memory": "2Gi", "ephemeral-storage": "5Gi"}],
                )
            ]
        )

        mock_core_v1 = MagicMock()
        mock_core_v1.list_node.return_value = mock_nodes
        mock_core_v1.list_pod_for_all_namespaces.return_value = mock_pods
        mock_core_v1.list_namespaced_pod.return_value = SimpleNamespace(items=[])

        mock_version_api = MagicMock()
        mock_version_api.get_code.return_value = SimpleNamespace(git_version="v1.36.3+k3s1")

        mock_custom_api = MagicMock()
        mock_custom_api.list_namespaced_custom_object.return_value = {"items": []}

        class MockRequest:
            headers = {}

        svc = K8sClusterService(MockRequest(), session)
        with (
            patch("kubernetes.config.load_kube_config"),
            patch("kubernetes.client.ApiClient"),
            patch("kubernetes.client.CoreV1Api", return_value=mock_core_v1),
            patch("kubernetes.client.VersionApi", return_value=mock_version_api),
            patch("kubernetes.client.CustomObjectsApi", return_value=mock_custom_api),
        ):
            await svc.poll_status(cluster)
            await session.commit()

        with patch(
            "mindweaver.service.k8s_cluster.service.schedule_k8s_cluster_poll"
        ):
            resp = client.get(f"/api/v1/k8s_clusters/{cluster_id}/_state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cpu_allocated"] == pytest.approx(0.5)
        assert data["ram_allocated"] == pytest.approx(2.0)
        assert len(data["nodes_details"]) == 1
        node = data["nodes_details"][0]
        assert node["hostname"] == "cp-1.home.kagesenshi.org"
        assert node["ip"] == "10.0.0.1"
        assert node["status"] == "Ready"
        assert node["version"] == "v1.36.3+k3s1"
        assert node["cpu_total"] == pytest.approx(4.0)
        assert node["cpu_requested"] == pytest.approx(0.5)
        assert node["ram_total"] == pytest.approx(16.0)
        assert node["ram_requested"] == pytest.approx(2.0)
        assert node["ephemeral_storage_total"] == pytest.approx(80.0)
        assert node["ephemeral_storage_requested"] == pytest.approx(5.0)

    await engine.dispose()
