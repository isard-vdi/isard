#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards that stand in front of the destructive recycle-bin paths.

``delete_storage`` permanently deletes (or move-deletes) the disks of an entry;
``owns_recycle_bin_id`` is the authz gate every recycle-bin API call passes
through. A missing guard here is data loss or a cross-tenant leak, so each of
these tests must go red when its guard is inverted.
"""

from unittest.mock import MagicMock

import pytest


def _bare_entry(**attrs):
    from isardvdi_common.helpers.recycle_bin import RecycleBin

    rb = RecycleBin.__new__(RecycleBin)
    for k, v in attrs.items():
        setattr(rb, k, v)
    return rb


class TestDeleteStorageRefusesTerminalStatus:
    """``delete_storage`` must refuse an entry already ``restored`` or
    ``deleted``: re-running the permanent delete on a restored entry would
    delete disks the user got back, and on a deleted one it would re-queue
    deletes for disks that are already gone."""

    @pytest.mark.parametrize("status", ["restored", "deleted"])
    def test_refuses_to_delete_a_terminal_entry(self, status):
        from isardvdi_common.helpers.recycle_bin import Error

        rb = _bare_entry(status=status, storages=[{"id": "s1"}])
        with pytest.raises(Error) as exc:
            rb.delete_storage("agent-user")
        # 428 precondition_required, and it never reached the delete machinery.
        assert exc.value.status_code == 428
        assert exc.value.error["error"] == "precondition_required"
        assert status in exc.value.error["description"]

    def test_a_recycled_entry_is_NOT_stopped_here(self):
        """The guard must let a genuinely recycled entry through — otherwise
        nothing could ever be deleted. It proceeds past the guard and fails
        later (no DB), which is a DIFFERENT error than the 428 above."""
        from isardvdi_common.helpers.recycle_bin import Error

        rb = _bare_entry(status="recycled", users=[], storages=[])
        rb._update_agent = MagicMock()
        # storages == [] -> takes the "no storages" branch, which calls
        # Helpers.update_status; stub it so we prove the guard did NOT fire.
        import isardvdi_common.helpers.recycle_bin as mod

        called = {}
        mod.Helpers.update_status = staticmethod(
            lambda rid, oid, st: called.setdefault("status", st)
        )
        rb.id = "rb-1"
        rb.owner_id = "o1"
        rb.categories = rb.groups = rb.users = []
        rb.delete_storage("agent-user")
        assert called["status"] == "deleted"  # reached the body, guard passed


class TestOwnsRecycleBinIdAuthz:
    """``Helpers.owns_recycle_bin_id`` — the ownership gate. Admin passes,
    the owner passes, a manager of the same category passes, everyone else is
    forbidden. Inverting any branch is a cross-tenant read/delete."""

    @pytest.fixture
    def caches(self, monkeypatch):
        import isardvdi_common.helpers.recycle_bin as mod

        store = {}
        monkeypatch.setattr(
            mod.Caches,
            "get_document",
            staticmethod(lambda table, doc_id, fields: store.get(tuple(fields))),
        )
        return mod, store

    def test_admin_passes_without_a_lookup(self, caches):
        mod, store = caches
        # No document seeded: an admin must NOT need one.
        assert mod.Helpers.owns_recycle_bin_id({"role_id": "admin"}, "rb-1") == "rb-1"

    def test_owner_passes(self, caches):
        mod, store = caches
        store[("owner_id",)] = "u1"
        payload = {"role_id": "user", "user_id": "u1"}
        assert mod.Helpers.owns_recycle_bin_id(payload, "rb-1") == "rb-1"

    def test_manager_of_the_same_category_passes(self, caches):
        mod, store = caches
        store[("owner_id",)] = "someone-else"
        store[("owner_category_id",)] = "cat-1"
        payload = {"role_id": "manager", "user_id": "mgr", "category_id": "cat-1"}
        assert mod.Helpers.owns_recycle_bin_id(payload, "rb-1") == "rb-1"

    def test_a_stranger_is_forbidden(self, caches):
        mod, store = caches
        store[("owner_id",)] = "someone-else"
        payload = {"role_id": "user", "user_id": "intruder"}
        with pytest.raises(mod.Error) as exc:
            mod.Helpers.owns_recycle_bin_id(payload, "rb-1")
        assert exc.value.status_code == 403

    def test_manager_of_a_different_category_is_forbidden(self, caches):
        mod, store = caches
        store[("owner_id",)] = "someone-else"
        store[("owner_category_id",)] = "cat-OTHER"
        payload = {"role_id": "manager", "user_id": "mgr", "category_id": "cat-mine"}
        with pytest.raises(mod.Error) as exc:
            mod.Helpers.owns_recycle_bin_id(payload, "rb-1")
        assert exc.value.status_code == 403

    def test_missing_entry_is_not_found(self, caches):
        mod, store = caches  # store empty -> get_document returns None
        payload = {"role_id": "user", "user_id": "u1"}
        with pytest.raises(mod.Error) as exc:
            mod.Helpers.owns_recycle_bin_id(payload, "rb-gone")
        assert exc.value.status_code == 404
