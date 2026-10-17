# SPDX-License-Identifier: AGPL-3.0-or-later

"""The disk measurement must be told which format it is looking at.

``qemu-img info`` is invoked with an explicit ``-f`` rather than letting
qemu-img probe the header — probing is what lets a guest-controlled disk claim
to be another format. The cost is that the caller owns the format, and the
default of ``qcow2`` is right for every disk IsardVDI creates itself.

``convert`` is the exception: producing a vmdk/raw is its entire purpose.
Measured as qcow2, a good vmdk exits non-zero with

    qemu-img: Could not open '/isard/groups/<id>.vmdk': Image is not in qcow2 format

and the error branch below matches that path against the path it was asked
about. They are the same path, and it used to conclude the file was gone and
report ``deleted`` — the destination row marked deleted while the real file
stayed on disk, invisible and never reclaimed, after a convert that reported
success. It now reports an open error, but the measurement still fails.
"""

import json

import pytest


class _Completed:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


_INFO = json.dumps(
    [
        {
            "virtual-size": 1073741824,
            "actual-size": 23035904,
            "filename": "/isard/groups/d.vmdk",
            "format": "vmdk",
        }
    ]
).encode()


def _capture_run(monkeypatch, result):
    from isardvdi_storage import task

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return result

    monkeypatch.setattr(task, "run", fake_run)
    return calls


def test_defaults_to_qcow2_so_every_existing_caller_is_unchanged(monkeypatch):
    from isardvdi_storage import task

    calls = _capture_run(monkeypatch, _Completed(stdout=_INFO))
    task.qemu_img_info_backing_chain("s1", "/isard/groups/s1.qcow2")

    assert calls[0][calls[0].index("-f") + 1] == "qcow2"


@pytest.mark.parametrize("fmt", ["vmdk", "raw", "qcow2"])
def test_the_requested_format_is_the_one_passed_to_qemu_img(monkeypatch, fmt):
    from isardvdi_storage import task

    calls = _capture_run(monkeypatch, _Completed(stdout=_INFO))
    task.qemu_img_info_backing_chain("s1", f"/isard/groups/s1.{fmt}", fmt)

    assert calls[0][calls[0].index("-f") + 1] == fmt


def test_a_vmdk_measured_as_vmdk_is_ready_and_carries_its_size(monkeypatch):
    from isardvdi_storage import task

    _capture_run(monkeypatch, _Completed(stdout=_INFO))
    data = task.qemu_img_info_backing_chain("s1", "/isard/groups/d.vmdk", "vmdk")

    assert data["status"] == "ready"
    assert data["qemu-img-info"]["actual-size"] == 23035904
    assert data["qemu-img-info"]["virtual-size"] == 1073741824


def test_a_good_vmdk_measured_as_qcow2_is_an_open_error_not_deleted(
    monkeypatch, tmp_path
):
    """Measured without ``-f vmdk``: an open error, never ``ready`` or ``deleted``."""
    from isardvdi_storage import task

    disk = tmp_path / "d.vmdk"
    disk.write_bytes(b"KDMV")
    path = str(disk)
    stderr = f"qemu-img: Could not open '{path}': Image is not in qcow2 format\n"
    _capture_run(monkeypatch, _Completed(returncode=1, stderr=stderr.encode()))

    data = task.qemu_img_info_backing_chain("s1", path)
    assert "status" not in data
    assert "qemu-img-info" not in data
    assert "not in qcow2 format" in data["open_error"]


def test_a_missing_file_still_reads_as_deleted(monkeypatch, tmp_path):
    """The deleted branch must keep working for the case it was written for."""
    from isardvdi_storage import task

    path = str(tmp_path / "gone.vmdk")
    stderr = f"qemu-img: Could not open '{path}': No such file or directory\n"
    _capture_run(monkeypatch, _Completed(returncode=1, stderr=stderr.encode()))

    assert task.qemu_img_info_backing_chain("s1", path, "vmdk")["status"] == "deleted"


def test_the_orphan_probe_reuses_the_same_format(monkeypatch):
    """A broken backing link re-measures the file itself; same format applies."""
    from isardvdi_storage import task

    path = "/isard/groups/d.vmdk"
    stderr = b"qemu-img: Could not open '/isard/templates/parent.qcow2': No such file or directory\n"
    _capture_run(monkeypatch, _Completed(returncode=1, stderr=stderr))

    seen = {}

    def fake_info(storage_id, storage_path, storage_type="qcow2"):
        seen["type"] = storage_type
        return {"qemu-img-info": {"backing-filename": "/isard/templates/parent.qcow2"}}

    monkeypatch.setattr(task, "qemu_img_info", fake_info)
    data = task.qemu_img_info_backing_chain("s1", path, "vmdk")

    assert seen["type"] == "vmdk"
    assert data["status"] == "orphan"
