#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``placement=False`` keeps the hypervisor fields out of the domain
listings, so callers serving non-admin roles never read them from the
database instead of dropping them afterwards.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib import api_admin as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.ApiAdmin, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(mod.ApiAdmin),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    monkeypatch.setattr(mod.r, "table", MagicMock(name="r.table"))
    yield mod.ApiAdmin


def _plucked_fields(query):
    """Field names the last pluck call asked for."""
    fields = query.eq_join.return_value.map.return_value
    fields = fields.eq_join.return_value.map.return_value
    fields = fields.eq_join.return_value.map.return_value
    [selector] = fields.pluck.call_args.args
    return [f for f in selector if isinstance(f, str)]


def test_domain_listing_drops_the_placement(stub_rdb):
    query = MagicMock(name="query")

    stub_rdb._apply_domain_joins_and_pluck(query, bastion=False, placement=False)

    fields = _plucked_fields(query)
    assert "hyp_started" not in fields
    assert "forced_hyp" not in fields
    assert "favourite_hyp" in fields


def test_domain_listing_keeps_the_placement_by_default(stub_rdb):
    query = MagicMock(name="query")

    stub_rdb._apply_domain_joins_and_pluck(query, bastion=False)

    fields = _plucked_fields(query)
    assert "hyp_started" in fields
    assert "forced_hyp" in fields
