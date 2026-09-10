#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Forward path-builder tests for the {category} placeholder.

Storage / StoragePool are built with ``__new__`` so they never touch RethinkDB;
the DB-backed properties (``pool``, ``pool_usage``, ``category`` /
``_require_category``) and ``StoragePool.get_by_user_kind`` / ``User`` are
monkeypatched. The path assembly itself runs the real
``build_category_pool_dir`` helper and the real ``get_usage_path``.
"""

import isardvdi_common.models.storage as storage_mod
from isardvdi_common.models.storage import Storage, new_storage_directory_path
from isardvdi_common.models.storage_pool import StoragePool

MP = "/isard/storage_pools/pool-a"


def _pool(paths, id="pool-a", mountpoint=MP):
    pool = StoragePool.__new__(StoragePool)
    object.__setattr__(pool, "id", id)
    object.__setattr__(pool, "mountpoint", mountpoint)
    object.__setattr__(pool, "paths", paths)
    return pool


def _storage(**attrs):
    s = Storage.__new__(Storage)
    for key, value in attrs.items():
        object.__setattr__(s, key, value)
    return s


class _FakeUser:
    category = "cat-a"

    def __init__(self, _user_id):
        pass

    @staticmethod
    def exists(_user_id):
        return True


# --------------------------------------------------------------------------- #
# new_storage_directory_path  (module function, primary placement path)
# --------------------------------------------------------------------------- #
def test_new_storage_directory_path_token(monkeypatch):
    pool = _pool({"template": [{"path": "fast/{category}/templates", "weight": 100}]})
    monkeypatch.setattr(
        StoragePool, "get_by_user_kind", classmethod(lambda cls, u, k: pool)
    )
    monkeypatch.setattr(storage_mod, "User", _FakeUser)
    assert new_storage_directory_path("u1", "template") == f"{MP}/fast/cat-a/templates"


def test_new_storage_directory_path_legacy(monkeypatch):
    pool = _pool({"template": [{"path": "templates", "weight": 100}]})
    monkeypatch.setattr(
        StoragePool, "get_by_user_kind", classmethod(lambda cls, u, k: pool)
    )
    monkeypatch.setattr(storage_mod, "User", _FakeUser)
    assert new_storage_directory_path("u1", "template") == f"{MP}/cat-a/templates"


# --------------------------------------------------------------------------- #
# path_in_pool  (full file path)
# --------------------------------------------------------------------------- #
def test_path_in_pool_token(monkeypatch):
    pool = _pool({"template": [{"path": "fast/{category}/templates", "weight": 100}]})
    storage = _storage(id="disk-1", type="qcow2")
    monkeypatch.setattr(Storage, "pool_usage", property(lambda self: "template"))
    monkeypatch.setattr(Storage, "_require_category", lambda self: "cat-a")
    assert storage.path_in_pool(pool) == f"{MP}/fast/cat-a/templates/disk-1.qcow2"


# --------------------------------------------------------------------------- #
# get_storage_pool_path  (directory)
# --------------------------------------------------------------------------- #
def test_get_storage_pool_path_token(monkeypatch):
    pool = _pool({"desktop": [{"path": "slow/{category}/desktops", "weight": 100}]})
    storage = _storage(id="disk-2", type="qcow2")
    monkeypatch.setattr(Storage, "pool_usage", property(lambda self: "desktop"))
    monkeypatch.setattr(Storage, "_require_category", lambda self: "cat-a")
    assert storage.get_storage_pool_path(pool) == f"{MP}/slow/cat-a/desktops"


# --------------------------------------------------------------------------- #
# set_storage_pool  (writes directory_path)
# --------------------------------------------------------------------------- #
def test_set_storage_pool_token(monkeypatch):
    pool = _pool({"desktop": [{"path": "slow/{category}/desktops", "weight": 100}]})
    storage = _storage(id="disk-3", type="qcow2")
    monkeypatch.setattr(Storage, "pool", property(lambda self: None))  # != pool
    monkeypatch.setattr(Storage, "pool_usage", property(lambda self: "desktop"))
    monkeypatch.setattr(Storage, "_require_category", lambda self: "cat-a")
    monkeypatch.setattr(Storage, "__setattr__", object.__setattr__)  # avoid DB write
    storage.set_storage_pool(pool)
    assert storage.directory_path == f"{MP}/slow/cat-a/desktops"
