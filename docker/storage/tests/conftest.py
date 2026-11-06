#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The operator tools import ``storage_lib`` as a top-level package because they
run from their own directory. Put that directory on the path so the tests import
the same modules the tools do."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "utils"))


@pytest.fixture(autouse=True)
def _copies_do_not_clone(monkeypatch):
    """Whether ``tmp_path`` can clone depends on the filesystem under the runner,
    and a clone skips the free-space floor. Every test copies for real unless
    it asks for the clone path with :func:`allow_clone`."""
    if _disk_copy is not None:
        monkeypatch.setattr(_disk_copy, "clone", lambda src_fd, dst_fd: False)


@pytest.fixture
def allow_clone(monkeypatch):
    monkeypatch.setattr(_disk_copy, "clone", _REAL_CLONE)


try:
    from isardvdi_storage import disk_copy as _disk_copy
except ImportError:
    # a tree without the module still collects, so each test that needs it
    # fails on its own instead of the whole suite at conftest
    _disk_copy = None
_REAL_CLONE = getattr(_disk_copy, "clone", None)


@pytest.fixture
def geo():
    """The four required geometry kwargs, default install policy."""
    return {
        "cluster_size": "4k",
        "extended_l2": "off",
        "lazy_refcounts": "off",
        "preallocation": "off",
    }
