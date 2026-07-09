#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guard ``StorageProcessed.get_storage_derivatives`` against missing rows.

Companion to ``models/tests/test_storage_parents_guard.py`` — same root
cause (apiv4-integration ported main ``74a0a4bf1``'s strict
``RethinkBase.__init__`` but not its ``Storage.exists`` guards).

``get_storage_derivatives`` opens with ``Storage(storage_id).domains``
and then **recurses on ``derivative["storage"]``**, a storage id read out
of a domain's ``create_dict``. That id can name a row that no longer
exists (a deleted derivative), so the strict constructor raises
``Error("not_found")`` part-way through the recursion. main guards this
exact function; this branch did not.
"""

from unittest.mock import MagicMock, patch

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.storage import storage as mod
from isardvdi_common.models.storage import Storage


def test_get_storage_derivatives_returns_empty_for_missing_storage():
    """A storage id that no longer exists must yield an empty derivative
    list, not raise. Pre-fix the strict ctor raised ``Error("not_found")``
    on the very first ``Storage(storage_id)``."""
    with patch.object(Storage, "exists", return_value=False):
        assert mod.StorageProcessed.get_storage_derivatives("dead-uuid") == []


def test_get_storage_derivatives_does_not_construct_missing_storage():
    """The ``exists`` guard must be consulted BEFORE the constructor, so a
    missing row never reaches ``Storage(...)``."""
    fake_storage_cls = MagicMock(
        name="Storage",
        side_effect=AssertionError("Storage(...) must not be constructed"),
    )
    fake_storage_cls.exists.return_value = False

    with patch.object(mod, "Storage", fake_storage_cls):
        result = mod.StorageProcessed.get_storage_derivatives("dead-uuid")

    assert result == []
    fake_storage_cls.exists.assert_called_once_with("dead-uuid")
    fake_storage_cls.assert_not_called()


def test_get_storage_derivatives_walks_domains_for_existing_storage():
    """Behaviour preserved: an existing storage with a non-template domain
    returns that domain id (no recursion, no derivative lookup)."""
    domain = MagicMock(id="domain-1", kind="desktop")
    storage_obj = MagicMock(domains=[domain])

    fake_storage_cls = MagicMock(name="Storage", return_value=storage_obj)
    fake_storage_cls.exists.return_value = True

    with patch.object(mod, "Storage", fake_storage_cls):
        result = mod.StorageProcessed.get_storage_derivatives("live-uuid")

    assert result == ["domain-1"]
    fake_storage_cls.assert_called_once_with("live-uuid")


def test_strict_constructor_still_raises_for_missing_row():
    """Sanity: the guard must not weaken the strict constructor itself."""
    with patch.object(Storage, "exists", return_value=False):
        with pytest.raises(Error):
            Storage("dead-uuid")
