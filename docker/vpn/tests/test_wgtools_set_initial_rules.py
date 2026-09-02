# SPDX-License-Identifier: AGPL-3.0-or-later
"""``set_initial_rules`` must actually match the started desktops and seed the
applied-desktop index.

``domains.status`` is a single-field index, so the list key it used matched no
rows at all: the index stayed empty for every desktop that predated the
container start, and the reap that depends on it could never find them.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

STARTED = [
    {
        "id": "d1",
        "user": "u1",
        "status": "Started",
        "viewer": {"guest_ip": "10.2.0.5"},
    },
    {"id": "d2", "user": "u2", "status": "Started", "viewer": {}},
]


@pytest.fixture
def wg(wgtools_module):
    instance = wgtools_module.Wg.__new__(wgtools_module.Wg)
    instance.table = "users"
    instance.interface = "users"
    # lazily built by the property; start from a clean one
    instance.__dict__["_applied_desktops_index"] = {}
    return instance


def _run(wgtools_module, wg):
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    query = MagicMock()
    query.pluck.return_value.run.return_value = STARTED
    table = MagicMock()
    table.get_all.return_value = query
    with patch.object(
        wgtools_module, "vpn_rethink_conn", return_value=conn
    ), patch.object(wgtools_module.r, "table", return_value=table):
        wg.set_initial_rules()
    return table


def test_the_status_index_is_queried_with_a_scalar_key(wgtools_module, wg):
    table = _run(wgtools_module, wg)
    assert table.get_all.call_args.args == ("Started",), table.get_all.call_args
    assert table.get_all.call_args.kwargs == {"index": "status"}


def test_the_applied_index_is_seeded_for_desktops_that_have_a_guest_ip(
    wgtools_module, wg
):
    _run(wgtools_module, wg)
    assert "d1" in wg._applied_desktops
    assert wg._applied_desktops["d1"] == {"user": "u1", "guest_ip": "10.2.0.5"}
    # No guest_ip means no rule was installed, so nothing to remember.
    assert "d2" not in wg._applied_desktops
