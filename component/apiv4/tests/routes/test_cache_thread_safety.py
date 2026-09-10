# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression guard for tiquet #1096 — apiv4 module-global cachetools caches.

apiv4 offloads every blocking RethinkDB call to a 128-worker
``asyncio.to_thread`` executor. A plain ``cachetools`` ``TTLCache``/``LRUCache``
mutated from several of those real OS threads corrupts its internal
``OrderedDict`` (``RuntimeError: OrderedDict mutated during iteration`` plus
sibling ``KeyError``/``TypeError``), surfacing as intermittent 500s. Every
module-global cache must therefore be a thread-safe
``SynchronizedTTLCache``/``SynchronizedLRUCache`` from ``isardvdi_common``.

These tests fail loudly if a plain cachetools cache creeps back in.
"""

import pathlib
import re

from isardvdi_common.helpers.synchronized_cache import (
    SynchronizedLRUCache,
    SynchronizedTTLCache,
)

_API_ROOT = pathlib.Path(__file__).resolve().parents[2]  # .../api
_PLAIN_CACHE = re.compile(
    r"(?<![A-Za-z_])(TTLCache|LRUCache|LFUCache|RRCache|FIFOCache)\s*\("
)


def test_no_plain_cachetools_cache_in_apiv4_source():
    """No source line constructs a bare cachetools cache (only the
    ``Synchronized*`` subclasses are allowed)."""
    offenders = []
    for path in sorted(_API_ROOT.rglob("*.py")):
        if "tests" in path.parts:
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]  # ignore comments
            if _PLAIN_CACHE.search(code) and "Synchronized" not in code:
                offenders.append(
                    f"{path.relative_to(_API_ROOT.parent)}:{lineno}: {line.strip()}"
                )
    assert not offenders, (
        "Non-thread-safe cachetools cache(s) found — regression of #1096. Use "
        "SynchronizedTTLCache/SynchronizedLRUCache from "
        "isardvdi_common.helpers.synchronized_cache:\n" + "\n".join(offenders)
    )


def test_hot_apiv4_caches_are_synchronized_instances():
    """Spot-check the most contended caches are the thread-safe variants at
    runtime (the source scan guards the rest)."""
    from api.services.admin.queues import queue_jobs_cache
    from api.services.desktops import _GET_DESKTOP_VIEWER_CACHE

    for cache in (_GET_DESKTOP_VIEWER_CACHE, queue_jobs_cache):
        assert isinstance(cache, (SynchronizedTTLCache, SynchronizedLRUCache))
        assert hasattr(cache, "lock")
