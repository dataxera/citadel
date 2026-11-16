# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine

from citadel.config import settings
from citadel.platform_service.base import PlatformService
from citadel.platform_service.pgsql import (
    PgSqlPlatform,
    PgSqlPlatformService,
    PgSqlPlatformState,
)
from citadel.platform_service.pgsql.poller import PgSQLPoller
from citadel.service.k8s_cluster import K8sCluster, K8sClusterStatus, K8sClusterType
from citadel.service.k8s_cluster.service import K8sClusterService
from citadel.service.project import Project


class FakeRedis:
    """In-memory fake async Redis client for testing poll deduplication."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def exists(self, key: str) -> int:
        return 1 if key in self.store else 0

    async def delete(self, key: str):
        self.store.pop(key, None)

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_poll_coordinator_deduplicates_within_cooldown():
    """Multiple requests for the same resource within 3s only enqueue 1 poll task."""
    from citadel.tasks import poll_coordinator

    fake_redis = FakeRedis()
    mock_task = MagicMock()

    with patch.object(poll_coordinator, "_get_redis_client", return_value=fake_redis), patch(
        "citadel.tasks.platform_status.poll_platform_status.apply_async", mock_task
    ):
        first = await poll_coordinator.schedule_platform_poll("PgSqlPlatformService", 42)
        second = await poll_coordinator.schedule_platform_poll("PgSqlPlatformService", 42)
        third = await poll_coordinator.schedule_platform_poll("PgSqlPlatformService", 42)

        assert first is True
        assert second is False
        assert third is False
        mock_task.assert_called_once_with(
            args=["PgSqlPlatformService", 42],
            expires=settings.status_polling_expiry,
        )

        # Different resource ID should still be scheduled
        other = await poll_coordinator.schedule_platform_poll("PgSqlPlatformService", 99)
        assert other is True
        assert mock_task.call_count == 2


@pytest.mark.asyncio
async def test_poll_coordinator_skips_when_inflight_lock_held():
    """If an in-flight lock is held, do not enqueue another poll even after cooldown."""
    from citadel.tasks import poll_coordinator

    fake_redis = FakeRedis()
    fake_redis.store["mw:poll:lock:k8s_cluster:7"] = "1"
    mock_task = MagicMock()

    with patch.object(poll_coordinator, "_get_redis_client", return_value=fake_redis), patch(
        "citadel.tasks.k8s_cluster_status.poll_k8s_cluster_status.apply_async", mock_task
    ):
        scheduled = await poll_coordinator.schedule_k8s_cluster_poll(7)
        assert scheduled is False
        mock_task.assert_not_called()


def test_get_state_triggers_demand_poll(client: TestClient, test_project: dict):
    """GET /_state triggers a demand-driven poll for active platforms and k8s clusters."""
    cluster_id = test_project.get("k8s_cluster_id")
    if cluster_id:
        with patch(
            "citadel.service.k8s_cluster.service.schedule_k8s_cluster_poll",
            new_callable=AsyncMock,
        ) as mock_cluster_poll:
            resp = client.get(f"/api/v1/k8s_clusters/{cluster_id}/_state")
            assert resp.status_code == 200
            mock_cluster_poll.assert_awaited_once_with(cluster_id)

    # Create a PgSql platform (not yet deployed -> no state)
    with patch("citadel.platform_service.pgsql.PgSqlPlatformService.poll_status", new_callable=AsyncMock):
        create_resp = client.post(
            "/api/v1/platform/pgsql",
            json={
                "name": "test-pg-demand-poll",
                "title": "Test PG Demand Poll",
                "project_id": test_project["id"],
            },
        )
        assert create_resp.status_code in (200, 201)
        platform_id = create_resp.json()["data"]["id"]

    with patch(
        "citadel.platform_service.base.schedule_platform_poll",
        new_callable=AsyncMock,
    ) as mock_plat_poll:
        state_resp = client.get(f"/api/v1/platform/pgsql/{platform_id}/_state")
        assert state_resp.status_code == 200
        mock_plat_poll.assert_not_awaited()

    # Deploy / activate the PgSql platform, then GET /_state should trigger a poll
    with patch("citadel.platform_service.base.PlatformService.deploy", new_callable=AsyncMock), patch(
        "citadel.platform_service.pgsql.PgSqlPlatformService.poll_status", new_callable=AsyncMock
    ):
        activate_resp = client.post(
            f"/api/v1/platform/pgsql/{platform_id}/_state",
            json={"active": True},
        )
        assert activate_resp.status_code == 200

    with patch(
        "citadel.platform_service.base.schedule_platform_poll",
        new_callable=AsyncMock,
    ) as mock_plat_poll:
        state_resp = client.get(f"/api/v1/platform/pgsql/{platform_id}/_state")
        assert state_resp.status_code == 200
        mock_plat_poll.assert_awaited_once_with("PgSqlPlatformService", platform_id)


@pytest.mark.asyncio
async def test_k8s_cluster_poll_error_preserves_existing_state(postgresql_proc, test_project):
    """K8sClusterService.poll_status must not reset existing fields on error."""
    settings.db_host = postgresql_proc.host
    settings.db_port = postgresql_proc.port
    settings.db_name = postgresql_proc.dbname
    settings.db_user = postgresql_proc.user
    settings.db_pass = postgresql_proc.password

    engine = create_async_engine(settings.db_async_uri)
    async with AsyncSession(engine) as session:
        cluster = K8sCluster(
            name="test-preserve-cluster",
            title="Test Preserve Cluster",
            type=K8sClusterType.REMOTE,
            kubeconfig="apiVersion: v1\nkind: Config",
        )
        session.add(cluster)
        await session.flush()

        status_model = K8sClusterStatus(
            k8s_cluster_id=cluster.id,
            status="online",
            node_count=3,
            nodes_status={"node-1": "Ready"},
            node_ips=[{"hostname": "node-1", "ipv4": "10.0.0.1"}],
            cpu_total=16.0,
            ram_total=64.0,
            argocd_installed=True,
            cert_manager_installed=True,
            cnpg_installed=True,
            envoy_gateway_installed=True,
        )
        session.add(status_model)
        await session.commit()
        await session.refresh(cluster)

        class MockRequest:
            headers = {}

        svc = K8sClusterService(MockRequest(), session)
        with patch("kubernetes.config.new_client_from_config", side_effect=RuntimeError("timeout")):
            await svc.poll_status(cluster)
            await session.commit()

        await session.refresh(status_model)
        assert status_model.status == "error"
        assert "Cluster is unreachable" in (status_model.message or "")
        # Existing values must be preserved!
        assert status_model.node_count == 3
        assert status_model.nodes_status == {"node-1": "Ready"}
        assert status_model.node_ips == [{"hostname": "node-1", "ipv4": "10.0.0.1"}]
        assert status_model.cpu_total == 16.0
        assert status_model.ram_total == 64.0
        assert status_model.argocd_installed is True
        assert status_model.cert_manager_installed is True
        assert status_model.cnpg_installed is True
        assert status_model.envoy_gateway_installed is True

    await engine.dispose()


@pytest.mark.asyncio
async def test_mark_cluster_services_unreachable_preserves_state(postgresql_proc, test_project):
    """mark_cluster_services_unreachable must not clear node_ports, cluster_nodes, or URIs."""
    settings.db_host = postgresql_proc.host
    settings.db_port = postgresql_proc.port
    settings.db_name = postgresql_proc.dbname
    settings.db_user = postgresql_proc.user
    settings.db_pass = postgresql_proc.password

    engine = create_async_engine(settings.db_async_uri)
    async with AsyncSession(engine) as session:
        db_project = await session.get(Project, test_project["id"])
        cluster_id = db_project.k8s_cluster_id
        platform = PgSqlPlatform(
            name="test-pg-preserve",
            title="Test PG Preserve",
            project_id=db_project.id,
        )
        session.add(platform)
        await session.flush()

        state = PgSqlPlatformState(
            platform_id=platform.id,
            status="online",
            active=True,
            node_ports=[{"name": "pg-rw", "port": 5432, "node_port": 30432}],
            cluster_nodes=[{"hostname": "node-1", "ipv4": "10.0.0.1", "ipv6": None}],
            extra_data={"phase": "Cluster in healthy state"},
        )
        session.add(state)
        await session.commit()
        await session.refresh(platform)

        await PlatformService.mark_cluster_services_unreachable(
            session, cluster_id, "test-cluster", "connection refused"
        )
        await session.commit()
        await session.refresh(state)

        assert state.status == "error"
        assert "connection refused" in (state.message or "")
        assert state.node_ports == [{"name": "pg-rw", "port": 5432, "node_port": 30432}]
        assert state.cluster_nodes == [{"hostname": "node-1", "ipv4": "10.0.0.1", "ipv6": None}]
        assert state.extra_data == {"phase": "Cluster in healthy state"}

    await engine.dispose()


@pytest.mark.asyncio
async def test_pgsql_poller_error_preserves_existing_state(postgresql_proc, test_project):
    """PgSQLPoller must not overwrite extra_data, node_ports, cluster_nodes on K8s error."""
    settings.db_host = postgresql_proc.host
    settings.db_port = postgresql_proc.port
    settings.db_name = postgresql_proc.dbname
    settings.db_user = postgresql_proc.user
    settings.db_pass = postgresql_proc.password

    engine = create_async_engine(settings.db_async_uri)
    async with AsyncSession(engine) as session:
        platform = PgSqlPlatform(
            name="test-pg-poller-preserve",
            title="Test PG Poller Preserve",
            project_id=test_project["id"],
        )
        session.add(platform)
        await session.flush()

        state = PgSqlPlatformState(
            platform_id=platform.id,
            status="online",
            active=True,
            node_ports=[{"name": "pg-rw", "port": 5432, "node_port": 30432}],
            cluster_nodes=[{"hostname": "node-1", "ipv4": "10.0.0.1", "ipv6": None}],
            extra_data={"phase": "Cluster in healthy state"},
            db_user="app",
            db_name="app",
        )
        session.add(state)
        await session.commit()
        await session.refresh(platform)

        class MockRequest:
            headers = {}

        svc = PgSqlPlatformService(MockRequest(), session)
        poller = PgSQLPoller(svc, platform)

        with patch("kubernetes.config.new_client_from_config"), patch(
            "kubernetes.client.CustomObjectsApi"
        ) as mock_custom:
            mock_custom.return_value.get_namespaced_custom_object.side_effect = RuntimeError("k8s down")
            await poller.poll()
            await session.commit()

        await session.refresh(state)
        assert state.status == "error"
        assert "k8s down" in (state.message or "")
        assert state.node_ports == [{"name": "pg-rw", "port": 5432, "node_port": 30432}]
        assert state.cluster_nodes == [{"hostname": "node-1", "ipv4": "10.0.0.1", "ipv6": None}]
        assert state.extra_data == {"phase": "Cluster in healthy state"}
        assert state.db_user == "app"
        assert state.db_name == "app"

    await engine.dispose()
