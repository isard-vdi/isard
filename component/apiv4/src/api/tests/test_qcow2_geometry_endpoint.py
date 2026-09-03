#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The read-only endpoint that hands the qcow2 geometry policy to the storage CLI.

apiv4 is the single central resolver of the policy; the CLI (whose container no
longer holds the QCOW2_* vars) reads it here. This pins that the endpoint returns
exactly what ``qcow2_geometry.policy()`` resolved.
"""

import asyncio
import json

import pytest
from api.routes import storage as storage_routes
from isardvdi_common.helpers import qcow2_geometry


@pytest.fixture(autouse=True)
def _reset_cache():
    qcow2_geometry._cached = None
    yield
    qcow2_geometry._cached = None


def test_endpoint_returns_the_resolved_policy(monkeypatch):
    monkeypatch.setenv("QCOW2_CLUSTER_SIZE", "128k")
    monkeypatch.setenv("QCOW2_EXTENDED_L2", "on")
    monkeypatch.setenv("QCOW2_LAZY_REFCOUNTS", "off")
    monkeypatch.setenv("QCOW2_PREALLOCATION", "off")
    resp = asyncio.run(storage_routes.get_qcow2_geometry(request=None))
    assert resp.status_code == 200
    assert json.loads(resp.body) == {
        "cluster_size": "128k",
        "extended_l2": "on",
        "lazy_refcounts": "off",
        "preallocation": "off",
    }
