# SPDX-License-Identifier: AGPL-3.0-or-later

"""_db_update backing-field regression test (saga-3).

After a non-root disk is moved + rebased its backing points at the parent's NEW
path, but _db_update rewrote only qemu-img-info.filename — leaving
backing-filename / full-backing-filename pointing at the deleted old parent. The
disk still boots (the on-disk header was rebased) but DB-based chain audits flag
a disk/DB mismatch. _db_update now also writes the backing fields.
"""

import isardvdi_common.lib.storage.migration_run as mr


def _runner():
    return object.__new__(mr.MigrationRunner)


def _capture_storage(monkeypatch):
    captured = {}

    class _S:
        @classmethod
        def update_document(cls, sid, fields, validate=True):
            captured["sid"] = sid
            captured["fields"] = fields

    monkeypatch.setattr(mr, "Storage", _S)
    # ledger write is a no-op for this test
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "update_document",
        classmethod(lambda cls, iid, fields, validate=True: None),
    )
    return captured


def test_db_update_sets_backing_fields_for_nonroot(monkeypatch):
    captured = _capture_storage(monkeypatch)
    item = {
        "id": "i1",
        "storage_id": "s1",
        "dst_path": "/dst/c.qcow2",
        "dst_dir": "/dst",
        "parent_dst_path": "/dst/p.qcow2",
    }
    _runner()._db_update(item)
    qii = captured["fields"]["qemu-img-info"]
    assert captured["fields"]["directory_path"] == "/dst"
    assert qii["filename"] == "/dst/c.qcow2"
    assert qii["backing-filename"] == "/dst/p.qcow2"
    assert qii["full-backing-filename"] == "/dst/p.qcow2"


def test_db_update_root_leaves_backing_untouched(monkeypatch):
    captured = _capture_storage(monkeypatch)
    item = {
        "id": "i0",
        "storage_id": "s0",
        "dst_path": "/dst/r.qcow2",
        "dst_dir": "/dst",
        "parent_dst_path": None,  # root: backing is outside the tree, unchanged
    }
    _runner()._db_update(item)
    qii = captured["fields"]["qemu-img-info"]
    assert qii["filename"] == "/dst/r.qcow2"
    assert "backing-filename" not in qii
    assert "full-backing-filename" not in qii
