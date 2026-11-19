# SPDX-License-Identifier: AGPL-3.0-or-later

"""A manager cannot raise a user's privileges through any user write path."""

from __future__ import annotations

import os
from typing import Iterator

import pytest

from .helpers.client import IsardClient

pytestmark = pytest.mark.real

MANAGER01 = (
    os.environ.get("E2E_MANAGER01_USERNAME", "manager01"),
    os.environ.get("E2E_MANAGER01_PASSWORD", "LB`*F9Uw"),
    os.environ.get("E2E_MANAGER01_CATEGORY", "default"),
)
PASSWORD = "Elevation-Test-9!"
# Seeded group of the "hidden" category: user02 and manager02.
FOREIGN_GROUP = "cca27c62-9db4-45a2-8faa-3897f095d507"


@pytest.fixture(scope="module")
def manager_client() -> IsardClient:
    client = IsardClient()
    client.login(MANAGER01[0], MANAGER01[1], category_id=MANAGER01[2])
    return client


def _user_body(name: str, role: str) -> dict:
    return {
        "username": name,
        "name": name,
        "provider": "local",
        "category": "default",
        "group": "default-default",
        "role": role,
        "password": PASSWORD,
    }


@pytest.fixture
def make_user(admin_client: IsardClient, test_namespace: str) -> Iterator:
    created = []

    def _make(suffix: str, role: str) -> str:
        user = admin_client.post(
            "/api/v4/admin/item/user",
            json_body=_user_body(f"{test_namespace}{suffix}", role),
        )
        created.append(user["id"])
        return user["id"]

    yield _make
    if created:
        admin_client.raw(
            "DELETE",
            "/api/v4/admin/items/users",
            json={"user": created, "delete_user": True},
        )


def _role(admin_client: IsardClient, user_id: str) -> str:
    return admin_client.get(f"/api/v4/admin/item/user/{user_id}")["role"]


def test_a_manager_cannot_create_an_admin(manager_client, test_namespace):
    resp = manager_client.raw(
        "POST",
        "/api/v4/admin/item/user",
        json=_user_body(f"{test_namespace}elev_create", "admin"),
    )
    assert resp.status_code == 403, resp.text


def test_a_manager_cannot_raise_a_user_to_admin_through_csv_edit(
    manager_client, admin_client, make_user
):
    user_id = make_user("elev_csv", "user")

    resp = manager_client.raw(
        "PUT",
        "/api/v4/admin/items/users/csv",
        json={"users": [{"id": user_id, "role": "admin"}]},
    )

    # role is not a column of the CSV-update files
    assert resp.status_code == 400, resp.text
    assert _role(admin_client, user_id) == "user"


def test_a_manager_cannot_add_another_categorys_group_through_csv_edit(
    manager_client, admin_client, make_user
):
    user_id = make_user("elev_sg", "user")

    resp = manager_client.raw(
        "PUT",
        "/api/v4/admin/items/users/csv",
        json={"users": [{"id": user_id, "secondary_groups": [FOREIGN_GROUP]}]},
    )

    assert resp.status_code == 403, resp.text
    raw = admin_client.get(f"/api/v4/admin/item/user/{user_id}/raw")
    assert FOREIGN_GROUP not in (raw.get("secondary_groups") or [])


def test_csv_bulk_create_refuses_a_field_outside_the_csv_columns(
    manager_client, test_namespace
):
    resp = manager_client.raw(
        "POST",
        "/api/v4/admin/items/bulk/user",
        json={
            "users": [
                {
                    "username": f"{test_namespace}elev_bulk",
                    "name": f"{test_namespace}elev_bulk",
                    "email": "",
                    "group": "Default",
                    "category": "Default",
                    "role": "user",
                    "password": PASSWORD,
                    "quota": {"desktops": 999},
                }
            ]
        },
    )

    assert resp.status_code == 400, resp.text
