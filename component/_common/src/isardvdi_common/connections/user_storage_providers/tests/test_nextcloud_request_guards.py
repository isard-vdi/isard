#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guard paths of ``nextcloud.py`` ``Helpers._request`` (status/exception ->
Error mapping) and the pure ``parse_dav_propstat`` XML helper.

``_request`` is exercised for real; only ``requests.request`` (the network
collaborator) is faked so the real status-code / exception decision logic runs.
Errors assert the ``Error`` type + status_code.
"""

import pytest
import requests
from isardvdi_common.connections.user_storage_providers import nextcloud as mod
from isardvdi_common.helpers.error_base import ErrorBase


class _Resp:
    def __init__(self, status_code, text="ok"):
        self.status_code = status_code
        self.text = text


@pytest.fixture
def fake_request(monkeypatch):
    holder = {}

    def _install(resp=None, exc=None):
        def _req(*a, **k):
            if exc is not None:
                raise exc
            return resp

        monkeypatch.setattr(mod.requests, "request", _req)

    holder["install"] = _install
    return holder


class TestParseDavPropstat:
    def test_extracts_prop_leaf_values(self):
        xml = (
            "<d:multistatus xmlns:d='DAV:'><d:response><d:propstat><d:prop>"
            "<d:displayname>Alice</d:displayname>"
            "<d:quota-used-bytes>42</d:quota-used-bytes>"
            "</d:prop></d:propstat></d:response></d:multistatus>"
        )
        got = mod.Helpers.parse_dav_propstat(xml)
        assert got == {"displayname": "Alice", "quota-used-bytes": "42"}


class TestRequestStatusGuards:
    def _call(self, method="GET"):
        return mod.Helpers._request(method, "https://nc.example/x")

    def test_401_is_bad_request(self, fake_request):
        fake_request["install"](_Resp(401))
        with pytest.raises(ErrorBase) as exc:
            self._call()
        assert exc.value.status_code == 400

    def test_404_is_not_found(self, fake_request):
        fake_request["install"](_Resp(404))
        with pytest.raises(ErrorBase) as exc:
            self._call()
        assert exc.value.status_code == 404

    def test_499_is_not_found(self, fake_request):
        fake_request["install"](_Resp(499))
        with pytest.raises(ErrorBase) as exc:
            self._call()
        assert exc.value.status_code == 404

    def test_mkcol_405_is_conflict(self, fake_request):
        fake_request["install"](_Resp(405))
        with pytest.raises(ErrorBase) as exc:
            self._call("MKCOL")
        assert exc.value.status_code == 409

    def test_mkcol_non_201_is_internal_server(self, fake_request):
        fake_request["install"](_Resp(500))
        with pytest.raises(ErrorBase) as exc:
            self._call("MKCOL")
        assert exc.value.status_code == 500

    def test_mkcol_201_returns_text(self, fake_request):
        fake_request["install"](_Resp(201, text="created"))
        assert self._call("MKCOL") == "created"

    def test_propfind_405_is_conflict(self, fake_request):
        fake_request["install"](_Resp(405))
        with pytest.raises(ErrorBase) as exc:
            self._call("PROPFIND")
        assert exc.value.status_code == 409

    def test_propfind_non_207_is_internal_server(self, fake_request):
        fake_request["install"](_Resp(500))
        with pytest.raises(ErrorBase) as exc:
            self._call("PROPFIND")
        assert exc.value.status_code == 500

    def test_generic_non_2xx_is_internal_server(self, fake_request):
        fake_request["install"](_Resp(500))
        with pytest.raises(ErrorBase) as exc:
            self._call("GET")
        assert exc.value.status_code == 500

    def test_success_returns_text(self, fake_request):
        fake_request["install"](_Resp(200, text="body"))
        assert self._call("GET") == "body"


class TestRequestExceptionGuards:
    def _call(self):
        return mod.Helpers._request("GET", "https://nc.example/x")

    def test_timeout_is_gateway_timeout(self, fake_request):
        fake_request["install"](exc=requests.exceptions.Timeout())
        with pytest.raises(ErrorBase) as exc:
            self._call()
        assert exc.value.status_code == 504

    def test_ssl_error_is_bad_request(self, fake_request):
        fake_request["install"](exc=requests.exceptions.SSLError())
        with pytest.raises(ErrorBase) as exc:
            self._call()
        assert exc.value.status_code == 400

    def test_connection_error_is_gateway_timeout(self, fake_request):
        fake_request["install"](exc=requests.exceptions.ConnectionError())
        with pytest.raises(ErrorBase) as exc:
            self._call()
        assert exc.value.status_code == 504
