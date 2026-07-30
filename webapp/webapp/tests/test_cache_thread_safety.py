#
#   Copyright © 2026 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression guard — webapp module-global cachetools caches must be thread-safe.

``start.py`` serves the webapp with ``waitress.serve()``, whose default
``threads=4`` dispatches requests onto four real OS threads (and the devel/debug
branch uses Flask's ``app.run()``, which defaults to ``threaded=True``). A plain
``cachetools`` ``TTLCache``/``LRUCache`` mutated from several of those threads
corrupts its internal ``OrderedDict`` during ``popitem``/``expire``
(``RuntimeError: OrderedDict mutated during iteration`` plus sibling
``KeyError``/``TypeError``). Every cache must therefore be a
``SynchronizedTTLCache``/``SynchronizedLRUCache`` from ``isardvdi_common``.

Same shape as apiv4's ``test_cache_thread_safety``: a source scan plus a
runtime spot-check of the hot cache.
"""

import pathlib
import re

from isardvdi_common.helpers.synchronized_cache import (
    SynchronizedLRUCache,
    SynchronizedTTLCache,
)

from webapp.views import decorators

# Grabbed at import time: conftest's autouse ``disable_maintenance`` fixture
# rebinds the module attribute to a plain lambda before every test runs.
_MAINTENANCE_CACHE = decorators._get_maintenance.cache

_WEBAPP_ROOT = pathlib.Path(__file__).resolve().parents[1]  # .../webapp/webapp
_PLAIN_CACHE = re.compile(
    r"(?<![A-Za-z_])(TTLCache|LRUCache|LFUCache|RRCache|FIFOCache)\s*\("
)


def test_no_plain_cachetools_cache_in_webapp_source():
    """No webapp source line constructs a bare cachetools cache (only the
    ``Synchronized*`` subclasses are allowed)."""
    offenders = []
    for path in sorted(_WEBAPP_ROOT.rglob("*.py")):
        if "tests" in path.parts:
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]  # ignore comments
            if _PLAIN_CACHE.search(code) and "Synchronized" not in code:
                offenders.append(
                    f"{path.relative_to(_WEBAPP_ROOT)}:{lineno}: {line.strip()}"
                )
    assert not offenders, (
        "Non-thread-safe cachetools cache(s) found in the webapp. Use "
        "SynchronizedTTLCache/SynchronizedLRUCache from "
        "isardvdi_common.helpers.synchronized_cache:\n" + "\n".join(offenders)
    )


def test_maintenance_cache_is_a_synchronized_instance():
    """Spot-check the maintenance cache — hit on every decorated request from
    all waitress threads — is the thread-safe variant at runtime."""
    assert isinstance(_MAINTENANCE_CACHE, (SynchronizedTTLCache, SynchronizedLRUCache))
    assert hasattr(_MAINTENANCE_CACHE, "lock")
