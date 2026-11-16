# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient
from citadel.app import app
from citadel.platform_service.airflow.service import AirflowPlatformService
from citadel.platform_service.airflow.model import AirflowPlatform
from citadel.crypto import encrypt_password, decrypt_password


def test_airflow_platform_crud(client: TestClient, test_project):
    # 1. Update Project with K8s info
    project_update = {
        "name": test_project["name"],
        "title": test_project["title"],
        "description": test_project["description"],
        "k8s_cluster_id": test_project["k8s_cluster_id"],
        "k8s_cluster_type": "remote",
        "k8s_cluster_kubeconfig": 'apiVersion: v1\nkind: Config\nclusters: []\ncontexts: []\ncurrent-context: ""\nusers: []',
    }
    resp = client.put(
        f"/api/v1/projects/{test_project['id']}",
        json=project_update,
        headers={"X-Project-Id": str(test_project["id"])},
    )
    resp.raise_for_status()

    # 1.1 Create pgsql platform (dependency for Airflow)
    pgsql_data = {
        "name": "airflow-db",
        "title": "Airflow PG DB",
        "project_id": test_project["id"],
    }
    resp = client.post(
        "/api/v1/platform/pgsql",
        json=pgsql_data,
        headers={"X-Project-Id": str(test_project["id"])},
    )
    resp.raise_for_status()
    pgsql_id = resp.json()["data"]["id"]

    # 1.2 Create SSH Key
    ssh_data = {
        "name": "airflow-ssh",
        "title": "Airflow SSH",
        "project_id": test_project["id"],
        "algorithm": "rsa",
        "key_size": 4096,
    }
    resp = client.post(
        "/api/v1/ssh_keys",
        json=ssh_data,
        headers={"X-Project-Id": str(test_project["id"])},
    )
    resp.raise_for_status()

    # 1.3 Create Git repository with SSH
    git_data = {
        "name": "dags-repo",
        "title": "DAGs Repo",
        "project_id": test_project["id"],
        "url": "git@github.com:myorg/dags.git",
        "ssh_key_id": resp.json()["data"]["id"],
    }
    resp = client.post(
        "/api/v1/git_repos",
        json=git_data,
        headers={"X-Project-Id": str(test_project["id"])},
    )
    resp.raise_for_status()
    git_repo_id = resp.json()["data"]["id"]

    # 2. Create Airflow Platform referencing the Git Repo
    airflow_data = {
        "name": "my-airflow",
        "title": "My Airflow",
        "project_id": test_project["id"],
        "platform_pgsql_id": pgsql_id,
        "dags_git_sync_enabled": True,
        "git_repo_id": git_repo_id,
    }
    resp = client.post(
        "/api/v1/platform/airflow",
        json=airflow_data,
        headers={"X-Project-Id": str(test_project["id"])},
    )
    resp.raise_for_status()
    airflow_id = resp.json()["data"]["id"]
    assert resp.json()["data"]["git_repo_id"] == git_repo_id

    # 3. Read
    resp = client.get(
        f"/api/v1/platform/airflow/{airflow_id}",
        headers={"X-Project-Id": str(test_project["id"])},
    )
    resp.raise_for_status()
    assert resp.json()["data"]["git_repo_id"] == git_repo_id
    assert resp.json()["data"]["redis_password"] == "__REDACTED__"

    # 4. Update
    update_data = {
        "name": "my-airflow",
        "title": "My Airflow Updated",
        "project_id": test_project["id"],
        "platform_pgsql_id": pgsql_id,
        "dags_git_sync_enabled": True,
        "git_repo_id": git_repo_id,
        "dags_git_branch": "develop",
    }
    resp = client.put(
        f"/api/v1/platform/airflow/{airflow_id}",
        json=update_data,
        headers={"X-Project-Id": str(test_project["id"])},
    )
    resp.raise_for_status()
    assert resp.json()["data"]["title"] == "My Airflow Updated"
    assert resp.json()["data"]["dags_git_branch"] == "develop"

    # 5. Delete
    resp = client.delete(
        f"/api/v1/platform/airflow/{airflow_id}",
        headers={
            "X-Project-Id": str(test_project["id"]),
            "X-RESOURCE-NAME": "my-airflow",
        },
    )
    resp.raise_for_status()


def test_airflow_platform_git_repo_validation(client: TestClient, test_project):
    # 1. Update Project with K8s info
    project_update = {
        "name": test_project["name"],
        "title": test_project["title"],
        "description": test_project["description"],
        "k8s_cluster_id": test_project["k8s_cluster_id"],
        "k8s_cluster_type": "remote",
        "k8s_cluster_kubeconfig": 'apiVersion: v1\nkind: Config\nclusters: []\ncontexts: []\ncurrent-context: ""\nusers: []',
    }
    resp = client.put(
        f"/api/v1/projects/{test_project['id']}",
        json=project_update,
        headers={"X-Project-Id": str(test_project["id"])},
    )
    resp.raise_for_status()

    # Create project 2 programmatically
    proj2_data = {
        "name": "project-2",
        "title": "Project 2",
        "description": "Another test project",
        "k8s_cluster_id": test_project["k8s_cluster_id"],
    }
    resp = client.post("/api/v1/projects", json=proj2_data)
    resp.raise_for_status()
    project_2 = resp.json()["data"]

    # 1.1 Setup PG DB in project 1
    pgsql_data = {
        "name": "airflow-db-val",
        "title": "Airflow PG DB Validation",
        "project_id": test_project["id"],
    }
    resp = client.post(
        "/api/v1/platform/pgsql",
        json=pgsql_data,
        headers={"X-Project-Id": str(test_project["id"])},
    )
    resp.raise_for_status()
    pgsql_id = resp.json()["data"]["id"]

    # 2. Setup GitRepo in project 2 (cross-project)
    git_data = {
        "name": "dags-repo-cross",
        "title": "DAGs Repo Cross",
        "project_id": project_2["id"],
        "url": "https://github.com/myorg/dags.git",
        "username": "user",
        "password": "pwd",
    }
    resp = client.post(
        "/api/v1/git_repos",
        json=git_data,
        headers={"X-Project-Id": str(project_2["id"])},
    )
    resp.raise_for_status()
    cross_git_repo_id = resp.json()["data"]["id"]

    # 3. Try to create Airflow in project 1 referencing GitRepo from project 2
    airflow_data = {
        "name": "my-airflow-cross",
        "title": "My Airflow Cross",
        "project_id": test_project["id"],
        "platform_pgsql_id": pgsql_id,
        "dags_git_sync_enabled": True,
        "git_repo_id": cross_git_repo_id,
    }
    resp = client.post(
        "/api/v1/platform/airflow",
        json=airflow_data,
        headers={"X-Project-Id": str(test_project["id"])},
    )
    assert resp.status_code == 422
    assert "belongs to another project" in resp.json()["detail"][0]["msg"]


@pytest.mark.asyncio
async def test_airflow_template_vars_git_sync(client: TestClient, test_project):
    # Mock services/DB calls for template_vars test
    from citadel.platform_service.airflow.service import AirflowPlatformService
    from citadel.service.git_repo.model import GitRepo
    from citadel.service.ssh_key.model import SSHKey
    from citadel.platform_service.pgsql.model import PgSqlPlatform, PgSqlPlatformState
    from citadel.service.project.model import Project

    mock_request = MagicMock()
    mock_request.headers = {"X-Project-Id": str(test_project["id"])}
    mock_session = AsyncMock()
    mock_exec_result = MagicMock()
    mock_exec_result.all.return_value = []
    mock_exec_result.first.return_value = None
    mock_session.exec = AsyncMock(return_value=mock_exec_result)

    # Create mock pgsql service, pgsql platform, pgsql state, project
    mock_pgsql = PgSqlPlatform(id=1, name="my-pgsql", project_id=test_project["id"])
    mock_pgsql_state = PgSqlPlatformState(
        platform_id=1,
        active=True,
        db_user="app",
        db_name="app",
        db_pass=encrypt_password("secret_pass"),
        extra_data={"pgbouncer_host": "pgbouncer-host"},
    )
    mock_project = Project(id=test_project["id"], name="test-proj", ingress_domain="test.domain")

    # Mock services
    svc = AirflowPlatformService(mock_request, mock_session)
    svc._resolve_namespace = AsyncMock(return_value="airflow-ns")
    svc.project = AsyncMock(return_value=mock_project)

    # Mock foreign key resolution dependencies
    mock_pgsql_svc = MagicMock()
    mock_pgsql_svc.get = AsyncMock(return_value=mock_pgsql)
    mock_pgsql_svc.platform_state = AsyncMock(return_value=mock_pgsql_state)

    # Inject mock service getters
    from citadel.platform_service.pgsql.service import PgSqlPlatformService
    from citadel.service.git_repo.service import GitRepoService
    from citadel.service.ssh_key.service import SSHKeyService

    # Setup Airflow model
    airflow_model = AirflowPlatform(
        name="test-airflow",
        title="Test Airflow",
        project_id=test_project["id"],
        platform_pgsql_id=1,
        dags_git_sync_enabled=True,
        git_repo_id=10,
        dags_git_branch="main",
        dags_git_subpath="dags",
    )

    # 1. Test Git Repo with Username/Password
    mock_git_repo = GitRepo(
        id=10,
        name="my-http-repo",
        project_id=test_project["id"],
        url="https://github.com/org/repo.git",
        username="git-username",
        password=encrypt_password("git-token"),
    )
    mock_git_svc = MagicMock()
    mock_git_svc.get = AsyncMock(return_value=mock_git_repo)

    async def get_service_mock(req, sess):
        if req == mock_request and sess == mock_session:
            return mock_pgsql_svc
        return MagicMock()

    async def get_service_git_mock(req, sess):
        return mock_git_svc

    with patch.object(PgSqlPlatformService, "get_service", new=get_service_mock), \
         patch.object(GitRepoService, "get_service", new=get_service_git_mock):
        vars_res = await svc.template_vars(airflow_model)
        assert vars_res["dags_git_sync_enabled"] is True
        assert vars_res["dags_git_repo"] == "https://github.com/org/repo.git"
        assert vars_res["git_repo"]["username"] == "git-username"
        assert vars_res["git_repo"]["password"] == "git-token"
        assert vars_res["ssh_key"] is None

    # 2. Test Git Repo with SSH Key
    mock_git_repo_ssh = GitRepo(
        id=10,
        name="my-ssh-repo",
        project_id=test_project["id"],
        url="git@github.com:org/repo.git",
        ssh_key_id=20,
    )
    mock_git_svc.get = AsyncMock(return_value=mock_git_repo_ssh)

    mock_ssh_key = SSHKey(
        id=20,
        name="my-key",
        project_id=test_project["id"],
        private_key=encrypt_password("ssh-private-key-data"),
        public_key="ssh-rsa-pubkey",
    )
    mock_ssh_svc = MagicMock()
    mock_ssh_svc.get = AsyncMock(return_value=mock_ssh_key)

    async def get_service_ssh_mock(req, sess):
        return mock_ssh_svc

    with patch.object(PgSqlPlatformService, "get_service", new=get_service_mock), \
         patch.object(GitRepoService, "get_service", new=get_service_git_mock), \
         patch.object(SSHKeyService, "get_service", new=get_service_ssh_mock):
        vars_res = await svc.template_vars(airflow_model)
        assert vars_res["dags_git_sync_enabled"] is True
        assert vars_res["dags_git_repo"] == "git@github.com:org/repo.git"
        assert vars_res["ssh_key"]["private_key"] == "ssh-private-key-data"
        assert vars_res["ssh_key"]["public_key"] == "ssh-rsa-pubkey"


def test_airflow_no_oidc_fields():
    """Test that Airflow platform model, schema, widgets, and fields have no OIDC references."""
    schema = AirflowPlatformService.schema_class()
    assert "oidc_enabled" not in schema.model_fields
    assert "oidc_client_secret" not in schema.model_fields
    assert "oidc_enabled" not in AirflowPlatform.model_fields
    assert "oidc_client_secret" not in AirflowPlatform.model_fields
    assert "oidc_client_secret" not in AirflowPlatformService.redacted_fields()
    assert "oidc_client_secret" not in AirflowPlatformService.internal_fields()
    assert "oidc_enabled" not in AirflowPlatformService.widgets()


@pytest.mark.asyncio
async def test_airflow_load_examples(test_project):
    """Test that load_examples field is rendered correctly in Airflow templates"""
    from citadel.platform_service.airflow.service import AirflowPlatformService
    from citadel.platform_service.airflow.model import AirflowPlatform
    from citadel.platform_service.pgsql.model import PgSqlPlatform, PgSqlPlatformState
    from citadel.service.project.model import Project

    mock_request = MagicMock()
    mock_request.headers = {"X-Project-Id": str(test_project["id"])}
    mock_session = AsyncMock()
    mock_exec_result = MagicMock()
    mock_exec_result.all.return_value = []
    mock_exec_result.first.return_value = None
    mock_session.exec = AsyncMock(return_value=mock_exec_result)

    mock_pgsql = PgSqlPlatform(id=1, name="my-pgsql", project_id=test_project["id"])
    mock_pgsql_state = PgSqlPlatformState(
        platform_id=1,
        active=True,
        db_user="app",
        db_name="app",
        db_pass=encrypt_password("secret_pass"),
        extra_data={"pgbouncer_host": "pgbouncer-host"},
    )
    mock_project = Project(id=test_project["id"], name="test-proj", ingress_domain="test.domain")

    svc = AirflowPlatformService(mock_request, mock_session)
    svc._resolve_namespace = AsyncMock(return_value="airflow-ns")
    svc.project = AsyncMock(return_value=mock_project)

    mock_pgsql_svc = MagicMock()
    mock_pgsql_svc.get = AsyncMock(return_value=mock_pgsql)
    mock_pgsql_svc.platform_state = AsyncMock(return_value=mock_pgsql_state)

    from citadel.platform_service.pgsql.service import PgSqlPlatformService

    async def get_service_mock(req, sess):
        return mock_pgsql_svc

    # 1. Test load_examples is True
    airflow_model_true = AirflowPlatform(
        name="test-airflow",
        title="Test Airflow",
        project_id=test_project["id"],
        platform_pgsql_id=1,
        load_examples=True,
    )
    with patch.object(PgSqlPlatformService, "get_service", new=get_service_mock):
        manifests = await svc.render_manifests(airflow_model_true)
        assert "AIRFLOW__CORE__LOAD_EXAMPLES" in manifests
        assert "value: \"True\"" in manifests

    # 2. Test load_examples is False
    airflow_model_false = AirflowPlatform(
        name="test-airflow",
        title="Test Airflow",
        project_id=test_project["id"],
        platform_pgsql_id=1,
        load_examples=False,
    )
    with patch.object(PgSqlPlatformService, "get_service", new=get_service_mock):
        manifests = await svc.render_manifests(airflow_model_false)
        assert "AIRFLOW__CORE__LOAD_EXAMPLES" in manifests
        assert "value: \"False\"" in manifests


def test_airflow_widgets():
    """Test that Airflow widgets are correctly configured, particularly foreign key relationships."""
    widgets = AirflowPlatformService.widgets()
    assert "git_repo_id" in widgets
    assert widgets["git_repo_id"]["type"] == "relationship"
    assert widgets["git_repo_id"]["endpoint"] == "/api/v1/git_repos"
    assert widgets["git_repo_id"]["field"] == "id"
    assert "oidc_enabled" not in widgets
    assert "redis_password" not in widgets


def test_airflow_redis_password_field_configuration():
    """Test that redis_password is registered as an internal, encrypted, redacted field."""
    assert "redis_password" in AirflowPlatform.model_fields
    assert "redis_password" in AirflowPlatformService.internal_fields()
    assert "redis_password" in AirflowPlatformService.redacted_fields()


@pytest.mark.asyncio
async def test_airflow_redis_password_persistence_in_template_vars(test_project):
    """Test that redis_password remains consistent across template_vars invocations."""
    from citadel.platform_service.pgsql.model import PgSqlPlatform, PgSqlPlatformState
    from citadel.platform_service.pgsql.service import PgSqlPlatformService
    from citadel.service.project.model import Project

    mock_request = MagicMock()
    mock_request.headers = {"X-Project-Id": str(test_project["id"])}
    mock_session = AsyncMock()

    mock_project = Project(
        id=test_project["id"],
        name="test-project",
        title="Test Project",
        k8s_cluster_id=test_project["k8s_cluster_id"],
        ingress_domain="apps.example.com",
    )
    mock_pgsql = PgSqlPlatform(id=1, name="my-pgsql", project_id=test_project["id"])
    mock_pgsql_state = PgSqlPlatformState(
        platform_id=1,
        active=True,
        db_user="app",
        db_name="app",
        db_pass=encrypt_password("secret_pass"),
    )

    svc = AirflowPlatformService(mock_request, mock_session)
    svc.project = AsyncMock(return_value=mock_project)
    svc._resolve_namespace = AsyncMock(return_value="test-project")

    mock_pgsql_svc = MagicMock()
    mock_pgsql_svc.get = AsyncMock(return_value=mock_pgsql)
    mock_pgsql_svc.platform_state = AsyncMock(return_value=mock_pgsql_state)
    mock_pgsql_svc._resolve_namespace = AsyncMock(return_value="test-project")

    async def get_service_mock(req, sess):
        return mock_pgsql_svc

    fixed_pass = "my-stable-redis-pwd-12345"
    airflow_model = AirflowPlatform(
        name="test-airflow-redis",
        title="Test Airflow Redis",
        project_id=test_project["id"],
        platform_pgsql_id=1,
        redis_password=encrypt_password(fixed_pass),
    )

    with patch.object(PgSqlPlatformService, "get_service", new=get_service_mock):
        vars1 = await svc.template_vars(airflow_model)
        vars2 = await svc.template_vars(airflow_model)
        assert vars1["redis_password"] == fixed_pass
        assert vars2["redis_password"] == fixed_pass
        assert vars1["redis_password"] == vars2["redis_password"]


@pytest.mark.asyncio
async def test_airflow_images_resolved_and_rendered(test_stack_session):
    """Test that Airflow resolves and renders main, redis, statsd_exporter, and git_sync images from test_stack."""
    from citadel.platform_service.pgsql.service import PgSqlPlatformService

    req = MagicMock()
    svc = AirflowPlatformService(req, test_stack_session)
    svc._resolve_namespace = AsyncMock(return_value="ns")
    mock_project = MagicMock()
    mock_project.name = "myproject"
    mock_project.ingress_domain = None
    mock_project.ldap_config_id = None
    mock_project.stack_id = 1
    svc.project = AsyncMock(return_value=mock_project)

    mock_pgsql_svc = MagicMock()
    mock_pgsql_model = MagicMock()
    mock_pgsql_model.name = "test-pg"
    mock_pgsql_svc.get = AsyncMock(return_value=mock_pgsql_model)

    mock_pgsql_state = MagicMock()
    mock_pgsql_state.active = True
    mock_pgsql_state.db_user = "app"
    mock_pgsql_state.db_name = "app"
    mock_pgsql_state.db_pass = "pass"
    mock_pgsql_state.extra_data = {"pgbouncer_host": "test-pg-pooler.ns.svc.cluster.local"}
    mock_pgsql_svc.platform_state = AsyncMock(return_value=mock_pgsql_state)
    mock_pgsql_svc._resolve_namespace = AsyncMock(return_value="ns")

    async def get_service_mock(req, sess):
        return mock_pgsql_svc

    airflow_model = AirflowPlatform(
        name="test-airflow-imgs",
        title="Test Airflow Images",
        project_id=1,
        platform_pgsql_id=1,
        redis_password=encrypt_password("redis-pwd"),
    )

    with patch.object(PgSqlPlatformService, "get_service", new=get_service_mock):
        manifest = await svc.render_manifests(airflow_model)

    assert 'repository: "test.registry/citadel/airflow"' in manifest
    assert 'tag: "3.99.0"' in manifest
    assert 'repository: "test.registry/redis"' in manifest
    assert 'tag: "7.99-bookworm"' in manifest
    assert 'repository: "test.registry/prometheus/statsd-exporter"' in manifest
    assert 'tag: "v0.99.0"' in manifest
    assert 'repository: "test.registry/git-sync/git-sync"' in manifest
    assert 'tag: "v4.99.0"' in manifest
    assert "ignoreDifferences:" in manifest
    assert "/status" in manifest


@pytest.mark.asyncio
async def test_airflow_poller_pod_stats():
    """Test AirflowPoller reports pod statistics for core pod types (API, Scheduler, Worker)."""
    from citadel.platform_service.airflow.model import AirflowPlatformState
    from citadel.platform_service.airflow.poller import AirflowPoller

    req = MagicMock()
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()

    svc = AirflowPlatformService(req, session)
    model = AirflowPlatform(
        id=1,
        name="my-airflow",
        title="My Airflow",
        project_id=1,
        platform_pgsql_id=1,
        admin_password=encrypt_password("secret123"),
    )
    state = AirflowPlatformState(platform_id=1, active=True)
    svc.platform_state = AsyncMock(return_value=state)
    svc.kubeconfig = AsyncMock(return_value=None)
    svc._resolve_namespace = AsyncMock(return_value="test-ns")
    svc.project = AsyncMock(return_value=MagicMock(ingress_domain="apps.example.com"))

    def _make_pod(name: str, phase: str = "Running", ready: bool = True):
        pod = MagicMock()
        pod.metadata.name = name
        pod.status.phase = phase
        cs = MagicMock()
        cs.ready = ready
        pod.status.container_statuses = [cs]
        return pod

    mock_pods = MagicMock()
    mock_pods.items = [
        _make_pod("my-airflow-api-server-abc123", "Running", True),
        _make_pod("my-airflow-scheduler-def456", "Running", True),
        _make_pod("my-airflow-worker-0", "Running", True),
        _make_pod("my-airflow-worker-1", "Pending", False),
        _make_pod("my-airflow-redis-0", "Running", True),
        _make_pod("my-airflow-statsd-xyz", "Running", True),
    ]

    mock_custom_api = MagicMock()
    mock_custom_api.get_namespaced_custom_object.return_value = {
        "status": {
            "sync": {"status": "Synced"},
            "health": {"status": "Healthy"},
        }
    }

    mock_core_v1 = MagicMock()
    mock_core_v1.list_namespaced_pod.return_value = mock_pods
    mock_core_v1.list_namespaced_service.return_value = MagicMock(items=[])
    mock_core_v1.list_node.return_value = MagicMock(items=[])

    with (
        patch("citadel.platform_service.airflow.poller.config.load_incluster_config"),
        patch("citadel.platform_service.airflow.poller.client.ApiClient"),
        patch("citadel.platform_service.airflow.poller.client.CustomObjectsApi", return_value=mock_custom_api),
        patch("citadel.platform_service.airflow.poller.client.CoreV1Api", return_value=mock_core_v1),
    ):
        poller = AirflowPoller(svc, model)
        await poller.poll()

    mock_core_v1.list_namespaced_pod.assert_called_once_with(
        namespace="test-ns",
        label_selector="release=my-airflow",
    )
    assert state.status == "online"
    assert state.message == "Sync: Synced, Health: Healthy | Pods: API 1/1, Scheduler 1/1, Worker 1/2"




