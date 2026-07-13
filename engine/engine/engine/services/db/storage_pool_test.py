"""Unit tests for engine storage_pool path resolution (F8) and pool cache.

The conftest stubs ``engine.services.db`` in ``sys.modules`` (the preamble below
drops the stubs this module needs to load the real code), which also means
pytest's default prepend import mode cannot collect a test under that stubbed
package. Run with importlib mode, e.g.:

    docker exec isard-engine python3 -m pytest --import-mode=importlib \
        /isard/engine/services/db/storage_pool_test.py -q
"""

import sys as _sys

# This module exercises the REAL engine.services.db.storage_pool. The engine
# test conftest stubs it (and its constant dependency) in sys.modules so heavy
# production imports don't connect at collection time; drop those stubs here so
# the imports below load the real code under test.
for _m in (
    "engine.services.db",
    "engine.services.db.storage_pool",
    "isardvdi_common.helpers.default_storage_pool",
):
    _sys.modules.pop(_m, None)

from isardvdi_common.helpers.default_storage_pool import (  # noqa: E402
    DEFAULT_STORAGE_POOL_ID,
)

from engine.services.db import storage_pool as mod  # noqa: E402


def _pools():
    return [
        {"id": DEFAULT_STORAGE_POOL_ID, "mountpoint": "/isard", "qos_disk_id": None},
        {
            "id": "pool-a",
            "mountpoint": "/isard/storage_pools/pool-a",
            "qos_disk_id": "slow",
        },
    ]


def test_get_path_storage_pool_resolves_category(monkeypatch):
    monkeypatch.setattr(mod, "get_storage_pools", _pools)
    sp = mod.get_path_storage_pool("/isard/storage_pools/pool-a/cat/desktops/x.qcow2")
    assert sp["id"] == "pool-a"
    assert sp["qos_disk_id"] == "slow"


def test_get_path_storage_pool_resolves_default(monkeypatch):
    monkeypatch.setattr(mod, "get_storage_pools", _pools)
    sp = mod.get_path_storage_pool("/isard/groups/x.qcow2")
    assert sp["id"] == DEFAULT_STORAGE_POOL_ID


def test_get_path_storage_pool_longest_prefix_wins(monkeypatch):
    monkeypatch.setattr(mod, "get_storage_pools", _pools)
    sp = mod.get_path_storage_pool("/isard/storage_pools/pool-a/cat/media/y.qcow2")
    assert sp["id"] == "pool-a"


def test_get_path_storage_pool_none_for_unknown(monkeypatch):
    monkeypatch.setattr(
        mod,
        "get_storage_pools",
        lambda: [{"id": "pool-fast", "mountpoint": "/mnt/fast"}],
    )
    assert mod.get_path_storage_pool("/srv/other/x.qcow2") is None


def test_get_path_storage_pool_empty_path():
    assert mod.get_path_storage_pool("") is None
    assert mod.get_path_storage_pool(None) is None


def test_clear_storage_pools_cache_empties_both():
    mod._storage_pools_cache["storage_pools"] = ["x"]
    mod._all_storage_pools_cache["storage_pools"] = ["y"]
    mod.clear_storage_pools_cache()
    assert len(mod._storage_pools_cache) == 0
    assert len(mod._all_storage_pools_cache) == 0
