#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin the wiring around ``change_user_group``, which had no coverage at all.

It is destructive — it force-stops the user's desktops, empties their recycle
bin and re-parents every domain and media row — and three defects lived in that
blind spot: ``update_user`` ran it twice per request, ``update_multiple_users``
decided from a loop variable left over from an earlier loop, and
``owns_deployment_desktop_id`` passed a keyword the callee does not accept.

The move itself needs a real RethinkDB and is verified on the staging testbed.
"""

from unittest.mock import MagicMock

import pytest


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def users_mod(monkeypatch):
    from isardvdi_common.lib.users.users import user as mod

    monkeypatch.setattr(
        mod.UsersProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.UsersProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    monkeypatch.setattr(mod, "revoke_user_session", lambda *a, **k: None)
    monkeypatch.setattr(mod, "notify_admin", lambda *a, **k: None)
    monkeypatch.setattr(
        mod.Caches, "invalidate_cache", classmethod(lambda cls, *a: None)
    )
    monkeypatch.setattr(
        mod.Caches, "invalidate_caches", classmethod(lambda cls, *a: None)
    )
    monkeypatch.setattr(
        mod.Caches,
        "get_document",
        classmethod(lambda cls, table, item_id, *a, **k: {"parent_category": "cat-1"}),
    )
    monkeypatch.setattr(
        mod.UserStorage,
        "isard_user_storage_update_user",
        staticmethod(lambda **k: None),
    )

    calls = []
    monkeypatch.setattr(
        mod.UsersProcessed,
        "change_user_group",
        classmethod(lambda cls, user_id, group_id: calls.append((user_id, group_id))),
    )
    return {"mod": mod, "calls": calls, "monkeypatch": monkeypatch}


def _stub_users_table(monkeypatch, mod, single=None, many=None):
    """Serve ``users`` reads from fixtures and swallow every write."""
    writes = []

    def fake_table(name):
        table = MagicMock(name="table-" + name)

        def fake_get(item_id):
            row = MagicMock(name="row")
            row.pluck = lambda *f: MagicMock(run=lambda conn: single)
            row.update = lambda payload: MagicMock(
                run=lambda conn: writes.append((name, item_id, payload))
            )
            return row

        def fake_get_all(*args, **kwargs):
            sel = MagicMock(name="selection")
            sel.pluck = lambda *f: MagicMock(run=lambda conn: list(many or []))
            sel.update = lambda payload: MagicMock(
                run=lambda conn: writes.append((name, "ALL", payload))
            )
            return sel

        table.get = fake_get
        table.get_all = fake_get_all
        return table

    monkeypatch.setattr(mod.r, "table", fake_table)
    monkeypatch.setattr(mod.r, "args", lambda x: x)
    return writes


def test_update_user_moves_the_group_exactly_once(users_mod):
    """A single group change must trigger a single migration."""
    mod, calls, monkeypatch = (
        users_mod["mod"],
        users_mod["calls"],
        users_mod["monkeypatch"],
    )
    _stub_users_table(
        monkeypatch,
        mod,
        single={
            "id": "usr-1",
            "email": "a@example.org",
            "category": "cat-1",
            "role": "advanced",
            "email_verified": 1,
            "group": "grp-A",
            "provider": "local",
        },
    )

    mod.UsersProcessed.update_user("usr-1", {"group": "grp-B"})

    assert calls == [("usr-1", "grp-B")], (
        "change_user_group must run once per request; running it twice replays "
        "the force-stop, the recycle-bin purge and the re-parenting"
    )


def test_update_user_does_not_move_the_group_when_unchanged(users_mod):
    mod, calls, monkeypatch = (
        users_mod["mod"],
        users_mod["calls"],
        users_mod["monkeypatch"],
    )
    _stub_users_table(
        monkeypatch,
        mod,
        single={
            "id": "usr-1",
            "email": "a@example.org",
            "category": "cat-1",
            "role": "advanced",
            "email_verified": 1,
            "group": "grp-A",
            "provider": "local",
        },
    )

    mod.UsersProcessed.update_user("usr-1", {"group": "grp-A", "name": "New Name"})

    assert calls == []


def test_update_multiple_users_decides_per_user_not_per_batch(users_mod):
    """The first user already sitting in the target group must not mask the rest."""
    mod, calls, monkeypatch = (
        users_mod["mod"],
        users_mod["calls"],
        users_mod["monkeypatch"],
    )
    _stub_users_table(
        monkeypatch,
        mod,
        many=[
            {
                "id": "usr-already",
                "category": "cat-1",
                "group": "grp-B",
                "uid": "already",
                "provider": "local",
                "email": "already@example.org",
                "role": "advanced",
            },
            {
                "id": "usr-moves",
                "category": "cat-1",
                "group": "grp-A",
                "uid": "moves",
                "provider": "local",
                "email": "moves@example.org",
                "role": "advanced",
            },
        ],
    )

    mod.UsersProcessed.update_multiple_users(
        ["usr-already", "usr-moves"], {"group": "grp-B"}
    )

    assert calls == [
        ("usr-moves", "grp-B")
    ], "the migration decision must read the group of the user being processed"


def test_bulk_pluck_covers_every_field_the_body_dereferences(users_mod):
    """``email`` and ``role`` are read in the body, so they must be fetched."""
    mod, _, monkeypatch = users_mod["mod"], users_mod["calls"], users_mod["monkeypatch"]
    plucked = {}

    def fake_table(name):
        table = MagicMock(name="table-" + name)

        def fake_get_all(*args, **kwargs):
            sel = MagicMock(name="selection")

            def fake_pluck(*fields):
                plucked["fields"] = set(fields)
                return MagicMock(run=lambda conn: [])

            sel.pluck = fake_pluck
            sel.update = lambda payload: MagicMock(run=lambda conn: None)
            return sel

        table.get_all = fake_get_all
        return table

    monkeypatch.setattr(mod.r, "table", fake_table)
    monkeypatch.setattr(mod.r, "args", lambda x: x)

    mod.UsersProcessed.update_multiple_users(["usr-1"], {"name": "x"})

    assert {"email", "role"} <= plucked["fields"], (
        "the body dereferences user['email'] and user['role']; a pluck that "
        "omits them raises KeyError as soon as an email is being updated"
    )


def test_owns_deployment_desktop_id_grants_the_owner():
    """The co-owner flag must reach the callee under its real parameter name."""
    from isardvdi_common.helpers import helpers as mod

    docs = {
        ("domains", "dsk-1"): {"id": "dsk-1", "tag": "dep-1"},
        ("deployments", "dep-1"): {"id": "dep-1", "user": "usr-1", "co_owners": []},
    }

    original = mod.Caches.get_document
    mod.Caches.get_document = classmethod(
        lambda cls, table, item_id, *a, **k: docs.get((table, item_id))
    )
    try:
        assert (
            mod.Helpers.owns_deployment_desktop_id(
                {"role_id": "advanced", "user_id": "usr-1"}, "dsk-1"
            )
            is True
        )
    finally:
        mod.Caches.get_document = original
