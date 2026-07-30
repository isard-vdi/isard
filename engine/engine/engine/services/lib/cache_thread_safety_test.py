"""Regression guard — engine module-global cachetools caches must be thread-safe.

The engine runs one process with many real OS threads: ``start.py`` serves the
Flask API with ``app.run()`` (Flask defaults ``threaded=True``, so every request
gets its own thread) while ``Engine`` starts ``t_background``,
``t_changes_domains``, ``t_broom``, ``t_events``, ``t_orchestrator``, a
``HypWorkerThread`` per hypervisor and several ``ThreadPoolExecutor``s. Those
threads share the module-global caches — ``get_next_hypervisor()`` alone is
called from both the background thread and the Flask API handlers.

A plain ``cachetools`` ``TTLCache``/``LRUCache`` mutated from several of those
threads corrupts its internal ``OrderedDict`` during ``popitem``/``expire``
(``RuntimeError: OrderedDict mutated during iteration`` plus sibling
``KeyError``/``TypeError``). Every cache must therefore be a
``SynchronizedTTLCache``/``SynchronizedLRUCache`` from ``isardvdi_common``.

Mirrors ``test_no_plain_cachetools_cache_in_isardvdi_common`` and apiv4's
``test_no_plain_cachetools_cache_in_apiv4_source``: a pure source scan, so it
needs none of the engine's heavy runtime imports.
"""

import pathlib
import re

_ENGINE_ROOT = pathlib.Path(__file__).resolve().parents[3]  # engine app root
_PLAIN_CACHE = re.compile(
    r"(?<![A-Za-z_])(TTLCache|LRUCache|LFUCache|RRCache|FIFOCache)\s*\("
)


def test_no_plain_cachetools_cache_in_engine_source():
    """No engine source line constructs a bare cachetools cache (only the
    ``Synchronized*`` subclasses are allowed)."""
    offenders = []
    for path in sorted(_ENGINE_ROOT.rglob("*.py")):
        if "tests" in path.parts or path.name.endswith("_test.py"):
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]  # ignore comments
            if _PLAIN_CACHE.search(code) and "Synchronized" not in code:
                offenders.append(
                    f"{path.relative_to(_ENGINE_ROOT)}:{lineno}: {line.strip()}"
                )
    assert not offenders, (
        "Non-thread-safe cachetools cache(s) found in the engine. Use "
        "SynchronizedTTLCache/SynchronizedLRUCache from "
        "isardvdi_common.helpers.synchronized_cache:\n" + "\n".join(offenders)
    )
