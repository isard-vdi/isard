# SPDX-License-Identifier: AGPL-3.0-or-later

"""``move_delete`` must not claim success for a path it cannot reach.

A missing file whose directory IS reachable is treated as "already gone" (a
storage whose file was never materialised must not strand its recycle-bin
entry). But a path whose directory does NOT exist cannot be observed at all, so
returning 0 there would report a deletion that never happened.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import task  # noqa: E402


def test_move_delete_raises_when_the_directory_is_unreachable(tmp_path):
    missing = str(tmp_path / "no-such-dir" / "d.qcow2")
    with pytest.raises(ValueError):
        task.move_delete(missing)


def test_move_delete_treats_a_reachable_missing_file_as_already_gone(tmp_path):
    """The other arm stays intact: a reachable directory with no file is a
    no-op success, not a raise."""
    gone = str(tmp_path / "d.qcow2")  # tmp_path exists, the file does not
    assert task.move_delete(gone) == 0
