#
#   Copyright © 2025 Pau Abril Iranzo
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
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later


import pytest
from api.routes.tests.factories import make_config
from api.routes.tests.helpers import MockJWT


@pytest.fixture()
def bastion_db_factory():
    """Fixture to create a mock database for bastion tests."""

    def bastion_db_tables_data(jwt):
        return {
            "config": [
                make_config(
                    bastion={
                        "allowed": {
                            "categories": False,
                            "groups": False,
                            "roles": [],
                            "users": False,
                        },
                        "domain": "bastion.example.org",
                        "domain_verification_required": False,
                        "enabled": True,
                        "individual_domains": {
                            "allowed": {
                                "categories": False,
                                "groups": False,
                                "roles": [],
                                "users": False,
                            }
                        },
                    }
                )
            ],
            "targets": [
                {
                    "desktop_id": "desktop-1",
                    "domain": None,
                    "domains": [],
                    "http": {
                        "enabled": True,
                        "http_port": 8000,
                        "https_port": 4430,
                    },
                    "id": "43179a19-62e9-4a75-8529-0678afbc84a0",
                    "ssh": {
                        "authorized_keys": [
                            f"ssh-ed25519 AAAAC3NzPLACEHOLDER+SSH+PUBLIC+KEYaC1lZDI1NTE5AAAQO2nQGEHulu4ywKsZJm {jwt.payload['name']}@example.com",
                        ],
                        "enabled": True,
                        "port": 22,
                    },
                    "user_id": jwt.payload["user_id"],
                },
                {
                    "desktop_id": "desktop-2",
                    "domain": "dktp2.example.com",
                    "domains": ["dktp2.example.com"],
                    "http": {
                        "enabled": True,
                        "http_port": 80,
                        "https_port": 443,
                    },
                    "id": "521b217d-325e-4b54-bbd8-f71a7037c21b",
                    "ssh": {
                        "authorized_keys": [],
                        "enabled": False,
                        "port": 22,
                    },
                    "user_id": jwt.payload["user_id"],
                },
                {
                    "desktop_id": "desktop-3",
                    "domain": None,
                    "domains": [],
                    "http": {
                        "enabled": False,
                        "http_port": 80,
                        "https_port": 443,
                    },
                    "id": "c259ba7b-b1ed-41e2-85b4-9ee57f19bb09",
                    "ssh": {
                        "authorized_keys": [
                            f"ssh-ed25519 AAAAC3NzPLACEHOLDER+SSH+PUBLIC+KEYaC1ct3qnAy7j87n08nNBDEHulu4ywKsZJm {jwt.payload['name']}@example.com",
                        ],
                        "enabled": True,
                        "port": 22,
                    },
                    "user_id": "another-user",
                },
            ],
            "domains": [
                {
                    "id": "desktop-1",
                    "kind": "desktop",
                    "user": jwt.payload["user_id"],
                    "group": jwt.payload["group_id"],
                    "category": jwt.payload["category_id"],
                },
                {
                    "id": "desktop-2",
                    "kind": "desktop",
                    "user": jwt.payload["user_id"],
                    "group": jwt.payload["group_id"],
                    "category": jwt.payload["category_id"],
                },
                {
                    "id": "desktop-3",
                    "kind": "desktop",
                    "user": "another-user",
                    "group": jwt.payload["group_id"],
                    "category": jwt.payload["category_id"],
                },
            ],
            "users": [
                {
                    "id": jwt.payload["user_id"],
                    "name": jwt.payload["name"],
                    "username": jwt.payload["name"],
                    "role_id": jwt.payload["role_id"],
                    "provider": jwt.payload["provider"],
                    "group": jwt.payload["group_id"],
                    "category": jwt.payload["category_id"],
                },
                {
                    "id": "another-user",
                    "name": "Another User",
                    "username": "another-user",
                    "role_id": "advanced",
                    "provider": "local",
                    "group": jwt.payload["group_id"],
                    "category": jwt.payload["category_id"],
                },
            ],
            "groups": [
                {
                    "id": jwt.payload["group_id"],
                }
            ],
            "categories": [
                {
                    "id": jwt.payload["category_id"],
                }
            ],
        }

    return bastion_db_tables_data


@pytest.mark.setup_clear_cache
def test_get_all_bastion_targets(monkeypatch, test_client, bastion_db_factory):
    monkeypatch.setenv("BASTION_ENABLED", "true")

    jwt = MockJWT()

    expected_response = [
        {
            "desktop_id": "desktop-1",
            "domain": None,
            "domains": [],
            "http": {"enabled": True, "http_port": 8000, "https_port": 4430},
            "id": "43179a19-62e9-4a75-8529-0678afbc84a0",
            "ssh": {
                "authorized_keys": [
                    f"ssh-ed25519 AAAAC3NzPLACEHOLDER+SSH+PUBLIC+KEYaC1lZDI1NTE5AAAQO2nQGEHulu4ywKsZJm {jwt.payload['name']}@example.com",
                ],
                "enabled": True,
                "port": 22,
            },
            "user_id": jwt.payload["user_id"],
        },
        {
            "desktop_id": "desktop-2",
            "domain": "dktp2.example.com",
            "domains": ["dktp2.example.com"],
            "http": {"enabled": True, "http_port": 80, "https_port": 443},
            "id": "521b217d-325e-4b54-bbd8-f71a7037c21b",
            "ssh": {"authorized_keys": [], "enabled": False, "port": 22},
            "user_id": jwt.payload["user_id"],
        },
    ]

    response = test_client(
        db_tables_data=bastion_db_factory(jwt),
        method="GET",
        url="/api/v4/items/bastions",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == expected_response


@pytest.mark.setup_clear_cache
def test_get_all_bastion_targets_bastion_disabled(
    monkeypatch, test_client, bastion_db_factory
):
    monkeypatch.setenv("BASTION_ENABLED", "true")

    jwt = MockJWT(role_id="user")

    db_data = bastion_db_factory(jwt)
    db_data["config"][0]["bastion"]["enabled"] = False

    response = test_client(
        db_tables_data=db_data,
        method="GET",
        url="/api/v4/items/bastions",
        jwt=jwt,
    )

    assert response.status_code == 403


@pytest.mark.setup_clear_cache
def test_get_all_bastion_targets_bastion_disallowed(
    monkeypatch, test_client, bastion_db_factory
):
    monkeypatch.setenv("BASTION_ENABLED", "true")

    jwt = MockJWT(role_id="admin")

    db_data = bastion_db_factory(jwt)
    db_data["config"][0]["bastion"]["allowed"] = {
        "categories": False,
        "groups": False,
        "roles": ["user"],
        "users": False,
    }

    response = test_client(
        db_tables_data=db_data,
        method="GET",
        url="/api/v4/items/bastions",
        jwt=jwt,
    )

    assert response.status_code == 403


@pytest.mark.setup_clear_cache
def test_get_all_bastion_targets_cfg_bastion_disabled(
    monkeypatch,
    test_client,
    bastion_db_factory,
):
    monkeypatch.setenv("BASTION_ENABLED", "false")

    jwt = MockJWT(role_id="user")

    db_data = bastion_db_factory(jwt)
    db_data["config"][0]["bastion"]["enabled"] = False

    response = test_client(
        db_tables_data=db_data,
        method="GET",
        url="/api/v4/items/bastions",
        jwt=jwt,
    )

    assert response.status_code == 403


# ─── Admin bastion routes (T1 shim replacements) ────────────────────────


def _stub_admin_bastion_config() -> dict:
    return {
        "bastion_enabled": True,
        "bastion_enabled_in_cfg": True,
        "bastion_enabled_in_db": True,
        "bastion_domain": "bastion.example",
        "bastion_ssh_port": "2222",
        "domain_verification_required": False,
    }


def test_get_admin_bastion_config(monkeypatch, test_client):
    """GET /admin/bastion — replaces v3 /admin/bastion/ shim."""
    jwt = MockJWT()
    stub = _stub_admin_bastion_config()
    monkeypatch.setattr(
        "api.services.bastion.BastionService.get_admin_bastion_config",
        staticmethod(lambda: stub),
    )

    response = test_client(url="/admin/item/config/bastion", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert body["bastion_enabled"] is True
    assert body["bastion_domain"] == "bastion.example"


def test_update_bastion_config(monkeypatch, test_client):
    """PUT /admin/bastion/config — replaces v3 /admin/bastion/config shim."""
    jwt = MockJWT()
    captured = {}

    def fake_update(enabled, bastion_domain, domain_verification_required):
        captured["enabled"] = enabled
        captured["bastion_domain"] = bastion_domain
        captured["domain_verification_required"] = domain_verification_required

    monkeypatch.setattr(
        "api.services.bastion.BastionService.update_bastion_config",
        staticmethod(fake_update),
    )

    response = test_client(
        url="/admin/item/config/bastion",
        method="PUT",
        body={
            "enabled": True,
            "bastion_domain": "bastion.example",
            "domain_verification_required": False,
        },
        jwt=jwt,
    )

    assert response.status_code == 204
    assert captured == {
        "enabled": True,
        "bastion_domain": "bastion.example",
        "domain_verification_required": False,
    }


def test_remove_disallowed_bastion_targets(monkeypatch, test_client):
    """DELETE /admin/bastion/disallowed — replaces v3
    /admin/bastion/disallowed shim. ``Alloweds.remove_disallowed_bastion_targets``
    returns the list of deleted target ids; the route wraps it into
    ``DeleteBastionDisallowedTargetsResponse(removed_targets=...)``."""
    jwt = MockJWT()
    removed = ["t-1", "t-2", "t-3"]
    monkeypatch.setattr(
        "api.services.bastion.BastionService.remove_disallowed_bastion_targets",
        staticmethod(lambda: removed),
    )

    response = test_client(
        url="/admin/items/bastion/disallowed",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"removed_targets": removed}


# ─── User bastion target management ─────────────────────────────────────


def _bypass_owns_domain_id(monkeypatch):
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_domain_id",
        staticmethod(lambda payload, domain_id: domain_id),
    )


def _bypass_bastion_checks(monkeypatch):
    """Bypass bastion enabled + individual domains checks."""
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.can_use_bastion",
        staticmethod(lambda payload: True),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.alloweds.Alloweds.is_allowed",
        staticmethod(lambda payload, allowed, kind, default: True),
    )


def test_update_bastion_authorized_keys(monkeypatch, test_client, bastion_db_factory):
    """PUT /item/desktop/{id}/bastion/authorized-keys"""
    jwt = MockJWT()
    captured = {}

    def fake_update(desktop_id, authorized_keys):
        captured["desktop_id"] = desktop_id
        captured["authorized_keys"] = authorized_keys
        return {}

    monkeypatch.setattr(
        "api.services.bastion.BastionService.update_bastion_authorized_keys",
        staticmethod(fake_update),
    )
    _bypass_owns_domain_id(monkeypatch)
    _bypass_bastion_checks(monkeypatch)

    response = test_client(
        url="/item/desktop/desktop-1/bastion/authorized-keys",
        method="PUT",
        body={"authorized_keys": ["ssh-ed25519 AAAA... user@host"]},
        jwt=jwt,
        db_tables_data=bastion_db_factory(jwt),
    )

    assert response.status_code == 204
    assert captured["desktop_id"] == "desktop-1"
    assert captured["authorized_keys"] == ["ssh-ed25519 AAAA... user@host"]


def test_update_bastion_authorized_keys_empty_rejected(
    monkeypatch, test_client, bastion_db_factory
):
    """PUT /item/desktop/{id}/bastion/authorized-keys with empty list."""
    jwt = MockJWT()
    _bypass_owns_domain_id(monkeypatch)
    _bypass_bastion_checks(monkeypatch)

    def fake_update(desktop_id, authorized_keys):
        from api.services.error import Error

        raise Error("bad_request", "Authorized keys are required")

    monkeypatch.setattr(
        "api.services.bastion.BastionService.update_bastion_authorized_keys",
        staticmethod(fake_update),
    )

    response = test_client(
        url="/item/desktop/desktop-1/bastion/authorized-keys",
        method="PUT",
        body={"authorized_keys": []},
        jwt=jwt,
        db_tables_data=bastion_db_factory(jwt),
    )

    assert response.status_code == 400


def test_update_bastion_domains(monkeypatch, test_client, bastion_db_factory):
    """PUT /item/desktop/{id}/bastion/domains"""
    jwt = MockJWT()
    captured = {}

    def fake_update(desktop_id, domains, category_id):
        captured["desktop_id"] = desktop_id
        captured["domains"] = domains
        captured["category_id"] = category_id
        return {}

    monkeypatch.setattr(
        "api.services.bastion.BastionService.update_bastion_domains",
        staticmethod(fake_update),
    )
    _bypass_owns_domain_id(monkeypatch)
    _bypass_bastion_checks(monkeypatch)

    response = test_client(
        url="/item/desktop/desktop-1/bastion/domains",
        method="PUT",
        body={"domains": ["app.example.com", "web.example.com"]},
        jwt=jwt,
        db_tables_data=bastion_db_factory(jwt),
    )

    assert response.status_code == 204
    assert captured["desktop_id"] == "desktop-1"
    assert captured["domains"] == ["app.example.com", "web.example.com"]
    assert captured["category_id"] == jwt.payload["category_id"]


def test_update_bastion_domains_forbidden_without_individual(
    monkeypatch, test_client, bastion_db_factory
):
    """PUT /item/desktop/{id}/bastion/domains — forbidden when user lacks
    individual domain permission."""
    jwt = MockJWT()
    _bypass_owns_domain_id(monkeypatch)
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.can_use_bastion",
        staticmethod(lambda payload: True),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.alloweds.Alloweds.is_allowed",
        staticmethod(lambda payload, allowed, kind, default: False),
    )

    response = test_client(
        url="/item/desktop/desktop-1/bastion/domains",
        method="PUT",
        body={"domains": ["app.example.com"]},
        jwt=jwt,
        db_tables_data=bastion_db_factory(jwt),
    )

    assert response.status_code == 403


def test_verify_bastion_domain(monkeypatch, test_client, bastion_db_factory):
    """POST /item/desktop/{id}/bastion/domain/verify"""
    jwt = MockJWT()
    captured = {}

    def fake_verify(desktop_id, domain, category_id):
        captured["desktop_id"] = desktop_id
        captured["domain"] = domain
        captured["category_id"] = category_id
        return {"verified": True}

    monkeypatch.setattr(
        "api.services.bastion.BastionService.verify_bastion_domain",
        staticmethod(fake_verify),
    )
    _bypass_owns_domain_id(monkeypatch)
    _bypass_bastion_checks(monkeypatch)

    response = test_client(
        url="/item/desktop/desktop-1/bastion/domain/verify",
        method="POST",
        body={"domain": "myapp.example.com"},
        jwt=jwt,
        db_tables_data=bastion_db_factory(jwt),
    )

    assert response.status_code == 200
    assert response.json() == {"verified": True}
    assert captured["desktop_id"] == "desktop-1"
    assert captured["domain"] == "myapp.example.com"
    assert captured["category_id"] == jwt.payload["category_id"]


def test_verify_bastion_domain_forbidden_without_individual(
    monkeypatch, test_client, bastion_db_factory
):
    """POST /item/desktop/{id}/bastion/domain/verify — forbidden when user
    lacks individual domain permission."""
    jwt = MockJWT()
    _bypass_owns_domain_id(monkeypatch)
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.can_use_bastion",
        staticmethod(lambda payload: True),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.alloweds.Alloweds.is_allowed",
        staticmethod(lambda payload, allowed, kind, default: False),
    )

    response = test_client(
        url="/item/desktop/desktop-1/bastion/domain/verify",
        method="POST",
        body={"domain": "myapp.example.com"},
        jwt=jwt,
        db_tables_data=bastion_db_factory(jwt),
    )

    assert response.status_code == 403


def test_verify_bastion_domain_empty_rejected(
    monkeypatch, test_client, bastion_db_factory
):
    """POST /item/desktop/{id}/bastion/domain/verify — empty domain
    rejected by Pydantic min_length=1."""
    jwt = MockJWT()
    _bypass_owns_domain_id(monkeypatch)
    _bypass_bastion_checks(monkeypatch)

    response = test_client(
        url="/item/desktop/desktop-1/bastion/domain/verify",
        method="POST",
        body={"domain": ""},
        jwt=jwt,
        db_tables_data=bastion_db_factory(jwt),
    )

    # FastAPI custom error handler converts Pydantic validation errors to 400
    assert response.status_code == 400


# ────────────────────────────────────────────────────────────────────
# Bug 40 — async offload of GET /items/bastions
# ────────────────────────────────────────────────────────────────────


@pytest.mark.setup_clear_cache
def test_get_bastion_targets_offloads_to_worker_thread(
    monkeypatch, test_client, bastion_db_factory
):
    """``Targets.get_user_targets`` must run on a worker thread, not
    on the asyncio event loop. Pinning this catches a regression to
    the pre-fix shape where the sync rdb call blocked the loop and
    serialised concurrent requests under load (rev-13 bastions_list
    p95 = 3947 ms).

    Strategy: patch ``asyncio.to_thread`` to record every call and
    confirm the route routes ``Targets.get_user_targets`` through it.
    """
    import asyncio as _asyncio

    monkeypatch.setenv("BASTION_ENABLED", "true")

    jwt = MockJWT()

    from isardvdi_common.models.targets import Targets

    scheduled = []

    real_to_thread = _asyncio.to_thread

    async def recording_to_thread(fn, *args, **kwargs):
        scheduled.append((fn, args))
        return await real_to_thread(fn, *args, **kwargs)

    monkeypatch.setattr("api.routes.bastion.asyncio.to_thread", recording_to_thread)

    response = test_client(
        db_tables_data=bastion_db_factory(jwt),
        method="GET",
        url="/api/v4/items/bastions",
        jwt=jwt,
    )

    assert response.status_code == 200
    # ``Targets.get_user_targets`` is a classmethod — accessing it
    # produces a fresh bound-method per lookup, so identity (``is``)
    # comparison won't work. Match by the underlying ``__func__`` /
    # qualname instead.
    expected = Targets.get_user_targets.__func__
    assert any(getattr(fn, "__func__", fn) is expected for fn, _args in scheduled), (
        "Targets.get_user_targets must be dispatched through "
        "asyncio.to_thread — see Bug 40 in load-testing markdown. "
        f"Saw: {[getattr(fn, '__qualname__', repr(fn)) for fn, _ in scheduled]}"
    )
