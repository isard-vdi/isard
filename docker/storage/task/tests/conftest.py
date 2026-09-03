# SPDX-License-Identifier: AGPL-3.0-or-later

"""Make the storage-worker ``task`` module importable from tests.

The worker runs as ``rq worker`` with ``docker/storage/task`` on the path
(no src layout, no package ``__init__``), so add that directory to
``sys.path`` for the test process too.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def geo():
    """The four required geometry kwargs, default install policy."""
    return {
        "cluster_size": "4k",
        "extended_l2": "off",
        "lazy_refcounts": "off",
        "preallocation": "off",
    }
