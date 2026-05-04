# SPDX-License-Identifier: AGPL-3.0-or-later

from api.dependencies.alloweds import owns_deployment_id
from api.routes.tests.helpers import MockJWT


def test_get_user_deployments(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.deployments.DeploymentService.get_owned_deployments",
        staticmethod(lambda payload: []),
    )
    response = test_client(url="/items/deployments", jwt=jwt)
    assert response.status_code == 200
    assert response.json()["deployments"] == []


def test_get_deployment(monkeypatch, test_client):
    from api import app

    jwt = MockJWT()

    deployment_data = {
        "info": {
            "id": "dep-1",
            "name": "Test Deployment",
            "description": "A test deployment",
            "tag_visible": True,
            "started_desktops": 0,
            "visible_desktops": 0,
            "total_users": 1,
            "total_desktops": 1,
            "desktops_each_user": 1,
        },
        "users": [],
    }

    monkeypatch.setattr(
        "api.services.deployments.DeploymentService.get_deployment",
        staticmethod(lambda deployment_id: deployment_data),
    )

    async def mock_owns_deployment_id(deployment_id: str = "dep-1"):
        return deployment_id

    app.dependency_overrides[owns_deployment_id] = mock_owns_deployment_id

    try:
        response = test_client(url="/item/deployment/dep-1", jwt=jwt)
        assert response.status_code == 200
        data = response.json()
        assert data["info"]["id"] == "dep-1"
        assert data["info"]["name"] == "Test Deployment"
        assert data["users"] == []
    finally:
        app.dependency_overrides.pop(owns_deployment_id, None)


def test_get_shared_deployments(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.deployments.DeploymentService.get_shared_deployments",
        staticmethod(lambda payload: []),
    )
    response = test_client(url="/items/deployments/get-shared", jwt=jwt)
    assert response.status_code == 200
    assert response.json()["deployments"] == []


# ─── Deployment action endpoints (T1 shim replacements) ─────────────────
# Cover the PUT/GET handlers behind /item/deployment/{id}/... that the
# v3 /deployment/* shims used to route. These routes use
# ``Depends(owns_deployment_id())`` (factory-called), so the inner
# checker closure is baked into the router at import time and can't be
# overridden via ``app.dependency_overrides`` — instead we monkeypatch
# the underlying ``Helpers.owns_deployment_id`` at the common-lib path.


def _bypass_owns_deployment_id(monkeypatch):
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_deployment_id",
        staticmethod(lambda payload, deployment_id, check_co_owner=True: deployment_id),
    )


def test_stop_all_desktops_in_deployment(monkeypatch, test_client):
    jwt = MockJWT(role_id="advanced")
    calls = []
    monkeypatch.setattr(
        "api.services.deployments.DeploymentService.stop_all_desktops",
        staticmethod(lambda deployment_id: calls.append(deployment_id)),
    )
    _bypass_owns_deployment_id(monkeypatch)

    response = test_client(
        url="/item/deployment/dep-1/stop",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 204
    assert calls == ["dep-1"]


def test_toggle_deployment_visibility(monkeypatch, test_client):
    # The route now accepts an optional body {stop_started_domains: bool}
    # and forwards it to the service. Default when no body is sent is True
    # (matches the apiv3 contract Vue 2 has always relied on).
    jwt = MockJWT(role_id="advanced")
    calls = []
    monkeypatch.setattr(
        "api.services.deployments.DeploymentService.toggle_visibility",
        staticmethod(
            lambda deployment_id, stop_started_domains: calls.append(
                (deployment_id, stop_started_domains)
            )
        ),
    )
    _bypass_owns_deployment_id(monkeypatch)

    response = test_client(
        url="/item/deployment/dep-1/toggle-visibility",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": "dep-1"}
    assert calls == [("dep-1", True)]


def test_toggle_deployment_visibility_with_body(monkeypatch, test_client):
    jwt = MockJWT(role_id="advanced")
    calls = []
    monkeypatch.setattr(
        "api.services.deployments.DeploymentService.toggle_visibility",
        staticmethod(
            lambda deployment_id, stop_started_domains: calls.append(
                (deployment_id, stop_started_domains)
            )
        ),
    )
    _bypass_owns_deployment_id(monkeypatch)

    response = test_client(
        url="/item/deployment/dep-1/toggle-visibility",
        method="PUT",
        jwt=jwt,
        body={"stop_started_domains": False},
    )

    assert response.status_code == 200
    assert calls == [("dep-1", False)]


def test_get_deployment_co_owners(monkeypatch, test_client):
    # The service now returns the full {owner, co_owners} dict so vue 2
    # (which displays the primary owner) and vue 3 (co-owners list) both
    # render from a single fetch.
    jwt = MockJWT(role_id="advanced")
    co_owners = [
        {"id": "user-1", "name": "User One", "uid": "u1", "photo": None},
        {
            "id": "user-2",
            "name": "User Two",
            "uid": "u2",
            "photo": "https://example.com/p.png",
        },
    ]
    owner = {"id": "user-0", "name": "Owner Zero", "uid": "u0", "photo": None}
    stub = {"owner": owner, "co_owners": co_owners}
    monkeypatch.setattr(
        "api.services.deployments.DeploymentService.get_co_owners",
        staticmethod(lambda deployment_id: stub),
    )
    _bypass_owns_deployment_id(monkeypatch)

    response = test_client(url="/item/deployment/dep-1/co-owners", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == {"owner": owner, "co_owners": co_owners}


def test_update_deployment_co_owners(monkeypatch, test_client):
    jwt = MockJWT(role_id="advanced")
    captured = {}

    def fake_update(deployment_id, co_owners):
        captured["deployment_id"] = deployment_id
        captured["co_owners"] = co_owners

    monkeypatch.setattr(
        "api.services.deployments.DeploymentService.update_co_owners",
        staticmethod(fake_update),
    )
    _bypass_owns_deployment_id(monkeypatch)

    response = test_client(
        url="/item/deployment/dep-1/co-owners",
        method="PUT",
        body={"co_owners": ["user-a", "user-b"]},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": "dep-1"}
    assert captured == {
        "deployment_id": "dep-1",
        "co_owners": ["user-a", "user-b"],
    }


def test_get_deployment_permissions(monkeypatch, test_client):
    jwt = MockJWT(role_id="advanced")
    # Service returns list[DeploymentPermissions] enum string values.
    # Old-frontend stores this verbatim and re-sends as
    # ``user_permissions: <list>`` on the edit-form PUT — the GET and
    # PUT contracts must agree on shape.
    stub = ["recreate"]
    monkeypatch.setattr(
        "api.services.deployments.DeploymentService.get_permissions",
        staticmethod(lambda deployment_id: stub),
    )
    _bypass_owns_deployment_id(monkeypatch)

    response = test_client(url="/item/deployment/dep-1/permissions", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_get_deployment_permissions_empty_list(monkeypatch, test_client):
    """A legacy deployment row missing ``user_permissions`` must surface
    as ``[]`` — old-frontend's edit form re-sends the response verbatim
    and the PUT body schema rejects ``{}`` with a 422."""
    jwt = MockJWT(role_id="advanced")
    monkeypatch.setattr(
        "api.services.deployments.DeploymentService.get_permissions",
        staticmethod(lambda deployment_id: []),
    )
    _bypass_owns_deployment_id(monkeypatch)

    response = test_client(url="/item/deployment/dep-1/permissions", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == []


def test_get_user_deployments_with_data(monkeypatch, test_client):
    jwt = MockJWT()

    deployment = {
        "id": "dep-1",
        "name": "Test Deployment",
        "description": "A test deployment",
        "image": {"type": "stock", "id": "img-1"},
        "desktop_names": ["desktop-1"],
        "started_desktops": 1,
        "tag_visible": True,
        "total_desktops": 1,
        "visible_desktops": 1,
        "total_users": 1,
        "co_owner": False,
        "needs_booking": False,
        "next_booking_start": None,
        "next_booking_end": None,
        "booking_id": None,
    }

    monkeypatch.setattr(
        "api.services.deployments.DeploymentService.get_owned_deployments",
        staticmethod(lambda payload: [deployment]),
    )
    response = test_client(url="/items/deployments", jwt=jwt)
    assert response.status_code == 200
    assert len(response.json()["deployments"]) == 1


# ─── §99 audit fix: DELETE deployment must allow co-owners ──────────


def test_recreate_deployment_offloads_to_thread(monkeypatch, test_client):
    """``PUT /item/deployment/{id}/recreate`` wraps the sync
    ``DeploymentService.recreate_desktops`` in ``asyncio.to_thread`` to
    keep the event loop free during a multi-desktop recreate (commit
    695852b09 "offload sync rethinkdb i/o off the asyncio event loop").

    Pin both that the service is called with the right args AND the
    response shape — the wrapping must not change the wire contract.
    """
    jwt = MockJWT(role_id="advanced")
    captured = {}

    def fake_recreate(payload, deployment_id):
        captured["role_id"] = payload["role_id"]
        captured["deployment_id"] = deployment_id

    monkeypatch.setattr(
        "api.services.deployments.DeploymentService.recreate_desktops",
        staticmethod(fake_recreate),
    )
    _bypass_owns_deployment_id(monkeypatch)

    response = test_client(
        url="/item/deployment/dep-1/recreate",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": "dep-1"}
    assert captured == {"role_id": "advanced", "deployment_id": "dep-1"}


def test_recreate_deployment_typed_error_propagates(monkeypatch, test_client):
    """Service ``Error`` (e.g. not_found) must surface with the right
    status — the asyncio.to_thread wrapping must NOT swallow Error
    exceptions raised inside the thread."""
    from api.services.error import Error

    jwt = MockJWT(role_id="advanced")

    def fail(payload, deployment_id):
        raise Error("not_found", "Deployment not found")

    monkeypatch.setattr(
        "api.services.deployments.DeploymentService.recreate_desktops",
        staticmethod(fail),
    )
    _bypass_owns_deployment_id(monkeypatch)

    response = test_client(
        url="/item/deployment/ghost/recreate",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 404


def test_recreate_deployment_unexpected_exception_returns_500(monkeypatch, test_client):
    """Bare ``RuntimeError`` from inside the to_thread wrapper still
    falls into the route's ``except Exception`` branch → 500."""
    jwt = MockJWT(role_id="advanced")

    def boom(payload, deployment_id):
        raise RuntimeError("DB unreachable")

    monkeypatch.setattr(
        "api.services.deployments.DeploymentService.recreate_desktops",
        staticmethod(boom),
    )
    _bypass_owns_deployment_id(monkeypatch)

    response = test_client(
        url="/item/deployment/dep-1/recreate",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 500


def test_delete_deployment_allows_co_owners(monkeypatch, test_client):
    """``DELETE /item/deployment/{id}`` regressed: v3
    ``DeploymentsView.api_v3_deployments_delete`` calls
    ``ownsDeploymentId(payload, id, check_co_owners=False)`` so that
    co-owners (not just primary owners) can delete deployments. v4 was
    using the default ``owns_deployment_id()`` which has
    ``check_co_owner=True``. This test pins the fix by capturing the
    ``check_co_owner`` flag passed through ``Helpers.owns_deployment_id``
    and asserting it is ``False``.
    """
    from api import app
    from api.dependencies.domains import deployment_has_no_started_desktops

    jwt = MockJWT(role_id="advanced")
    captured = {}

    def fake_owns(payload, deployment_id, check_co_owner=True):
        captured["check_co_owner"] = check_co_owner
        return deployment_id

    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_deployment_id",
        staticmethod(fake_owns),
    )
    monkeypatch.setattr(
        "api.services.deployments.DeploymentService.delete_deployment",
        staticmethod(lambda deployment_id, user_id, permanent=False: None),
    )

    async def mock_no_started_desktops(deployment_id: str = "dep-1"):
        return None

    app.dependency_overrides[deployment_has_no_started_desktops] = (
        mock_no_started_desktops
    )
    try:
        response = test_client(
            url="/item/deployment/dep-1",
            method="DELETE",
            jwt=jwt,
        )
    finally:
        app.dependency_overrides.pop(deployment_has_no_started_desktops, None)

    assert response.status_code == 200
    assert captured["check_co_owner"] is False
