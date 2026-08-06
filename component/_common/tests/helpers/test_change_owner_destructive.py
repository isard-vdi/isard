# SPDX-License-Identifier: AGPL-3.0-or-later

"""Destructive ownership-transfer paths of ``Helpers`` in ``helpers.py``.

Reassigning a resource's owner is a one-shot, hard-to-undo write; volatile
desktops are torn down (not migrated). These pin, on the real functions:

* ``change_owner_domains`` -- persistent domains are reassigned with
  ``booking_id`` cleared while NON-persistent (volatile) domains are handed to
  the engine via ``ForceDeleting`` (never reassigned); an empty input writes
  nothing; a cross-category move drops the carried-over allowed grants.
* ``change_owner_desktops`` -- before the reassign it stops the desktops,
  deletes the previous owner's bookings, removes bastion targets and clears the
  direct viewer url, then delegates to ``change_owner_domains``.

Only rethink and the sibling collaborators are stubbed; the decisions are the
code's. We also assert what is NOT written on each branch.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub(monkeypatch):
    from isardvdi_common.helpers import helpers as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.Helpers, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(mod.Helpers),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    tables = {}

    def router(name):
        return tables.setdefault(name, MagicMock(name=f"table-{name}"))

    monkeypatch.setattr(mod.r, "table", MagicMock(side_effect=router))
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", tuple(x)))
    return {"mod": mod, "Cls": mod.Helpers, "router": router, "mp": monkeypatch}


def _domain_updates(stub):
    dom = stub["router"]("domains")
    return [c.args[0] for c in dom.get_all.return_value.update.call_args_list]


CAT = "cat-1"  # shared object so ``is`` comparison holds (same category)


def _user_data(category=CAT):
    return {
        "new_user": {
            "user": "u-new",
            "category": category,
            "allowed": {"categories": ["c"], "groups": False, "users": False},
        },
        "payload": {"role_id": "manager"},
    }


class TestChangeOwnerDomains:
    def _wire_fetch(self, stub, domains):
        stub["router"](
            "domains"
        ).get_all.return_value.pluck.return_value.run.return_value = domains
        # collaborators that would hit the DB / quotas
        for name in (
            "update_duplicated_names",
            "revoke_hardware_permissions",
            "change_storage_ownership",
        ):
            stub["mp"].setattr(
                stub["Cls"], name, classmethod(lambda cls, *a, **k: None)
            )

    def test_persistent_is_reassigned_not_torn_down(self, stub):
        ud = _user_data()
        self._wire_fetch(
            stub,
            [{"id": "d1", "category": CAT, "persistent": True}],
        )
        stub["Cls"].change_owner_domains(["d1"], ud, "desktop")
        updates = _domain_updates(stub)
        # Owner reassigned with booking cleared...
        assert {**ud["new_user"], "booking_id": False} in updates
        # ...and the volatile teardown status was NEVER written.
        assert all(
            u.get("status") != stub["mod"].DesktopStatusEnum.force_deleting.value
            for u in updates
        )

    def test_volatile_is_force_deleted_not_reassigned(self, stub):
        ud = _user_data()
        self._wire_fetch(
            stub,
            [{"id": "v1", "category": CAT, "persistent": False}],
        )
        stub["Cls"].change_owner_domains(["v1"], ud, "desktop")
        updates = _domain_updates(stub)
        # Volatile desktop handed to the engine for teardown...
        assert {"status": stub["mod"].DesktopStatusEnum.force_deleting.value} in updates
        # ...and it was NEVER reassigned to the new owner.
        assert all("booking_id" not in u for u in updates)

    def test_cross_category_drops_allowed_grants(self, stub):
        ud = _user_data(category="other-cat")  # different object -> cross category
        self._wire_fetch(
            stub,
            [{"id": "d1", "category": CAT, "persistent": True}],
        )
        stub["Cls"].change_owner_domains(["d1"], ud, "desktop")
        updates = _domain_updates(stub)
        reassign = [u for u in updates if "booking_id" in u][0]
        assert reassign["allowed"] == {
            "categories": False,
            "groups": False,
            "users": False,
        }


class TestChangeOwnerDesktops:
    def test_clears_bookings_targets_and_viewer_then_delegates(self, stub):
        # Isolate from change_owner_domains + quotas + stop.
        delegated = MagicMock(name="change_owner_domains")
        stub["mp"].setattr(
            stub["Cls"],
            "change_owner_domains",
            classmethod(lambda cls, ids, ud, kind: delegated(ids, kind)),
        )
        stub["mp"].setattr(
            stub["Cls"], "desktops_stop", classmethod(lambda cls, *a: None)
        )
        stub["mp"].setattr(
            stub["mod"].Quotas,
            "get_user_migration_check_quota_config",
            classmethod(lambda cls: False),
        )
        stub["router"](
            "domains"
        ).get_all.return_value.pluck.return_value.run.return_value = [
            {"id": "d1", "tag": None}
        ]

        stub["Cls"].change_owner_desktops(["d1"], _user_data(), "old-owner")

        # Old owner's bookings deleted, keyed on the PREVIOUS owner id.
        bookings = stub["router"]("bookings")
        bookings.get_all.assert_called_once_with("old-owner", index="user_id")
        bookings.get_all.return_value.delete.assert_called_once()
        # Bastion targets for these desktops removed.
        stub["router"]("targets").get_all.return_value.delete.assert_called_once()
        # Direct viewer url cleared.
        assert {"jumperurl": False} in _domain_updates(stub)
        # Finally delegates the actual owner change as a desktop.
        delegated.assert_called_once_with(["d1"], "desktop")


class TestChangeOwnerRoleGuards:
    """A ``user`` role may not own templates or media; the guard must fire
    before any ownership write is delegated."""

    def _spy_domains(self, stub):
        spy = MagicMock(name="change_owner_domains")
        stub["mp"].setattr(
            stub["Cls"],
            "change_owner_domains",
            classmethod(lambda cls, *a, **k: spy(*a)),
        )
        return spy

    def test_user_cannot_own_templates(self, stub):
        from isardvdi_common.helpers.error_base import ErrorBase

        spy = self._spy_domains(stub)
        ud = {"payload": {"role_id": "user"}, "new_user": {"user": "u"}}
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].change_owner_templates(["t1"], ud)
        assert exc.value.error["error"] == "bad_request"
        spy.assert_not_called()

    def test_user_cannot_own_media(self, stub):
        from isardvdi_common.helpers.error_base import ErrorBase

        spy = self._spy_domains(stub)
        ud = {"payload": {"role_id": "user"}, "new_user": {"user": "u"}}
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].change_owner_medias(["m1"], ud)
        assert exc.value.error["error"] == "bad_request"
        spy.assert_not_called()
