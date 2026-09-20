# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the net-new ``task.migration_verify_destination_absent`` task.

The pre-move mirror of ``migration_verify_destination``: the migration saga
enqueues the move only after this task proves the destination is CLEAR, so
``rsync -a`` can never adopt a byte-stale orphan (its quick-check skips a
same-size same-mtime file). Each case drives the task body over REAL files and
asserts raise-vs-0 directly.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "utils"))
sys.path.insert(0, "/opt/isardvdi/isardvdi_task")
sys.path.insert(0, "/utils")

from isardvdi_storage import task  # noqa: E402  the storage worker task module


# (a) destination absent -> returns 0 (the move may proceed)
def test_absent_destination_returns_zero(tmp_path):
    assert task.migration_verify_destination_absent(str(tmp_path / "nope.qcow2")) == 0


# (b) destination occupied -> raise, so the saga refuses the disk instead of
# letting rsync -a adopt the pre-existing file. The message names the path.
def test_occupied_destination_raises_with_the_path(tmp_path):
    dst = tmp_path / "dst.qcow2"
    dst.write_bytes(b"an orphan a prior run left behind")
    with pytest.raises(Exception) as exc:
        task.migration_verify_destination_absent(str(dst))
    assert f"destination_exists: {dst}" in str(exc.value)


# (c) a directory at the exact path is refused too (rsync onto it would misbehave)
def test_directory_at_the_path_is_also_refused(tmp_path):
    dst = tmp_path / "dst.qcow2"
    dst.mkdir()
    with pytest.raises(Exception):
        task.migration_verify_destination_absent(str(dst))
