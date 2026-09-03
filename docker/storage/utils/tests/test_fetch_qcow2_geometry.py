#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The storage CLI resolves the qcow2 geometry from apiv4, and fails hard.

This container no longer carries the QCOW2_* env vars, so the admin CLI must ask
the single central resolver (apiv4). It must RAISE on any failure: writing a disk
with the wrong geometry -- or silently falling back to defaults -- is worse than
refusing the operation.
"""

from contextlib import contextmanager

import httpx
import pytest
from storage_lib import api


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)


def _patch_client(monkeypatch, resp):
    class _Httpx:
        def get(self, url):
            _Httpx.url = url
            return resp

    class _Client:
        def get_httpx_client(self):
            return _Httpx()

    @contextmanager
    def _cm(*a, **k):
        yield _Client()

    monkeypatch.setattr(api, "_client", _cm)
    return _Httpx


def test_fetch_returns_the_policy_dict(monkeypatch):
    geo = {
        "cluster_size": "128k",
        "extended_l2": "on",
        "lazy_refcounts": "off",
        "preallocation": "off",
    }
    httpx_cls = _patch_client(monkeypatch, _Resp(200, geo))
    assert api.fetch_qcow2_geometry() == geo
    assert httpx_cls.url == "/api/v4/storage/qcow2-geometry"


def test_fetch_raises_on_http_error(monkeypatch):
    _patch_client(monkeypatch, _Resp(500))
    with pytest.raises(httpx.HTTPStatusError):
        api.fetch_qcow2_geometry()


def test_fetch_raises_when_the_client_cannot_connect(monkeypatch):
    @contextmanager
    def _cm(*a, **k):
        raise httpx.ConnectError("no route to apiv4")
        yield  # pragma: no cover

    monkeypatch.setattr(api, "_client", _cm)
    with pytest.raises(httpx.ConnectError):
        api.fetch_qcow2_geometry()
