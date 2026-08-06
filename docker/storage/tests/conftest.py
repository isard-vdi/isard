# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared fixtures for the storage worker suites."""

import pytest


@pytest.fixture
def geo():
    """The four required geometry kwargs, default install policy."""
    return {
        "cluster_size": "4k",
        "extended_l2": "off",
        "lazy_refcounts": "off",
        "preallocation": "off",
    }
