# SPDX-License-Identifier: AGPL-3.0-or-later

"""Disk-integrity classification in ``qemu_img_info_backing_chain``.

This turns a ``qemu-img info --backing-chain`` outcome into a storage
status, and that status drives whether a disk is treated as usable,
orphaned, or broken. A misclassification here marks a good disk broken or a
broken one ready, so the mapping is pinned:

* qemu-img timeout            -> broken_chain
* rc 0                        -> ready (+ backing-filename keys defaulted)
* rc != 0, stderr unrecognized -> broken_chain
* "Could not open '<self>'"   -> deleted
* "Could not open '<parent>'" where parent is this disk's backing -> orphan
* "Could not open '<parent>'" where it is NOT the backing -> broken_chain

DB-free: it runs with no RQ job (the _publishes_result decorator no-ops),
and only the qemu-img subprocess (``run``) and the sibling ``qemu_img_info``
lookup are stubbed.
"""


class _Proc:
    def __init__(self, returncode, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestBackingChainClassification:
    def test_timeout_is_broken_chain(self, monkeypatch):
        import task

        def _boom(*a, **k):
            raise task.TimeoutExpired(cmd="qemu-img", timeout=1)

        monkeypatch.setattr(task, "run", _boom)
        result = task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")
        assert result["status"] == "broken_chain"

    def test_rc0_is_ready_with_defaults(self, monkeypatch):
        import task

        monkeypatch.setattr(
            task, "run", lambda *a, **k: _Proc(0, stdout=b'[{"virtual-size": 10}]')
        )
        result = task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")
        assert result["status"] == "ready"
        assert "backing-filename" in result["qemu-img-info"]  # defaulted to None

    def test_unrecognized_stderr_is_broken_chain(self, monkeypatch):
        import task

        monkeypatch.setattr(
            task, "run", lambda *a, **k: _Proc(1, stderr=b"some other error")
        )
        result = task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")
        assert result["status"] == "broken_chain"

    def test_could_not_open_self_is_deleted(self, monkeypatch):
        import task

        stderr = b"qemu-img: Could not open '/isard/x.qcow2': No such file\n"
        monkeypatch.setattr(task, "run", lambda *a, **k: _Proc(1, stderr=stderr))
        result = task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")
        assert result["status"] == "deleted"

    def test_could_not_open_missing_backing_is_orphan(self, monkeypatch):
        import task

        stderr = b"qemu-img: Could not open '/isard/parent.qcow2': No such file\n"
        monkeypatch.setattr(task, "run", lambda *a, **k: _Proc(1, stderr=stderr))
        monkeypatch.setattr(
            task,
            "qemu_img_info",
            lambda sid, p: {
                "qemu-img-info": {"backing-filename": "/isard/parent.qcow2"}
            },
        )
        result = task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")
        assert result["status"] == "orphan"

    def test_could_not_open_unrelated_path_is_broken_chain(self, monkeypatch):
        import task

        stderr = b"qemu-img: Could not open '/isard/parent.qcow2': No such file\n"
        monkeypatch.setattr(task, "run", lambda *a, **k: _Proc(1, stderr=stderr))
        monkeypatch.setattr(
            task,
            "qemu_img_info",
            lambda sid, p: {
                "qemu-img-info": {"backing-filename": "/isard/other.qcow2"}
            },
        )
        result = task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")
        assert result["status"] == "broken_chain"
