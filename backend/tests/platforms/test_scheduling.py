# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import yaml
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mindweaver.fw.model import AsyncSession
from mindweaver.platform_service.base import PlatformDeploymentMethod
from mindweaver.platform_service.pgsql import PgSqlPlatform, PgSqlPlatformService
from mindweaver.platform_service.hive_metastore import (
    HiveMetastorePlatform,
    HiveMetastorePlatformService,
)
from mindweaver.platform_service.trino import TrinoPlatform, TrinoPlatformService
from mindweaver.platform_service.superset import (
    SupersetPlatform,
    SupersetPlatformService,
)
from mindweaver.platform_service.airflow import AirflowPlatform, AirflowPlatformService
from mindweaver.platform_service.kafka import KafkaPlatform, KafkaPlatformService
from mindweaver.platform_service.nifi import NifiPlatform, NifiPlatformService
from mindweaver.platform_service.doris import DorisPlatform, DorisPlatformService
from mindweaver.service.k8s_cluster.model import DEFAULT_NODE_ROLES


def _mock_request_session():
    request = MagicMock(spec=Request)
    session = MagicMock(spec=AsyncSession)
    mock_exec_result = MagicMock()
    mock_exec_result.all.return_value = []
    mock_exec_result.first.return_value = None
    mock_exec_result.one_or_none.return_value = None
    session.exec = AsyncMock(return_value=mock_exec_result)
    session.flush = AsyncMock()
    return request, session


def test_platform_scheduling_defaults():
    """Verify PlatformBase models default cluster_role=None and deployment_method=default."""
    model = KafkaPlatform(name="test-kafka", title="Test Kafka", project_id=1)
    assert model.cluster_role is None
    assert model.deployment_method == PlatformDeploymentMethod.DEFAULT


def test_cluster_role_validation():
    """Verify cluster_role coerces empty strings to None and rejects invalid/protected roles."""
    m_empty = KafkaPlatform.model_validate(
        {"name": "k1", "title": "K1", "project_id": 1, "cluster_role": "  "}
    )
    assert m_empty.cluster_role is None

    m_valid = KafkaPlatform.model_validate(
        {"name": "k2", "title": "K2", "project_id": 1, "cluster_role": "queue"}
    )
    assert m_valid.cluster_role == "queue"

    for bad_role in ["control-plane", "master", "etcd", "bad role!"]:
        with pytest.raises(ValidationError):
            KafkaPlatform.model_validate(
                {"name": "k3", "title": "K3", "project_id": 1, "cluster_role": bad_role}
            )


def test_all_platform_services_expose_scheduling_widgets():
    """Verify all 8 platform services include cluster_role and deployment_method widgets."""
    services = [
        PgSqlPlatformService,
        HiveMetastorePlatformService,
        TrinoPlatformService,
        SupersetPlatformService,
        AirflowPlatformService,
        KafkaPlatformService,
        NifiPlatformService,
        DorisPlatformService,
    ]
    for svc_cls in services:
        widgets = svc_cls.widgets()
        assert "cluster_role" in widgets, f"{svc_cls.__name__} missing cluster_role widget"
        assert "deployment_method" in widgets, f"{svc_cls.__name__} missing deployment_method widget"
        assert widgets["cluster_role"]["type"] == "select"
        assert widgets["cluster_role"]["endpoint"].endswith("/_cluster-roles")
        assert widgets["deployment_method"]["type"] == "select"
        values = [opt["value"] for opt in widgets["deployment_method"]["options"]]
        assert set(values) == {m.value for m in PlatformDeploymentMethod}


def test_cluster_roles_endpoint(client: TestClient, test_project):
    """Verify /_cluster-roles returns defaults without cluster and custom roles when cluster is attached."""
    headers = {"x-project-id": str(test_project["id"])}
    resp = client.get("/api/v1/platform/pgsql/_cluster-roles", headers=headers)
    resp.raise_for_status()
    values = [item["value"] for item in resp.json()]
    for r in DEFAULT_NODE_ROLES:
        assert r in values

    cluster_resp = client.post(
        "/api/v1/k8s_clusters",
        json={
            "name": "sched-cluster",
            "title": "Sched Cluster",
            "type": "remote",
            "kubeconfig": "dummy-kubeconfig",
        },
    )
    cluster_resp.raise_for_status()
    cluster_id = cluster_resp.json()["data"]["id"]

    topo_resp = client.put(
        f"/api/v1/k8s_clusters/{cluster_id}/_topology",
        json={"roles": ["database", "gpu-worker"]},
    )
    topo_resp.raise_for_status()

    proj_resp = client.put(
        f"/api/v1/projects/{test_project['id']}",
        json={
            "name": test_project["name"],
            "title": test_project["title"],
            "description": test_project["description"],
            "k8s_cluster_id": cluster_id,
        },
    )
    proj_resp.raise_for_status()

    resp2 = client.get("/api/v1/platform/pgsql/_cluster-roles", headers=headers)
    resp2.raise_for_status()
    values2 = [item["value"] for item in resp2.json()]
    assert values2 == ["database", "gpu-worker"]


@pytest.mark.parametrize(
    "method,expected_key,expected_kind,expected_topo",
    [
        (PlatformDeploymentMethod.DEFAULT, None, None, None),
        (
            PlatformDeploymentMethod.PREFER_SAME_NODE,
            "podAffinity",
            "preferredDuringSchedulingIgnoredDuringExecution",
            "kubernetes.io/hostname",
        ),
        (
            PlatformDeploymentMethod.PREFER_DIFFERENT_NODES,
            "podAntiAffinity",
            "preferredDuringSchedulingIgnoredDuringExecution",
            "kubernetes.io/hostname",
        ),
        (
            PlatformDeploymentMethod.REQUIRE_DIFFERENT_NODES,
            "podAntiAffinity",
            "requiredDuringSchedulingIgnoredDuringExecution",
            "kubernetes.io/hostname",
        ),
        (
            PlatformDeploymentMethod.PREFER_DIFFERENT_ZONES,
            "podAntiAffinity",
            "preferredDuringSchedulingIgnoredDuringExecution",
            "topology.kubernetes.io/zone",
        ),
        (
            PlatformDeploymentMethod.PREFER_DIFFERENT_RACKS,
            "podAntiAffinity",
            "preferredDuringSchedulingIgnoredDuringExecution",
            "topology.kubernetes.io/rack",
        ),
    ],
)
def test_build_scheduling_config_methods(
    method, expected_key, expected_kind, expected_topo
):
    """Verify build_scheduling_config generates correct Kubernetes affinity structures."""
    request, session = _mock_request_session()
    svc = KafkaPlatformService(request, session)
    model = KafkaPlatform(
        name="kafka-sched",
        title="Kafka Sched",
        project_id=1,
        cluster_role="queue",
        deployment_method=method,
    )
    cfg = svc.build_scheduling_config(model, pod_labels={"strimzi.io/cluster": "kafka-sched"})
    affinity = cfg["affinity"]
    assert "nodeAffinity" in affinity
    expr = affinity["nodeAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"][
        "nodeSelectorTerms"
    ][0]["matchExpressions"][0]
    assert expr == {"key": "node-role.kubernetes.io/queue", "operator": "Exists"}

    if expected_key is None:
        assert "podAffinity" not in affinity
        assert "podAntiAffinity" not in affinity
    else:
        assert expected_key in affinity
        rules = affinity[expected_key][expected_kind]
        term = rules[0]["podAffinityTerm"] if "podAffinityTerm" in rules[0] else rules[0]
        assert term["topologyKey"] == expected_topo
        assert term["labelSelector"]["matchLabels"] == {"strimzi.io/cluster": "kafka-sched"}


@pytest.mark.asyncio
async def test_render_manifests_includes_scheduling_for_all_services():
    """Verify all 8 platform services render valid YAML with cluster_role and deployment_method."""
    request, session = _mock_request_session()

    mock_pgsql_svc = AsyncMock()
    mock_pgsql_model = MagicMock()
    mock_pgsql_model.name = "test-pgsql"
    mock_pgsql_svc.get.return_value = mock_pgsql_model
    mock_pgsql_state = MagicMock()
    mock_pgsql_state.active = True
    mock_pgsql_state.db_user = "app_user"
    mock_pgsql_state.db_name = "app_db"
    mock_pgsql_state.db_pass = "secret"
    mock_pgsql_svc.platform_state.return_value = mock_pgsql_state

    mock_s3_svc = AsyncMock()
    mock_s3_model = MagicMock()
    mock_s3_model.endpoint_url = "http://minio:9000"
    mock_s3_model.access_key = "ak"
    mock_s3_model.secret_key = "sk"
    mock_s3_svc.get.return_value = mock_s3_model

    # 1. PgSql
    pgsql_svc = PgSqlPlatformService(request, session)
    pgsql_model = PgSqlPlatform(
        name="pg-sched",
        title="PG Sched",
        project_id=1,
        cluster_role="database",
        deployment_method=PlatformDeploymentMethod.REQUIRE_DIFFERENT_NODES,
    )
    pg_docs = list(yaml.safe_load_all(await pgsql_svc.render_manifests(pgsql_model)))
    pg_app = next(d for d in pg_docs if d and d.get("kind") == "Application")
    pg_vals = yaml.safe_load(pg_app["spec"]["source"]["helm"]["values"])
    assert "nodeAffinity" in pg_vals["cluster"]["affinity"]
    assert "additionalPodAntiAffinity" in pg_vals["cluster"]["affinity"]

    # 2. Hive Metastore
    hms_svc = HiveMetastorePlatformService(request, session)
    hms_model = HiveMetastorePlatform(
        name="hms-sched",
        title="HMS Sched",
        project_id=1,
        database_id=1,
        s3_storage_id=1,
        cluster_role="warehouse",
        deployment_method=PlatformDeploymentMethod.PREFER_DIFFERENT_NODES,
    )
    with (
        patch(
            "mindweaver.platform_service.hive_metastore.service.PgSqlPlatformService.get_service",
            AsyncMock(return_value=mock_pgsql_svc),
        ),
        patch(
            "mindweaver.platform_service.hive_metastore.service.S3StorageService.get_service",
            AsyncMock(return_value=mock_s3_svc),
        ),
    ):
        hms_docs = list(yaml.safe_load_all(await hms_svc.render_manifests(hms_model)))
    hms_app = next(d for d in hms_docs if d and d.get("kind") == "Application")
    hms_vals = yaml.safe_load(hms_app["spec"]["source"]["helm"]["values"])
    assert "nodeAffinity" in hms_vals["affinity"]
    assert "podAntiAffinity" in hms_vals["affinity"]

    # 3. Trino
    trino_svc = TrinoPlatformService(request, session)
    trino_model = TrinoPlatform(
        name="trino-sched",
        title="Trino Sched",
        project_id=1,
        cluster_role="compute",
        deployment_method=PlatformDeploymentMethod.PREFER_SAME_NODE,
    )
    mock_project = MagicMock()
    mock_project.name = "mock-project"
    mock_project.title = "Mock Project"
    mock_project.ingress_domain = "example.com"
    mock_project.ldap_config_id = None
    with patch.object(trino_svc, "project", AsyncMock(return_value=mock_project)):
        trino_docs = list(yaml.safe_load_all(await trino_svc.render_manifests(trino_model)))
    trino_app = next(d for d in trino_docs if d and d.get("kind") == "Application")
    trino_vals = yaml.safe_load(trino_app["spec"]["source"]["helm"]["values"])
    assert "nodeAffinity" in trino_vals["coordinator"]["affinity"]
    assert "podAffinity" in trino_vals["worker"]["affinity"]

    # 4. Superset
    superset_svc = SupersetPlatformService(request, session)
    superset_model = SupersetPlatform(
        name="superset-sched",
        title="Superset Sched",
        project_id=1,
        platform_pgsql_id=1,
        cluster_role="application",
        deployment_method=PlatformDeploymentMethod.PREFER_DIFFERENT_ZONES,
    )
    with (
        patch.object(superset_svc, "project", AsyncMock(return_value=mock_project)),
        patch(
            "mindweaver.platform_service.superset.service.PgSqlPlatformService.get_service",
            AsyncMock(return_value=mock_pgsql_svc),
        ),
    ):
        sup_docs = list(
            yaml.safe_load_all(await superset_svc.render_manifests(superset_model))
        )
    sup_app = next(d for d in sup_docs if d and d.get("kind") == "Application")
    sup_vals = yaml.safe_load(sup_app["spec"]["source"]["helm"]["values"])
    assert "nodeAffinity" in sup_vals["affinity"]
    assert "podAntiAffinity" in sup_vals["affinity"]

    # 5. Airflow
    airflow_svc = AirflowPlatformService(request, session)
    airflow_model = AirflowPlatform(
        name="airflow-sched",
        title="Airflow Sched",
        project_id=1,
        platform_pgsql_id=1,
        cluster_role="compute",
        deployment_method=PlatformDeploymentMethod.PREFER_DIFFERENT_RACKS,
    )
    with (
        patch.object(airflow_svc, "project", AsyncMock(return_value=mock_project)),
        patch(
            "mindweaver.platform_service.airflow.service.PgSqlPlatformService.get_service",
            AsyncMock(return_value=mock_pgsql_svc),
        ),
    ):
        af_docs = list(
            yaml.safe_load_all(await airflow_svc.render_manifests(airflow_model))
        )
    af_app = next(d for d in af_docs if d and d.get("kind") == "Application")
    af_vals = yaml.safe_load(af_app["spec"]["source"]["helm"]["values"])
    assert "nodeAffinity" in af_vals["affinity"]
    assert "podAntiAffinity" in af_vals["affinity"]

    # 6. Kafka
    kafka_svc = KafkaPlatformService(request, session)
    kafka_model = KafkaPlatform(
        name="kafka-sched",
        title="Kafka Sched",
        project_id=1,
        cluster_role="queue",
        deployment_method=PlatformDeploymentMethod.REQUIRE_DIFFERENT_NODES,
    )
    kafka_docs = list(yaml.safe_load_all(await kafka_svc.render_manifests(kafka_model)))
    kafka_app = next(d for d in kafka_docs if d and d.get("kind") == "Application")
    kafka_vals = yaml.safe_load(kafka_app["spec"]["source"]["helm"]["values"])
    assert "nodeAffinity" in kafka_vals["controller"]["affinity"]
    assert "podAntiAffinity" in kafka_vals["controller"]["affinity"]

    # 7. NiFi
    nifi_svc = NifiPlatformService(request, session)
    nifi_model = NifiPlatform(
        name="nifi-sched",
        title="NiFi Sched",
        project_id=1,
        cluster_role="ingest",
        deployment_method=PlatformDeploymentMethod.PREFER_DIFFERENT_NODES,
    )
    nifi_docs = list(yaml.safe_load_all(await nifi_svc.render_manifests(nifi_model)))
    nifi_app = next(d for d in nifi_docs if d and d.get("kind") == "Application")
    nifi_vals = yaml.safe_load(nifi_app["spec"]["source"]["helm"]["values"])
    ng = nifi_vals["cluster"]["nodeConfigGroups"]["default-group"]
    assert "nodeAffinity" in ng
    assert "podAntiAffinity" in ng

    # 8. Doris
    doris_svc = DorisPlatformService(request, session)
    doris_model = DorisPlatform(
        name="doris-sched",
        title="Doris Sched",
        project_id=1,
        cluster_role="warehouse",
        deployment_method=PlatformDeploymentMethod.PREFER_DIFFERENT_NODES,
    )
    doris_docs = list(yaml.safe_load_all(await doris_svc.render_manifests(doris_model)))
    doris_app = next(d for d in doris_docs if d and d.get("kind") == "Application")
    doris_vals = yaml.safe_load(doris_app["spec"]["source"]["helm"]["values"])
    assert "nodeAffinity" in doris_vals["feSpec"]["affinity"]
    assert "podAntiAffinity" in doris_vals["beSpec"]["affinity"]
    doris_job = next(d for d in doris_docs if d and d.get("kind") == "Job")
    assert "nodeAffinity" in doris_job["spec"]["template"]["spec"]["affinity"]
