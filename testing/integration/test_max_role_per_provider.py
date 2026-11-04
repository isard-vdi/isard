# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-provider ``max_role`` cap (feat/max-role-per-provider), end to end.

A category's ``authentication.<provider>.max_role`` caps the role that provider
can grant. Driven against a live stack with a local provider (no IdP needed):

* write cap: creating or raising a user above the cap is rejected (apiv4);
* login gate: an existing user whose role is above the cap can no longer log in
  (authentication service).

Only an admin may set max_role, so the fixtures use the seeded admin.
"""

import time
from typing import Iterator

import pytest

from .helpers.client import IsardClient, auth_login

pytestmark = pytest.mark.real

PASSWORD = "Max-Role-E2E-9!"
# process_*_limits/get_document and the auth provider cache settle within ~10s;
# wait after a max_role change so the gate reads the new value deterministically.
_SETTLE = 12


def _auth_local(max_role=None):
    local = {
        "disabled": False,
        "config_source": "global",
        "email_domain_restriction": {"enabled": False, "allowed": []},
    }
    if max_role is not None:
        local["max_role"] = max_role
    return {
        "authentication": {
            "local": local,
            "ldap": {"disabled": True},
            "google": {"disabled": True},
            "saml": {"disabled": True},
        }
    }


@pytest.fixture
def cat(admin_client: IsardClient, test_namespace: str) -> Iterator[dict]:
    name = f"{test_namespace}mr"
    c = admin_client.post(
        "/api/v4/admin/item/category",
        json_body={"name": name, "description": "max_role", "manager_permissions": {}},
    )
    cid = c["id"]
    g = admin_client.post(
        "/api/v4/admin/item/group",
        json_body={"name": "classe", "description": "x", "parent_category": cid},
    )
    try:
        yield {"id": cid, "name": name, "group": g["id"]}
    finally:
        admin_client.raw("DELETE", f"/api/v4/admin/item/category/{cid}")


def _set_max_role(admin_client, cid, max_role):
    admin_client.put(
        f"/api/v4/admin/item/category/{cid}/authentication",
        json_body=_auth_local(max_role),
    )
    time.sleep(_SETTLE)


def _new_local(admin_client, cat, username, role):
    return admin_client.request(
        "POST",
        "/api/v4/admin/item/user",
        json_body={
            "username": username,
            "name": username,
            "category": cat["id"],
            "group": cat["group"],
            "role": role,
            "password": PASSWORD,
            "email": f"{username}@example.org",
        },
        expected=None,
    )


def _roles(admin_client, cid):
    users = admin_client.get(f"/api/v4/admin/items/category/{cid}/users")
    return {u.get("username"): u.get("role") for u in users}


def test_write_cap_blocks_create_and_raise_above_max_role(
    admin_client, cat, test_namespace
):
    _set_max_role(admin_client, cat["id"], "advanced")

    admin_client.post(
        "/api/v4/admin/item/user",
        json_body={
            "username": f"{test_namespace}u",
            "name": "u",
            "category": cat["id"],
            "group": cat["group"],
            "role": "user",
            "password": PASSWORD,
        },
        expected=(200, 201),
    )
    # creating a manager (> advanced) is rejected and nothing is written
    _new_local(admin_client, cat, f"{test_namespace}m", "manager")
    roles = _roles(admin_client, cat["id"])
    assert f"{test_namespace}m" not in roles

    # raising the existing user to manager is rejected too
    uid = [
        u["id"]
        for u in admin_client.get(f"/api/v4/admin/items/category/{cat['id']}/users")
        if u["username"] == f"{test_namespace}u"
    ][0]
    admin_client.request(
        "PUT",
        f"/api/v4/admin/item/user/{uid}",
        json_body={"role": "manager"},
        expected=(403,),
    )
    assert _roles(admin_client, cat["id"])[f"{test_namespace}u"] == "user"


def test_login_gate_blocks_user_above_lowered_cap(admin_client, cat, test_namespace):
    # With cap=manager, create a local manager and prove it logs in.
    _set_max_role(admin_client, cat["id"], "manager")
    mgr = f"{test_namespace}lm"
    admin_client.post(
        "/api/v4/admin/item/user",
        json_body={
            "username": mgr,
            "name": mgr,
            "category": cat["id"],
            "group": cat["group"],
            "role": "manager",
            "password": PASSWORD,
        },
        expected=(200, 201),
    )
    token = auth_login(admin_client.auth_url, mgr, PASSWORD, category_id=cat["id"])
    assert token and token.count(".") == 2

    # Lower the cap to advanced: the stored manager is now above it and is
    # refused at login (treated as invalid credentials).
    _set_max_role(admin_client, cat["id"], "advanced")
    with pytest.raises(RuntimeError):
        auth_login(admin_client.auth_url, mgr, PASSWORD, category_id=cat["id"])
