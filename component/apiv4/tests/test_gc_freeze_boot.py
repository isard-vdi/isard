# SPDX-License-Identifier: AGPL-3.0-or-later

"""The apiv4 lifespan freezes its startup object graph so full collections skip it."""

import ast
import gc
import inspect
import textwrap

import api
import pytest


@pytest.fixture(autouse=True)
def _restore_gc():
    # gc.freeze() touches the whole heap; never leak a freeze into the next test.
    gc.unfreeze()
    yield
    gc.unfreeze()


def _tracked_cyclic_graph(n):
    # Cyclic so refcounting alone cannot reclaim them: they reach the generation
    # the cyclic collector walks, which is what freezing has to remove them from.
    graph = [{} for _ in range(n)]
    for item in graph:
        item["self"] = item
    return graph


def test_freeze_moves_the_live_graph_into_the_permanent_generation():
    assert gc.get_freeze_count() == 0  # the fixture left us a clean heap
    api._freeze_gc_after_startup()
    assert gc.get_freeze_count() > 0


def test_a_full_collection_no_longer_walks_the_frozen_startup_graph():
    graph = _tracked_cyclic_graph(5000)
    ids = {id(item) for item in graph}

    # Promote the graph so a gen-2 collection would otherwise walk every object.
    gc.collect()
    gc.collect()
    assert sum(1 for o in gc.get_objects(generation=2) if id(o) in ids) == 5000

    api._freeze_gc_after_startup()

    # Frozen objects leave the generations entirely: generation 2 has none of the
    # startup graph left to walk, and a full collection still touches none of it.
    assert not any(id(o) in ids for o in gc.get_objects(generation=2))
    assert not any(id(o) in ids for o in gc.get_objects())
    gc.collect(2)
    assert not any(id(o) in ids for o in gc.get_objects(generation=2))


def test_freeze_does_not_disable_collection_of_post_startup_garbage():
    # A plausible wrong fix is gc.disable(), which would stop reclaiming
    # per-request cycles and leak. Freezing must leave the collector enabled.
    api._freeze_gc_after_startup()
    frozen = gc.get_freeze_count()
    assert gc.isenabled()  # freeze must not disable automatic collection

    garbage = _tracked_cyclic_graph(2000)
    del garbage
    collected = gc.collect()

    # Collectable (not frozen), and the frozen boot graph is untouched. Assert the
    # collected *count*, not id() membership: freed addresses get reused and flake.
    assert collected >= 2000
    assert gc.get_freeze_count() == frozen


def test_lifespan_freezes_the_heap_at_the_end_of_startup():
    # AST, not a substring check: the call must be real (not commented out) and
    # sit before the yield, so it runs at the end of startup, not in shutdown.
    tree = ast.parse(textwrap.dedent(inspect.getsource(api.lifespan)))

    freeze_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_freeze_gc_after_startup"
    ]
    assert freeze_calls, "lifespan must call _freeze_gc_after_startup()"

    yield_lines = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, (ast.Yield, ast.YieldFrom))
    ]
    assert yield_lines, "lifespan is expected to yield once"
    assert all(
        call.lineno < min(yield_lines) for call in freeze_calls
    ), "the freeze must run during startup, before the lifespan yields"
