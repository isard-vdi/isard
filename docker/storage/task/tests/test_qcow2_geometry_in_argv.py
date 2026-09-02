# SPDX-License-Identifier: AGPL-3.0-or-later

"""The geometry travels in the payload and lands verbatim in the qemu-img argv.

The install-wide qcow2 policy is resolved by the enqueuer and passed to the
worker as four required kwargs. These tests pin that the worker splices them
into the ``-o`` option string of ``create`` / ``convert`` / ``disconnect``, in a
position that is valid regardless of whether a backing file is present, and that
the effective geometry is stamped onto the ``qemu-img info`` result.

Assertions are index-relative (``cmd.index("-o")``), never by absolute
position: the argv length changes with backing files and sizes.
"""

import pytest


class _Completed:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _capture_run(monkeypatch, attr="run", result=None):
    import task

    calls = []

    def fake(cmd, *a, **k):
        calls.append(cmd)
        return result if result is not None else _Completed()

    monkeypatch.setattr(task, attr, fake)
    return calls


def _opts(cmd):
    return cmd[cmd.index("-o") + 1]


# --- create ------------------------------------------------------------------


class TestCreateArgv:
    def test_create_with_parent_carries_full_geometry(self, monkeypatch):
        import task

        monkeypatch.setattr(task, "isdir", lambda p: True)
        monkeypatch.setattr(task, "isfile", lambda p: False)
        calls = _capture_run(monkeypatch)
        task.create(
            "/isard/g/d.qcow2",
            "qcow2",
            parent_path="/isard/g/base.qcow2",
            parent_type="qcow2",
            cluster_size="128k",
            extended_l2="on",
            lazy_refcounts="off",
            preallocation="metadata",
        )
        assert _opts(calls[0]) == (
            "cluster_size=128k,extended_l2=on,lazy_refcounts=off,preallocation=metadata"
        )

    def test_create_parentless_no_size_places_o_before_positional(
        self, monkeypatch, geo
    ):
        import task

        monkeypatch.setattr(task, "isdir", lambda p: True)
        monkeypatch.setattr(task, "isfile", lambda p: False)
        calls = _capture_run(monkeypatch)
        task.create("/isard/g/d.qcow2", "qcow2", **geo)
        cmd = calls[0]
        assert "-o" in cmd
        assert cmd.index("-o") < cmd.index("/isard/g/d.qcow2")

    def test_create_parentless_with_size_places_o_before_both_positionals(
        self, monkeypatch, geo
    ):
        import task

        monkeypatch.setattr(task, "isdir", lambda p: True)
        monkeypatch.setattr(task, "isfile", lambda p: False)
        calls = _capture_run(monkeypatch)
        task.create("/isard/g/d.qcow2", "qcow2", size="10G", **geo)
        cmd = calls[0]
        assert cmd.index("-o") < cmd.index("/isard/g/d.qcow2")
        assert cmd.index("-o") < cmd.index("10G")

    def test_preallocation_omitted_with_backing_when_extended_off(
        self, monkeypatch, geo
    ):
        import task

        monkeypatch.setattr(task, "isdir", lambda p: True)
        monkeypatch.setattr(task, "isfile", lambda p: False)
        calls = _capture_run(monkeypatch)
        task.create(
            "/isard/g/d.qcow2",
            "qcow2",
            parent_path="/isard/g/base.qcow2",
            parent_type="qcow2",
            **geo,
        )
        assert "preallocation" not in _opts(calls[0])

    def test_preallocation_present_with_backing_when_extended_on(self, monkeypatch):
        import task

        monkeypatch.setattr(task, "isdir", lambda p: True)
        monkeypatch.setattr(task, "isfile", lambda p: False)
        calls = _capture_run(monkeypatch)
        task.create(
            "/isard/g/d.qcow2",
            "qcow2",
            parent_path="/isard/g/base.qcow2",
            parent_type="qcow2",
            cluster_size="16k",
            extended_l2="on",
            lazy_refcounts="off",
            preallocation="metadata",
        )
        assert "preallocation=metadata" in _opts(calls[0])


# --- convert -----------------------------------------------------------------


class TestConvertArgv:
    def _stub(self, monkeypatch):
        import task

        monkeypatch.setattr(task, "_require_free_space", lambda *a, **k: None)
        calls = []
        monkeypatch.setattr(
            task, "run_with_progress", lambda cmd, *a, **k: calls.append(cmd) or 0
        )
        return calls

    def test_qcow2_destination_carries_geometry(self, monkeypatch, geo):
        import task

        calls = self._stub(monkeypatch)
        task.convert("/isard/s.qcow2", "/isard/d.qcow2", "qcow2", False, **geo)
        assert _opts(calls[0]) == (
            "cluster_size=4k,extended_l2=off,lazy_refcounts=off,preallocation=off"
        )

    def test_vmdk_destination_has_no_geometry(self, monkeypatch, geo):
        import task

        calls = self._stub(monkeypatch)
        task.convert("/isard/s.qcow2", "/isard/d.vmdk", "vmdk", False, **geo)
        assert "-o" not in calls[0]

    def test_compression_drops_preallocation(self, monkeypatch):
        """Q2: qemu-img convert -c rejects any preallocation != off. When the
        install policy asks for preallocation, the convert option string must
        omit it while compression is on, keeping the rest of the geometry."""
        import task

        calls = self._stub(monkeypatch)
        task.convert(
            "/isard/s.qcow2",
            "/isard/d.qcow2",
            "qcow2",
            True,
            cluster_size="16k",
            extended_l2="on",
            lazy_refcounts="on",
            preallocation="full",
        )
        opts = _opts(calls[0])
        assert "preallocation" not in opts
        assert "extended_l2=on" in opts
        assert "-c" in calls[0]


# --- disconnect --------------------------------------------------------------


class TestDisconnectArgv:
    def test_disconnect_carries_geometry_and_still_renames(self, monkeypatch, geo):
        import task

        monkeypatch.setattr(task, "_safe_unlink", lambda p: None)
        monkeypatch.setattr(task, "_require_free_space", lambda *a, **k: None)
        calls = _capture_run(monkeypatch)
        renamed = []
        monkeypatch.setattr(task, "rename", lambda a, b: renamed.append((a, b)))
        task.disconnect("/isard/g/d.qcow2", **geo)
        cmd = calls[0]
        assert "-o" in cmd
        assert cmd.index("-o") < cmd.index("/isard/g/d.qcow2")
        assert renamed == [("/isard/g/d.qcow2.wo_chain", "/isard/g/d.qcow2")]


# --- qemu_img_info_backing_chain stamping ------------------------------------

_INFO = b'[{"virtual-size": 1, "actual-size": 1, "filename": "/isard/g/d.qcow2", "format": "qcow2"}]'


class TestInfoStamp:
    def test_stamps_geometry_on_success(self, monkeypatch, geo):
        import task

        _capture_run(monkeypatch, result=_Completed(stdout=_INFO))
        data = task.qemu_img_info_backing_chain(
            "s1", "/isard/g/d.qcow2", qcow2_geometry=geo
        )
        assert data["qcow2_geometry"] == geo

    def test_does_not_stamp_geometry_on_failure(self, monkeypatch, geo):
        import task

        _capture_run(
            monkeypatch,
            result=_Completed(returncode=1, stderr=b"qemu-img: some error"),
        )
        data = task.qemu_img_info_backing_chain(
            "s1", "/isard/g/d.qcow2", qcow2_geometry=geo
        )
        assert "qcow2_geometry" not in data

    def test_omitting_geometry_stamps_nothing(self, monkeypatch):
        import task

        _capture_run(monkeypatch, result=_Completed(stdout=_INFO))
        data = task.qemu_img_info_backing_chain("s1", "/isard/g/d.qcow2")
        assert "qcow2_geometry" not in data
