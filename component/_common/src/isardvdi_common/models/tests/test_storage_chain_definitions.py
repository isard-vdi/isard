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


def _template_chain_dependents(s, template_storage_id):
    """Run the template chain on ``s`` with the heavy bits mocked out
    and return the captured ``dependents`` dict."""
    tpl_storage_obj = MagicMock()
    tpl_storage_obj.pool = MagicMock(id="dst-pool")
    tpl_storage_obj.path = f"/isard/templates/{template_storage_id}.qcow2"
    tpl_storage_obj.type = "qcow2"
    tpl_storage_obj.set_maintenance = MagicMock()

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
    return mock_create.call_args.kwargs["dependents"]


def test_template_chain_has_storage_update_parent_for_template_storage():
    """The template-side storage_update must be followed by a
    storage_update_parent targeting the new template storage's id, so
    the new template row's ``parent`` field reflects on-disk reality."""
    s = _bare_storage(id="src-desktop-storage")
    template_storage_id = "new-template-storage-99"

    dependents = _template_chain_dependents(s, template_storage_id)

    parents_calls = [
        dep["job_kwargs"]["kwargs"]["storage_id"]
        for _parent, dep in _walk_with_parents(dependents)
        if dep.get("task") == "storage_update_parent"
    ]
    assert template_storage_id in parents_calls, (
        f"template chain missing storage_update_parent(storage_id={template_storage_id!r}); "
        f"found parent updates for: {parents_calls}"
    )


def test_template_chain_has_storage_update_parent_for_desktop_storage():
    """The desktop-side storage_update must also be followed by a
    storage_update_parent — this is what flips the desktop storage's
    parent from None (or its previous backing) to the new template."""
    s = _bare_storage(id="src-desktop-storage")
    template_storage_id = "new-template-storage-99"

    dependents = _template_chain_dependents(s, template_storage_id)

    parents_calls = [
        dep["job_kwargs"]["kwargs"]["storage_id"]
        for _parent, dep in _walk_with_parents(dependents)
        if dep.get("task") == "storage_update_parent"
    ]
    assert s.id in parents_calls, (
        f"template chain missing storage_update_parent(storage_id={s.id!r}); "
        f"found parent updates for: {parents_calls}"
    )


# ---------------------------------------------------------------------------
# Typed Error vs plain Exception in chain enqueue methods. The apiv4 error
# mapper only recognises ``isardvdi_common.helpers.error_factory.Error``;
# plain ``Exception`` falls through to a generic 500. These tests pin the
# typed-error contract so the frontend sees actionable 404/428 instead.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Terminal-status cleanup: root-terminal chains (convert / delete /
# virt_win_reg) whose trailing update_status keys off the ROOT op's status
# must clean up on a FAILED terminal, not only on CANCELED. A running-cancel
# surfaces to the consumer as job_status="failed" (the worker decorator maps
# any raise to "failed"), and now that the consumer honours job_status the
# root is marked FAILED — so the cleanup branch must exist under "failed".
# ---------------------------------------------------------------------------


def _find_update_status_statuses(dependents):
    """Return the ``statuses`` dict of the first ``update_status`` dependent."""
    for _parent, dep in _walk_with_parents(dependents):
        if dep.get("task") == "update_status":
            return dep["job_kwargs"]["kwargs"]["statuses"]
    return None


def test_convert_update_status_deletes_dest_on_failed_and_canceled():
    """A failed OR cancelled convert must mark the half-written destination
    ``deleted`` — never leave it at its target status (which reads as a good
    disk)."""
    s = _bare_storage()
    new_storage = MagicMock()
    new_storage.id = "new-99"
    new_storage.path = "/isard/groups/new-99.qcow2"
    new_storage.type = "qcow2"
    with (
        patch.object(Storage, "create_task") as mc,
        patch.object(Storage, "set_maintenance"),
        patch.object(
            Storage,
            "path",
            new_callable=PropertyMock,
            return_value="/isard/groups/src.qcow2",
            create=True,
        ),
        patch("isardvdi_common.models.storage.StoragePool") as mp,
    ):
        mp.get_best_for_action.return_value = MagicMock(id="poolA")
        s.convert(
            user_id="u1",
            new_storage=new_storage,
            new_storage_type="qcow2",
            new_storage_status="ready",
            compress=False,
        )
    statuses = _find_update_status_statuses(mc.call_args.kwargs["dependents"])
    assert statuses is not None
    assert statuses["canceled"]["deleted"]["storage"] == ["new-99"]
    assert statuses["failed"]["deleted"]["storage"] == ["new-99"]


def test_task_delete_update_status_restores_on_failed_like_canceled():
    """A failed OR cancelled delete must restore the source to ``ready`` (and
    domains to ``Stopped``) — NOT fall through to the ``finished`` branch that
    marks it ``deleted`` and drops the DB row."""
    s = _bare_storage()
    with (
        patch.object(Storage, "create_task") as mc,
        patch.object(Storage, "set_maintenance"),
        patch.object(
            Storage, "domains", new_callable=PropertyMock, return_value=[], create=True
        ),
        patch.object(
            Storage,
            "domains_derivatives",
            new_callable=PropertyMock,
            return_value=[],
            create=True,
        ),
        patch.object(
            Storage,
            "derivatives",
            new_callable=PropertyMock,
            return_value=[],
            create=True,
        ),
        patch.object(
            Storage,
            "path",
            new_callable=PropertyMock,
            return_value="/isard/groups/src.qcow2",
            create=True,
        ),
        patch("isardvdi_common.models.storage.StoragePool") as mp,
    ):
        mp.get_best_for_action.return_value = MagicMock(id="poolA")
        s.task_delete(user_id="u1")
    statuses = _find_update_status_statuses(mc.call_args.kwargs["dependents"])
    assert statuses is not None
    assert "failed" in statuses
    assert statuses["failed"] == statuses["canceled"]


def test_virt_win_reg_update_status_has_failed_block():
    """A failed OR cancelled virt_win_reg must take the same restore branch as
    canceled (both leave the storage ``ready``), not the missing-branch no-op
    that today only worked because the root was force-FINISHED."""
    s = _bare_storage()
    with (
        patch.object(Storage, "create_task") as mc,
        patch.object(Storage, "set_maintenance"),
        patch.object(
            Storage, "domains", new_callable=PropertyMock, return_value=[], create=True
        ),
        patch.object(
            Storage,
            "path",
            new_callable=PropertyMock,
            return_value="/isard/groups/src.qcow2",
            create=True,
        ),
        patch("isardvdi_common.models.storage.StoragePool") as mp,
    ):
        mp.get_best_for_action.return_value = MagicMock(id="poolA")
        s.virt_win_reg(user_id="u1", registry_patch="[HKEY_LOCAL_MACHINE]")
    statuses = _find_update_status_statuses(mc.call_args.kwargs["dependents"])
    assert statuses is not None
    assert "failed" in statuses
    assert statuses["failed"] == statuses["canceled"]


def _import_error_class():
    """Import the same Error class the chain raises, so isinstance checks
    work whether or not apiv4 happened to import first in the test process."""
    from isardvdi_common.helpers.error_factory import Error

    return Error


def test_enqueue_disk_creation_raises_typed_error_when_parent_not_ready():
    """``enqueue_disk_creation_chain_for_domain`` checked
    ``storage_parent.status != "ready"`` with a plain ``Exception`` raise,
    causing a 500. Must be a typed ``Error`` so the route layer maps to
    428 with a readable description."""
    Error = _import_error_class()
    s = _bare_storage(id="child-storage", parent="parent-storage-uuid")

    parent_storage_obj = MagicMock()
    parent_storage_obj.status = "maintenance"
    parent_storage_obj.type = "qcow2"
    parent_storage_obj.path = "/isard/templates/parent-storage-uuid.qcow2"

    real_new = Storage.__new__

    def fake_new(cls, *args, **kwargs):
        if args and args[0] == "parent-storage-uuid":
            return parent_storage_obj
        return real_new(cls)

    with (
        patch.object(Storage, "create_task") as _mock_create,
        patch.object(Storage, "exists", return_value=True),
        patch("isardvdi_common.models.storage.Storage.__new__", side_effect=fake_new),
    ):
        import pytest

        with pytest.raises(Error) as exc_info:
            s.enqueue_disk_creation_chain_for_domain(domain_id="d1")
        # Reject the regression shape explicitly.
        assert not isinstance(exc_info.value, Exception) or isinstance(
            exc_info.value, Error
        )
        assert "not ready" in str(exc_info.value).lower()


def test_enqueue_disk_creation_raises_typed_error_when_parent_missing():
    """The ``Storage.exists(self.parent)`` False branch must also raise
    typed ``Error("not_found", ...)`` so the route layer maps to 404."""
    Error = _import_error_class()
    s = _bare_storage(id="child-storage", parent="missing-parent-uuid")

    with (
        patch.object(Storage, "create_task") as _mock_create,
        patch.object(Storage, "exists", return_value=False),
    ):
        import pytest

        with pytest.raises(Error) as exc_info:
            s.enqueue_disk_creation_chain_for_domain(domain_id="d1")
        assert "not found" in str(exc_info.value).lower()


def test_enqueue_template_creation_raises_typed_error_when_template_storage_missing():
    """``enqueue_template_creation_chain_from_desktop`` not-found branch
    must raise typed Error so the route layer maps to 404 instead of 500."""
    Error = _import_error_class()
    s = _bare_storage(id="src-desktop-storage")

    with (
        patch.object(Storage, "create_task") as _mock_create,
        patch.object(Storage, "exists", return_value=False),
    ):
        import pytest

        with pytest.raises(Error) as exc_info:
            s.enqueue_template_creation_chain_from_desktop(
                desktop_id="d1",
                template_id="t1",
                template_storage_id="missing-template-storage",
            )
        assert "not found" in str(exc_info.value).lower()
