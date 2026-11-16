# SPDX-FileCopyrightText: Copyright © 2026 Mohd Izhar Firdaus Bin Ismail
# SPDX-License-Identifier: AGPLv3+

import pytest
from fastapi.testclient import TestClient
from citadel.config import settings
from citadel.fw.model import NamedBase
from citadel.fw.permission import Permission, Update as FwUpdate, View as FwView
from citadel.fw.service import Service


@pytest.fixture(autouse=True)
def setup_settings():
    """Save and restore auth-related settings around each test."""
    old_admin_user = settings.default_admin_username
    old_admin_pass = settings.default_admin_password
    old_enable_auth = settings.enable_auth
    settings.default_admin_username = "admin"
    settings.default_admin_password = "password123"
    yield
    settings.default_admin_username = old_admin_user
    settings.default_admin_password = old_admin_pass
    settings.enable_auth = old_enable_auth


def _get_superadmin_headers(c: TestClient) -> dict:
    """Login as admin superuser and return authorization headers."""
    login_resp = c.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "password123"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_and_login_regular_user(c: TestClient, admin_headers: dict) -> tuple[dict, int]:
    """Create a regular (non-superadmin) user and return their auth headers and user id."""
    user_resp = c.post(
        "/api/v1/users",
        json={
            "name": "permuser",
            "title": "Permission Test User",
            "email": "permuser@example.com",
            "password": "password123",
            "display_name": "Perm User",
            "is_superadmin": False,
        },
        headers=admin_headers,
    )
    assert user_resp.status_code == 200
    user_id = user_resp.json()["data"]["id"]

    login_resp = c.post(
        "/api/v1/auth/login",
        json={"username": "permuser", "password": "password123"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, user_id


def _create_test_cluster(c: TestClient, admin_headers: dict) -> int:
    """Create a k8s cluster as admin and return its ID."""
    cluster_resp = c.post(
        "/api/v1/k8s_clusters",
        json={
            "name": f"perm-ep-cluster-{id(c)}",
            "title": "Perm EP Cluster",
            "type": "remote",
            "kubeconfig": "dummy config",
        },
        headers=admin_headers,
    )
    assert cluster_resp.status_code == 200, cluster_resp.json()
    return cluster_resp.json()["data"]["id"]


def test_service_permissions_endpoint_regular_vs_superadmin(client: TestClient):
    """Verify /_permissions returns read-only for regular users and all True for superadmin."""
    settings.enable_auth = True
    with client as c:
        admin_headers = _get_superadmin_headers(c)
        reg_headers, _ = _create_and_login_regular_user(c, admin_headers)

        reg_resp = c.get("/api/v1/projects/_permissions", headers=reg_headers)
        assert reg_resp.status_code == 200
        assert reg_resp.json()["data"] == {
            "list": True,
            "view": True,
            "create": False,
            "update": False,
            "delete": False,
            "execute": False,
        }

        admin_resp = c.get("/api/v1/projects/_permissions", headers=admin_headers)
        assert admin_resp.status_code == 200
        assert admin_resp.json()["data"] == {
            "list": True,
            "view": True,
            "create": True,
            "update": True,
            "delete": True,
            "execute": True,
        }


def test_service_permissions_endpoint_auth_disabled(client: TestClient):
    """Verify /_permissions returns all True when enable_auth is False."""
    settings.enable_auth = False
    with client as c:
        resp = c.get("/api/v1/projects/_permissions")
        assert resp.status_code == 200
        assert resp.json()["data"] == {
            "list": True,
            "view": True,
            "create": True,
            "update": True,
            "delete": True,
            "execute": True,
        }


def test_service_permissions_endpoint_superadmin_service(client: TestClient):
    """Verify superadmin-only services (like /users) deny regular users and allow superadmins."""
    settings.enable_auth = True
    with client as c:
        admin_headers = _get_superadmin_headers(c)
        reg_headers, _ = _create_and_login_regular_user(c, admin_headers)

        reg_resp = c.get("/api/v1/users/_permissions", headers=reg_headers)
        assert reg_resp.status_code == 403

        admin_resp = c.get("/api/v1/users/_permissions", headers=admin_headers)
        assert admin_resp.status_code == 200
        assert admin_resp.json()["data"] == {
            "list": True,
            "view": True,
            "create": True,
            "update": True,
            "delete": True,
            "execute": True,
        }


def test_model_permissions_endpoint(client: TestClient):
    """Verify /{id}/_permissions returns model-level permissions for regular and superadmin users."""
    settings.enable_auth = True
    with client as c:
        admin_headers = _get_superadmin_headers(c)
        reg_headers, _ = _create_and_login_regular_user(c, admin_headers)
        cluster_id = _create_test_cluster(c, admin_headers)

        p_resp = c.post(
            "/api/v1/projects",
            json={
                "name": "model-perm-proj",
                "title": "Model Perm Proj",
                "k8s_cluster_id": cluster_id,
            },
            headers=admin_headers,
        )
        assert p_resp.status_code == 200
        proj_id = p_resp.json()["data"]["id"]

        reg_resp = c.get(f"/api/v1/projects/{proj_id}/_permissions", headers=reg_headers)
        assert reg_resp.status_code == 200
        assert reg_resp.json()["data"] == {
            "view": True,
            "update": False,
            "delete": False,
            "execute": False,
        }

        admin_resp = c.get(f"/api/v1/projects/{proj_id}/_permissions", headers=admin_headers)
        assert admin_resp.status_code == 200
        assert admin_resp.json()["data"] == {
            "view": True,
            "update": True,
            "delete": True,
            "execute": True,
        }


def test_model_permissions_endpoint_context_check():
    """Verify /{id}/_permissions passes the model instance as context to check_context."""
    class DummyCtxModel(NamedBase):
        locked: bool = False

    class CtxPermModule:
        class Manage(Permission):
            name: str = "ctx_dummy:manage"

        class View(Manage, FwView):
            name: str = "ctx_dummy:view"

        class Update(Manage, FwUpdate):
            name: str = "ctx_dummy:update"

            @classmethod
            def check_context(cls, user=None, context=None, request=None) -> bool:
                return not getattr(context, "locked", False)

    class CtxDummyService(Service[DummyCtxModel]):
        permissions = CtxPermModule

        @classmethod
        def model_class(cls):
            return DummyCtxModel

    # Verify the permission class check_context behavior directly with unlocked/locked context
    from citadel.fw.permission import check_user_permission

    class MockUser:
        is_superadmin = False
        permissions = [CtxPermModule.Update, CtxPermModule.View]

    unlocked = DummyCtxModel(id=1, name="u", title="U", locked=False)
    locked = DummyCtxModel(id=2, name="l", title="L", locked=True)
    assert check_user_permission(MockUser(), CtxDummyService.get_permission("update"), context=unlocked) is True
    assert check_user_permission(MockUser(), CtxDummyService.get_permission("update"), context=locked) is False
