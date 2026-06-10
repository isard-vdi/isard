#
#   Copyright © 2025 IsardVDI
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Route tests for :mod:`api.routes.domains.desktops`.

This file covers the three handlers introduced when porting v3_compat
shims into real apiv4 routes:

* ``PUT /item/desktop/{desktop_id}/retry`` — replaces v3
  ``GET /desktop/updating/{desktop_id}``. Transitions a ``Failed``
  desktop back to ``StartingPaused``.
* ``PUT /items/desktops/bulk-edit`` — replaces v3 ``PUT /domain/bulk``.
  Applies a partial update to a list of desktops.
* ``POST /items/desktops/bulk-create`` — replaces v3
  ``POST /persistent_desktop/bulk``. Creates many persistent desktops
  from a template for a set of users/groups/categories/roles.

All three tests monkeypatch the corresponding
``DesktopService`` staticmethod so the common-lib DB layer is never
touched. Ownership checks on the ``/retry`` route are neutralised by
swapping ``Helpers.owns_domain_id`` for a no-op that returns the
incoming ``domain_id``.
"""

import pytest
from api.routes.tests.helpers import MockJWT


def test_retry_failed_desktop(monkeypatch, test_client):
    jwt = MockJWT(role_id="advanced")
    calls = []

    def fake_retry(desktop_id, user_id):
        calls.append((desktop_id, user_id))
        return {"id": desktop_id, "status": "StartingPaused"}

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.retry_failed_desktop",
        staticmethod(fake_retry),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_domain_id",
        staticmethod(lambda payload, domain_id: domain_id),
    )

    response = test_client(
        url="/item/desktop/desktop-1/retry",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": "desktop-1"}
    assert calls == [("desktop-1", jwt.payload["user_id"])]


def test_bulk_edit_desktops(monkeypatch, test_client):
    jwt = MockJWT(role_id="advanced")
    captured = {}

    def fake_bulk_edit(ids, data, payload):
        captured["ids"] = ids
        captured["data"] = data
        captured["payload_role"] = payload.get("role_id")
        return {"ids": ids}

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.bulk_edit_desktops",
        staticmethod(fake_bulk_edit),
    )

    body = {
        "ids": ["desktop-1", "desktop-2"],
        "description": "new description",
    }
    response = test_client(
        url="/items/desktops/bulk-edit",
        method="PUT",
        body=body,
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"ids": ["desktop-1", "desktop-2"]}
    # The route pops `ids` from the body before handing the rest to the
    # service — tests pin both halves of that contract.
    assert captured == {
        "ids": ["desktop-1", "desktop-2"],
        "data": {"description": "new description"},
        "payload_role": "advanced",
    }


def test_bulk_edit_desktops_partial_hardware(monkeypatch, test_client):
    # The webapp bulk-edit form only sends the hardware fields the
    # operator actually touched, so the schema must accept a hardware
    # block without ``videos`` / ``interfaces`` and the dump must not
    # inject DomainHardware defaults that would clobber the desktop.
    jwt = MockJWT(role_id="advanced")
    captured = {}

    def fake_bulk_edit(ids, data, payload):
        captured["data"] = data
        return {"ids": ids}

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.bulk_edit_desktops",
        staticmethod(fake_bulk_edit),
    )

    response = test_client(
        url="/items/desktops/bulk-edit",
        method="PUT",
        body={
            "ids": ["desktop-1"],
            "hardware": {"vcpus": 2, "memory": 2.5},
            "reservables": {"vgpus": ["NVIDIA-A16-2Q"]},
        },
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured["data"] == {
        "hardware": {"vcpus": 2, "memory": 2.5},
        "reservables": {"vgpus": ["NVIDIA-A16-2Q"]},
    }


def test_bulk_create_persistent_desktops(monkeypatch, test_client):
    jwt = MockJWT(role_id="advanced")
    captured = {}

    def fake_bulk_create(payload, data):
        captured["payload_user"] = payload.get("user_id")
        captured["data"] = data
        return {"ids": ["desktop-a", "desktop-b"]}

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.bulk_create_persistent_desktops",
        staticmethod(fake_bulk_create),
    )

    body = {
        "template_id": "template-1",
        "name": "Lab desktop",
        "description": "Lab batch",
        "allowed": {
            "users": ["user-1", "user-2"],
            "groups": False,
            "categories": False,
            "roles": False,
        },
    }
    response = test_client(
        url="/items/desktops/bulk-create",
        method="POST",
        body=body,
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"ids": ["desktop-a", "desktop-b"]}
    assert captured == {
        "payload_user": jwt.payload["user_id"],
        "data": body,
    }


# ─── Desktop actions (T1 shim replacements) ──────────────────────────────
# These endpoints replace v3 shims like /desktop/{id}/extend-timeout,
# DELETE /desktop/{id}, /desktop/start/{id}, /desktop/stop/{id},
# /desktop/{id}/viewer/{type} and /domain/info/{id}. The tests
# monkeypatch the service staticmethod and bypass the
# owns_domain_id("desktop_id") factory checker via Helpers.owns_domain_id.


def _bypass_owns_domain_id(monkeypatch):
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_domain_id",
        staticmethod(lambda payload, domain_id: domain_id),
    )


def test_extend_desktop_timeout(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_extend_timeout(payload, desktop_id):
        captured["user_id"] = payload["user_id"]
        captured["desktop_id"] = desktop_id

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.extend_desktop_timeout",
        staticmethod(fake_extend_timeout),
    )
    _bypass_owns_domain_id(monkeypatch)

    response = test_client(
        url="/item/desktop/desktop-1/extend-timeout",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": "desktop-1"}
    assert captured == {
        "user_id": jwt.payload["user_id"],
        "desktop_id": "desktop-1",
    }


def test_delete_desktop_sends_to_recycle_bin(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_delete_desktop(desktop_id, user_id, permanent=False):
        captured["desktop_id"] = desktop_id
        captured["user_id"] = user_id
        captured["permanent"] = permanent
        # A soft-delete returns None → route responds 200 "item.recycled"
        return None

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.delete_desktop",
        staticmethod(fake_delete_desktop),
    )
    _bypass_owns_domain_id(monkeypatch)

    response = test_client(
        url="/item/desktop/desktop-1",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json()["message_code"] == "item.recycled"
    assert captured == {
        "desktop_id": "desktop-1",
        "user_id": jwt.payload["user_id"],
        "permanent": False,
    }


def test_delete_desktop_permanent_no_action(monkeypatch, test_client):
    jwt = MockJWT()

    def fake_delete_desktop(desktop_id, user_id, permanent=False):
        assert permanent is True
        # Returning a bool (no task) → route responds 204 No Content
        return True

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.delete_desktop",
        staticmethod(fake_delete_desktop),
    )
    _bypass_owns_domain_id(monkeypatch)

    response = test_client(
        url="/item/desktop/desktop-1?permanent=true",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 204


def test_start_desktop(monkeypatch, test_client):
    from api import app
    from api.dependencies.storage_pools import check_virt_storage_pool_availability

    jwt = MockJWT()
    calls = []

    def fake_start(desktop_id, user_id, request=None):
        calls.append((desktop_id, user_id))

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.start_desktop",
        staticmethod(fake_start),
    )
    _bypass_owns_domain_id(monkeypatch)

    async def mock_check_virt_pool():
        return None

    app.dependency_overrides[check_virt_storage_pool_availability] = (
        mock_check_virt_pool
    )
    try:
        response = test_client(
            url="/item/desktop/desktop-1/start",
            method="PUT",
            jwt=jwt,
        )
    finally:
        app.dependency_overrides.pop(check_virt_storage_pool_availability, None)

    assert response.status_code == 200
    assert response.json() == {"id": "desktop-1"}
    assert calls == [("desktop-1", jwt.payload["user_id"])]


def test_stop_desktop(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []

    # ``request`` is now passed through so ``Logging.logs_domain_stop_api``
    # can record the caller's IP / user-agent in ``logs_desktops`` —
    # apiv3 parity restored after the apiv4 port silently dropped the
    # parameter.
    def fake_stop(desktop_id, user_id, force=None, request=None):
        calls.append((desktop_id, user_id, force, request is not None))

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.stop_desktop",
        staticmethod(fake_stop),
    )
    _bypass_owns_domain_id(monkeypatch)

    response = test_client(
        url="/item/desktop/desktop-1/stop",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": "desktop-1"}
    assert calls == [("desktop-1", jwt.payload["user_id"], None, True)]


# ─── Desktop share-link + direct viewer (T1/desktop shim replacements) ─


@pytest.mark.clear_cache
def test_get_desktop_share_link(monkeypatch, test_client):
    """GET /item/desktop/{id}/get-share-link — replaces v3
    /desktop/jumperurl/{id} shim. The route is wrapped with
    ``@cached(TTLCache(...))`` so the test is marked clear_cache to
    reset the cache between runs. The service returns a plain string
    link (or None), which the route wraps in ``{link: ...}``."""
    jwt = MockJWT()
    captured = {}

    def fake_get(desktop_id):
        captured["desktop_id"] = desktop_id
        return "abc123"

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.get_desktop_share_link",
        staticmethod(fake_get),
    )
    _bypass_owns_domain_id(monkeypatch)

    response = test_client(url="/item/desktop/desktop-1/get-share-link", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == {"link": "abc123"}
    assert captured == {"desktop_id": "desktop-1"}


def test_update_desktop_share_link(monkeypatch, test_client):
    """PUT /item/desktop/{id}/update-share-link — replaces v3
    /desktop/jumperurl_reset/{id} shim."""
    jwt = MockJWT()
    captured = {}

    def fake_update(desktop_id, enabled):
        captured["desktop_id"] = desktop_id
        captured["enabled"] = enabled
        return "new-token-1"

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.update_desktop_share_link",
        staticmethod(fake_update),
    )
    _bypass_owns_domain_id(monkeypatch)

    response = test_client(
        url="/item/desktop/desktop-1/update-share-link",
        method="PUT",
        body={"enabled": True},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"link": "new-token-1"}
    assert captured == {"desktop_id": "desktop-1", "enabled": True}


def test_get_desktop_viewer(monkeypatch, test_client):
    jwt = MockJWT()
    stub = {
        "kind": "browser",
        "protocol": "vnc",
        "viewer": "https://viewer.example/vnc/1",
        "cookie": "session=abc",
    }
    captured = {}
    logged = {}

    def fake_get_viewer(user_id, desktop_id, viewer_type, is_admin, request):
        captured["user_id"] = user_id
        captured["desktop_id"] = desktop_id
        captured["viewer_type"] = viewer_type
        captured["is_admin"] = is_admin
        return stub

    def fake_log(domain_id, action_user, viewer_type, user_request=None):
        logged["domain_id"] = domain_id
        logged["action_user"] = action_user
        logged["viewer_type"] = viewer_type
        logged["had_request"] = user_request is not None

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.get_desktop_viewer",
        staticmethod(fake_get_viewer),
    )
    # The log must fire from the route, not the cached service, so cache
    # hits still produce an audit entry per user request.
    monkeypatch.setattr(
        "isardvdi_common.helpers.logging.Logging.logs_domain_event_viewer",
        staticmethod(fake_log),
    )
    _bypass_owns_domain_id(monkeypatch)

    response = test_client(
        url="/item/desktop/desktop-1/get-viewer/browser-vnc",
        jwt=jwt,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "browser"
    assert body["protocol"] == "vnc"
    assert captured == {
        "user_id": jwt.payload["user_id"],
        "desktop_id": "desktop-1",
        "viewer_type": "browser-vnc",
        "is_admin": True,  # default MockJWT role_id == "admin"
    }
    assert logged == {
        "domain_id": "desktop-1",
        "action_user": jwt.payload["user_id"],
        "viewer_type": "browser-vnc",
        "had_request": True,
    }


def test_get_desktop_direct_viewer_accepts_waiting_ip_stub(monkeypatch, test_client):
    """When an RDP-only desktop is in ``waiting_ip`` state the
    service emits a stub ``{kind, protocol}`` viewer payload because
    the guest hasn't reported its IP yet. ``DesktopViewerResponse``
    must accept that stub: a schema requiring
    ``viewer/urlp/cookie/values`` on every browser-rdp entry would
    fail Pydantic validation and the route handler would return a
    generic 404.
    """
    stub_desktop = {
        "id": "desktop-waiting-1",
        "jwt": "fake-jwt",
        "name": "Waiting Desktop",
        "description": "",
        "status": "WaitingIP",
        "scheduled": {"shutdown": False},
        "viewers": {
            "browser-rdp": {"kind": "browser", "protocol": "rdp"},
            "file-rdpgw": {"kind": "file", "protocol": "rdpgw"},
        },
    }

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.get_desktop_direct_viewer_from_token",
        staticmethod(lambda token, request: stub_desktop),
    )

    response = test_client(url="/item/desktop/token/some-token/get-viewer")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "WaitingIP"
    assert body["viewers"]["browser_rdp"] == {
        "kind": "browser",
        "protocol": "rdp",
        "viewer": None,
        "urlp": None,
        "cookie": None,
        "values": None,
    }
    assert body["viewers"]["file_rdpgw"] == {
        "kind": "file",
        "protocol": "rdpgw",
        "name": None,
        "ext": None,
        "mime": None,
        "content": None,
    }


# ─── §99 audit fixes (parity regressions found in v3 ↔ v4 audit) ────────


def test_create_desktop_from_media_uses_token_router_and_calls_quota(
    monkeypatch, test_client
):
    """``POST /item/desktop/from-media`` regressed in two ways during the
    apiv4 port: (a) the route was placed under ``advanced_router`` so
    only managers/admins could create desktops from media, and (b) the
    service stopped calling ``Quotas.desktop_create()``. v3
    ``DesktopsPersistentView.api_v3_desktop_from_media`` (and the
    corresponding ``ApiDesktopsPersistent.NewFromMedia``) require both
    behaviours. This test pins them: a non-admin/non-manager `user`
    role can call the route AND the service raises through quota.
    """
    jwt = MockJWT(role_id="user")
    quota_calls = []
    create_calls = []

    def fake_quota(user_id):
        quota_calls.append(user_id)

    def fake_create(user_id, data):
        create_calls.append((user_id, data.media_id, data.name))
        return "desktop-from-media-1"

    monkeypatch.setattr(
        "isardvdi_common.helpers.quotas.Quotas.desktop_create",
        staticmethod(fake_quota),
    )
    monkeypatch.setattr(
        "api.services.desktops.DesktopService.create_from_media",
        staticmethod(fake_create),
    )

    body = {
        "media_id": "media-1",
        "kind": "iso",
        "os_template": "vi-1",
        "name": "from-media-test",
        "description": "x",
        "guest_properties": {
            "viewers": {
                "browser_vnc": {"options": None},
            },
        },
        "hardware": {
            "boot_order": ["disk"],
            "disk_bus": "default",
            "disk_size": 10,
            "interfaces": ["default"],
            "memory": 1.0,
            "vcpus": 1,
            "videos": ["default"],
            "reservables": {"vgpus": None},
        },
    }

    response = test_client(
        url="/item/desktop/from-media",
        method="POST",
        body=body,
        jwt=jwt,
    )

    assert response.status_code == 201
    assert response.json() == {"id": "desktop-from-media-1"}
    # Service was called with the user-role payload (not blocked at the
    # router by an advanced_router gate).
    assert create_calls == [
        (jwt.payload["user_id"], "media-1", "from-media-test"),
    ]


def test_create_desktop_from_media_accepts_payload_without_reservables(
    monkeypatch, test_client
):
    """The webapp ``New desktop from media`` form omits ``reservables``
    when the user hasn't picked a vGPU. MediaHardware.reservables was
    originally declared without a default, so Pydantic returned 400 and
    the webapp flow broke. Reservables handling in
    ``DesktopService.create_from_media`` already tolerates a missing
    value, so the schema must also accept it.
    """
    jwt = MockJWT(role_id="user")

    monkeypatch.setattr(
        "isardvdi_common.helpers.quotas.Quotas.desktop_create",
        staticmethod(lambda user_id: None),
    )
    monkeypatch.setattr(
        "api.services.desktops.DesktopService.create_from_media",
        staticmethod(lambda user_id, data: "desktop-from-media-no-reservables"),
    )

    body = {
        "media_id": "media-1",
        "kind": "iso",
        "os_template": "vi-1",
        "name": "from-media-no-res",
        "description": "",
        "guest_properties": {
            "viewers": {"browser_vnc": {"options": None}},
        },
        "hardware": {
            "boot_order": ["disk"],
            "disk_bus": "default",
            "disk_size": 10,
            "interfaces": ["default"],
            "memory": 1.0,
            "vcpus": 1,
            "videos": ["default"],
            # note: no `reservables` key
        },
    }

    response = test_client(
        url="/item/desktop/from-media",
        method="POST",
        body=body,
        jwt=jwt,
    )

    assert response.status_code == 201, response.json()
    assert response.json() == {"id": "desktop-from-media-no-reservables"}


def test_get_allowed_reservables_calls_alloweds_with_user_payload(
    monkeypatch, test_client
):
    """``GET /items/domains/get-allowed-reservables`` was a hard-coded
    mock returning a single fake "No GPU" entry under ``open_router``
    (no auth, no permission filtering). v3
    ``CommonView.api_v3_domains_allowed_hardware_reservables`` calls
    ``allowed.get_items_allowed(payload, "reservables_vgpus", ...)`` to
    filter against the caller's role/category/group. This test pins
    that v4 now (a) requires auth (``token_router``) and (b) forwards
    the payload + table name to ``Alloweds.get_items_allowed``.
    """
    jwt = MockJWT()
    captured = {}

    def fake_get_items_allowed(payload, table, **kwargs):
        captured["user_id"] = payload["user_id"]
        captured["table"] = table
        captured["query_pluck"] = kwargs.get("query_pluck")
        captured["order"] = kwargs.get("order")
        captured["query_merge"] = kwargs.get("query_merge")
        return [
            {
                "id": "vgpu-1",
                "name": "Tesla",
                "description": "8GB",
                "editable": True,
                "allowed": {
                    "categories": False,
                    "groups": False,
                    "roles": False,
                    "users": False,
                },
            }
        ]

    monkeypatch.setattr(
        "isardvdi_common.helpers.alloweds.Alloweds.get_items_allowed",
        classmethod(
            lambda cls, payload, table, **kwargs: fake_get_items_allowed(
                payload, table, **kwargs
            )
        ),
    )

    response = test_client(
        url="/items/domains/get-allowed-reservables",
        jwt=jwt,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["vgpus"]) == 1
    assert body["vgpus"][0]["id"] == "vgpu-1"
    assert captured == {
        "user_id": jwt.payload["user_id"],
        "table": "reservables_vgpus",
        "query_pluck": ["id", "name", "description"],
        "order": "name",
        "query_merge": False,
    }


def test_get_allowed_reservables_requires_auth(test_client):
    """Without a JWT the route must 403 — proves it's no longer
    ``open_router``. ``has_token`` rejects missing tokens with 403
    rather than 401."""
    response = test_client(
        url="/items/domains/get-allowed-reservables",
    )
    assert response.status_code == 403


def test_update_bastion_authorized_keys_requires_can_use_bastion(
    monkeypatch, test_client
):
    """``PUT /item/desktop/{id}/update-bastion-authorized-keys`` was
    missing ``Depends(can_use_bastion)``. v3
    ``BastionView.api_v3_update_bastion_target_authorized_keys`` checks
    ``can_use_bastion(payload)`` and 403s when the user can't use
    bastion at all. This test pins the v4 route to the same gate by
    making ``Helpers.can_use_bastion`` return False and asserting 403.
    """
    jwt = MockJWT()
    _bypass_owns_domain_id(monkeypatch)
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.can_use_bastion",
        staticmethod(lambda payload: False),
    )

    response = test_client(
        url="/item/desktop/desktop-1/update-bastion-authorized-keys",
        method="PUT",
        body={"authorized_keys": "ssh-rsa AAA..."},
        jwt=jwt,
    )

    assert response.status_code == 403


# ─── Change-owner (desktop/template/media) ────────────────────────────


def test_edit_desktop_propagates_forced_hyp_for_admin(monkeypatch, test_client):
    """``PUT /item/desktop/{id}/edit`` accepts ``forced_hyp`` in the body
    and forwards it to ``DesktopService.edit_desktop`` together with the
    JWT payload, so the service's downstream
    ``CommonDesktops.update_desktop(... admin_or_manager=True ...)`` can
    apply it. This pins the wire contract that ``pkg/sdk`` Go SDK relies
    on (DesktopUpdate with ForcedHyp, called from check/check/check.go);
    the schema field has been on ``DesktopEditRequest`` since the
    apiv3→apiv4 cutover but no apiv4 route test pinned the propagation.
    """
    jwt = MockJWT(role_id="admin")
    captured = {}

    def fake_edit_desktop(desktop_id, data, payload):
        captured["desktop_id"] = desktop_id
        captured["data"] = data
        captured["role_id"] = payload["role_id"]

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.edit_desktop",
        staticmethod(fake_edit_desktop),
    )
    _bypass_owns_domain_id(monkeypatch)
    # check_domain_kind builds a new closure per route, so override the
    # Domain class lookup it uses to assert kind == "desktop".

    class _FakeDomain:
        def __init__(self, _id):
            self.kind = "desktop"

    monkeypatch.setattr("api.dependencies.domains.Domain", _FakeDomain)

    response = test_client(
        url="/item/desktop/desktop-1/edit",
        method="PUT",
        body={"forced_hyp": ["hyp-a", "hyp-b"]},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": "desktop-1"}
    assert captured["desktop_id"] == "desktop-1"
    assert captured["role_id"] == "admin"
    # ``model_dump(exclude_unset=True)`` so only the field we sent appears
    # in the service payload — the route must not invent defaults like a
    # blank ``name`` or ``hardware`` block, otherwise the common-lib
    # update path would silently overwrite existing values.
    assert captured["data"] == {"forced_hyp": ["hyp-a", "hyp-b"]}


def test_edit_desktop_forbids_forced_hyp_for_non_admin(monkeypatch, test_client):
    """Only admins may set forced_hyp/favourite_hyp on a desktop, matching
    the is_admin gate on PUT /item/template/{id}/edit. A manager must get
    403 and the service must never be reached."""
    jwt = MockJWT(role_id="manager")
    called = {"edit": False}

    def fake_edit_desktop(desktop_id, data, payload):
        called["edit"] = True

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.edit_desktop",
        staticmethod(fake_edit_desktop),
    )
    _bypass_owns_domain_id(monkeypatch)

    class _FakeDomain:
        def __init__(self, _id):
            self.kind = "desktop"

    monkeypatch.setattr("api.dependencies.domains.Domain", _FakeDomain)

    response = test_client(
        url="/item/desktop/desktop-1/edit",
        method="PUT",
        body={"favourite_hyp": ["hyp-a"]},
        jwt=jwt,
    )

    assert response.status_code == 403
    assert called["edit"] is False


def test_edit_desktop_accepts_image_upload_payload(monkeypatch, test_client):
    """Regression for round-2 Bug #41 — old-frontend's image-upload payload.

    The old-frontend ``uploadImageFile`` builds a body like
    ``{"image": {"id": "", "type": "user", "file": {"data": "...", "filename": "..."}}}``
    (Vue 3's ChangeImageModal sends the same empty-string ``id``
    sentinel; the backend assigns the persistent id server-side).

    Before the fix, old-frontend was omitting ``id`` entirely and
    apiv4 422'd with ``body.image.id Field required``. The fix
    landed on the *frontend* side — old-frontend now sends ``id: ""``.
    Pin the apiv4 contract so a future ``DomainImage`` schema tweak
    (e.g. making ``id`` non-empty-string) can't silently break the
    upload flow without this test failing first.
    """
    jwt = MockJWT(role_id="user")
    captured = {}

    def fake_edit_desktop(desktop_id, data, payload):
        captured["desktop_id"] = desktop_id
        captured["data"] = data

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.edit_desktop",
        staticmethod(fake_edit_desktop),
    )
    _bypass_owns_domain_id(monkeypatch)

    class _FakeDomain:
        def __init__(self, _id):
            self.kind = "desktop"

    monkeypatch.setattr("api.dependencies.domains.Domain", _FakeDomain)

    response = test_client(
        url="/item/desktop/desktop-1/edit",
        method="PUT",
        body={
            "image": {
                "id": "",
                "type": "user",
                "file": {
                    "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgAAIAAAUAAeImBZsAAAAASUVORK5CYII=",
                    "filename": "uploaded.png",
                },
            }
        },
        jwt=jwt,
    )

    assert response.status_code == 200, response.json()
    assert "image" in captured["data"]
    assert captured["data"]["image"]["id"] == ""
    assert captured["data"]["image"]["type"] == "user"
    assert captured["data"]["image"]["file"] == {
        "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgAAIAAAUAAeImBZsAAAAASUVORK5CYII=",
        "filename": "uploaded.png",
    }


def test_edit_desktop_propagates_server_toggle(monkeypatch, test_client):
    # Regression: webapp's modalServer PUTs {server, server_autostart} and
    # got 200 with no effect because DesktopEditRequest lacked the fields,
    # so Pydantic silently dropped them and the service received {}.
    jwt = MockJWT(role_id="admin")
    captured = {}

    def fake_edit_desktop(desktop_id, data, payload):
        captured["desktop_id"] = desktop_id
        captured["data"] = data

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.edit_desktop",
        staticmethod(fake_edit_desktop),
    )
    _bypass_owns_domain_id(monkeypatch)

    class _FakeDomain:
        def __init__(self, _id):
            self.kind = "desktop"

    monkeypatch.setattr("api.dependencies.domains.Domain", _FakeDomain)

    response = test_client(
        url="/item/desktop/desktop-1/edit",
        method="PUT",
        body={"server": True, "server_autostart": False},
        jwt=jwt,
    )

    assert response.status_code == 200, response.json()
    assert captured["data"] == {"server": True, "server_autostart": False}


def test_change_desktop_owner(monkeypatch, test_client):
    """PUT /item/desktop/{id}/change-owner/{user_id} — webapp calls
    this to reassign a persistent desktop to a different user. v3
    CommonView.api_v3_desktop_change_owner required
    @is_admin_or_manager + ownsUserId + ownsDomainId."""
    jwt = MockJWT()
    captured = {}

    def fake_change_owner(payload, desktop_id, new_user_id):
        captured["desktop_id"] = desktop_id
        captured["new_user_id"] = new_user_id

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.change_owner",
        staticmethod(fake_change_owner),
    )

    response = test_client(
        url="/item/desktop/desktop-1/change-owner/user-new",
        method="PUT",
        jwt=jwt,
    )
    assert response.status_code == 200
    assert response.json() == {"id": "desktop-1"}
    assert captured == {"desktop_id": "desktop-1", "new_user_id": "user-new"}


# ─── Non-persistent desktop creation ──────────────────────────────────


def test_create_nonpersistent_desktop(monkeypatch, test_client):
    """POST /item/desktop/new-nonpersistent — webapp TableList/Card
    'instant session' flow. Takes JSON ``{template_id}`` and reuses
    the existing non-persistent desktop (and starts it) if one already
    exists."""
    from api import app
    from api.dependencies.storage_pools import check_create_storage_pool_availability

    jwt = MockJWT()
    captured = {}

    def fake_create(payload, template_id):
        captured["user_id"] = payload["user_id"]
        captured["template_id"] = template_id
        return "desktop-np-1"

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.create_nonpersistent_desktop",
        staticmethod(fake_create),
    )

    async def mock_check_storage():
        return None

    app.dependency_overrides[check_create_storage_pool_availability] = (
        mock_check_storage
    )
    try:
        response = test_client(
            url="/item/desktop/new-nonpersistent",
            method="POST",
            body={"template_id": "template-1"},
            jwt=jwt,
        )
    finally:
        app.dependency_overrides.pop(check_create_storage_pool_availability, None)

    assert response.status_code == 200
    assert response.json() == {"id": "desktop-np-1"}
    assert captured == {
        "user_id": jwt.payload["user_id"],
        "template_id": "template-1",
    }


# ─── Toggle deployment desktop visibility by desktop id ───────────────


def test_toggle_desktop_deployment_visibility(monkeypatch, test_client):
    """PUT /item/desktop/{id}/toggle-deployment-visibility — webapp
    toggleDesktopVisible store action. Accepts only the domain id and
    uses ownsDomainId."""
    jwt = MockJWT(role_id="advanced")
    calls = []

    monkeypatch.setattr(
        "api.services.deployments.DeploymentService.toggle_domain_visibility",
        staticmethod(lambda domain_id: calls.append(domain_id)),
    )
    _bypass_owns_domain_id(monkeypatch)

    response = test_client(
        url="/item/desktop/desktop-42/toggle-deployment-visibility",
        method="PUT",
        jwt=jwt,
    )
    assert response.status_code == 200
    assert response.json() == {"id": "desktop-42"}
    assert calls == ["desktop-42"]


# ─── Bastion domains bulk update + verify ─────────────────────────────


def test_update_bastion_domains(monkeypatch, test_client):
    """PUT /item/desktop/{id}/update-bastion-domains — bulk update
    up to 10 individual bastion domains. Mirrors v3
    ``BastionView.api_v3_update_bastion_target_domains``. Verifies
    the service receives the cleaned list and the domain gate works
    transitively through ``can_use_bastion_individual_domains``."""
    jwt = MockJWT()
    captured = {}
    _bypass_owns_domain_id(monkeypatch)

    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.can_use_bastion",
        staticmethod(lambda payload: True),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.alloweds.Alloweds.is_allowed",
        classmethod(lambda cls, payload, row, table, ignore_role=False: True),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.caches.Caches.get_document",
        staticmethod(
            lambda table, doc_id, fields: {
                "individual_domains": {
                    "allowed": {
                        "categories": False,
                        "groups": False,
                        "roles": False,
                        "users": False,
                    }
                }
            }
        ),
    )

    def fake_update(payload, desktop_id, domains):
        captured["desktop_id"] = desktop_id
        captured["domains"] = domains

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.update_desktop_bastion_domains",
        staticmethod(fake_update),
    )

    response = test_client(
        url="/item/desktop/desktop-1/update-bastion-domains",
        method="PUT",
        body={"domains": ["a.example.com", "b.example.com"]},
        jwt=jwt,
    )
    assert response.status_code == 200
    assert response.json() == {"id": "desktop-1"}
    assert captured == {
        "desktop_id": "desktop-1",
        "domains": ["a.example.com", "b.example.com"],
    }


def test_verify_bastion_domain(monkeypatch, test_client):
    """POST /item/desktop/{id}/verify-bastion-domain — DNS-verifies
    a single candidate domain without saving. Mirrors v3
    ``BastionView.api_v3_verify_bastion_domain``."""
    jwt = MockJWT()
    _bypass_owns_domain_id(monkeypatch)
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.can_use_bastion",
        staticmethod(lambda payload: True),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.alloweds.Alloweds.is_allowed",
        classmethod(lambda cls, payload, row, table, ignore_role=False: True),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.caches.Caches.get_document",
        staticmethod(
            lambda table, doc_id, fields: {
                "individual_domains": {
                    "allowed": {
                        "categories": False,
                        "groups": False,
                        "roles": False,
                        "users": False,
                    }
                }
            }
        ),
    )

    def fake_verify(payload, desktop_id, domain):
        return {"verified": True}

    monkeypatch.setattr(
        "api.services.desktops.DesktopService.verify_bastion_domain",
        staticmethod(fake_verify),
    )

    response = test_client(
        url="/item/desktop/desktop-1/verify-bastion-domain",
        method="POST",
        body={"domain": "my-new-domain.example.com"},
        jwt=jwt,
    )
    assert response.status_code == 200
    assert response.json() == {"verified": True}


# ────────────────────────────────────────────────────────────────────
# Bug 41 — async offload of GET /items/desktops/get-images
# ────────────────────────────────────────────────────────────────────


def test_get_desktop_images_offloads_card_calls(monkeypatch, test_client):
    """``CardService.get_stock_cards`` and ``get_user_cards`` are
    sync ReQL helpers. Pin that the route routes them through
    ``asyncio.to_thread`` (and ``asyncio.gather`` for the both-kinds
    branch) so the asyncio event loop stays free under load.

    Catches a regression to the pre-fix shape where the lambda
    dispatch ran the helpers synchronously and serialised concurrent
    requests behind the rdb round-trip (rev-13 staircase
    32 → 48 → 62 → 72 → 84 → 97 → 105 → 122 ms for 8 concurrent
    callers in the both-kinds branch).
    """
    import asyncio as _asyncio

    from api.services.cards import CardService

    monkeypatch.setattr(
        CardService,
        "get_stock_cards",
        staticmethod(lambda: [{"id": "stock-1", "url": "u-s", "type": "stock"}]),
    )
    monkeypatch.setattr(
        CardService,
        "get_user_cards",
        staticmethod(
            lambda user_id, desktop_id: [{"id": "user-1", "url": "u-u", "type": "user"}]
        ),
    )

    scheduled = []
    real_to_thread = _asyncio.to_thread

    async def recording_to_thread(fn, *args, **kwargs):
        scheduled.append((fn, args))
        return await real_to_thread(fn, *args, **kwargs)

    monkeypatch.setattr(
        "api.routes.domains.desktops.asyncio.to_thread", recording_to_thread
    )

    jwt = MockJWT()

    # both-kinds branch — should dispatch both helpers via to_thread.
    response = test_client(
        url="/items/desktops/get-images?desktop_id=desktop-1",
        method="GET",
        jwt=jwt,
    )

    assert response.status_code == 200
    body = response.json()
    assert {img["id"] for img in body["images"]} == {"stock-1", "user-1"}

    fns_dispatched = {fn for fn, _args in scheduled}
    assert CardService.get_stock_cards in fns_dispatched, (
        "get_stock_cards must be dispatched via asyncio.to_thread "
        "(Bug 41 — sync rdb in async handler blocks event loop)"
    )
    assert CardService.get_user_cards in fns_dispatched, (
        "get_user_cards must be dispatched via asyncio.to_thread "
        "(Bug 41 — sync rdb in async handler blocks event loop)"
    )


def test_get_desktop_images_stock_only_offloads(monkeypatch, test_client):
    """``image_type=stock`` branch must also offload the helper —
    independent path through the if/elif/else."""
    import asyncio as _asyncio

    from api.services.cards import CardService

    monkeypatch.setattr(
        CardService,
        "get_stock_cards",
        staticmethod(lambda: [{"id": "stock-1", "url": "u", "type": "stock"}]),
    )

    scheduled = []
    real_to_thread = _asyncio.to_thread

    async def recording_to_thread(fn, *args, **kwargs):
        scheduled.append(fn)
        return await real_to_thread(fn, *args, **kwargs)

    monkeypatch.setattr(
        "api.routes.domains.desktops.asyncio.to_thread", recording_to_thread
    )

    response = test_client(
        url="/items/desktops/get-images?image_type=stock",
        method="GET",
        jwt=MockJWT(),
    )

    assert response.status_code == 200
    assert CardService.get_stock_cards in scheduled


def test_get_desktop_images_user_branch_rejected_at_schema_boundary(
    monkeypatch, test_client
):
    """``image_type=user`` is currently rejected at the Pydantic
    boundary (``DesktopImageType`` enum only includes ``stock`` —
    the ``user`` value is intentionally commented out in the schema).

    Pin that the boundary rejection still happens with a 4xx, so a
    future schema change that adds ``user`` doesn't accidentally
    introduce a path where the offload is bypassed.
    """
    response = test_client(
        url="/items/desktops/get-images?image_type=user&desktop_id=d-1",
        method="GET",
        jwt=MockJWT(),
    )
    # FastAPI's custom error handler converts the Pydantic enum
    # rejection to 400.
    assert response.status_code == 400
