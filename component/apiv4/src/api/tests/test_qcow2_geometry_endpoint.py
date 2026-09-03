#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The read-only endpoint that hands the qcow2 geometry policy to the storage CLI.

apiv4 is the single central resolver of the policy; the CLI (whose container no
longer holds the QCOW2_* vars) reads it here. These pin the resolved values, the
registered path/method the CLI hardcodes, and that a bad policy is not served.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from isardvdi_common.helpers import qcow2_geometry

from api.routes import storage as storage_routes

_EXPECTED_PATH = "/api/v4/storage/qcow2-geometry"


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
    assert resp.model_dump() == {
        "cluster_size": "128k",
        "extended_l2": "on",
        "lazy_refcounts": "off",
        "preallocation": "off",
    }


def test_endpoint_does_not_serve_an_invalid_policy(monkeypatch):
    # extended_l2=on with a 4k cluster is invalid; the endpoint must raise, not
    # hand the storage CLI a policy qemu-img would reject.
    monkeypatch.setenv("QCOW2_CLUSTER_SIZE", "4k")
    monkeypatch.setenv("QCOW2_EXTENDED_L2", "on")
    monkeypatch.setattr(
        storage_routes.Error, "create", AsyncMock(return_value=RuntimeError("boom"))
    )
    with pytest.raises(RuntimeError):
        asyncio.run(storage_routes.get_qcow2_geometry(request=MagicMock()))


def test_the_route_is_registered_at_the_path_the_cli_hardcodes():
    # #11: the CLI hardcodes _EXPECTED_PATH; assert the router really registers
    # it (right relative path, right prefix, right method), so a rename cannot
    # silently 404 the CLI. prefix + relative path must equal _EXPECTED_PATH.
    import api

    registered = {
        (route.path, method)
        for route in api.manager_router.routes
        if getattr(route, "methods", None)
        for method in route.methods
    }
    assert (_EXPECTED_PATH, "GET") in registered
