#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Response classification in ``NextcloudApi._request``.

This is where the provider client *decides*: which transport failure maps
to which typed ``Error``, which HTTP status is "not found" vs a generic
failure, and which method-specific codes mean "already exists". These
decisions are what callers act on, so they are pinned here; the plumbing
(building and sending the request) is left to ``requests`` and only its
outcome is stubbed.

``_request`` runs unmocked; only ``requests.request`` is replaced with a
fake that returns a chosen status/body or raises a chosen transport error.
"""

from types import SimpleNamespace

import pytest
import requests
from isardvdi_common.connections.user_storage_providers import nextcloud as mod
from isardvdi_common.helpers.error_factory import Error

NextcloudApi = mod.NextcloudApi


def _api():
    api = NextcloudApi("nc.example", verify_cert=False)
    api.set_basic_auth("admin", "pw")
    return api


def _resp(status_code, text="body"):
    return SimpleNamespace(status_code=status_code, text=text)


def _raises(exc):
    def _request(*a, **k):
        raise exc

    return _request


class TestRequestTransportErrors:
    def test_no_auth_protocol(self):
        api = NextcloudApi("nc.example", verify_cert=False)  # never authed
        with pytest.raises(Error) as exc:
            api._request("GET", "http://x")
        assert exc.value.error["error"] == "bad_request"

    def test_timeout_is_gateway_timeout(self, monkeypatch):
        monkeypatch.setattr(
            mod.requests, "request", _raises(requests.exceptions.Timeout())
        )
        with pytest.raises(Error) as exc:
            _api()._request("GET", "http://x")
        assert exc.value.error["error"] == "gateway_timeout"

    def test_ssl_error_is_bad_request(self, monkeypatch):
        monkeypatch.setattr(
            mod.requests, "request", _raises(requests.exceptions.SSLError())
        )
        with pytest.raises(Error) as exc:
            _api()._request("GET", "http://x")
        assert exc.value.error["error"] == "bad_request"

    def test_connection_error_is_gateway_timeout(self, monkeypatch):
        monkeypatch.setattr(
            mod.requests, "request", _raises(requests.exceptions.ConnectionError())
        )
        with pytest.raises(Error) as exc:
            _api()._request("GET", "http://x")
        assert exc.value.error["error"] == "gateway_timeout"

    def test_generic_request_exception_is_internal_server(self, monkeypatch):
        monkeypatch.setattr(
            mod.requests, "request", _raises(requests.exceptions.RequestException())
        )
        with pytest.raises(Error) as exc:
            _api()._request("GET", "http://x")
        assert exc.value.error["error"] == "internal_server"


class TestRequestStatusCodes:
    def test_401_is_bad_request(self, monkeypatch):
        monkeypatch.setattr(mod.requests, "request", lambda *a, **k: _resp(401))
        with pytest.raises(Error) as exc:
            _api()._request("GET", "http://x")
        assert exc.value.error["error"] == "bad_request"

    def test_404_is_not_found(self, monkeypatch):
        monkeypatch.setattr(mod.requests, "request", lambda *a, **k: _resp(404))
        with pytest.raises(Error) as exc:
            _api()._request("GET", "http://x")
        assert exc.value.error["error"] == "not_found"

    def test_499_is_not_found(self, monkeypatch):
        monkeypatch.setattr(mod.requests, "request", lambda *a, **k: _resp(499))
        with pytest.raises(Error) as exc:
            _api()._request("GET", "http://x")
        assert exc.value.error["error"] == "not_found"

    def test_generic_non_2xx_is_internal_server(self, monkeypatch):
        monkeypatch.setattr(mod.requests, "request", lambda *a, **k: _resp(500))
        with pytest.raises(Error) as exc:
            _api()._request("GET", "http://x")
        assert exc.value.error["error"] == "internal_server"

    def test_200_returns_body(self, monkeypatch):
        monkeypatch.setattr(
            mod.requests, "request", lambda *a, **k: _resp(200, "hello")
        )
        assert _api()._request("GET", "http://x") == "hello"


class TestMethodSpecificCodes:
    def test_mkcol_405_is_conflict(self, monkeypatch):
        monkeypatch.setattr(mod.requests, "request", lambda *a, **k: _resp(405))
        with pytest.raises(Error) as exc:
            _api()._request("MKCOL", "http://x")
        assert exc.value.error["error"] == "conflict"

    def test_mkcol_non_201_is_internal_server(self, monkeypatch):
        monkeypatch.setattr(mod.requests, "request", lambda *a, **k: _resp(500))
        with pytest.raises(Error) as exc:
            _api()._request("MKCOL", "http://x")
        assert exc.value.error["error"] == "internal_server"

    def test_mkcol_201_returns_body(self, monkeypatch):
        monkeypatch.setattr(
            mod.requests, "request", lambda *a, **k: _resp(201, "created")
        )
        assert _api()._request("MKCOL", "http://x") == "created"

    def test_propfind_405_is_conflict(self, monkeypatch):
        monkeypatch.setattr(mod.requests, "request", lambda *a, **k: _resp(405))
        with pytest.raises(Error) as exc:
            _api()._request("PROPFIND", "http://x")
        assert exc.value.error["error"] == "conflict"

    def test_propfind_207_returns_body(self, monkeypatch):
        monkeypatch.setattr(
            mod.requests, "request", lambda *a, **k: _resp(207, "multi")
        )
        assert _api()._request("PROPFIND", "http://x") == "multi"
