#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The admin-CLI qcow2 writers must apply the install geometry, resolved
centrally, not qemu-img's built-in defaults.

``create_incremental`` (storage recover --fix) and ``compress_file``
(storage --compress rewrite in place) both write a fresh qcow2. This container
no longer carries the QCOW2_* env vars, so the caller resolves the policy from
the API and passes the ``-o`` option string in; these tests pin that the string
reaches the qemu-img argv, and that the option is REQUIRED (a caller that did
not resolve the policy cannot write a defaulted disk by accident).
"""

import subprocess

import pytest
from storage_lib import qcow

_OPTS = "cluster_size=128k,extended_l2=on,lazy_refcounts=off"


def _capture(monkeypatch):
    calls = []

    class _R:
        stdout = ""
        stderr = ""

    def _run(cmd, **kwargs):
        calls.append(cmd)
        return _R()

    monkeypatch.setattr(qcow.subprocess, "run", _run)
    return calls


def test_create_incremental_splices_the_options_before_the_path(tmp_path, monkeypatch):
    calls = _capture(monkeypatch)
    dst = str(tmp_path / "d.qcow2")
    ok, err = qcow.create_incremental(dst, "/isard/g/base.qcow2", _OPTS)
    assert ok, err
    cmd = calls[0]
    assert cmd[cmd.index("-o") + 1] == _OPTS
    assert cmd.index("-o") < cmd.index(dst)


def test_create_incremental_requires_the_options():
    with pytest.raises(TypeError):
        qcow.create_incremental("/isard/g/d.qcow2", "/isard/g/base.qcow2")


def test_compress_file_splices_the_options(tmp_path, monkeypatch):
    calls = _capture(monkeypatch)
    src = tmp_path / "c.qcow2"
    src.write_bytes(b"\0" * 4096)
    monkeypatch.setattr(qcow, "is_file_in_use", lambda p: (False, None))
    monkeypatch.setattr(qcow, "has_backing_file", lambda p: (False, None))

    def _run_and_make_tmp(cmd, **kwargs):
        calls.append(cmd)
        # the real code shutil.move()s the tmp over the original; create it
        open(str(src) + ".compress-tmp", "wb").write(b"\0" * 2048)

        class _R:
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(qcow.subprocess, "run", _run_and_make_tmp)
    ok, saved, err = qcow.compress_file(str(src), _OPTS)
    assert ok, err
    cmd = calls[0]
    assert cmd[cmd.index("-o") + 1] == _OPTS
    assert "convert" in cmd and "-c" in cmd


def test_compress_file_requires_the_options(tmp_path, monkeypatch):
    monkeypatch.setattr(qcow, "is_file_in_use", lambda p: (False, None))
    monkeypatch.setattr(qcow, "has_backing_file", lambda p: (False, None))
    with pytest.raises(TypeError):
        qcow.compress_file("/isard/g/d.qcow2")
