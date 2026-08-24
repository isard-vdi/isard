# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fast-path decisions in ``find``.

When the file exists at its expected path (default, no full walk), find
returns O(1). What it does with that hit is the decision pinned here:

* a real ``.qcow2`` is inspected (qemu backing chain) and its status is
  reported;
* a non-qcow2 file gets no storage_data and the default ``deleted`` status;
* a hidden ``.qcow2`` (dotfile) is treated like a non-qcow2 — no inspection.

DB-free: only the filesystem probes and ``qemu_img_info_backing_chain`` are
stubbed; the O(1) branch never reaches the DB-touching heartbeat of the full
walk.
"""


def _fast(monkeypatch, task, chain=None):
    monkeypatch.setattr(task, "isfile", lambda p: True)
    monkeypatch.setattr(task, "getmtime", lambda p: 123.0)
    monkeypatch.setattr(task, "qemu_img_info_backing_chain", lambda sid, p: chain)


class TestFindFastPath:
    def test_qcow2_reports_chain_status(self, monkeypatch):
        import task

        _fast(monkeypatch, task, chain={"status": "ready"})
        result = task.find("st-1", "/isard/g/st-1.qcow2")
        assert result["status"] == "ready"
        assert result["matching_files"][0]["storage_data"] == {"status": "ready"}

    def test_non_qcow2_has_no_storage_data(self, monkeypatch):
        import task

        # chain would raise if called; it must not be for a non-qcow2 file
        def _boom(sid, p):
            raise AssertionError("qemu inspection must not run for non-qcow2")

        monkeypatch.setattr(task, "isfile", lambda p: True)
        monkeypatch.setattr(task, "getmtime", lambda p: 1.0)
        monkeypatch.setattr(task, "qemu_img_info_backing_chain", _boom)
        result = task.find("st-1", "/isard/g/st-1.iso")
        assert result["status"] == "deleted"
        assert result["matching_files"][0]["storage_data"] is None

    def test_hidden_qcow2_is_not_inspected(self, monkeypatch):
        import task

        def _boom(sid, p):
            raise AssertionError("qemu inspection must not run for a dotfile")

        monkeypatch.setattr(task, "isfile", lambda p: True)
        monkeypatch.setattr(task, "getmtime", lambda p: 1.0)
        monkeypatch.setattr(task, "qemu_img_info_backing_chain", _boom)
        result = task.find("st-1", "/isard/g/.st-1.qcow2")
        assert result["matching_files"][0]["storage_data"] is None
