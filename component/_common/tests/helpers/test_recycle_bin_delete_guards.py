#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards that stand in front of the destructive recycle-bin paths.

``delete_storage`` permanently deletes (or move-deletes) the disks of an entry;
``owns_recycle_bin_id`` is the authz gate every recycle-bin API call passes
through. A missing guard here is data loss or a cross-tenant leak, so each of
these tests must go red when its guard is inverted.

The status guard has a second face, covered at the bottom of this file: it
refuses an entry the cascade already marked, so any per-entry work the cascade
skipped can never be done later. Personal-unit removal is that work.
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


def _chain(result):
    """A rethink query chain (``.get_all(...).filter(...).pluck(...)[...]``)
    that yields ``result`` however it is walked."""
    m = MagicMock(name="query")
    for step in ("get_all", "filter", "pluck", "distinct", "merge"):
        getattr(m, step).return_value = m
    m.__getitem__.return_value = m
    m.run.return_value = result
    return m


@pytest.fixture
def cascade(monkeypatch):
    """The real ``delete_storage`` driven over a real cascade.

    ``dependent_storages`` is deliberately NOT replaced. The ``recycle_bin``
    table answers with a dependent entry instead, so the code that finds the
    dependants, merges them into the delete list and de-duplicates it all runs
    for real. A fixture that hands the cascade an empty list cannot see what
    the cascade does to the entries it adopts.

    The test steers two things: ``tables["recycle_bin"]`` (who the cascade
    adopts) and ``lane["ok"]`` (whether the delete lanes have a consumer).
    """
    import isardvdi_common.helpers.recycle_bin as mod
    from isardvdi_common.lib import governor_counters, queue_coverage

    Real = mod.RecycleBin  # keep the real class; the factory below shadows the name
    events = []

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    lane = {"ok": True}

    def fake_decision(conn, queue, now=None):
        if lane["ok"]:
            return "ok", {"reason": None, "has_consumer": True, "pool": "pool-1"}
        return "reject", {
            "reason": "no_consumer",
            "has_consumer": False,
            "pool": "pool-1",
        }

    monkeypatch.setattr(queue_coverage, "lane_shed_decision", fake_decision)
    monkeypatch.setattr(
        governor_counters,
        "record_shed",
        lambda conn, reason, pool=None, tier=None, now=None: None,
    )

    # --- rethink layer, answering per table: the recycle_bin reads are the
    #     cascade's own dependant lookup, the storage read is the per-entry
    #     status probe. One live disk -> the branch that queues the deletes.
    tables = {
        "recycle_bin": [{"id": "rb-dep", "storages": [{"id": "s-dep"}]}],
        "storage": ["ready"],
    }
    monkeypatch.setattr(mod.RecycleBin, "_rdb_context", lambda self: _Ctx())
    monkeypatch.setattr(
        type(mod.RecycleBin),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
        raising=False,
    )
    monkeypatch.setattr(mod.r, "table", lambda name: _chain(tables[name]))
    monkeypatch.setattr(mod.r, "args", lambda x: x)

    # --- two entries that each own a user, so a removal driven from ``self``
    #     and one driven from the cascade's list are told apart.
    rb = Real.__new__(Real)
    rb.status = "recycled"
    rb.id = "rb-self"
    rb.owner_id = "owner-1"
    rb.storages = [{"id": "s-self"}]
    rb.templates = [{"id": "t1"}]  # what the dependants hang from
    rb.users = [{"id": "u-self", "category": "cat-1"}]
    rb.groups = rb.categories = []
    rb.agent_type = rb.agent_id = rb.agent_name = None
    rb.agent_category_id = rb.agent_category_name = rb.agent_role = None
    rb._update_agent = lambda user_id: None
    rb._add_task = lambda payload: events.append(("task", "rb-self"))

    dep = Real.__new__(Real)
    dep.status = "recycled"
    dep.id = "rb-dep"
    dep.owner_id = "owner-2"
    dep.storages = [{"id": "s-dep"}]
    dep.templates = []
    dep.users = [{"id": "u-dep", "category": "cat-1"}]
    dep.groups = dep.categories = []
    dep._add_task = lambda payload: events.append(("task", "rb-dep"))

    loaded = {"rb-self": rb, "rb-dep": dep}
    monkeypatch.setattr(mod, "RecycleBin", lambda _id: loaded[_id])

    storages = {}
    for sid in ("s-self", "s-dep"):
        storage = MagicMock(name="storage-" + sid)
        storage.id = sid
        storage.status = "ready"
        storage.path = f"/pool/{sid}.qcow2"
        storage.directory_path = "/pool"
        storage.category = "cat-1"
        storages[sid] = storage

    class FakeStorage:
        exists = staticmethod(lambda sid: True)

        def __new__(cls, sid):
            return storages[sid]

    monkeypatch.setattr(mod, "Storage", FakeStorage)

    pool = MagicMock(name="pool")
    pool.id = "pool-1"
    monkeypatch.setattr(
        mod.StoragePool, "get_best_for_action", staticmethod(lambda *a, **k: pool)
    )
    monkeypatch.setattr(
        mod.queue_tiers, "retier_queue", lambda base, task, cat=None: f"q:{task}"
    )
    monkeypatch.setattr(
        mod.Helpers, "get_delete_action", staticmethod(lambda: "delete")
    )

    def fake_task(*a, **k):
        task = MagicMock(name="task")
        task.id = "task-" + str(k.get("storage_id"))
        task.status = "queued"
        task.enqueue = lambda **_: None
        return task

    fake_task._redis = MagicMock(name="redis")
    monkeypatch.setattr(mod, "Task", fake_task)

    monkeypatch.setattr(
        mod.Helpers,
        "update_status",
        staticmethod(lambda rb_id, owner_id, status: events.append((status, rb_id))),
    )
    monkeypatch.setattr(mod.Helpers, "add_log", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(
        mod.NotificationsDataProcessed,
        "delete_users_notifications_data",
        staticmethod(lambda users_ids: None),
    )
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)

    # --- the destructive call under test. ``remove_user`` is an OCS DELETE:
    #     the cloud account AND everything in it, with no undo.
    monkeypatch.setattr(
        mod.UserStorage,
        "isard_user_storage_remove_users",
        staticmethod(
            lambda users: events.append(("remove_users", [u["id"] for u in users]))
        ),
    )
    monkeypatch.setattr(
        mod.UserStorage,
        "isard_user_storage_remove_groups",
        staticmethod(lambda groups: events.append(("remove_groups", groups))),
    )
    monkeypatch.setattr(
        mod.UserStorage,
        "isard_user_storage_remove_categories",
        staticmethod(
            lambda categories, groups: events.append(("remove_categories", categories))
        ),
    )

    return mod, events, rb, tables, lane


def _removed_users(events):
    return [payload for name, payload in events if name == "remove_users"]


class TestCascadeCarriesTheUserStorageRemoval:
    """The cascade permanently deletes the entries it adopts, so it owes them
    everything a permanent delete owes an entry — including taking the owner's
    personal unit down.

    It is the only chance those entries get: the cascade leaves them
    ``deleting`` and then ``deleted``, and ``delete_storage`` refuses a
    ``deleted`` entry (the guard at the top of this file), so a removal the
    cascade skipped is not late, it is lost. What survives is a disabled
    Nextcloud account holding the user's files for good, after an operator
    asked for a permanent delete.
    """

    def test_the_adopted_dependant_loses_its_personal_unit_too(self, cascade):
        mod, events, rb, tables, lane = cascade

        rb.delete_storage("agent-user")

        # Both entries were deleted, so both owners lose their personal unit.
        assert _removed_users(events) == [["u-self"], ["u-dep"]]

    def test_the_entry_that_owns_no_dependant_is_not_forgotten(self, cascade):
        """The fix moves the removal off ``self`` and onto the delete list; the
        plain single-entry delete has to keep working."""
        mod, events, rb, tables, lane = cascade
        tables["recycle_bin"] = []  # the cascade finds nobody, for real

        rb.delete_storage("agent-user")

        assert _removed_users(events) == [["u-self"]]

    def test_no_account_goes_before_every_disk_is_committed(self, cascade):
        """Order, not just presence: the cascade marks and queues every entry
        it adopted, and only then destroys the accounts.

        A removal fired as each entry is visited would take the first owner's
        account and then, if a later entry raised, leave the caller with a
        half-done delete it is invited to retry — except that account is
        already gone.
        """
        mod, events, rb, tables, lane = cascade

        rb.delete_storage("agent-user")

        assert events == [
            ("deleting", "rb-self"),
            ("task", "rb-self"),
            ("deleting", "rb-dep"),
            ("task", "rb-dep"),
            ("remove_users", ["u-self"]),
            ("remove_users", ["u-dep"]),
        ]

    def test_a_deferred_entry_keeps_its_personal_unit(self, cascade):
        """No consumer on the lane: nothing was enqueued and both entries went
        back to ``recycled``, the state a normal delete re-drives. Destroying
        the cloud accounts anyway would delete the user's files for an
        operation that was declined — and the retry would find nothing left to
        take down."""
        mod, events, rb, tables, lane = cascade
        lane["ok"] = False

        rb.delete_storage("agent-user")

        assert [name for name, _ in events] == ["recycled", "recycled"]
