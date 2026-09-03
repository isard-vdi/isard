# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin the *shape* of chain definitions on ``Storage`` so the DB-side
backing-chain mirror (``storage.parent`` / domain disks[*].parent) keeps
matching the on-disk reality main establishes.

Background — these tests guard against three classes of regression
observed during the apiv4-integration port:

1. The ``find`` chain accidentally referenced an unimplemented
   ``storage_domains_force_update`` handler instead of main's
   ``storage_update_parent`` — silently no-oping the post-find
   reconciliation step.
2. ``enqueue_template_creation_chain_from_desktop`` replaced engine's
   SSH path but dropped the equivalent of its post-SSH
   ``Storage(id).find()`` reconciliation, so neither the new template
   nor the rebased desktop storage rows ever had their ``parent``
   field refreshed.
3. ``rsync`` / ``mv`` accumulated extra ``storage_domains_force_update``
   dependents that don't exist on main and rely on a handler that was
   never implemented.

The tests build a bare ``Storage`` via ``__new__`` (no DB hit), patch
``Storage.create_task`` at the *class* level to capture the chain dict
the method would have built, and walk that dict to assert exactly which
task names appear and which don't. They do NOT execute the chain —
chain execution is covered by the change-handler consumer tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from isardvdi_common.models.storage import Storage


@pytest.fixture(autouse=True)
def _repair_storage_new_slot():
    """Undo the process-wide damage ``patch(... "Storage.__new__")`` leaves behind.

    Assigning ``__new__`` on a class switches its C-level ``tp_new`` to
    ``slot_tp_new``. Deleting the attribute again does NOT switch it back:
    CPython's ``update_one_slot`` special-cases ``__new__`` and re-uses the
    type's *current* ``tp_new``. So after ``mock.patch`` restores, we are left
    with ``tp_new == slot_tp_new`` dispatching to the inherited
    ``object.__new__``, and every later ``Storage(some_id)`` in the same
    interpreter dies with::

        TypeError: object.__new__() takes exactly one argument (the type to instantiate)

    That made the whole ``_common`` suite order-dependent: any module collected
    after this one could no longer construct a ``Storage``. Reinstall an
    explicit pass-through ``__new__`` (semantically identical to the default)
    so construction keeps working.
    """
    yield
    if "__new__" not in Storage.__dict__:
        Storage.__new__ = staticmethod(lambda cls, *args, **kwargs: object.__new__(cls))


def _bare_storage(
    *,
    id: str = "src-storage-1",
    directory_path: str = "/isard/groups",
    type: str = "qcow2",
    user_id: str = "u1",
    parent: str | None = None,
) -> Storage:
    """Construct a Storage without hitting Redis or RethinkDB.

    ``RethinkCustomBase.__setattr__`` writes through to RethinkDB on
    every assignment, so use ``object.__setattr__`` to populate just the
    attrs the chain methods read (id / directory_path / type / user_id /
    parent). ``path``, ``pool`` and ``status`` are properties; tests
    patch them on the class as needed.
    """
    s = Storage.__new__(Storage)
    object.__setattr__(s, "id", id)
    object.__setattr__(s, "directory_path", directory_path)
    object.__setattr__(s, "type", type)
    object.__setattr__(s, "user_id", user_id)
    object.__setattr__(s, "parent", parent)
    # Chain methods end with ``return self.task``. With ``create_task``
    # mocked out, ``self.task`` is never set; __getattr__ would fall
    # through to RethinkDB. Pre-seed it.
    object.__setattr__(s, "task", None)
    return s


def _collect_task_names(dep_list):
    """Yield every ``task`` string reachable from a ``dependents`` list."""
    for dep in dep_list or []:
        if "task" in dep:
            yield dep["task"]
        for nested in _collect_task_names(dep.get("dependents")):
            yield nested


def _walk_with_parents(dep_list, parent_task=None):
    """Yield ``(parent_task, dep_dict)`` for every dep in the tree."""
    for dep in dep_list or []:
        yield (parent_task, dep)
        for nested in _walk_with_parents(dep.get("dependents"), dep.get("task")):
            yield nested


# ---------------------------------------------------------------------------
# find: mirrors main's `find -> storage_update_pool -> storage_update_parent`
# ---------------------------------------------------------------------------


def test_find_chain_ends_with_storage_update_parent():
    """Regression: the post-port ``find`` chain wired the unimplemented
    ``storage_domains_force_update`` handler. Main's chain ends with
    ``storage_update_parent`` so the discovered storage's parent field
    is reconciled from the on-disk backing-filename."""
    s = _bare_storage()
    with (
        patch.object(Storage, "create_task") as mock_create,
        patch("isardvdi_common.models.storage.StoragePool") as mock_pool,
    ):
        mock_pool.get_best_for_action.return_value = MagicMock(id="poolA")
        s.find(user_id="u1")
    dependents = mock_create.call_args.kwargs["dependents"]
    names = list(_collect_task_names(dependents))
    assert "storage_update_pool" in names
    assert "storage_update_parent" in names
    assert "storage_domains_force_update" not in names
    parents = {dep["task"]: parent for parent, dep in _walk_with_parents(dependents)}
    assert parents["storage_update_parent"] == "storage_update_pool"


# ---------------------------------------------------------------------------
# disconnect_chain: pin existing behaviour (already correct, matches main)
# ---------------------------------------------------------------------------


def test_disconnect_chain_still_runs_storage_update_parent():
    """Disconnect rewrites the on-disk file to have no backing chain;
    the trailing ``storage_update_parent`` is what flips
    ``storage.parent`` to None."""
    s = _bare_storage()
    with (
        patch.object(Storage, "create_task") as mock_create,
        patch.object(Storage, "set_maintenance"),
        patch("isardvdi_common.models.storage.StoragePool") as mock_pool,
    ):
        mock_pool.get_best_for_action.return_value = MagicMock(id="poolA")
        s.disconnect_chain(user_id="u1")
    dependents = mock_create.call_args.kwargs["dependents"]
    names = list(_collect_task_names(dependents))
    assert "qemu_img_info_backing_chain" in names
    assert "storage_update" in names
    assert "storage_update_parent" in names
    parents = {dep["task"]: parent for parent, dep in _walk_with_parents(dependents)}
    assert parents["storage_update_parent"] == "storage_update"


# ---------------------------------------------------------------------------
# rsync / mv: storage_domains_force_update must not be present
# ---------------------------------------------------------------------------


def test_rsync_chain_does_not_reference_storage_domains_force_update():
    """The unimplemented handler was accumulated during port; main's
    rsync chain stops at ``update_status``."""
    s = _bare_storage()
    with (
        patch.object(Storage, "create_task") as mock_create,
        patch.object(Storage, "set_maintenance"),
        patch.object(
            Storage,
            "pool",
            new_callable=PropertyMock,
            return_value=MagicMock(id="poolA"),
        ),
        patch.object(
            Storage,
            "status",
            new_callable=PropertyMock,
            return_value="ready",
            create=True,
        ),
        patch("isardvdi_common.models.storage.StoragePool") as mock_pool,
        patch(
            "isardvdi_common.models.storage.get_queue_from_storage_pools",
            return_value="poolA",
        ),
    ):
        mock_pool.get_best_for_action.return_value = MagicMock(id="poolA")
        s.rsync(user_id="u1", destination_path="/isard/templates/x.qcow2")
    dependents = mock_create.call_args.kwargs["dependents"]
    names = list(_collect_task_names(dependents))
    assert "storage_domains_force_update" not in names


def test_mv_chain_does_not_reference_storage_domains_force_update():
    """Same regression class as rsync."""
    s = _bare_storage()
    with (
        patch.object(Storage, "create_task") as mock_create,
        patch.object(Storage, "set_maintenance"),
        patch.object(
            Storage,
            "pool",
            new_callable=PropertyMock,
            return_value=MagicMock(id="poolA"),
        ),
        patch.object(
            Storage,
            "status",
            new_callable=PropertyMock,
            return_value="ready",
            create=True,
        ),
        patch.object(
            Storage, "domains", new_callable=PropertyMock, return_value=[], create=True
        ),
        patch("isardvdi_common.models.storage.StoragePool") as mock_pool,
        patch(
            "isardvdi_common.models.storage.get_queue_from_storage_pools",
            return_value="poolA",
        ),
    ):
        mock_pool.get_best_for_action.return_value = MagicMock(id="poolA")
        s.mv(user_id="u1", destination_path="/isard/templates")
    dependents = mock_create.call_args.kwargs["dependents"]
    names = list(_collect_task_names(dependents))
    assert "storage_domains_force_update" not in names


# ---------------------------------------------------------------------------
# enqueue_template_creation_chain_from_desktop: BOTH storage_update steps
# must have a storage_update_parent dependent that names the right storage
# ---------------------------------------------------------------------------


class _ParkedRow:
    """Stand-in for the NEW template storage row the chain parks.

    A plain object rather than a ``MagicMock`` on purpose: a MagicMock
    auto-creates any attribute on first read, so a field the chain never
    writes would look written and the assertions would pass vacuously.
    """

    def __init__(self, storage_id):
        self.id = storage_id
        self.pool = MagicMock(id="dst-pool")
        self.path = f"/isard/templates/{storage_id}.qcow2"
        self.type = "qcow2"
        self.set_maintenance = MagicMock()


def _run_template_chain(s, template_storage_id):
    """Run the template chain on ``s`` with the heavy bits mocked out and
    return the captured ``create_task`` mock plus the parked template row."""
    tpl_storage_obj = _ParkedRow(template_storage_id)

    # The chain calls ``Storage(template_storage_id)`` once. Route that
    # construction to our mock without affecting the bare ``s`` already
    # constructed by the test.
    real_new = Storage.__new__

    def fake_new(cls, *args, **kwargs):
        if args and args[0] == template_storage_id:
            return tpl_storage_obj
        return real_new(cls)

    with (
        patch.object(Storage, "create_task") as mock_create,
        # These tests are about the SHAPE of the definition and run with no fleet;
        # admission is pinned in its own suite.
        patch.object(Storage, "_preflight_lane"),
        patch.object(Storage, "exists", return_value=True),
        patch.object(
            Storage,
            "pool",
            new_callable=PropertyMock,
            return_value=MagicMock(id="src-pool"),
        ),
        patch("isardvdi_common.models.storage.Storage.__new__", side_effect=fake_new),
    ):
        s.enqueue_template_creation_chain_from_desktop(
            desktop_id="desktop-1",
            template_id="template-1",
            template_storage_id=template_storage_id,
        )
    return mock_create, tpl_storage_obj


def _template_chain_dependents(s, template_storage_id):
    """The captured ``dependents`` dict of the template chain."""
    mock_create, _ = _run_template_chain(s, template_storage_id)
    return mock_create.call_args.kwargs["dependents"]


# ---------------------------------------------------------------------------
# enqueue_template_creation_chain_from_desktop: a parked row is also an owner
# of the chain's tasks
# ---------------------------------------------------------------------------


def test_template_chain_lists_its_tasks_under_the_parked_row_too():
    """The chain's only task is created on the DESKTOP's row, but the disk it
    is producing is the TEMPLATE's. Listed only under the desktop, the template
    row's own task history would be empty for the whole copy — the one moment
    a user has something to watch."""
    s = _bare_storage(id="src-desktop-storage")
    mock_create, _ = _run_template_chain(s, "new-template-storage-99")
    assert mock_create.call_args.kwargs["index_owners"] == [
        s.id,
        "new-template-storage-99",
    ]


def test_the_row_this_chain_parks_is_the_row_it_lists_under():
    """Naming the parked row as an owner of the chain's tasks IS the park: it
    is what makes the index answer "what is this row busy with" for a row whose
    chain another row started, which is what the 428 gate and the self-heal
    both ask. There is no second marker to drift from."""
    s = _bare_storage(id="src-desktop-storage")
    mock_create, parked = _run_template_chain(s, "new-template-storage-99")
    owners = mock_create.call_args.kwargs["index_owners"]
    assert set(owners) - {s.id} == {parked.id}
    assert not hasattr(parked, "parked_by"), "the marker is retired"


def test_the_desktop_row_keeps_its_own_tasks_listed():
    """The origin does not lose its history to the row it parks."""
    s = _bare_storage(id="src-desktop-storage")
    mock_create, _ = _run_template_chain(s, "new-template-storage-99")
    assert mock_create.call_args.kwargs["index_owners"][0] == s.id
