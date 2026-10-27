# SPDX-License-Identifier: AGPL-3.0-or-later

"""The costly-repair allowed list and the desktop disk fix through HTTP."""

import pytest
from isardvdi_common.helpers.alloweds import Alloweds
from tests.routes.helpers import MockJWT

ALLOWED = {"roles": ["manager"], "categories": False, "groups": False, "users": False}
EMPTY = {"roles": False, "categories": False, "groups": False, "users": False}


@pytest.mark.parametrize("role, status", [("admin", 204), ("manager", 403)])
def test_the_update_route_takes_the_storage_repair_table(
    monkeypatch, test_client, role, status
):
    written = []
    monkeypatch.setattr(
        "api.services.admin.alloweds.Alloweds.update_storage_repair_alloweds",
        lambda allowed: written.append(allowed),
    )
    response = test_client(
        url="/item/allowed/update/storage_repair",
        method="POST",
        jwt=MockJWT(role_id=role),
        body={"id": "1", "allowed": ALLOWED},
    )
    assert response.status_code == status
    assert written == ([ALLOWED] if status == 204 else [])


@pytest.fixture
def desktop(monkeypatch):
    from api.services import storage_problems as sp

    queued = []
    row = {"status": "damaged", "directory_path": "/isard/groups"}

    class FakeStorage:
        get = staticmethod(lambda i: row if i == "s1" else None)

        def __init__(self, storage_id):
            self.id = storage_id

        def repair(self, user_id, what, **kwargs):
            queued.append((user_id, what))
            return "t1"

    monkeypatch.setattr(sp, "Storage", FakeStorage)
    monkeypatch.setattr(
        sp.StorageProblemsService, "_desktop_disks", staticmethod(lambda p, d: ["s1"])
    )
    monkeypatch.setattr(sp, "_running_task", lambda i: None)
    monkeypatch.setattr(sp, "_estimate", lambda fix, row: None)
    return queued


@pytest.mark.parametrize(
    "role, allowed, status",
    [
        ("user", EMPTY, 403),
        ("manager", EMPTY, 403),
        ("manager", ALLOWED, 200),
        ("admin", EMPTY, 200),
    ],
)
def test_a_costly_fix_through_http_checks_the_list(
    monkeypatch, test_client, desktop, role, allowed, status
):
    monkeypatch.setattr(Alloweds, "get_storage_repair_allowed_dict", lambda: allowed)
    response = test_client(
        url="/item/desktop/d1/storage/s1/fix/repair_all",
        method="PUT",
        jwt=MockJWT(role_id=role),
    )
    assert response.status_code == status, response.text
    if status == 403:
        assert response.json()["description_code"] == "storage_repair_not_allowed"
        assert desktop == []
    else:
        assert [what for _, what in desktop] == ["all"]


def test_a_fix_name_outside_the_list_is_rejected(test_client):
    response = test_client(
        url="/item/desktop/d1/storage/s1/fix/convert",
        method="PUT",
        jwt=MockJWT(role_id="admin"),
    )
    assert response.status_code in (400, 422), response.text
