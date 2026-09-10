#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the cached category -> storage-pool resolver.

Drives category_pools.category_pool_ids by monkeypatching StoragePool.get_all
(the model method it calls) -- no real DB involved.
"""

import pytest
from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.lib import category_pools as cp
from isardvdi_common.models.storage_pool import StoragePool


def make_pool(**attrs):
    """Build a StoragePool without running its DB/socketio __init__."""
    pool = StoragePool.__new__(StoragePool)
    for key, value in attrs.items():
        object.__setattr__(pool, key, value)
    return pool


@pytest.fixture(autouse=True)
def _clear_cache():
    cp.invalidate_category_pool_cache()
    yield
    cp.invalidate_category_pool_cache()


def test_assigned_category_returns_its_pool(monkeypatch):
    pools = [
        make_pool(id=DEFAULT_STORAGE_POOL_ID, categories=[], enabled=True),
        make_pool(id="pool-a", categories=["cat-a"], enabled=True),
    ]
    monkeypatch.setattr(StoragePool, "get_all", classmethod(lambda cls: pools))

    assert cp.category_pool_ids("cat-a") == ["pool-a"]


def test_unassigned_category_returns_default(monkeypatch):
    pools = [
        make_pool(id=DEFAULT_STORAGE_POOL_ID, categories=[], enabled=True),
        make_pool(id="pool-a", categories=["cat-a"], enabled=True),
    ]
    monkeypatch.setattr(StoragePool, "get_all", classmethod(lambda cls: pools))

    assert cp.category_pool_ids("cat-x") == [DEFAULT_STORAGE_POOL_ID]


def test_cache_hit_skips_db(monkeypatch):
    pools = [
        make_pool(id=DEFAULT_STORAGE_POOL_ID, categories=[], enabled=True),
        make_pool(id="pool-a", categories=["cat-a"], enabled=True),
    ]
    calls = []

    def fake_get_all(cls):
        calls.append(1)
        return pools

    monkeypatch.setattr(StoragePool, "get_all", classmethod(fake_get_all))

    assert cp.category_pool_ids("cat-a") == ["pool-a"]
    assert cp.category_pool_ids("cat-a") == ["pool-a"]
    assert len(calls) == 1


def test_invalidate_forces_reresolve(monkeypatch):
    pools = [
        make_pool(id=DEFAULT_STORAGE_POOL_ID, categories=[], enabled=True),
        make_pool(id="pool-a", categories=["cat-a"], enabled=True),
    ]
    calls = []

    def fake_get_all(cls):
        calls.append(1)
        return pools

    monkeypatch.setattr(StoragePool, "get_all", classmethod(fake_get_all))

    cp.category_pool_ids("cat-a")
    cp.invalidate_category_pool_cache("cat-a")
    cp.category_pool_ids("cat-a")

    assert len(calls) == 2
