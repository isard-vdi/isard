"""The workdir free-space preflight.

A dump expands to several times its compressed size. The workdir comes from
`TMPDIR`, which is a small tmpfs on many hosts, so without a check the run dies
with `OSError: [Errno 28]` minutes in, after copying and expanding the archive.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from anonymize_db.cli import _WORKDIR_SIZE_FACTOR, _check_workdir_space


class _Usage:
    def __init__(self, free: int):
        self.free = free


def _patch_free(monkeypatch, free: int) -> None:
    monkeypatch.setattr(shutil, "disk_usage", lambda _p: _Usage(free))


def test_refuses_a_workdir_too_small_for_the_dump(monkeypatch, tmp_path: Path):
    dump = tmp_path / "dump.tar.gz"
    dump.write_bytes(b"x" * 1000)
    _patch_free(monkeypatch, 1000 * _WORKDIR_SIZE_FACTOR - 1)

    with pytest.raises(SystemExit) as exc:
        _check_workdir_space(tmp_path, str(dump))
    assert "TMPDIR" in str(exc.value)


def test_accepts_a_workdir_with_room(monkeypatch, tmp_path: Path):
    dump = tmp_path / "dump.tar.gz"
    dump.write_bytes(b"x" * 1000)
    _patch_free(monkeypatch, 1000 * _WORKDIR_SIZE_FACTOR)

    _check_workdir_space(tmp_path, str(dump))


def test_only_logs_when_the_input_size_is_unknown(monkeypatch, tmp_path: Path):
    """A dump pulled over ssh has no local size to measure yet."""
    _patch_free(monkeypatch, 1)
    _check_workdir_space(tmp_path, None)


def test_tolerates_an_unreadable_input_path(monkeypatch, tmp_path: Path):
    _patch_free(monkeypatch, 1)
    _check_workdir_space(tmp_path, str(tmp_path / "missing.tar.gz"))
