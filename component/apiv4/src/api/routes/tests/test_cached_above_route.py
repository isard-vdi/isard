# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression guard: a cache decorator must never sit above a route decorator.

``@router.get(...)`` (FastAPI) and ``@app.route(...)`` / ``@blueprint.route``
(Flask) register the function they are handed and return it *unwrapped*, so a
``@cached`` stacked above one only rebinds the module-level name. The object
the framework dispatches to is the raw handler: the cache never takes a hit
and never takes a miss.

The fix is to delete such a cache, not to reorder it, because neither
framework can run one where reordering would put it:

* FastAPI — ``cachetools.cached`` returns a *synchronous* wrapper and
  ``asyncio.iscoroutinefunction`` does not follow ``__wrapped__``, so FastAPI
  classes the endpoint as sync, runs it in the threadpool and gets back a
  coroutine it never awaits. Every request fails, starting with the first.
  Keying on the ``Request`` does not help either: ``starlette.Request`` is
  hashable and a fresh object per request, so each call stores an entry that
  can never be hit.
* Flask — the ``engine`` blueprint's ``is_admin`` hands the decoded JWT
  payload to the handler as a ``dict`` keyword argument. Below ``is_admin``
  the cache key is unhashable; above it the key is the empty tuple, and a
  response cached for an admin is then served to a caller that never passed
  the check.

``routes/open.py`` shows the supported alternative: cache the *synchronous*
helper the handler calls, and await that through ``asyncio.to_thread``.

The scan is AST-based, so decorator *order* is what is checked, not text.
"""

import ast
import os
import pathlib

import pytest

_API_ROOT = pathlib.Path(__file__).resolve().parents[2]  # .../api

# Decorator attribute names that register a handler and hand it back bare.
_ROUTE_METHODS = frozenset(
    {
        "route",
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "head",
        "options",
        "websocket",
    }
)

# Memoising decorators from cachetools, functools and async_lru.
_CACHE_DECORATORS = frozenset(
    {
        "alru_cache",
        "cache",
        "cached",
        "cachedmethod",
        "lfu_cache",
        "lru_cache",
        "ttl_cache",
    }
)

# Substring shared by every name in _CACHE_DECORATORS. A file that does not
# contain it cannot contain a decorator this guard recognises, so it can be
# skipped without parsing — see test_prefilter_cannot_hide_an_offender.
_CACHE_MARKER = "cach"

# Directories that hold no first-party handlers, or hold build output.
# Pruned during the walk so the repo-wide scan stays fast.
_SKIP_DIRS = frozenset(
    {
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        "tests",
    }
)


def _repo_root():
    """Walk up to the checkout root (the dir holding both trees)."""
    for parent in _API_ROOT.parents:
        if (parent / "component").is_dir() and (parent / "engine").is_dir():
            return parent
    return None


def _decorator_name(node):
    """Dotted name of a decorator expression, e.g. ``open_router.get``."""
    node = node.func if isinstance(node, ast.Call) else node
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _is_cached(name):
    return name.rsplit(".", 1)[-1] in _CACHE_DECORATORS


def _is_route(name):
    return "." in name and name.rsplit(".", 1)[1] in _ROUTE_METHODS


def _scan(tree):
    """Yield ``(lineno, funcname)`` for every cache decorator above a route."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        names = [_decorator_name(d) for d in node.decorator_list]
        cached_at = [i for i, n in enumerate(names) if _is_cached(n)]
        route_at = [i for i, n in enumerate(names) if _is_route(n)]
        # Decorators apply bottom-up, so a *lower* index is the outer one.
        if cached_at and route_at and min(cached_at) < min(route_at):
            yield node.lineno, node.name


def _sources(root):
    """Yield every first-party ``.py`` file under ``root``."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
        )
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            path = pathlib.Path(dirpath, name)
            if path.is_file():  # skips broken symlinks
                yield path


def _offenders(root):
    """Return ``(offenders, scanned_paths)`` for the tree under ``root``.

    ``encoding="utf-8"`` is explicit because ``read_text()`` falls back to the
    locale encoding, and under a non-UTF-8 locale most of the tree would raise
    ``UnicodeDecodeError``. That error is deliberately not caught: a guard
    that skips the files it cannot read stops guarding without saying so.
    """
    found = []
    scanned = []
    for path in _sources(root):
        source = path.read_text(encoding="utf-8")
        scanned.append(path)
        if _CACHE_MARKER not in source:
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for lineno, funcname in _scan(tree):
            found.append(f"{path}:{lineno}: {funcname}")
    return found, scanned


_HINT = (
    "A cache decorator stacked above a route decorator is a no-op — the "
    "framework registers the unwrapped handler. Delete the cache; do not "
    "reorder it (this module's docstring says why neither ordering runs). "
    "To memoise, cache the synchronous helper instead:\n"
)


def test_no_cached_above_route_decorator_in_apiv4():
    offenders, scanned = _offenders(_API_ROOT)
    assert len(scanned) > 50, (
        f"only {len(scanned)} files scanned under {_API_ROOT} — the guard is "
        "pointed at the wrong directory and would pass vacuously"
    )
    assert not offenders, _HINT + "\n".join(offenders)


def test_no_cached_above_route_decorator_repo_wide():
    """Same guard over every tree in the checkout, not just apiv4.

    ``engine``, ``webapp``, ``scheduler`` and ``notifier`` register handlers
    with the same decorator shape and hit the same trap.
    """
    root = _repo_root()
    if root is None:
        pytest.skip("not a full checkout; apiv4 is still covered on its own")
    offenders, scanned = _offenders(root)
    trees = {path.relative_to(root).parts[0] for path in scanned}
    assert {"component", "engine"} <= trees, (
        f"scan of {root} reached only {sorted(trees)} — it is not walking the "
        "whole checkout and would pass vacuously"
    )
    assert not offenders, _HINT + "\n".join(offenders)


def test_scanner_detects_a_planted_offender():
    """The guard itself must actually catch the pattern."""
    fastapi_bad = ast.parse(
        "@cached(cache=c)\n"
        "@open_router.get('/x')\n"
        "async def handler(request):\n"
        "    return 1\n"
    )
    flask_bad = ast.parse(
        "@cached(cache=TTLCache(maxsize=1, ttl=5))\n"
        "@api.route('/engine/status', methods=['GET'])\n"
        "@is_admin\n"
        "def engine_status(payload):\n"
        "    return 'Ok', 200\n"
    )
    good = ast.parse(
        "@open_router.get('/x')\n"
        "@cached(cache=c)\n"
        "async def handler(request):\n"
        "    return 1\n"
    )
    assert [name for _, name in _scan(fastapi_bad)] == ["handler"]
    assert [name for _, name in _scan(flask_bad)] == ["engine_status"]
    assert list(_scan(good)) == []


def test_prefilter_cannot_hide_an_offender():
    """Skipping files without _CACHE_MARKER must not skip a real offender."""
    assert all(_CACHE_MARKER in name for name in _CACHE_DECORATORS)
