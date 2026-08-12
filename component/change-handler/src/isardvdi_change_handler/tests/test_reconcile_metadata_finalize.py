# SPDX-License-Identifier: AGPL-3.0-or-later

"""Reconcile safety net for metadata finalize.

A metadata chain whose real (storage) work settled but whose finalize never
applied (the result event was lost) is pending yet not live work — the reconcile
must treat it as healable so Pass 2 recovers it from the storage's own reality,
the metadata analogue of the legacy core-tombstone reap.

The contract of ``_metadata_finalize_orphaned`` itself is pinned in
``test_reconcile_finalize_orphan_knot.py``, against chains built by the
product's own builder. It used to be pinned here against a hand-built task
whose ``job`` was a ``MagicMock`` and whose ``dependents`` was a list the test
supplied — which encoded the very assumption that turned out to be the defect:
that the finalize hangs off the task the reconcile was handed. A mock of the
one-level shape cannot notice that the real chain puts the finalize three jobs
down, so those five cases moved to the real harness rather than stay here as a
second, wrong opinion.

What remains is the pure tree helper, which has no graph in it to get wrong.
"""


def test_finalize_has_unstamped_walks_nested():
    from isardvdi_change_handler.streams import reconcile

    nested = [{"status": "finished", "core_finalize": [{"status": None}]}]
    assert reconcile._finalize_has_unstamped(nested) is True
    done = [{"status": "finished", "core_finalize": [{"status": "failed"}]}]
    assert reconcile._finalize_has_unstamped(done) is False
