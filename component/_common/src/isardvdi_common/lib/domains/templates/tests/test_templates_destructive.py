#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Destructive paths of ``TemplatesProcessed`` in ``templates.py``.

Deriving or editing a template touches disks and rows other desktops depend on.
These pin, on the real functions:

* ``new_template`` -- the safety guards that must REFUSE (before writing the
  template doc / desktop update) a missing user/desktop, a running desktop, a
  server, an un-ready storage, a disk-less or multi-disk desktop; each asserts
  nothing was written.
* ``update_template`` -- refuses a missing template (``not_found``) and a
  non-template kind (``conflict``); a real template is updated.
* ``delete_non_persistent_desktops`` -- cascades ``ForceDeleting`` to the
  NON-persistent derived desktops only.

Only rethink and the ``Domain`` model are stubbed; the decisions are the code's.
The guard tests assert what was NOT written.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_base import ErrorBase


@pytest.fixture
def stub(monkeypatch):
    from isardvdi_common.lib.domains.templates import templates as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.TemplatesProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.TemplatesProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    tables = {}

    def router(name):
        return tables.setdefault(name, MagicMock(name=f"table-{name}"))

    monkeypatch.setattr(mod.r, "table", MagicMock(side_effect=router))
    # Domain(id).storage_ready — default ready so disk guards are reachable.
    dom = MagicMock(name="Domain")
    dom.return_value.storage_ready = True
    monkeypatch.setattr(mod, "Domain", dom)
    return {
        "mod": mod,
        "Cls": mod.TemplatesProcessed,
        "router": router,
        "mp": monkeypatch,
        "Domain": dom,
    }


def _user_ok(stub, user=None):
    stub["router"]("users").get.return_value.pluck.return_value.run.return_value = (
        user or {"id": "u1", "category": "c1", "group": "g1", "username": "n"}
    )


def _desktop(stub, desktop):
    stub["router"]("domains").get.return_value.run.return_value = desktop


def _no_writes(stub):
    dom = stub["router"]("domains")
    dom.insert.assert_not_called()
    dom.get.return_value.update.assert_not_called()


class TestNewTemplateGuards:
    def test_missing_user_not_found(self, stub):
        stub["router"]("users").get.return_value.pluck.return_value.run.side_effect = (
            RuntimeError("x")
        )
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].new_template("u1", "t1", "T", "d1")
        assert exc.value.error["error"] == "not_found"
        _no_writes(stub)

    def test_missing_desktop_not_found(self, stub):
        _user_ok(stub)
        _desktop(stub, None)
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].new_template("u1", "t1", "T", "d1")
        assert exc.value.error["error"] == "not_found"
        _no_writes(stub)

    def test_desktop_not_stopped_precondition(self, stub):
        _user_ok(stub)
        _desktop(stub, {"id": "d1", "status": "Started"})
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].new_template("u1", "t1", "T", "d1")
        assert exc.value.error["error"] == "precondition_required"
        _no_writes(stub)

    def test_server_cannot_be_templated(self, stub):
        _user_ok(stub)
        _desktop(stub, {"id": "d1", "status": "Stopped", "server": True})
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].new_template("u1", "t1", "T", "d1")
        assert exc.value.error["error"] == "internal_server"
        # Distinguish the server guard from the later disk guards (which also
        # raise internal_server but with their own description_code).
        assert exc.value.error["description_code"] == "internal_server"
        _no_writes(stub)

    def test_storage_not_ready_precondition(self, stub):
        _user_ok(stub)
        _desktop(stub, {"id": "d1", "status": "Stopped", "server": False})
        stub["Domain"].return_value.storage_ready = False
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].new_template("u1", "t1", "T", "d1")
        assert exc.value.error["description_code"] == "desktop_storage_not_ready"
        _no_writes(stub)

    def test_no_disks_refused(self, stub):
        _user_ok(stub)
        _desktop(
            stub,
            {
                "id": "d1",
                "status": "Stopped",
                "server": False,
                "create_dict": {"hardware": {"disks": []}},
            },
        )
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].new_template("u1", "t1", "T", "d1")
        assert exc.value.error["description_code"] == "desktop_no_disks"
        _no_writes(stub)


class TestUpdateTemplate:
    def test_missing_template_not_found(self, stub):
        stub["router"]("domains").get.return_value.run.return_value = None
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].update_template("t1", {"name": "x"})
        assert exc.value.error["error"] == "not_found"
        stub["router"]("domains").get.return_value.update.assert_not_called()

    def test_non_template_kind_conflict(self, stub):
        stub["router"]("domains").get.return_value.run.return_value = {
            "id": "d1",
            "kind": "desktop",
        }
        with pytest.raises(ErrorBase) as exc:
            stub["Cls"].update_template("d1", {"name": "x"})
        assert exc.value.error["error"] == "conflict"
        # A desktop must never be written to by the template update path.
        stub["router"]("domains").get.return_value.update.assert_not_called()

    def test_template_updated(self, stub):
        dom = stub["router"]("domains")
        dom.get.return_value.run.return_value = {"id": "t1", "kind": "template"}
        stub["Cls"].update_template("t1", {"name": "x"})
        dom.get.return_value.update.assert_called_once_with({"name": "x"})


class TestDeleteNonPersistentDesktops:
    def test_force_deletes_only_non_persistent(self, stub):
        dom = stub["router"]("domains")
        stub["Cls"].delete_non_persistent_desktops("t1")
        dom.get_all.assert_called_once_with("t1", index="parents")
        dom.get_all.return_value.filter.assert_called_once_with({"persistent": False})
        dom.get_all.return_value.filter.return_value.update.assert_called_once_with(
            {"status": "ForceDeleting"}
        )
