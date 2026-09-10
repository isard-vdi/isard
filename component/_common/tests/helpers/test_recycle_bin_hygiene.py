#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Recycle-bin hygiene.

E1b — ``RecycleBinDomain.add`` wrapped BOTH the target read and the
recycle-bin write in ``try/except: pass`` and then deleted the target row
unconditionally. If the write failed, the ``targets`` row was deleted anyway
and the bastion config became irrecoverable. The read/save/delete must be
ordered so a write failure aborts before the delete.

E2 — ``RecycleBinStorage.add_storages`` (the bulk path used by every mass
delete) appended storages but never updated ``size``; only the single-item
``add_storage`` did. The bulk path must sum the batch's ``actual-size`` too.
"""

from unittest.mock import MagicMock

import pytest


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def rb_mod(monkeypatch):
    from isardvdi_common.helpers import recycle_bin as mod

    monkeypatch.setattr(
        mod.RecycleBinDomain, "_rdb_context", lambda self: _Ctx(), raising=False
    )
    monkeypatch.setattr(
        mod.RecycleBinStorage, "_rdb_context", lambda self: _Ctx(), raising=False
    )
    return mod


class TestAddDomainTargetOrdering:
    def _instance(self, mod):
        rb = object.__new__(mod.RecycleBinDesktop)
        rb.id = "rb-1"
        rb.agent_id = "u1"
        rb.item_name = "already-set"
        return rb

    def _wire(self, mod, monkeypatch, *, add_target_raises):
        monkeypatch.setattr(
            mod.CommonHelpers, "desktops_stop", staticmethod(lambda ids, n=5: None)
        )
        domain = {
            "id": "dom-1",
            "user": "u1",
            "kind": "desktop",
            "name": "D1",
            "create_dict": {"hardware": {"disks": []}},
        }
        table = MagicMock(name="table")
        table.get.return_value.run.return_value = domain
        table.get.return_value.delete.return_value.run.return_value = None
        monkeypatch.setattr(mod.r, "table", lambda name: table)

        monkeypatch.setattr(mod.RecycleBinDesktop, "add_domain", lambda self, d: None)
        # _add_owner is reached via super() and _set_data/_add_owner live on the
        # RecycleBin base — patch there so the real DB-touching methods don't run.
        monkeypatch.setattr(mod.RecycleBin, "_add_owner", lambda self, u: None)
        monkeypatch.setattr(mod.RecycleBin, "_set_data", lambda self, i: {"id": i})

        def _add_target(self, target):
            if add_target_raises:
                raise Exception("recycle_bin write failed")

        monkeypatch.setattr(mod.RecycleBinDesktop, "add_target", _add_target)

        monkeypatch.setattr(
            mod.Targets,
            "find_domain_target",
            classmethod(lambda cls, did: {"desktop_id": did, "ssh": {}}),
        )
        deleted = []
        monkeypatch.setattr(
            mod.Targets,
            "delete_domain_target",
            classmethod(lambda cls, did: deleted.append(did)),
        )
        return deleted

    def test_write_failure_does_not_delete_target(self, rb_mod, monkeypatch):
        deleted = self._wire(rb_mod, monkeypatch, add_target_raises=True)
        rb = self._instance(rb_mod)
        with pytest.raises(Exception):
            rb.add("dom-1")
        # The target row must survive: delete must NOT have run.
        assert deleted == []

    def test_happy_path_saves_then_deletes_target(self, rb_mod, monkeypatch):
        deleted = self._wire(rb_mod, monkeypatch, add_target_raises=False)
        rb = self._instance(rb_mod)
        rb.add("dom-1")
        assert deleted == ["dom-1"]


class TestAddStoragesSize:
    def test_bulk_add_storages_sums_actual_size(self, rb_mod, monkeypatch):
        mod = rb_mod
        log = {}

        class _Term:
            def add(self, x):
                return ("storages_add", x)

            def __add__(self, n):
                log["size_add"] = n
                return ("size_expr", n)

        class _Row:
            def __getitem__(self, key):
                return _Term()

        monkeypatch.setattr(mod.r, "row", _Row())

        captured = {}
        table = MagicMock(name="table")

        def _update(payload):
            captured["payload"] = payload
            return MagicMock(run=MagicMock(return_value=None))

        table.get.return_value.update = _update
        monkeypatch.setattr(mod.r, "table", lambda name: table)

        rb = object.__new__(mod.RecycleBinStorage)
        rb.id = "rb-1"

        storages = [
            {"id": "s1", "qemu-img-info": {"actual-size": 100}},
            {"id": "s2", "qemu-img-info": {"actual-size": 250}},
            {"id": "s3"},  # missing qemu-img-info → contributes 0
        ]
        rb.add_storages(storages)

        assert "size" in captured["payload"]
        assert log["size_add"] == 350
