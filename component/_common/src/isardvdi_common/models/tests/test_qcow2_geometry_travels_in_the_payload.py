#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Every disk-writing enqueue site carries the qcow2 geometry in its payload.

The install-wide geometry is resolved once by the enqueuer and spread into the
``job_kwargs["kwargs"]`` of every ``create`` / ``convert`` / ``disconnect``
task. This walks ``models/storage.py`` as source -- the chain is a tree of dict
literals handed to RQ, so the declaration IS the behaviour -- and asserts that
each of the (exactly six) disk-writing tasks names all four geometry keys, or
spreads them with ``**geometry``.

It walks the whole module, not one method, so a seventh site added later (or a
nested one, like the ``create`` hung under a ``move`` in template creation) is
caught too. The exact count is pinned so both a new site and a deleted one are
loud.
"""

import ast
from pathlib import Path

from isardvdi_common.helpers import qcow2_geometry

_SOURCE = Path(__file__).resolve().parents[1] / "storage.py"
_DISK_TASKS = {"create", "convert", "disconnect"}
_EXPECTED_SITES = 6

_TREE = ast.parse(_SOURCE.read_text())

# Some sites build their create kwargs in a local variable (e.g. ``create_kwargs
# = {..., **geometry}``) and hand it to ``create_task`` by name. Map every
# ``<name> = {dict literal}`` so a Name in the ``"kwargs"`` slot can be resolved
# back to the dict it refers to.
_DICT_ASSIGNMENTS = {
    target.id: node.value
    for node in ast.walk(_TREE)
    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict)
    for target in node.targets
    if isinstance(target, ast.Name)
}


def _resolve(node):
    """Follow a Name to its ``<name> = {dict}`` definition, else return node."""
    if isinstance(node, ast.Name) and node.id in _DICT_ASSIGNMENTS:
        return _DICT_ASSIGNMENTS[node.id]
    return node


def _dict_get(node, key):
    """Return the value node for ``key`` in an ``ast.Dict`` literal, or None."""
    if not isinstance(node, ast.Dict):
        return None
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant) and k.value == key:
            return v
    return None


def _kwargs_dict(job_kwargs_node):
    """From a ``job_kwargs`` dict node, return its inner ``"kwargs"`` dict,
    resolving a variable reference to its dict-literal definition."""
    return _resolve(_dict_get(_resolve(job_kwargs_node), "kwargs"))


def _carries_geometry(kwargs_node):
    """True if the kwargs dict names all four geometry keys, or spreads them
    with ``**geometry``.

    A ``**spread`` is an ``ast.Dict`` entry whose key is ``None``; only a spread
    of a name called ``geometry`` counts -- an unrelated ``**parent_args`` must
    not pass this off as carrying the policy."""
    if not isinstance(kwargs_node, ast.Dict):
        return False
    for k, v in zip(kwargs_node.keys, kwargs_node.values):
        if k is None and isinstance(v, ast.Name) and v.id == "geometry":
            return True
    named = {k.value for k in kwargs_node.keys if isinstance(k, ast.Constant)}
    return set(qcow2_geometry.KEYS).issubset(named)


def _collect_sites():
    """Return ``[(task, lineno, carries_geometry_bool), ...]`` for every
    disk-writing task declared in the module, whether a ``create_task(...)``
    call or a nested ``{"task": ...}`` dependent dict."""
    tree = ast.parse(_SOURCE.read_text())
    sites = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_task"
        ):
            task = None
            job_kwargs = None
            for kw in node.keywords:
                if (
                    kw.arg == "task"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value in _DISK_TASKS
                ):
                    task = kw.value.value
                if kw.arg == "job_kwargs":
                    job_kwargs = kw.value
            if task is not None:
                sites.append(
                    (task, node.lineno, _carries_geometry(_kwargs_dict(job_kwargs)))
                )
        if isinstance(node, ast.Dict):
            task_node = _dict_get(node, "task")
            if isinstance(task_node, ast.Constant) and task_node.value in _DISK_TASKS:
                job_kwargs = _dict_get(node, "job_kwargs")
                sites.append(
                    (
                        task_node.value,
                        node.lineno,
                        _carries_geometry(_kwargs_dict(job_kwargs)),
                    )
                )
    return sites


def test_exactly_six_disk_writing_sites():
    sites = _collect_sites()
    assert len(sites) == _EXPECTED_SITES, (
        f"expected {_EXPECTED_SITES} disk-writing enqueue sites, found "
        f"{len(sites)} at lines {[s[1] for s in sites]}"
    )


def test_every_disk_writing_site_carries_the_geometry():
    missing = [(task, lineno) for task, lineno, ok in _collect_sites() if not ok]
    assert not missing, (
        "these disk-writing tasks do not carry the four qcow2 geometry keys in "
        f"job_kwargs['kwargs']: {missing}"
    )


# --- invariant: change-handler never has to resolve geometry -----------------


def _queue_is_core(dict_node):
    """True if this dependent's ``queue`` resolves to the ``core`` lane, whether
    a bare ``"core"`` constant or an f-string starting with ``core``."""
    q = _dict_get(dict_node, "queue")
    if isinstance(q, ast.Constant) and isinstance(q.value, str):
        return q.value.startswith("core")
    if isinstance(q, ast.JoinedStr) and q.values:
        first = q.values[0]
        return isinstance(first, ast.Constant) and str(first.value).startswith("core")
    return False


def _walk_dependents(dict_node, under_core):
    """Yield ``(under_core, task, dict_node)`` for every dependent in the tree
    rooted at ``dict_node``. ``under_core`` says whether an ANCESTOR is on the
    core lane."""
    task = _dict_get(dict_node, "task")
    yield (
        under_core,
        task.value if isinstance(task, ast.Constant) else None,
        dict_node,
    )
    deps = _dict_get(dict_node, "dependents")
    if isinstance(deps, ast.List):
        child_under_core = under_core or _queue_is_core(dict_node)
        for child in deps.elts:
            if isinstance(child, ast.Dict):
                yield from _walk_dependents(child, child_under_core)


def test_no_disk_task_lives_under_a_core_finalize_knot():
    """A task under a ``core`` finalize knot is re-materialised at run time by
    change-handler (``Task(**c)``), not frozen DEFERRED at chain-build time. So
    a create/convert/disconnect there would force change-handler to resolve the
    geometry -- which is exactly what keeps its compose file free of QCOW2_*.
    The three storage-under-core children in main are info/delete/info, none of
    them disk-writers; this keeps it that way."""
    violations = []
    for node in ast.walk(_TREE):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_task"
        ):
            for kw in node.keywords:
                if kw.arg == "dependents" and isinstance(kw.value, ast.List):
                    for dep in kw.value.elts:
                        if isinstance(dep, ast.Dict):
                            for under_core, task, dep_node in _walk_dependents(
                                dep, under_core=False
                            ):
                                if under_core and task in _DISK_TASKS:
                                    violations.append((task, dep_node.lineno))
    assert not violations, (
        "disk-writing tasks found under a core-queued dependent (change-handler "
        f"would have to resolve their geometry): {violations}"
    )
