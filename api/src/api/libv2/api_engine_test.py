"""Unit tests for the engine HTTP client (api_engine.get_desktop_live_xml).

Loaded directly with isardvdi_common stubbed, so it runs without the api
package's heavy import side effects.
"""

import importlib.util
import os
import sys
import types

import pytest


class _Error(Exception):
    def __init__(self, code, msg, tb=""):
        super().__init__(f"{code}:{msg}")
        self.code = code
        self.msg = msg


if "isardvdi_common" not in sys.modules:
    sys.modules["isardvdi_common"] = types.ModuleType("isardvdi_common")
_exc = types.ModuleType("isardvdi_common.api_exceptions")
_exc.Error = _Error
sys.modules["isardvdi_common.api_exceptions"] = _exc
os.environ.setdefault("API_ISARDVDI_SECRET", "testsecret")

_spec = importlib.util.spec_from_file_location(
    "api_engine", os.path.join(os.path.dirname(__file__), "api_engine.py")
)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


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
    with pytest.raises(m.Error) as e:
        m.get_desktop_live_xml("d1")
    assert e.value.code == "conflict"


def test_404_maps_to_not_found(monkeypatch):
    monkeypatch.setattr(m.requests, "get", lambda *a, **k: _Resp(404))
    with pytest.raises(m.Error) as e:
        m.get_desktop_live_xml("d1")
    assert e.value.code == "not_found"


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
        captured["auth"].split(" ", 1)[1], "testsecret", algorithms=["HS256"]
    )
    assert decoded["data"]["role_id"] == "admin"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
