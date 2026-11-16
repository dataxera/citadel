# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from citadel.config import settings
from citadel.service.k8s_cluster.model import (
    K8sCluster,
    K8sClusterStatus,
    K8sClusterType,
)
from citadel.service.k8s_cluster.service import (
    K8sClusterService,
    build_pvs_details,
    query_prometheus_volume_stats,
)
from citadel.service.k8s_cluster.state import K8sClusterState


def _make_pv(
    name: str,
    storage_class: str = "openebs-lvm",
    capacity: str = "20Gi",
    phase: str = "Bound",
    reclaim_policy: str = "Delete",
    access_modes: list[str] | None = None,
    claim_namespace: str | None = "proj-analytics",
    claim_name: str | None = "data-pg-0",
    node_name: str | None = "worker-1",
    created_at: datetime | None = None,
):
    """Build a mock Kubernetes V1PersistentVolume object for testing."""
    claim_ref = (
        SimpleNamespace(namespace=claim_namespace, name=claim_name)
        if claim_namespace and claim_name
        else None
    )
    node_affinity = None
    if node_name:
        node_affinity = SimpleNamespace(
            required=SimpleNamespace(
                node_selector_terms=[
                    SimpleNamespace(
                        match_expressions=[
                            SimpleNamespace(
                                key="kubernetes.io/hostname",
                                operator="In",
                                values=[node_name],
                            )
                        ]
                    )
                ]
            )
        )

    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            creation_timestamp=created_at
            or datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc),
        ),
        spec=SimpleNamespace(
            storage_class_name=storage_class,
            capacity={"storage": capacity} if capacity else {},
            persistent_volume_reclaim_policy=reclaim_policy,
            access_modes=access_modes if access_modes is not None else ["ReadWriteOnce"],
            claim_ref=claim_ref,
            node_affinity=node_affinity,
        ),
        status=SimpleNamespace(phase=phase),
    )


def test_build_pvs_details_with_and_without_telemetry():
    """build_pvs_details extracts PV metadata, node affinity, and merges Prometheus volume stats."""
    pvs = [
        _make_pv(
            name="pvc-111",
            storage_class="openebs-lvm",
            capacity="20Gi",
            phase="Bound",
            claim_namespace="proj-a",
            claim_name="pg-data-0",
            node_name="node-1",
        ),
        _make_pv(
            name="pvc-222",
            storage_class="local-path",
            capacity="50Gi",
            phase="Released",
            reclaim_policy="Retain",
            claim_namespace="proj-b",
            claim_name="kafka-data-0",
            node_name="node-2",
        ),
        _make_pv(
            name="pvc-333",
            storage_class="openebs-lvm",
            capacity="10Gi",
            phase="Available",
            claim_namespace=None,
            claim_name=None,
            node_name=None,
        ),
    ]

    volume_stats = {
        ("proj-a", "pg-data-0"): {
            "used_bytes": 5 * 1024**3,
            "capacity_bytes": 20 * 1024**3,
            "available_bytes": 15 * 1024**3,
        }
    }

    details = build_pvs_details(pvs, volume_stats=volume_stats)
    assert len(details) == 3

    pv1 = details[0]
    assert pv1["name"] == "pvc-111"
    assert pv1["storage_class"] == "openebs-lvm"
    assert pv1["capacity_gib"] == pytest.approx(20.0)
    assert pv1["status"] == "Bound"
    assert pv1["reclaim_policy"] == "Delete"
    assert pv1["access_modes"] == ["ReadWriteOnce"]
    assert pv1["claim_namespace"] == "proj-a"
    assert pv1["claim_name"] == "pg-data-0"
    assert pv1["node_name"] == "node-1"
    assert pv1["used_gib"] == pytest.approx(5.0)
    assert pv1["available_gib"] == pytest.approx(15.0)
    assert pv1["utilization_pct"] == pytest.approx(25.0)

    pv2 = details[1]
    assert pv2["name"] == "pvc-222"
    assert pv2["status"] == "Released"
    assert pv2["used_gib"] is None
    assert pv2["available_gib"] is None
    assert pv2["utilization_pct"] is None

    pv3 = details[2]
    assert pv3["claim_namespace"] is None
    assert pv3["claim_name"] is None
    assert pv3["node_name"] is None


def test_query_prometheus_volume_stats_parses_proxy_response():
    """query_prometheus_volume_stats queries Prometheus via K8s API proxy and maps PVC stats."""
    core_v1 = MagicMock()
    k8s_client = MagicMock()

    prom_svc = SimpleNamespace(
        metadata=SimpleNamespace(name="kube-prometheus-stack-prometheus", namespace="monitoring"),
        spec=SimpleNamespace(ports=[SimpleNamespace(name="http-web", port=9090)]),
    )
    core_v1.list_service_for_all_namespaces.return_value = SimpleNamespace(items=[prom_svc])

    def _mock_call_api(resource_path, method, **kwargs):
        query = dict(kwargs.get("query_params") or []).get("query", "")
        if query == "kubelet_volume_stats_used_bytes":
            payload = {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"namespace": "proj-a", "persistentvolumeclaim": "pg-data-0"},
                            "value": [1700000000, str(4 * 1024**3)],
                        }
                    ]
                },
            }
        elif query == "kubelet_volume_stats_capacity_bytes":
            payload = {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"namespace": "proj-a", "persistentvolumeclaim": "pg-data-0"},
                            "value": [1700000000, str(16 * 1024**3)],
                        }
                    ]
                },
            }
        else:
            payload = {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "metric": {"namespace": "proj-a", "persistentvolumeclaim": "pg-data-0"},
                            "value": [1700000000, str(12 * 1024**3)],
                        }
                    ]
                },
            }
        return json.dumps(payload)

    k8s_client.call_api.side_effect = _mock_call_api

    stats = query_prometheus_volume_stats(core_v1, k8s_client)
    assert ("proj-a", "pg-data-0") in stats
    entry = stats[("proj-a", "pg-data-0")]
    assert entry["used_bytes"] == pytest.approx(4 * 1024**3)
    assert entry["capacity_bytes"] == pytest.approx(16 * 1024**3)
    assert entry["available_bytes"] == pytest.approx(12 * 1024**3)


def test_query_prometheus_volume_stats_handles_missing_prometheus():
    """query_prometheus_volume_stats returns empty dict if no Prometheus service or proxy error."""
    core_v1 = MagicMock()
    k8s_client = MagicMock()
    core_v1.list_service_for_all_namespaces.return_value = SimpleNamespace(items=[])

    assert query_prometheus_volume_stats(core_v1, k8s_client) == {}

    core_v1.list_service_for_all_namespaces.side_effect = RuntimeError("timeout")
    assert query_prometheus_volume_stats(core_v1, k8s_client) == {}


@pytest.mark.asyncio
async def test_poll_status_persists_pvs_details_and_state_exposes_it(
    postgresql_proc, client
):
    """poll_status saves pvs_details into K8sClusterStatus and K8sClusterState returns it."""
    settings.db_host = postgresql_proc.host
    settings.db_port = postgresql_proc.port
    settings.db_name = postgresql_proc.dbname
    settings.db_user = postgresql_proc.user
    settings.db_pass = postgresql_proc.password

    engine = create_async_engine(settings.db_async_uri)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        cluster = K8sCluster(
            name="test-pv-cluster",
            title="Test PV Cluster",
            type=K8sClusterType.IN_CLUSTER,
        )
        session.add(cluster)
        await session.commit()
        await session.refresh(cluster)

        mock_core_v1 = MagicMock()
        mock_core_v1.list_node.return_value = SimpleNamespace(items=[])
        mock_core_v1.list_pod_for_all_namespaces.return_value = SimpleNamespace(items=[])
        mock_core_v1.list_persistent_volume.return_value = SimpleNamespace(
            items=[
                _make_pv(
                    name="pv-test-1",
                    storage_class="openebs-lvm",
                    capacity="10Gi",
                    phase="Bound",
                    claim_namespace="default",
                    claim_name="my-pvc",
                    node_name="node-1",
                )
            ]
        )
        mock_core_v1.list_namespaced_secret.return_value = SimpleNamespace(items=[])
        mock_core_v1.list_namespaced_pod.return_value = SimpleNamespace(items=[])
        mock_core_v1.list_service_for_all_namespaces.return_value = SimpleNamespace(items=[])

        mock_version_api = MagicMock()
        mock_version_api.get_code.return_value = SimpleNamespace(git_version="v1.36.3+k3s1")

        svc = K8sClusterService(None, session)
        with (
            patch("citadel.service.k8s_cluster.service.config.load_incluster_config"),
            patch("citadel.service.k8s_cluster.service.client.CoreV1Api", return_value=mock_core_v1),
            patch("citadel.service.k8s_cluster.service.client.VersionApi", return_value=mock_version_api),
            patch("citadel.service.k8s_cluster.service.client.ApiClient", return_value=MagicMock()),
        ):
            await svc.poll_status(cluster)

        state = K8sClusterState(cluster, svc)
        data = await state.get()
        assert "pvs_details" in data
        assert len(data["pvs_details"]) == 1
        assert data["pvs_details"][0]["name"] == "pv-test-1"
        assert data["pvs_details"][0]["storage_class"] == "openebs-lvm"
        assert data["pvs_details"][0]["capacity_gib"] == pytest.approx(10.0)
        assert data["pvs_details"][0]["node_name"] == "node-1"

    await engine.dispose()
