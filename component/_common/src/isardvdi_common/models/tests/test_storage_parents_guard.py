#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guard the ``Storage.parents`` chain walk against missing parent rows.

Background — this is the apiv4-integration port of main ``74a0a4bf1``
(``fix(common): stop RethinkBase from auto-creating stub rows``).

That commit made ``RethinkBase.__init__`` **strict**: constructing
``Storage(uuid)`` for a row that does not exist now raises
``Error("not_found")`` instead of silently inserting a stub row. It
therefore *also* guarded every site that WALKS the parent chain, because
a strict constructor turns every previously-silent stale/missing parent
into a raised exception.

apiv4-integration ported the strict constructor but **not** the guards,
so ``Storage.parents`` crashes on a storage that exists but whose
``parent`` UUID points at a deleted row. That state is reachable in
production: ``Storage.delete`` leaves dangling ``parent`` UUIDs on its
children, and the legacy path->UUID migration is not on this branch yet
so path-shaped ``parent`` values can still exist too.

Live blast radius:

* ``StorageService.get_parents`` (apiv4 ``services/storage.py``) does
  ``for s in [storage] + storage.parents``, reached by the manager route
  ``GET /item/storage/{storage_id}/parents``. A storage that EXISTS but
  has a deleted parent answered **404** instead of **200 + the readable
  partial chain**.
* ``Storage.operational`` iterates ``self.parents`` and is evaluated at
  the recreate precondition *before* the explicit
  ``if not Storage.exists(self.parent):`` guard — so the graceful
  ``storage_has_no_parent`` error was dead-code-shadowed by the crash.

The tests below never touch RethinkDB. ``_bare_storage`` builds an
instance via ``__new__`` (mirroring
``test_storage_chain_definitions.py``), and the *parent* objects are
built by the REAL strict constructor with only its two DB touchpoints
(``Storage.exists`` / ``Storage.get``) patched — so the pre-fix failures
are genuine ``Error("not_found")`` raises from the real constructor, not
simulated ones.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models.storage import Storage


def _bare_storage(
    *,
    id: str = "child-storage",
    parent: str | None = None,
) -> Storage:
    """Construct a Storage without hitting Redis or RethinkDB.

    ``RethinkCustomBase.__setattr__`` writes through to RethinkDB on every
    assignment, so use ``object.__setattr__`` to populate only the attrs
    the ``parents`` / ``operational`` properties read.
    """
    s = Storage.__new__(Storage)
    object.__setattr__(s, "id", id)
    object.__setattr__(s, "parent", parent)
    return s


def _rows_patch(rows: dict[str, dict]):
    """Patch the two DB touchpoints of the strict ``RethinkBase.__init__``.

    ``exists(id)`` answers from ``rows``; ``get(id)`` returns the row.
    Constructing a ``Storage`` for an id absent from ``rows`` therefore
    runs the REAL strict constructor and raises ``Error("not_found")``.
    """
    return (
        patch.object(Storage, "exists", side_effect=lambda doc_id: doc_id in rows),
        patch.object(Storage, "get", side_effect=lambda doc_id: rows[doc_id]),
    )


# ---------------------------------------------------------------------------
# 1. Direct parent missing -> [] (no raise)
# ---------------------------------------------------------------------------


def test_parents_returns_empty_when_direct_parent_missing():
    """A storage whose ``parent`` UUID names a deleted row must terminate
    the walk silently. Pre-fix this raised ``Error("not_found")`` from the
    strict constructor and turned ``GET .../parents`` into a 404."""
    s = _bare_storage(id="orphan-1", parent="00000000-dead-dead-dead-000000000000")

    with patch.object(Storage, "exists", return_value=False):
        assert s.parents == []


# ---------------------------------------------------------------------------
# 2. Grandparent missing -> partial chain (walk stops at last existing ancestor)
# ---------------------------------------------------------------------------


def test_parents_returns_partial_chain_when_grandparent_missing():
    """Parent exists, grandparent is gone: the walk must return the parent
    and stop, rather than raising while recursing into the grandparent."""
    rows = {
        "parent-2": {
            "id": "parent-2",
            "parent": "missing-grandparent-2",
            "status": "ready",
        }
    }
    s = _bare_storage(id="child-2", parent="parent-2")

    exists_p, get_p = _rows_patch(rows)
    with exists_p, get_p:
        chain = s.parents

    assert [p.id for p in chain] == ["parent-2"]


# ---------------------------------------------------------------------------
# 3. Healthy chain -> unchanged behaviour (this one is GREEN before the fix too)
# ---------------------------------------------------------------------------


def test_parents_returns_full_chain_when_all_ancestors_exist():
    """Regression guard: the guard must not truncate a healthy chain.
    child-3 -> parent-3 -> grandparent-3 -> (root)."""
    rows = {
        "parent-3": {"id": "parent-3", "parent": "grandparent-3", "status": "ready"},
        "grandparent-3": {"id": "grandparent-3", "parent": None, "status": "ready"},
    }
    s = _bare_storage(id="child-3", parent="parent-3")

    exists_p, get_p = _rows_patch(rows)
    with exists_p, get_p:
        chain = s.parents

    assert [p.id for p in chain] == ["parent-3", "grandparent-3"]


def test_parents_returns_empty_when_no_parent():
    """``parent is None`` short-circuits before any ``exists`` lookup."""
    s = _bare_storage(id="root-3b", parent=None)

    with patch.object(Storage, "exists", side_effect=AssertionError("no DB hit")):
        assert s.parents == []


# ---------------------------------------------------------------------------
# 4. operational must not raise on a dangling parent
# ---------------------------------------------------------------------------


def test_operational_does_not_raise_on_dangling_parent():
    """``operational`` iterates ``self.parents``; with the parent row gone
    the walk yields [] and ``all([])`` is True. Pre-fix this raised
    ``Error("not_found")``, dead-code-shadowing the graceful
    ``storage_has_no_parent`` precondition in ``recreate``."""
    s = _bare_storage(id="orphan-4", parent="00000000-dead-dead-dead-000000000000")

    with patch.object(Storage, "exists", return_value=False):
        result = s.operational

    assert result is True
    assert isinstance(result, bool)


def test_operational_false_when_existing_parent_not_ready():
    """Behaviour preserved: an existing but non-ready ancestor still makes
    the storage non-operational."""
    rows = {
        "parent-5": {"id": "parent-5", "parent": None, "status": "maintenance"},
    }
    s = _bare_storage(id="child-5", parent="parent-5")

    exists_p, get_p = _rows_patch(rows)
    with exists_p, get_p:
        assert s.operational is False


# ---------------------------------------------------------------------------
# Pin the pre-fix failure mode: the strict ctor is what raises.
# ---------------------------------------------------------------------------


def test_strict_constructor_still_raises_for_missing_row():
    """Sanity: the guard added to ``parents`` must NOT weaken the strict
    constructor itself — ``Storage(missing_id)`` still raises."""
    with patch.object(Storage, "exists", return_value=False):
        with pytest.raises(Error):
            Storage("00000000-dead-dead-dead-000000000000")
