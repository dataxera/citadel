# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import Request
from kubernetes.client.exceptions import ApiException
from sqlmodel import Session

from citadel.platform_service.airflow import AirflowPlatformService
from citadel.platform_service.doris import DorisPlatformService
from citadel.platform_service.hive_metastore import HiveMetastorePlatformService
from citadel.platform_service.kafka import KafkaPlatformService
from citadel.platform_service.nifi import NifiPlatformService
from citadel.platform_service.pgsql import PgSqlPlatformService
from citadel.platform_service.superset import SupersetPlatformService
from citadel.platform_service.trino import TrinoPlatformService


@pytest.fixture
def mock_service_deps():
    """Return mocked request and session dependencies for platform services."""
    request = MagicMock(spec=Request)
    session = MagicMock(spec=Session)
    return request, session


@pytest.mark.parametrize(
    "service_cls",
    [
        AirflowPlatformService,
        DorisPlatformService,
        HiveMetastorePlatformService,
        KafkaPlatformService,
        NifiPlatformService,
        PgSqlPlatformService,
        SupersetPlatformService,
        TrinoPlatformService,
    ],
)
def test_restart_service_action_registered_on_all_platform_services(service_cls):
    """Verify restart_service action is inherited by every platform service."""
    actions = service_cls.get_actions()
    assert "restart_service" in actions


@pytest.mark.asyncio
async def test_restart_service_action_available(mock_service_deps):
    """Verify RestartServiceAction.available reflects active platform state."""
    request, session = mock_service_deps
    svc = TrinoPlatformService(request, session)
    model = SimpleNamespace(id=1, name="trino-1")

    action_cls = TrinoPlatformService.get_actions()["restart_service"]
    action = action_cls(model, svc)

    svc.platform_state = AsyncMock(return_value=None)
    assert await action.available() is False

    svc.platform_state = AsyncMock(return_value=SimpleNamespace(active=False))
    assert await action.available() is False

    svc.platform_state = AsyncMock(return_value=SimpleNamespace(active=True))
    assert await action.available() is True


@pytest.mark.asyncio
async def test_base_restart_service_restarts_argocd_and_labeled_workloads(
    mock_service_deps,
):
    """Verify default restart_service patches Deployments and StatefulSets."""
    request, session = mock_service_deps
    svc = TrinoPlatformService(request, session)
    model = SimpleNamespace(id=1, name="trino-1")

    svc.kubeconfig = AsyncMock(return_value=None)
    svc._resolve_namespace = AsyncMock(return_value="proj-ns")

    mock_custom_api = MagicMock()
    mock_custom_api.get_namespaced_custom_object.return_value = {
        "status": {
            "resources": [
                {
                    "kind": "Deployment",
                    "name": "trino-1-coordinator",
                    "namespace": "proj-ns",
                },
                {
                    "kind": "StatefulSet",
                    "name": "trino-1-worker",
                    "namespace": "proj-ns",
                },
                {
                    "kind": "Service",
                    "name": "trino-1",
                    "namespace": "proj-ns",
                },
            ]
        }
    }

    mock_apps_api = MagicMock()
    mock_apps_api.list_namespaced_deployment.return_value = SimpleNamespace(
        items=[SimpleNamespace(metadata=SimpleNamespace(name="trino-1-coordinator"))]
    )
    mock_apps_api.list_namespaced_stateful_set.return_value = SimpleNamespace(items=[])

    with (
        patch("citadel.platform_service.base.config.load_incluster_config"),
        patch("citadel.platform_service.base.client.ApiClient"),
        patch(
            "citadel.platform_service.base.client.CustomObjectsApi",
            return_value=mock_custom_api,
        ),
        patch(
            "citadel.platform_service.base.client.AppsV1Api",
            return_value=mock_apps_api,
        ),
    ):
        result = await svc.restart_service(model)

    assert result["status"] == "success"
    assert ("Deployment/trino-1-coordinator") in result["restarted"]
    assert ("StatefulSet/trino-1-worker") in result["restarted"]
    assert len(result["restarted"]) == 2
    mock_apps_api.patch_namespaced_deployment.assert_called_once()
    mock_apps_api.patch_namespaced_stateful_set.assert_called_once()


@pytest.mark.asyncio
async def test_base_restart_service_raises_when_no_workloads_found(mock_service_deps):
    """Verify restart_service raises RuntimeError if no workloads are discovered."""
    request, session = mock_service_deps
    svc = TrinoPlatformService(request, session)
    model = SimpleNamespace(id=1, name="trino-empty")

    svc.kubeconfig = AsyncMock(return_value=None)
    svc._resolve_namespace = AsyncMock(return_value="proj-ns")

    mock_custom_api = MagicMock()
    mock_custom_api.get_namespaced_custom_object.side_effect = ApiException(
        status=404, reason="Not Found"
    )
    mock_apps_api = MagicMock()
    mock_apps_api.list_namespaced_deployment.return_value = SimpleNamespace(items=[])
    mock_apps_api.list_namespaced_stateful_set.return_value = SimpleNamespace(items=[])

    with (
        patch("citadel.platform_service.base.config.load_incluster_config"),
        patch("citadel.platform_service.base.client.ApiClient"),
        patch(
            "citadel.platform_service.base.client.CustomObjectsApi",
            return_value=mock_custom_api,
        ),
        patch(
            "citadel.platform_service.base.client.AppsV1Api",
            return_value=mock_apps_api,
        ),
    ):
        with pytest.raises(RuntimeError, match="No restartable workloads found"):
            await svc.restart_service(model)


@pytest.mark.asyncio
async def test_pgsql_restart_service_patches_cnpg_cluster_and_pooler(mock_service_deps):
    """Verify PgSqlPlatformService.restart_service patches CNPG Cluster and pooler."""
    request, session = mock_service_deps
    svc = PgSqlPlatformService(request, session)
    model = SimpleNamespace(id=1, name="pg-main")

    svc.kubeconfig = AsyncMock(return_value=None)
    svc._resolve_namespace = AsyncMock(return_value="proj-ns")

    mock_custom_api = MagicMock()
    mock_apps_api = MagicMock()
    mock_apps_api.list_namespaced_deployment.return_value = SimpleNamespace(
        items=[SimpleNamespace(metadata=SimpleNamespace(name="pg-main-rw"))]
    )

    with (
        patch.object(svc, "_build_k8s_client", return_value=MagicMock()),
        patch(
            "citadel.platform_service.pgsql.service.client.CustomObjectsApi",
            return_value=mock_custom_api,
        ),
        patch(
            "citadel.platform_service.pgsql.service.client.AppsV1Api",
            return_value=mock_apps_api,
        ),
    ):
        result = await svc.restart_service(model)

    assert result["status"] == "success"
    assert "Cluster/pg-main" in result["restarted"]
    assert "Deployment/pg-main-rw" in result["restarted"]
    mock_custom_api.patch_namespaced_custom_object.assert_called_once()
    mock_apps_api.patch_namespaced_deployment.assert_called_once()


@pytest.mark.asyncio
async def test_kafka_restart_service_patches_strimzipodsets_and_deployments(
    mock_service_deps,
):
    """Verify KafkaPlatformService.restart_service annotates StrimziPodSets."""
    request, session = mock_service_deps
    svc = KafkaPlatformService(request, session)
    model = SimpleNamespace(id=1, name="kafka-1")

    svc.kubeconfig = AsyncMock(return_value=None)
    svc._resolve_namespace = AsyncMock(return_value="proj-ns")

    mock_custom_api = MagicMock()
    mock_custom_api.list_namespaced_custom_object.return_value = {
        "items": [{"metadata": {"name": "kafka-1-broker"}}]
    }
    mock_apps_api = MagicMock()
    mock_apps_api.list_namespaced_deployment.return_value = SimpleNamespace(
        items=[SimpleNamespace(metadata=SimpleNamespace(name="kafka-1-entity-operator"))]
    )

    with (
        patch.object(svc, "_build_k8s_client", return_value=MagicMock()),
        patch(
            "citadel.platform_service.kafka.service.client.CustomObjectsApi",
            return_value=mock_custom_api,
        ),
        patch(
            "citadel.platform_service.kafka.service.client.AppsV1Api",
            return_value=mock_apps_api,
        ),
    ):
        result = await svc.restart_service(model)

    assert result["status"] == "success"
    assert "StrimziPodSet/kafka-1-broker" in result["restarted"]
    assert "Deployment/kafka-1-entity-operator" in result["restarted"]
    mock_custom_api.patch_namespaced_custom_object.assert_called_once()
    mock_apps_api.patch_namespaced_deployment.assert_called_once()


@pytest.mark.asyncio
async def test_doris_restart_service_patches_fe_and_be_statefulsets(mock_service_deps):
    """Verify DorisPlatformService.restart_service restarts FE and BE StatefulSets."""
    request, session = mock_service_deps
    svc = DorisPlatformService(request, session)
    model = SimpleNamespace(id=1, name="doris-1")

    svc.kubeconfig = AsyncMock(return_value=None)
    svc._resolve_namespace = AsyncMock(return_value="proj-ns")

    mock_apps_api = MagicMock()
    mock_apps_api.list_namespaced_stateful_set.return_value = SimpleNamespace(
        items=[
            SimpleNamespace(metadata=SimpleNamespace(name="doris-1-fe")),
            SimpleNamespace(metadata=SimpleNamespace(name="doris-1-be")),
            SimpleNamespace(metadata=SimpleNamespace(name="other-sts")),
        ]
    )

    with (
        patch.object(svc, "_build_k8s_client", return_value=MagicMock()),
        patch(
            "citadel.platform_service.doris.service.client.AppsV1Api",
            return_value=mock_apps_api,
        ),
    ):
        result = await svc.restart_service(model)

    assert result["status"] == "success"
    assert result["restarted"] == ["StatefulSet/doris-1-fe", "StatefulSet/doris-1-be"]
    assert mock_apps_api.patch_namespaced_stateful_set.call_count == 2
