#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A category recycle-bin cutoff must not exceed the global one.

Setting the GLOBAL cutoff clamps any category above it down to the new value
(set_system_recycle_bin_cutoff_time, else-branch). Setting a CATEGORY cutoff
did no such check — a plain update, and RecycleBinUpdateCutoffTimeRequest
carries no ge=/le= — so a category could be pushed ABOVE the global, an
invariant the webapp enforces on the client but the backend did not. Guard it
server-side.
"""

from unittest.mock import MagicMock

import pytest


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def rb_helpers(monkeypatch):
    from isardvdi_common.helpers import recycle_bin as mod

    monkeypatch.setattr(mod.Helpers, "_rdb_context", classmethod(lambda cls: _Ctx()))
    table = MagicMock(name="table")
    monkeypatch.setattr(mod.r, "table", lambda name: table)
    return mod, table


def _set_global(mod, monkeypatch, value):
    monkeypatch.setattr(
        mod.Helpers,
        "get_system_recycle_bin_cutoff_time",
        classmethod(lambda cls: value),
    )


class TestCategoryCutoffGuard:
    def test_rejects_category_cutoff_above_global(self, rb_helpers, monkeypatch):
        mod, table = rb_helpers
        _set_global(mod, monkeypatch, 24)
        with pytest.raises(mod.Error) as exc:
            mod.Helpers.set_system_recycle_bin_cutoff_time(48, category_id="cat-x")
        assert exc.value.status_code == 400
        # Nothing was written to the categories table.
        assert not table.get.return_value.update.called

    def test_allows_category_cutoff_below_global(self, rb_helpers, monkeypatch):
        mod, table = rb_helpers
        _set_global(mod, monkeypatch, 24)
        mod.Helpers.set_system_recycle_bin_cutoff_time(12, category_id="cat-x")
        table.get.return_value.update.assert_called()

    def test_allows_category_cutoff_equal_to_global(self, rb_helpers, monkeypatch):
        mod, table = rb_helpers
        _set_global(mod, monkeypatch, 24)
        mod.Helpers.set_system_recycle_bin_cutoff_time(24, category_id="cat-x")
        table.get.return_value.update.assert_called()

    def test_allows_zero_category_cutoff(self, rb_helpers, monkeypatch):
        # 0 (bin disabled for the category) is always <= global.
        mod, table = rb_helpers
        _set_global(mod, monkeypatch, 24)
        mod.Helpers.set_system_recycle_bin_cutoff_time(0, category_id="cat-x")
        table.get.return_value.update.assert_called()
