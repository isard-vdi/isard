#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the engine HTTP client (helpers.engine_api).

Port of upstream MR !4535's ``api_engine_test.py``; the twin imports as a
normal package module here, so the upstream stub machinery is unnecessary.
The ``Error`` raised is the isardvdi_common error factory's typed error —
assertions pin the HTTP status it maps to.
"""

import os

import pytest

os.environ.setdefault("API_ISARDVDI_SECRET", "testsecret")

from isardvdi_common.helpers import engine_api as m
from isardvdi_common.helpers.error_base import ErrorBase


class _Resp:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


def test_returns_xml_dict_on_200(monkeypatch):
    monkeypatch.setattr(
        m.requests, "get", lambda *a, **k: _Resp(200, {"xml": "<domain/>", "hyp": "h1"})
    )
    assert m.get_desktop_live_xml("d1") == {"xml": "<domain/>", "hyp": "h1"}


def test_409_maps_to_conflict(monkeypatch):
    monkeypatch.setattr(m.requests, "get", lambda *a, **k: _Resp(409))
    with pytest.raises(ErrorBase) as e:
        m.get_desktop_live_xml("d1")
    assert e.value.status_code == 409


def test_404_maps_to_not_found(monkeypatch):
    monkeypatch.setattr(m.requests, "get", lambda *a, **k: _Resp(404))
    with pytest.raises(ErrorBase) as e:
        m.get_desktop_live_xml("d1")
    assert e.value.status_code == 404


def test_sends_admin_bearer_to_engine_route(monkeypatch):
    captured = {}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["auth"] = headers["Authorization"]
        return _Resp(200, {"xml": "x", "hyp": "h"})

    monkeypatch.setattr(m.requests, "get", fake_get)
    m.get_desktop_live_xml("abc-123")
    assert captured["url"].endswith("/engine/desktop/abc-123/live_xml")
    assert captured["auth"].startswith("Bearer ")
    # the minted token must carry an admin role the engine @is_admin accepts
    import jwt as _jwt

    decoded = _jwt.decode(
        captured["auth"].split(" ", 1)[1],
        os.environ["API_ISARDVDI_SECRET"],
        algorithms=["HS256"],
    )
    assert decoded["data"]["role_id"] == "admin"
