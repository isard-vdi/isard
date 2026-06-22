"""Unit tests for ``ApiAllowed.is_allowed`` with a missing/partial ``allowed``.

A template or media migrated before the alloweds mechanism may have no
``allowed`` key. Previously ``is_allowed`` did ``item["allowed"]["roles"]``
unconditionally, raising ``KeyError: 'allowed'`` -> HTTP 500 on read paths
(get-info / get-details). It must treat a missing axis as "not shared via
that axis", while owner/admin/manager fast-paths keep working.

Loaded with the api package's heavy imports stubbed, so it runs without
the Flask app side effects (same pattern as api_engine_test.py).
"""

import importlib.util
import os
import sys
import types


class _Error(Exception):
    pass


def _stub(name, **attrs):
    m = sys.modules.get(name) or types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


_stub("isardvdi_common")
_stub("isardvdi_common.api_exceptions", Error=_Error)
_stub("gevent")
_stub("cachetools", TTLCache=dict, cached=lambda *a, **k: (lambda f: f))
_stub("cachetools.keys", hashkey=lambda *a, **k: a)
_stub("rethinkdb", RethinkDB=lambda *a, **k: types.SimpleNamespace())

_api = _stub("api", app=types.SimpleNamespace(config={}))
_api.__path__ = []
_libv2 = _stub("api.libv2")
_libv2.__path__ = []


class _RDB:
    def __init__(self, *a, **k):
        pass

    def init_app(self, *a, **k):
        pass


_stub("api.libv2.flask_rethink", RDB=_RDB)

_spec = importlib.util.spec_from_file_location(
    "api.libv2.api_allowed",
    os.path.join(os.path.dirname(__file__), "api_allowed.py"),
)
m = importlib.util.module_from_spec(_spec)
sys.modules["api.libv2.api_allowed"] = m
_spec.loader.exec_module(m)


def _payload(role_id="advanced", user_id="u-1", category_id="cat-1", group_id="g-1"):
    return {
        "user_id": user_id,
        "role_id": role_id,
        "category_id": category_id,
        "group_id": group_id,
    }


def _alloweds():
    return m.ApiAllowed.__new__(m.ApiAllowed)


def test_missing_allowed_non_owner_denied_not_crashing():
    item = {"id": "t-1", "user": "someone-else", "category": "other-cat"}
    assert _alloweds().is_allowed(_payload(), item, "domains") is False


def test_missing_allowed_owner_still_allowed():
    item = {"id": "t-1", "user": "u-1", "category": "other-cat"}
    assert _alloweds().is_allowed(_payload(user_id="u-1"), item, "domains") is True


def test_missing_allowed_admin_still_allowed():
    item = {"id": "t-1", "user": "x", "category": "other-cat"}
    assert _alloweds().is_allowed(_payload(role_id="admin"), item, "domains") is True


def test_partial_allowed_roles_only_no_keyerror():
    # allowed present but missing categories/groups/users axes.
    item = {"id": "t-1", "user": "x", "category": "c", "allowed": {"roles": False}}
    assert _alloweds().is_allowed(_payload(), item, "domains") is False


def test_allowed_roles_empty_list_shares_to_all():
    item = {"id": "t-1", "user": "x", "category": "c", "allowed": {"roles": []}}
    assert _alloweds().is_allowed(_payload(), item, "domains") is True
