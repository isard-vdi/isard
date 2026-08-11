#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The dependents walk: one answer to "what depends on this disk?".

Before this, three properties answered that question three different ways
while claiming to answer it the same way:

* ``children`` — direct children, ``status="deleted"`` rows dropped.
* ``derivatives`` — documented as "recursively including all descendant
  children (leaf nodes)", implemented as children + *their* children and
  nothing deeper. A three-level chain lost its bottom level.
* ``domains_derivatives`` — documented as "descendants recursively",
  implemented as the domains of the *direct* children only.

``task_delete`` reads both of the broken ones: ``derivatives`` to mark
storages ``orphan`` and ``domains_derivatives`` to mark domains
``Failed``. Deleting the root of a three-level chain therefore left the
deepest disks pointing at a backing file that had just been removed,
still reading ``ready``, with their desktops still reading ``Stopped``.

All three now go through ``Storage.get_children`` / ``dependent_levels``,
so they cannot drift apart again — and the walk that feeds them costs one
indexed query per *level* instead of one per node.

No RethinkDB here: ``get_index`` is answered from an in-memory table that
mirrors ReQL's filter semantics (a row missing the filtered field is
dropped, not an error).
"""

from __future__ import annotations

from unittest.mock import patch

from isardvdi_common.models.domain import Domain
from isardvdi_common.models.storage import Storage


def _bare_storage(id: str) -> Storage:
    """A Storage instance that never touches Redis or RethinkDB.

    ``RethinkCustomBase.__setattr__`` writes through on every assignment,
    hence ``object.__setattr__``.
    """
    s = Storage.__new__(Storage)
    object.__setattr__(s, "id", id)
    return s


def _bare_domain(id: str) -> Domain:
    d = Domain.__new__(Domain)
    object.__setattr__(d, "id", id)
    return d


class _FakeIndex:
    """Answer ``Storage.get_index(values, index="parent", filter=...)`` from
    a list of plain rows, counting the calls so the query cost is testable.
    """

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __call__(self, values, index, filter=None):
        assert index == "parent"
        self.calls.append(list(values))
        wanted = set(values)
        out = []
        for row in self.rows:
            if row.get("parent") not in wanted:
                continue
            if filter is not None:
                try:
                    if not filter(row):
                        continue
                except KeyError:
                    # ReQL drops rows missing the filtered field rather
                    # than erroring; mirror that.
                    continue
            out.append(_bare_storage(row["id"]))
        return out


# root
#  +- a1            (level 1)
#  |   +- b1        (level 2)
#  |   |   +- c1    (level 3)   <- the level the old walk never reached
#  |   +- bin1      (level 2, recycle-bin copy: status "deleted")
#  +- a2            (level 1)
_THREE_LEVELS = [
    {"id": "a1", "parent": "root", "status": "ready"},
    {"id": "a2", "parent": "root", "status": "ready"},
    {"id": "b1", "parent": "a1", "status": "ready"},
    {"id": "c1", "parent": "b1", "status": "ready"},
    {"id": "bin1", "parent": "a1", "status": "deleted"},
]


def _walk(rows, storage_id="root"):
    fake = _FakeIndex(rows)
    s = _bare_storage(storage_id)
    return s, fake, patch.object(Storage, "get_index", side_effect=fake)


def test_derivatives_reaches_the_third_level():
    """The old two-level walk returned a1, a2, b1 and stopped. c1 — a real
    disk whose backing file is about to be deleted — was invisible."""
    s, _fake, index_patch = _walk(_THREE_LEVELS)

    with index_patch:
        found = [child.id for child in s.derivatives]

    assert sorted(found) == ["a1", "a2", "b1", "c1"]


def test_derivatives_excludes_recycle_bin_copies_by_default():
    """Unchanged guard semantics: a row already flipped to ``deleted`` by
    the delete chain must not block or be re-marked."""
    s, _fake, index_patch = _walk(_THREE_LEVELS)

    with index_patch:
        found = [child.id for child in s.derivatives]

    assert "bin1" not in found


def test_dependents_include_deleted_sees_the_stranded_copy():
    """The copy sitting in ``deleted/`` still carries its ``backing_file=``
    link, so an operator deciding what a delete drags along has to be able
    to see it. That is the only way it stops being stranded."""
    s, _fake, index_patch = _walk(_THREE_LEVELS)

    with index_patch:
        found = [child.id for child in s.dependents(include_deleted=True)]

    assert sorted(found) == ["a1", "a2", "b1", "bin1", "c1"]


def test_dependent_levels_group_by_distance_leaf_last():
    """Reversing the levels is the enqueue order: no intermediate step may
    leave a child whose parent has already gone."""
    s, _fake, index_patch = _walk(_THREE_LEVELS)

    with index_patch:
        levels = [sorted(child.id for child in level) for level in s.dependent_levels()]

    assert levels == [["a1", "a2"], ["b1"], ["c1"]]

    leaf_first = [child for level in reversed(levels) for child in level]
    assert leaf_first == ["c1", "b1", "a1", "a2"]


def test_walk_costs_one_query_per_level_not_one_per_node():
    """Batched by level: one lookup per level plus the one that finds the
    bottom empty. The old walk issued one query per *node* of the first
    level and still missed everything below the second."""
    s, fake, index_patch = _walk(_THREE_LEVELS)

    with index_patch:
        s.derivatives

    assert fake.calls == [["root"], ["a1", "a2"], ["b1"], ["c1"]]


def test_walk_terminates_on_a_cycle():
    """``parent`` has no referential integrity. A row pointing back up its
    own chain used to be impossible only by convention; the walk must not
    depend on that convention holding."""
    rows = [
        {"id": "x", "parent": "root", "status": "ready"},
        {"id": "y", "parent": "x", "status": "ready"},
        {"id": "x", "parent": "y", "status": "ready"},
    ]
    s, _fake, index_patch = _walk(rows)

    with index_patch:
        found = [child.id for child in s.derivatives]

    assert sorted(set(found)) == ["x", "y"]


def test_children_is_direct_only_and_batches_nothing_on_empty():
    """``children`` keeps its meaning — it is the guard's question — but it
    now comes out of the same helper as everything else."""
    s, fake, index_patch = _walk(_THREE_LEVELS)

    with index_patch:
        direct = [child.id for child in s.children]

    assert sorted(direct) == ["a1", "a2"]
    assert fake.calls == [["root"]]


def test_get_children_short_circuits_on_no_ids():
    """A leaf's level is empty; asking RethinkDB for ``get_all()`` with no
    arguments would be a full-table read, not an empty answer."""
    with patch.object(
        Storage, "get_index", side_effect=AssertionError("no DB hit expected")
    ):
        assert Storage.get_children([]) == []


def test_domains_derivatives_is_transitive_and_one_query():
    """It fed ``task_delete``'s "which desktops must go Failed" list while
    only looking one level down, so the deepest desktops kept reading
    ``Stopped`` after their disk's backing file was removed."""
    s, fake, index_patch = _walk(_THREE_LEVELS)
    seen_ids = []

    def fake_domains(storage_ids):
        seen_ids.append(list(storage_ids))
        return [_bare_domain("d-" + sid) for sid in storage_ids]

    with index_patch, patch.object(
        Domain, "get_with_storages", side_effect=fake_domains
    ):
        domains = [d.id for d in s.domains_derivatives]

    assert seen_ids == [["a1", "a2", "b1", "c1"]]
    assert domains == ["d-a1", "d-a2", "d-b1", "d-c1"]
    assert fake.calls == [["root"], ["a1", "a2"], ["b1"], ["c1"]]


def test_get_with_storages_deduplicates_multi_index_hits():
    """``storage_ids`` is a multi index: a two-disk desktop matched by both
    of its disks comes back twice, and a caller counting domains would
    double-count it."""
    returned = [_bare_domain("dom-1"), _bare_domain("dom-1"), _bare_domain("dom-2")]

    with patch.object(Domain, "get_index", return_value=returned) as get_index:
        found = [d.id for d in Domain.get_with_storages(["s1", "s2", "s1"])]

    assert found == ["dom-1", "dom-2"]
    get_index.assert_called_once_with(["s1", "s2"], index="storage_ids")


def test_domains_dependents_reaches_through_a_deleted_row():
    """The two halves of "what breaks if this disk goes" must reach the same
    distance. The storage half walked through already-deleted rows while the
    domain half stopped at them, so a disk behind a recycle-bin copy was
    marked ``orphan`` while the desktop sitting on it kept reading
    ``Stopped`` — still startable in the UI, which is the exact failure the
    walk exists to prevent."""
    rows = [
        {"id": "bin", "parent": "root", "status": "deleted"},
        {"id": "live", "parent": "bin", "status": "ready"},
    ]
    s, _fake, index_patch = _walk(rows)
    seen_ids = []

    def fake_domains(storage_ids):
        seen_ids.append(list(storage_ids))
        return [_bare_domain("d-" + sid) for sid in storage_ids]

    with index_patch, patch.object(
        Domain, "get_with_storages", side_effect=fake_domains
    ):
        default = [d.id for d in s.domains_dependents()]
        through = [d.id for d in s.domains_dependents(include_deleted=True)]

    assert default == []
    assert through == ["d-bin", "d-live"]
    assert seen_ids == [[], ["bin", "live"]]


def test_domains_derivatives_keeps_the_default_view():
    """The property stays the guard's view — it must not silently start
    returning the domains of deleted rows."""
    s, _fake, index_patch = _walk(_THREE_LEVELS)

    with index_patch, patch.object(
        Domain, "get_with_storages", side_effect=lambda ids: list(ids)
    ):
        assert s.domains_derivatives == ["a1", "a2", "b1", "c1"]


def test_get_with_storages_short_circuits_on_no_ids():
    with patch.object(
        Domain, "get_index", side_effect=AssertionError("no DB hit expected")
    ):
        assert Domain.get_with_storages([]) == []
