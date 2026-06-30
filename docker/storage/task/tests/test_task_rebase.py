# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the net-new ``task.rebase`` storage-worker task.

Runs inside the storage image (qemu-img present). Creates a real qcow2
parent+child chain, simulates the parent being moved to a new path, and
asserts the child's backing pointer is repointed to the parent's NEW path
(``qemu-img rebase -u``) and the chain stays intact.
"""

import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, "/opt/isardvdi/isardvdi_task")
sys.path.insert(0, "/utils")

import task  # noqa: E402  the storage worker task module
from storage_lib import qcow  # noqa: E402


def _create_qcow(path, size="10M", backing=None):
    cmd = ["qemu-img", "create", "-f", "qcow2"]
    if backing:
        cmd += ["-b", backing, "-F", "qcow2"]
    cmd += [str(path)]
    if not backing:
        cmd += [size]
    subprocess.run(cmd, check=True, capture_output=True)


@pytest.fixture
def chain(tmp_path):
    """A parent.qcow2 + child.qcow2 (child backs onto parent), plus a COPY of
    the parent at a new path simulating a completed `move`."""
    orig = tmp_path / "orig"
    new = tmp_path / "new"
    orig.mkdir()
    new.mkdir()
    parent = orig / "parent.qcow2"
    child = orig / "child.qcow2"
    _create_qcow(parent)
    _create_qcow(child, backing=parent)
    new_parent = new / "parent.qcow2"
    shutil.copy2(parent, new_parent)
    return {
        "parent": str(parent),
        "child": str(child),
        "new_parent": str(new_parent),
    }


def test_rebase_repoints_backing_to_new_parent(chain):
    # Precondition: child currently backs onto the original parent path.
    assert qcow.get_backing_file(chain["child"]) == chain["parent"]

    rc = task.rebase(chain["child"], chain["new_parent"])

    assert rc == 0
    # Backing now points at the parent's NEW path.
    assert qcow.get_backing_file(chain["child"]) == chain["new_parent"]
    # Chain is still intact / bootable.
    assert qcow.qemu_img_check(chain["child"]) is True


def test_rebase_is_idempotent(chain):
    task.rebase(chain["child"], chain["new_parent"])
    # Re-running (resume / at-least-once redelivery) must be a safe no-op.
    rc = task.rebase(chain["child"], chain["new_parent"])
    assert rc == 0
    assert qcow.get_backing_file(chain["child"]) == chain["new_parent"]


def test_rebase_missing_child_raises(tmp_path):
    with pytest.raises(Exception):
        task.rebase(
            str(tmp_path / "nope.qcow2"),
            str(tmp_path / "parent.qcow2"),
        )


def test_rebase_verify_passes_on_intact_chain(chain):
    rc = task.rebase(chain["child"], chain["new_parent"], verify=True)
    assert rc == 0
    assert qcow.get_backing_file(chain["child"]) == chain["new_parent"]


def test_rebase_verify_fails_when_backing_missing(chain):
    # Rebase onto a path that does not exist -> chain is broken -> verify fails.
    missing = chain["new_parent"] + ".gone"
    with pytest.raises(Exception):
        task.rebase(chain["child"], missing, verify=True)
