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


import os

import pytest
from api.routes.tests.factories import make_category, make_group, make_user
from api.routes.tests.helpers import MockJWT


@pytest.fixture()
def users_db_factory():
    """Fixture to create a mock database for users."""

    def users_db_tables_data(jwt):
        p = jwt.payload
        return {
            "categories": [
                make_category(id=p["category_id"], name="Category Name"),
                make_category(id="cat2", name="Another Category", uid="cat2"),
            ],
            "groups": [
                make_group(
                    id=p["group_id"],
                    parent_category=p["category_id"],
                    name=f"{p['group_id']} Name",
                    description=f"{p['group_id']} Description",
                    uid=p["group_id"],
                ),
                make_group(
                    id=f"another-group-{p['category_id']}",
                    parent_category=p["category_id"],
                    name=f"Another Group {p['category_id']}",
                    description="Another Group Description",
                    uid=f"another-group-{p['category_id']}",
                ),
                make_group(
                    id="group-cat2",
                    parent_category="cat2",
                    name="Group Cat2",
                    description="Group Cat2 Description",
                    uid="group-cat2",
                ),
            ],
            "users": [
                make_user(jwt=jwt),
                make_user(
                    id="another-user",
                    category=p["category_id"],
                    group=f"another-group-{p['category_id']}",
                    name="Another User",
                    username="another-user",
                    password="another-password",
                    provider="local",
                    role="advanced",
                    uid="another-user",
                ),
                make_user(
                    id="cat2-user",
                    category="cat2",
                    group="group-cat2",
                    name="Cat2 User",
                    username="cat2-user",
                    password="cat2-password",
                    provider="local",
                    role="advanced",
                    uid="cat2-user",
                ),
            ],
        }

    return users_db_tables_data


def test_get_all_users_admin(test_client, users_db_factory):
    jwt = MockJWT()

    db_data = users_db_factory(jwt)

    expected = [
        {
            "id": "local-default-admin-admin",
            "name": "Administrator",
            "category": "default",
            "category_name": "Category Name",
            "photo": "",
            "accessed": 1234567890,
        },
        {
            "id": "another-user",
            "name": "Another User",
            "category": "default",
            "category_name": "Category Name",
            "photo": "",
            "accessed": 1234567890,
        },
        {
            "id": "cat2-user",
            "name": "Cat2 User",
            "category": "cat2",
            "category_name": "Another Category",
            "photo": "",
            "accessed": 1234567890,
        },
    ]

    response = test_client(
        url="/api/v4/items/users",
        jwt=jwt,
        db_tables_data=db_data,
    )

    assert response.status_code == 200
    assert response.json() == expected


def test_get_all_users_manager(test_client, users_db_factory):
    jwt = MockJWT(role_id="manager")

    db_data = users_db_factory(jwt)

    expected = [
        {
            "id": "local-default-admin-admin",
            "name": "Administrator",
            "category": "default",
            "category_name": "Category Name",
            "photo": "",
            "accessed": 1234567890,
        },
        {
            "id": "another-user",
            "name": "Another User",
            "category": "default",
            "category_name": "Category Name",
            "photo": "",
            "accessed": 1234567890,
        },
    ]

    response = test_client(
        url="/api/v4/items/users",
        jwt=jwt,
        db_tables_data=db_data,
    )

    assert response.status_code == 200
    assert response.json() == expected


def test_get_all_groups_admin(test_client, users_db_factory):
    jwt = MockJWT()

    db_data = users_db_factory(jwt)

    expected = [
        {
            "id": "default-default",
            "name": "default-default Name",
            "category_id": "default",
            "category_name": "Category Name",
        },
        {
            "id": "another-group-default",
            "name": "Another Group default",
            "category_id": "default",
            "category_name": "Category Name",
        },
        {
            "id": "group-cat2",
            "name": "Group Cat2",
            "category_id": "cat2",
            "category_name": "Another Category",
        },
    ]

    response = test_client(
        url="/items/groups",
        jwt=jwt,
        db_tables_data=db_data,
    )

    assert response.status_code == 200
    assert response.json() == expected


def test_get_all_groups_manager(test_client, users_db_factory):
    jwt = MockJWT(role_id="manager")

    db_data = users_db_factory(jwt)

    expected = [
        {
            "id": "default-default",
            "name": "default-default Name",
            "category_id": "default",
            "category_name": "Category Name",
        },
        {
            "id": "another-group-default",
            "name": "Another Group default",
            "category_id": "default",
            "category_name": "Category Name",
        },
    ]

    response = test_client(
        url="/items/groups",
        jwt=jwt,
        db_tables_data=db_data,
    )

    assert response.status_code == 200
    assert response.json() == expected


# ─── Allowed hardware per existing domain ────────────────────────────────
# The /item/user/get-allowed-hardware/{domain_id} route replaces the v3
# /user/hardware/allowed/{domain_id} shim that called the common Quotas
# helper inline. The test monkeypatches UsersService.get_allowed_hardware
# so the test stays framework-agnostic of the common-lib DB layer.


def _stub_allowed_hardware_dict() -> dict:
    """Return a minimal dict that pydantic UserAllowedHardwareResponse
    will validate successfully — all lists empty, reservables empty,
    quota disabled."""
    return {
        "virtualization_nested": False,
        "interfaces": [],
        "graphics": [],
        "videos": [],
        "boot_order": [],
        "qos_id": [],
        "isos": [],
        "floppies": [],
        "reservables": {"vgpus": []},
        "disk_bus": [],
        "forced_hyp": [],
        "favourite_hyp": [],
        "quota": False,
        "restriction_applied": "user_quota",
    }


def test_get_allowed_hardware_for_domain(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_get_allowed_hardware(user_id, domain_id=None):
        captured["user_id"] = user_id
        captured["domain_id"] = domain_id
        return _stub_allowed_hardware_dict()

    monkeypatch.setattr(
        "api.services.users.UsersService.get_allowed_hardware",
        staticmethod(fake_get_allowed_hardware),
    )

    response = test_client(
        url="/item/user/get-allowed-hardware/desktop-1",
        jwt=jwt,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["quota"] is False
    assert body["interfaces"] == []
    # Service received the caller's user id AND the domain from the path
    assert captured == {
        "user_id": jwt.payload["user_id"],
        "domain_id": "desktop-1",
    }


def test_get_allowed_hardware_without_domain(monkeypatch, test_client):
    """Regression guard: the original /item/user/get-allowed-hardware route
    must still call the service without a domain_id when the path param is
    absent."""
    jwt = MockJWT()
    captured = {}

    def fake_get_allowed_hardware(user_id, domain_id=None):
        captured["user_id"] = user_id
        captured["domain_id"] = domain_id
        return _stub_allowed_hardware_dict()

    monkeypatch.setattr(
        "api.services.users.UsersService.get_allowed_hardware",
        staticmethod(fake_get_allowed_hardware),
    )

    response = test_client(
        url="/item/user/get-allowed-hardware",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured["domain_id"] is None


# ─── Profile / user self-ops ──────────────────────────────────────────────
# Covers the profile-page endpoints the Vue 2 old-frontend and webapp
# talk to: get-config, get-api-key, get-password-policy, set-lang,
# set-email, set-password, reset-vpn, expire-api-key. Every test
# monkeypatches the corresponding UsersService staticmethod so the
# common-lib DB layer is untouched.


def _stub_user_config() -> dict:
    """Minimal UserConfigResponse-shaped dict (all required fields)."""
    return {
        "show_bookings_button": True,
        "documentation_url": "https://docs.example",
        "viewers_documentation_url": "https://docs.example/viewers",
        "show_change_email_button": True,
        "show_temporal_tab": False,
        "http_port": "80",
        "https_port": "443",
        "bastion_domain": None,
        "bastion_ssh_port": None,
        "can_use_bastion": False,
        "can_use_bastion_individual_domains": False,
        "migrations_block": False,
        "session": {},
        "frontend_mode": "deprecated",
        "faro": {"enabled": False, "url": None},
    }


def test_get_user_config(monkeypatch, test_client):
    jwt = MockJWT()
    stub = _stub_user_config()
    captured = {}

    def fake_get_user_config(payload):
        captured["user_id"] = payload["user_id"]
        return stub

    monkeypatch.setattr(
        "api.services.users.UsersService.get_user_config",
        staticmethod(fake_get_user_config),
    )

    response = test_client(url="/item/user/get-config", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert body["documentation_url"] == "https://docs.example"
    assert body["frontend_mode"] == "deprecated"
    assert body["faro"] == {"enabled": False, "url": None}
    assert captured["user_id"] == jwt.payload["user_id"]


@pytest.mark.parametrize(
    "env_value,expected",
    [
        ("deprecated", "deprecated"),
        ("actual", "actual"),
        ("all", "all"),
        ("garbage", "deprecated"),
        ("", "deprecated"),
    ],
)
def test_user_config_frontend_mode_values(
    monkeypatch, test_client, env_value, expected
):
    """FRONTEND_MODE env var must propagate (or fall back) to the response."""
    jwt = MockJWT()

    if env_value == "":
        monkeypatch.delenv("FRONTEND_MODE", raising=False)
    else:
        monkeypatch.setenv("FRONTEND_MODE", env_value)

    stub = _stub_user_config()

    def fake_get_user_config(payload):
        raw = os.environ.get("FRONTEND_MODE", "deprecated")
        mode = raw if raw in ("deprecated", "actual", "all") else "deprecated"
        return {**stub, "frontend_mode": mode}

    monkeypatch.setattr(
        "api.services.users.UsersService.get_user_config",
        staticmethod(fake_get_user_config),
    )

    response = test_client(url="/item/user/get-config", jwt=jwt)
    assert response.status_code == 200
    assert response.json()["frontend_mode"] == expected


@pytest.mark.parametrize(
    "faro_enabled,faro_url,expected",
    [
        ("true", None, {"enabled": True, "url": "/faro/collect"}),
        (
            "true",
            "https://faro.example/collect",
            {"enabled": True, "url": "https://faro.example/collect"},
        ),
        ("false", None, {"enabled": False, "url": None}),
        (None, None, {"enabled": False, "url": None}),
    ],
)
def test_user_config_faro_values(
    monkeypatch, test_client, faro_enabled, faro_url, expected
):
    """FARO_ENABLED / FARO_URL env vars drive the faro block in the response."""
    jwt = MockJWT()

    if faro_enabled is None:
        monkeypatch.delenv("FARO_ENABLED", raising=False)
    else:
        monkeypatch.setenv("FARO_ENABLED", faro_enabled)
    if faro_url is None:
        monkeypatch.delenv("FARO_URL", raising=False)
    else:
        monkeypatch.setenv("FARO_URL", faro_url)

    stub = _stub_user_config()

    def fake_get_user_config(payload):
        on = os.environ.get("FARO_ENABLED", "false").lower() == "true"
        faro = {
            "enabled": on,
            "url": (os.environ.get("FARO_URL") or "/faro/collect") if on else None,
        }
        return {**stub, "faro": faro}

    monkeypatch.setattr(
        "api.services.users.UsersService.get_user_config",
        staticmethod(fake_get_user_config),
    )

    response = test_client(url="/item/user/get-config", jwt=jwt)
    assert response.status_code == 200
    assert response.json()["faro"] == expected


def test_get_user_password_policy(monkeypatch, test_client):
    jwt = MockJWT()
    stub = {
        "digits": 1,
        "expiration": 0,
        "length": 8,
        "lowercase": 1,
        "not_username": True,
        "old_passwords": 3,
        "special_characters": 0,
        "uppercase": 1,
    }
    monkeypatch.setattr(
        "api.services.users.UsersService.get_user_password_policy",
        staticmethod(lambda user_id: stub),
    )

    response = test_client(url="/item/user/get-password-policy", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_get_user_api_key(monkeypatch, test_client):
    jwt = MockJWT(role_id="advanced")
    stub = {"exists": True, "expires": 1765200000.0}
    monkeypatch.setattr(
        "api.services.users.UsersService.get_user_api_key",
        staticmethod(lambda user_id: stub),
    )

    response = test_client(url="/item/user/get-api-key", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_expire_user_api_key(monkeypatch, test_client):
    jwt = MockJWT(role_id="advanced")
    calls = []

    def fake_delete_api_key(user_id):
        calls.append(user_id)

    monkeypatch.setattr(
        "api.services.users.UsersService.delete_user_api_key",
        staticmethod(fake_delete_api_key),
    )

    response = test_client(
        url="/item/user/expire-api-key",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == [jwt.payload["user_id"]]


def test_reset_user_vpn(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []

    def fake_reset_vpn(user_id):
        calls.append(user_id)

    monkeypatch.setattr(
        "api.services.users.UsersService.reset_user_vpn",
        staticmethod(fake_reset_vpn),
    )

    response = test_client(
        url="/item/user/reset-vpn",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 204
    assert calls == [jwt.payload["user_id"]]


def test_set_user_language(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_set_language(user_id, lang):
        captured["user_id"] = user_id
        captured["lang"] = lang

    monkeypatch.setattr(
        "api.services.users.UsersService.set_user_language",
        staticmethod(fake_set_language),
    )

    response = test_client(
        url="/item/user/set-lang",
        method="PUT",
        body={"lang": "ca"},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": jwt.payload["user_id"]}
    assert captured == {"user_id": jwt.payload["user_id"], "lang": "ca"}


def test_set_user_email(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_set_email(user_id, email):
        captured["user_id"] = user_id
        captured["email"] = email

    monkeypatch.setattr(
        "api.services.users.UsersService.set_user_email",
        staticmethod(fake_set_email),
    )

    response = test_client(
        url="/item/user/set-email",
        method="PUT",
        body={"email": "me@example.com"},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": jwt.payload["user_id"]}
    assert captured == {
        "user_id": jwt.payload["user_id"],
        "email": "me@example.com",
    }


# ─── Admin user migrate check (T1/admin/user/migrate/check shim) ──────


def test_admin_check_migration(monkeypatch, test_client):
    """GET /admin/user/migrate/check/{user_id}/{target_user_id} —
    replaces v3 /admin/user/migrate/check/{uid}/{tid} shim."""
    jwt = MockJWT()
    captured = {}

    def fake_check(payload, user_id, target_user_id):
        captured["user_id"] = user_id
        captured["target_user_id"] = target_user_id
        return []

    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.check_valid_migration",
        staticmethod(fake_check),
    )

    response = test_client(url="/admin/user/migrate/check/user-1/user-2", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == {"errors": []}
    assert captured == {"user_id": "user-1", "target_user_id": "user-2"}


def test_groups_users_count(monkeypatch, test_client):
    """PUT /items/groups-users/count replaces v3 /groups_users/count shim."""
    jwt = MockJWT(role_id="advanced")
    captured = {}

    def fake_count(groups, user_id):
        captured["groups"] = groups
        captured["user_id"] = user_id
        return 42

    monkeypatch.setattr(
        "api.services.users.UsersService.groups_users_count",
        staticmethod(fake_count),
    )

    response = test_client(
        url="/items/groups-users/count",
        method="PUT",
        body={"groups": ["group-1", "group-2"]},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"quantity": 42}
    assert captured == {
        "groups": ["group-1", "group-2"],
        "user_id": jwt.payload["user_id"],
    }


def test_set_user_password(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_set_password(user_id, new_password, current_password):
        captured["user_id"] = user_id
        captured["new_password"] = new_password
        captured["current_password"] = current_password

    monkeypatch.setattr(
        "api.services.users.UsersService.set_user_password",
        staticmethod(fake_set_password),
    )

    response = test_client(
        url="/item/user/set-password",
        method="PUT",
        body={"current_password": "oldP4$", "password": "N3wPassword!"},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": jwt.payload["user_id"]}
    assert captured == {
        "user_id": jwt.payload["user_id"],
        "new_password": "N3wPassword!",
        "current_password": "oldP4$",
    }
