# SPDX-License-Identifier: AGPL-3.0-or-later

"""A manager cannot reach the admin role through any user write path."""

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

    assert resp.status_code == 403, resp.text
    assert _role(admin_client, user_id) == "user"
