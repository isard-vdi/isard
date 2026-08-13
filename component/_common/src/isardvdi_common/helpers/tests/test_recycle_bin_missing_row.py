#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Recycling an item whose row is already gone must be a typed ``not_found``.

``r.table(...).get(id).run()`` returns ``None`` for a missing row. Every
``add`` in this module handed that ``None`` straight to code that subscripts
it (``category["id"]``, ``user["id"]``, ``domain["kind"]``,
``storage["user_id"]``), so a delete of an id that no longer exists — a stale
webapp tab, a double click, a concurrent delete — raised
``TypeError: 'NoneType' object is not subscriptable`` and apiv4's generic
``except Exception`` turned it into a **500**. It is a **404**:
``RecycleBinTemplate.add`` and ``RecycleBinDeployment.add`` already got this
right, and these paths did not.

``Helpers.get`` had the same hole one level up (``result.get(...)`` on
``None`` → ``AttributeError``). apiv4's service layer happens to pre-check
with ``RethinkRecycleBin.exists``, but that is a TOCTOU window and this
package is framework-agnostic — the scheduler and change-handler call it with
no such guard.

Each ``add`` is exercised in isolation: the instance is built without
``__init__`` (which would hit the DB) and its collaborators are stubbed, so
the test observes only which exception the missing row produces.
"""

from unittest.mock import MagicMock

import pytest


class _ReqlNonExistence(Exception):
    """Stand-in for ``rethinkdb.errors.ReqlNonExistenceError`` — what the
    server answers to ``.pluck`` on a null row. The driver's own class cannot
    be raised outside its error path (its ``__repr__`` needs a
    ``query_printer`` the driver attaches), and the identity of the class is
    not what is under test: what matters is that *something* escapes unless
    the query carries ``.default(...)``."""


class _Ctx:
    """Stand-in for ``RethinkSharedConnection._rdb_context`` (a class, not a function, so
    attribute access does not bind ``self`` — same shape as the real one)."""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def mod(monkeypatch):
    from isardvdi_common.helpers import recycle_bin as rb_mod

    # No real pool connection is acquired. ``self._rdb_connection`` then
    # resolves to None and is only handed to the mocked ``.run()`` below, so
    # its value is irrelevant. Patched on the shared base every
    # ``RecycleBin*`` (and ``Helpers``) inherits, so both ``self.`` and
    # ``cls.`` call sites are covered.
    monkeypatch.setattr(rb_mod.RethinkSharedConnection, "_rdb_context", _Ctx)
    # ``Helpers.get`` is @cached; a stale entry from another test would mask
    # the lookup under test.
    rb_mod.Helpers.clear_get_cache()
    return rb_mod


@pytest.fixture
def tables(mod, monkeypatch):
    """Route ``r.table(name).get(id).run(conn)`` to a per-table row.

    Any table not named in ``rows`` yields ``None``, which is exactly the
    "row is gone" case under test.
    """

    def _install(rows):
        made = {}

        def _table(name):
            if name not in made:
                table = MagicMock(name=f"table-{name}")
                table.get.return_value.run.return_value = rows.get(name)
                made[name] = table
            return made[name]

        monkeypatch.setattr(mod.r, "table", _table)
        return made

    return _install


def _instance(cls, **attrs):
    """Build a RecycleBin* without running ``__init__`` (which hits the DB)."""
    obj = object.__new__(cls)
    obj.id = "rb-1"
    obj.agent_id = "admin"
    obj.item_name = None
    for key, value in attrs.items():
        setattr(obj, key, value)
    return obj


class TestMissingRowIsNotFound:
    """A 404 with the item's ``description_code``, never a 500."""

    def test_category_that_does_not_exist(self, mod, tables):
        tables({})  # categories.get(...).run() -> None
        rb = _instance(mod.RecycleBinCategory)

        with pytest.raises(mod.Error) as exc:
            rb.add("ghost-category")

        assert exc.value.status_code == 404
        assert exc.value.error["description_code"] == "category_not_found"

    def test_user_that_does_not_exist(self, mod, tables):
        tables({})
        rb = _instance(mod.RecycleBinUser)

        with pytest.raises(mod.Error) as exc:
            rb.add("ghost-user")

        assert exc.value.status_code == 404
        assert exc.value.error["description_code"] == "user_not_found"

    def test_group_that_does_not_exist(self, mod, tables):
        tables({})
        rb = _instance(mod.RecycleBinGroup)

        with pytest.raises(mod.Error) as exc:
            rb.add("ghost-group")

        assert exc.value.status_code == 404
        assert exc.value.error["description_code"] == "group_not_found"

    def test_desktop_that_does_not_exist(self, mod, tables, monkeypatch):
        monkeypatch.setattr(
            mod.CommonHelpers, "desktops_stop", staticmethod(lambda ids, timeout: None)
        )
        tables({})
        rb = _instance(mod.RecycleBinDesktop)

        with pytest.raises(mod.Error) as exc:
            rb.add("ghost-desktop")

        assert exc.value.status_code == 404
        assert exc.value.error["description_code"] == "domain_not_found"

    def test_storage_that_does_not_exist(self, mod, tables):
        tables({})
        rb = _instance(mod.RecycleBinStorage)

        with pytest.raises(mod.Error) as exc:
            rb.add("ghost-storage")

        assert exc.value.status_code == 404
        assert exc.value.error["description_code"] == "storage_not_found"

    def test_recycle_bin_entry_that_does_not_exist(self, mod, tables):
        tables({})

        with pytest.raises(mod.Error) as exc:
            mod.Helpers.get(recycle_bin_id="ghost-entry", all_data=True)

        assert exc.value.status_code == 404


class TestMissingRowDoesNotMutate:
    """The guard must fire BEFORE anything is written, so a 404 leaves no
    half-recycled entry behind. ``add_*`` is the first mutating step."""

    @pytest.mark.parametrize(
        "cls_name, add_name, item_id",
        [
            ("RecycleBinCategory", "add_category", "ghost-category"),
            ("RecycleBinUser", "add_user", "ghost-user"),
            ("RecycleBinGroup", "add_group", "ghost-group"),
            ("RecycleBinDesktop", "add_domain", "ghost-desktop"),
            ("RecycleBinStorage", "add_storage", "ghost-storage"),
        ],
    )
    def test_nothing_is_recycled(
        self, mod, tables, monkeypatch, cls_name, add_name, item_id
    ):
        monkeypatch.setattr(
            mod.CommonHelpers, "desktops_stop", staticmethod(lambda ids, timeout: None)
        )
        cls = getattr(mod, cls_name)
        calls = []
        monkeypatch.setattr(
            cls, add_name, lambda self, *a, **kw: calls.append(a), raising=True
        )
        tables({})
        rb = _instance(cls)

        with pytest.raises(mod.Error):
            rb.add(item_id)

        assert calls == []


class TestPresentRowStillWorks:
    """The guard must not fire on the normal path."""

    def test_existing_category_is_recycled(self, mod, tables, monkeypatch):
        tables({"categories": {"id": "cat-1", "name": "Batxillerat"}})
        recorded = {}
        monkeypatch.setattr(
            mod.RecycleBinCategory,
            "add_category",
            lambda self, category: recorded.update(category=category),
        )
        monkeypatch.setattr(
            mod.RecycleBinCategory,
            "_add_item_name",
            lambda self, name: recorded.update(name=name),
        )
        monkeypatch.setattr(mod.RecycleBin, "_add_owner", lambda self, owner: None)
        monkeypatch.setattr(
            mod.RecycleBinCategory, "_set_data", lambda self, id: "rb-1"
        )
        rb = _instance(mod.RecycleBinCategory)

        assert rb.add("cat-1") == "rb-1"
        assert recorded["category"]["id"] == "cat-1"
        assert recorded["name"] == "Batxillerat"

    def test_existing_user_is_recycled(self, mod, tables, monkeypatch):
        tables({"users": {"id": "user-1", "name": "Alumne"}})
        recorded = {}
        monkeypatch.setattr(
            mod.RecycleBinUser,
            "add_user",
            lambda self, user, delete_user=True: recorded.update(user=user),
        )
        monkeypatch.setattr(
            mod.RecycleBinUser,
            "_add_item_name",
            lambda self, name: recorded.update(name=name),
        )
        monkeypatch.setattr(mod.RecycleBin, "_add_owner", lambda self, owner: None)
        monkeypatch.setattr(mod.RecycleBinUser, "_set_data", lambda self, id: "rb-1")
        rb = _instance(mod.RecycleBinUser)

        assert rb.add("user-1") == "rb-1"
        assert recorded["user"]["id"] == "user-1"
        assert recorded["name"] == "Alumne"

    def test_existing_entry_is_returned(self, mod, tables):
        tables({"recycle_bin": {"id": "rb-1", "status": "recycled"}})

        assert mod.Helpers.get(recycle_bin_id="rb-1") == {
            "id": "rb-1",
            "status": "recycled",
        }


class TestCutoffTimeOfAGoneUser:
    """``get_user_recycle_bin_cutoff_time`` plucks ``category`` off
    ``users.get(user_id)``. When that row is gone RethinkDB raises
    ``ReqlNonExistenceError`` server-side — another 500 on a delete path,
    since the owner of an orphaned desktop may well be deleted (the module is
    full of ``[Deleted]`` fallbacks for exactly that). Here the answer is the
    system-wide window, not a 404: the caller is asking how long to keep the
    entry, not asking about that user.
    """

    def test_falls_back_to_the_system_window(self, mod, monkeypatch):
        monkeypatch.setattr(
            mod.Helpers,
            "get_system_recycle_bin_cutoff_time",
            classmethod(lambda cls: 72),
        )
        mod.Helpers.clear_get_user_recycle_bin_cutoff_time_cache()

        # ``.default(...)`` is the ONLY thing that turns the server-side
        # error into a value, so the mock raises unless the query asks for
        # it: with the guard the lookup yields None and we fall back; without
        # it the error escapes, which is the 500.
        users = MagicMock(name="table-users")
        plucked = users.get.return_value.pluck.return_value.__getitem__.return_value
        plucked.run.side_effect = _ReqlNonExistence(
            "Cannot perform pluck on a non-object non-sequence null."
        )
        plucked.default.return_value.run.return_value = None
        monkeypatch.setattr(
            mod.r,
            "table",
            lambda name: users if name == "users" else MagicMock(name=f"table-{name}"),
        )

        assert mod.Helpers.get_user_recycle_bin_cutoff_time("ghost-user") == 72
