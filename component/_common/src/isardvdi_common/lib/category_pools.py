#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Cached category -> storage-pool id resolver.

The gate/health check is keyed on the requester's CATEGORY (from the JWT), so
resolving it to a storage pool on every call would hit RethinkDB per request.
That assignment changes rarely, so it is memoized in-process for a short TTL.
Resolution itself is delegated to
:class:`isardvdi_common.models.storage_pool.StoragePool` (``get_all`` +
``has_category``) -- this module owns only the caching, not the routing rule.
"""

import os
import time

from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.models.storage_pool import StoragePool

_cache = {}


def _env_int(name, default):
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _resolve(category_id):
    pool_ids = [
        pool.id
        for pool in StoragePool.get_all()
        if pool.id != DEFAULT_STORAGE_POOL_ID
        and pool.enabled is not False
        and pool.has_category(category_id)
    ]
    return pool_ids or [DEFAULT_STORAGE_POOL_ID]


def category_pool_ids(category_id):
    """Storage-pool id(s) serving ``category_id``, memoized for
    ``STORAGE_CATPOOL_CACHE_S`` seconds (default 30). Never returns an empty
    list: falls back to ``[DEFAULT_STORAGE_POOL_ID]``."""
    ttl = _env_int("STORAGE_CATPOOL_CACHE_S", 30)
    now = time.time()
    cached = _cache.get(category_id)
    if cached is not None and now - cached[0] < ttl:
        return cached[1]
    pool_ids = _resolve(category_id)
    _cache[category_id] = (now, pool_ids)
    return pool_ids


def invalidate_category_pool_cache(category_id=None):
    """Drop one category's memo, or the whole cache when ``category_id`` is None."""
    if category_id is None:
        _cache.clear()
    else:
        _cache.pop(category_id, None)
