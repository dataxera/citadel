# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from citadel.config import settings
from citadel.service.k8s_cluster.model import DEFAULT_TOPOLOGY_LEVELS
from citadel.service.k8s_cluster.permission import (
    ConfigureNodes,
    K8sClusterConfigureNodes,
    Write,
)
from citadel.service.k8s_cluster.service import (
    build_nodes_details,
    sanitize_topology_label_value,
    validate_k8s_label_key,
    validate_k8s_label_value,
    validate_role_name,
    validate_topology_value,
)


def _make_node(
    name: str,
    labels: dict[str, str] | None = None,
    capacity: dict[str, str] | None = None,
):
    """Build a mock Kubernetes V1Node object for testing."""
    cap = {"cpu": "4", "memory": "16Gi", "ephemeral-storage": "100Gi"}
    if capacity:
        cap.update(capacity)
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            creation_timestamp=datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
            labels=labels if labels is not None else {},
        ),
        status=SimpleNamespace(
            conditions=[SimpleNamespace(type="Ready", status="True")],
            addresses=[SimpleNamespace(type="InternalIP", address="10.0.0.10")],
            capacity=cap,
            node_info=SimpleNamespace(kubelet_version="v1.36.3+k3s1"),
        ),
    )


def test_configure_nodes_permission_hierarchy():
    """ConfigureNodes permission should inherit from Write."""
    assert issubclass(ConfigureNodes, Write)
    assert ConfigureNodes.name == "k8s_cluster:configure_nodes"
    assert K8sClusterConfigureNodes is ConfigureNodes


def test_validate_k8s_label_key_and_value():
    """Valid K8s label keys/values pass; invalid ones raise ValueError."""
    assert validate_k8s_label_key("env") == "env"
    assert validate_k8s_label_key("topology.kubernetes.io/rack") == "topology.kubernetes.io/rack"
    assert validate_k8s_label_key("nvidia.com/gpu.present") == "nvidia.com/gpu.present"

    assert validate_k8s_label_value("rack-01") == "rack-01"
    assert validate_k8s_label_value("") == ""

    with pytest.raises(ValueError):
        validate_k8s_label_key("")
    with pytest.raises(ValueError):
        validate_k8s_label_key("invalid key with spaces")
    with pytest.raises(ValueError):
        validate_k8s_label_key("-starts-with-dash")
    with pytest.raises(ValueError):
        validate_k8s_label_key("a/b/c")
    with pytest.raises(ValueError):
        validate_k8s_label_key("prefix/" + "x" * 64)

    with pytest.raises(ValueError):
        validate_k8s_label_value("invalid value")
    with pytest.raises(ValueError):
        validate_k8s_label_value("x" * 64)


def test_validate_role_name():
    """Valid user-defined role names pass; protected or invalid names raise ValueError."""
    assert validate_role_name("compute") == "compute"
    assert validate_role_name("ai-worker_01") == "ai-worker_01"

    for invalid in ("", "control-plane", "master", "bad role", "-bad"):
        with pytest.raises(ValueError):
            validate_role_name(invalid)


def test_validate_topology_value_and_rack_slash():
    """Rack topology values accept slash-delimited hierarchy and sanitize '/' for K8s labels."""
    assert validate_topology_value("dc1/row-a/rack-01", allow_slash=True) == "dc1/row-a/rack-01"
    assert sanitize_topology_label_value("dc1/row-a/rack-01") == "dc1-row-a-rack-01"

    for invalid in ("", "/dc1/rack-1", "dc1/rack-1/", "dc1//rack-1", "dc1/bad value", "x" * 64):
        with pytest.raises(ValueError):
            validate_topology_value(invalid, allow_slash=True)

    with pytest.raises(ValueError):
        validate_topology_value("us-east/1a", allow_slash=False)


def test_build_nodes_details_extracts_labels_topology_and_gpus():
    """build_nodes_details extracts labels, topology hierarchy, and NVIDIA/AMD GPU info."""
    nodes = [
        _make_node(
            "gpu-nvidia-1",
            labels={
                "node-role.kubernetes.io/worker": "",
                "node-role.kubernetes.io/ai-compute": "",
                "topology.kubernetes.io/region": "us-east",
                "topology.kubernetes.io/zone": "us-east-1a",
                "topology.kubernetes.io/rack": "rack-01",
                "nvidia.com/gpu.present": "true",
                "nvidia.com/gpu.product": "NVIDIA-A100-SXM4-80GB",
                "custom/tier": "gold",
            },
            capacity={"nvidia.com/gpu": "4"},
        ),
        _make_node(
            "gpu-amd-1",
            labels={
                "amd.com/gpu.present": "true",
                "feature.node.kubernetes.io/pci-1002.present": "true",
                "topology.kubernetes.io/region": "us-east",
                "topology.kubernetes.io/zone": "us-east-1b",
            },
            capacity={"amd.com/gpu": "2"},
        ),
        _make_node(
            "gpu-labeled-only",
            labels={"nvidia.com/gpu.present": "true"},
        ),
        _make_node("cpu-node", labels={"node-role.kubernetes.io/storage": ""}),
    ]

    *_, details = build_nodes_details(nodes, [], topology_levels=DEFAULT_TOPOLOGY_LEVELS)
    by_host = {d["hostname"]: d for d in details}

    nv = by_host["gpu-nvidia-1"]
    assert nv["roles"] == ["ai-compute", "worker"]
    assert nv["topology"] == {"region": "us-east", "zone": "us-east-1a", "rack": "rack-01"}
    assert nv["gpu_vendor"] == "nvidia"
    assert nv["gpu_count"] == 4
    assert nv["gpu_product"] == "NVIDIA-A100-SXM4-80GB"
    assert nv["labels"]["custom/tier"] == "gold"

    amd = by_host["gpu-amd-1"]
    assert amd["gpu_vendor"] == "amd"
    assert amd["gpu_count"] == 2
    assert amd["topology"] == {"region": "us-east", "zone": "us-east-1b"}

    labeled_only = by_host["gpu-labeled-only"]
    assert labeled_only["gpu_vendor"] == "nvidia"
    assert labeled_only["gpu_count"] == 0

    cpu = by_host["cpu-node"]
    assert cpu["gpu_vendor"] is None
    assert cpu["gpu_count"] == 0
    assert cpu["topology"] == {}


@pytest.fixture(autouse=True)
def setup_settings():
    """Ensure default admin credentials are consistent before client fixture initializes."""
    old_user = settings.default_admin_username
    old_pass = settings.default_admin_password
    settings.default_admin_username = "admin"
    settings.default_admin_password = "password123"
    yield
    settings.default_admin_username = old_user
    settings.default_admin_password = old_pass


@pytest.fixture
def auth_headers(client: TestClient) -> dict:
    """Login as default admin and return authorization headers."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "password123"},
    )
    if resp.status_code == 200:
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}
    return {}


def _create_cluster(client: TestClient, headers: dict, name: str = "topo-cluster") -> int:
    resp = client.post(
        "/api/v1/k8s_clusters",
        json={"name": name, "title": "Topology Cluster", "type": "in-cluster"},
        headers=headers,
    )
    assert resp.status_code == 200
    return int(resp.json()["data"]["id"])


def test_node_labels_and_gpu_and_roles_endpoint(client: TestClient, auth_headers: dict):
    """PUT /_nodes/{node}/labels patches K8s node with labels, roles, and NVIDIA/AMD GPU labels."""
    cluster_id = _create_cluster(client, auth_headers, "labels-cluster")

    mock_core = MagicMock()
    mock_core.read_node.return_value = _make_node(
        "worker-1",
        labels={
            "kubernetes.io/hostname": "worker-1",
            "node-role.kubernetes.io/control-plane": "",
            "node-role.kubernetes.io/old-role": "",
            "keep-me": "yes",
        },
    )
    mock_core.patch_node.return_value = _make_node("worker-1")

    with (
        patch(
            "citadel.service.k8s_cluster.service.K8sClusterService._get_core_v1_client",
            return_value=mock_core,
        ),
        patch(
            "citadel.service.k8s_cluster.service.K8sClusterService.poll_status",
            new_callable=AsyncMock,
        ) as mock_poll,
    ):
        resp = client.put(
            f"/api/v1/k8s_clusters/{cluster_id}/_nodes/worker-1/labels",
            json={
                "set_labels": {"env": "prod", "tier": "high-mem"},
                "remove_labels": ["keep-me"],
                "roles": ["compute", "storage"],
                "gpu_vendor": "nvidia",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200
        mock_poll.assert_awaited_once()

    mock_core.patch_node.assert_called_once()
    call_kwargs = mock_core.patch_node.call_args.kwargs
    assert call_kwargs["name"] == "worker-1"
    patched_labels = call_kwargs["body"]["metadata"]["labels"]

    assert patched_labels["env"] == "prod"
    assert patched_labels["tier"] == "high-mem"
    assert patched_labels["keep-me"] is None
    assert patched_labels["node-role.kubernetes.io/compute"] == ""
    assert patched_labels["node-role.kubernetes.io/storage"] == ""
    assert patched_labels["node-role.kubernetes.io/old-role"] is None
    # Protected system role must not be removed
    assert "node-role.kubernetes.io/control-plane" not in patched_labels
    # NVIDIA GPU provisioning label
    assert patched_labels["nvidia.com/gpu.present"] == "true"
    assert patched_labels["amd.com/gpu.present"] is None
    assert patched_labels["feature.node.kubernetes.io/pci-1002.present"] is None


def test_node_labels_amd_gpu_and_clear(client: TestClient, auth_headers: dict):
    """PUT /_nodes/{node}/labels supports AMD GPU provisioning labels and clearing GPU."""
    cluster_id = _create_cluster(client, auth_headers, "amd-cluster")
    mock_core = MagicMock()
    mock_core.read_node.return_value = _make_node("worker-amd")
    mock_core.patch_node.return_value = _make_node("worker-amd")

    with (
        patch(
            "citadel.service.k8s_cluster.service.K8sClusterService._get_core_v1_client",
            return_value=mock_core,
        ),
        patch(
            "citadel.service.k8s_cluster.service.K8sClusterService.poll_status",
            new_callable=AsyncMock,
        ),
    ):
        resp = client.put(
            f"/api/v1/k8s_clusters/{cluster_id}/_nodes/worker-amd/labels",
            json={"gpu_vendor": "amd"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        patched = mock_core.patch_node.call_args.kwargs["body"]["metadata"]["labels"]
        assert patched["amd.com/gpu.present"] == "true"
        assert patched["feature.node.kubernetes.io/pci-1002.present"] == "true"
        assert patched["nvidia.com/gpu.present"] is None

        mock_core.patch_node.reset_mock()
        resp_clear = client.put(
            f"/api/v1/k8s_clusters/{cluster_id}/_nodes/worker-amd/labels",
            json={"gpu_vendor": "none"},
            headers=auth_headers,
        )
        assert resp_clear.status_code == 200
        cleared = mock_core.patch_node.call_args.kwargs["body"]["metadata"]["labels"]
        assert cleared["nvidia.com/gpu.present"] is None
        assert cleared["amd.com/gpu.present"] is None
        assert cleared["feature.node.kubernetes.io/pci-1002.present"] is None


def test_node_labels_negative_validation(client: TestClient, auth_headers: dict):
    """Rejects protected system labels, invalid keys/values, and protected roles."""
    cluster_id = _create_cluster(client, auth_headers, "neg-labels-cluster")

    # Protected label modification
    resp = client.put(
        f"/api/v1/k8s_clusters/{cluster_id}/_nodes/worker-1/labels",
        json={"set_labels": {"kubernetes.io/hostname": "evil"}},
        headers=auth_headers,
    )
    assert resp.status_code == 400

    # Protected label removal
    resp = client.put(
        f"/api/v1/k8s_clusters/{cluster_id}/_nodes/worker-1/labels",
        json={"remove_labels": ["kubernetes.io/os"]},
        headers=auth_headers,
    )
    assert resp.status_code == 400

    # Invalid label key
    resp = client.put(
        f"/api/v1/k8s_clusters/{cluster_id}/_nodes/worker-1/labels",
        json={"set_labels": {"bad key!": "val"}},
        headers=auth_headers,
    )
    assert resp.status_code == 400

    # Protected role name
    resp = client.put(
        f"/api/v1/k8s_clusters/{cluster_id}/_nodes/worker-1/labels",
        json={"roles": ["control-plane"]},
        headers=auth_headers,
    )
    assert resp.status_code == 400

    # Protected internal k3s labels (modification and removal)
    for k3s_label in (
        "k3s.io/hostname",
        "k3s.io/internal-ip",
        "k3s.io/node-args",
        "k3s.io/node-config-hash",
        "node.k3s.io/custom",
        "svccontroller.k3s.cattle.io/lbpool",
    ):
        resp_set = client.put(
            f"/api/v1/k8s_clusters/{cluster_id}/_nodes/worker-1/labels",
            json={"set_labels": {k3s_label: "tampered"}},
            headers=auth_headers,
        )
        assert resp_set.status_code == 400

        resp_rm = client.put(
            f"/api/v1/k8s_clusters/{cluster_id}/_nodes/worker-1/labels",
            json={"remove_labels": [k3s_label]},
            headers=auth_headers,
        )
        assert resp_rm.status_code == 400


def test_topology_get_and_update(client: TestClient, auth_headers: dict):
    """GET and PUT /_topology manage rack hierarchy levels, custom roles, and node assignments."""
    cluster_id = _create_cluster(client, auth_headers, "rack-cluster")

    # Default topology before customization
    get_resp = client.get(f"/api/v1/k8s_clusters/{cluster_id}/_topology", headers=auth_headers)
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert [lvl["name"] for lvl in body["levels"]] == ["region", "zone", "rack"]
    for default_role in ("ingest", "queue", "compute", "database", "warehouse", "application"):
        assert default_role in body["roles"]

    mock_core = MagicMock()
    mock_core.patch_node.return_value = _make_node("node-a")

    with (
        patch(
            "citadel.service.k8s_cluster.service.K8sClusterService._get_core_v1_client",
            return_value=mock_core,
        ),
        patch(
            "citadel.service.k8s_cluster.service.K8sClusterService.poll_status",
            new_callable=AsyncMock,
        ),
    ):
        put_resp = client.put(
            f"/api/v1/k8s_clusters/{cluster_id}/_topology",
            json={
                "roles": ["compute", "storage"],
                "presets": [
                    {"region": "ap-southeast", "zone": "az-1", "rack": "dc1/row-a/rack-a1"},
                    {"region": "us-east", "zone": "az-2", "rack": "dc2/row-b/rack-b1"},
                ],
                "assignments": {
                    "node-a": {"region": "ap-southeast", "zone": "az-1", "rack": "dc1/row-a/rack-a1"},
                    "node-b": {"region": None, "zone": None, "rack": None},
                },
            },
            headers=auth_headers,
        )
        assert put_resp.status_code == 200
        updated = put_resp.json()
        assert updated["roles"] == ["compute", "storage"]
        assert updated["presets"] == [
            {"region": "ap-southeast", "zone": "az-1", "rack": "dc1/row-a/rack-a1"},
            {"region": "us-east", "zone": "az-2", "rack": "dc2/row-b/rack-b1"},
        ]
        assert updated["assignments"]["node-a"]["rack"] == "dc1/row-a/rack-a1"

        # Negative test: mixed region/zone/rack combination not in configured presets is rejected
        bad_resp = client.put(
            f"/api/v1/k8s_clusters/{cluster_id}/_topology",
            json={
                "assignments": {
                    "node-a": {"region": "ap-southeast", "zone": "az-2", "rack": "dc1/row-a/rack-a1"},
                },
            },
            headers=auth_headers,
        )
        assert bad_resp.status_code == 400

    assert mock_core.patch_node.call_count == 2
    calls = {c.kwargs["name"]: c.kwargs["body"]["metadata"]["labels"] for c in mock_core.patch_node.call_args_list}
    assert calls["node-a"] == {
        "topology.kubernetes.io/region": "ap-southeast",
        "topology.kubernetes.io/zone": "az-1",
        "topology.kubernetes.io/rack": "dc1-row-a-rack-a1",
    }
    assert calls["node-b"] == {
        "topology.kubernetes.io/region": None,
        "topology.kubernetes.io/zone": None,
        "topology.kubernetes.io/rack": None,
    }


def test_node_config_permissions_enforced(client: TestClient):
    """Users without k8s_cluster:configure_nodes permission receive 403 on node label & topology mutations."""
    old_auth = settings.enable_auth
    settings.enable_auth = True
    try:
        with client as c:
            login_admin = c.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "password123"},
            )
            assert login_admin.status_code == 200
            admin_headers = {"Authorization": f"Bearer {login_admin.json()['access_token']}"}
            cluster_id = _create_cluster(c, admin_headers, "perm-cluster")

            # Create a regular user with no permissions
            user_resp = c.post(
                "/api/v1/users",
                json={
                    "name": "readonly_op",
                    "title": "Viewer",
                    "email": "readonly_op@example.com",
                    "password": "password123",
                    "display_name": "Readonly",
                    "is_superadmin": False,
                },
                headers=admin_headers,
            )
            assert user_resp.status_code == 200
            login_resp = c.post(
                "/api/v1/auth/login",
                json={"username": "readonly_op", "password": "password123"},
            )
            assert login_resp.status_code == 200
            user_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

            resp1 = c.put(
                f"/api/v1/k8s_clusters/{cluster_id}/_nodes/node-1/labels",
                json={"set_labels": {"a": "b"}},
                headers=user_headers,
            )
            assert resp1.status_code == 403

            resp2 = c.put(
                f"/api/v1/k8s_clusters/{cluster_id}/_topology",
                json={"roles": ["compute"]},
                headers=user_headers,
            )
            assert resp2.status_code == 403
    finally:
        settings.enable_auth = old_auth
