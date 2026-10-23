# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import MagicMock

import pytest
from isardvdi_common.lib.deployments import deployment_users as mod

DU = mod.DeploymentUsers

USERS = {
    "u-own": {"id": "u-own", "username": "own", "category": "cat-a", "group": "g-a"},
    "u-other": {
        "id": "u-other",
        "username": "other",
        "category": "cat-b",
        "group": "g-b",
    },
}


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def get_all(self, *a, **k):
        return self

    def filter(self, predicate):
        if isinstance(predicate, dict):
            return _Query(
                [
                    row
                    for row in self.rows
                    if all(row.get(k) == v for k, v in predicate.items())
                ]
            )
        return self

    def pluck(self, *a):
        return self

    def run(self, conn):
        return list(self.rows)


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(DU, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(DU), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    monkeypatch.setattr(mod.r, "args", lambda values: values)

    def table(name):
        if name == "users":
            return _Query(list(USERS.values()))
        return _Query([])

    monkeypatch.setattr(mod.r, "table", table)


def _selected(**kwargs):
    return {
        "roles": False,
        "categories": False,
        "groups": False,
        "users": False,
        **kwargs,
    }


@pytest.mark.parametrize(
    "selected",
    [
        _selected(users=["u-own", "u-other"]),
        _selected(groups=["g-a", "g-b"]),
    ],
)
def test_a_manager_only_gets_users_of_its_own_category(db, selected):
    payload = {"user_id": "u-mgr", "role_id": "manager", "category_id": "cat-a"}

    users = DU.get_selected_users(payload, selected)

    assert {u["id"] for u in users} == {"u-own"}


def test_an_admin_gets_users_of_every_category(db):
    payload = {"user_id": "u-adm", "role_id": "admin", "category_id": "default"}

    users = DU.get_selected_users(payload, _selected(users=["u-own", "u-other"]))

    assert {u["id"] for u in users} == {"u-own", "u-other"}
