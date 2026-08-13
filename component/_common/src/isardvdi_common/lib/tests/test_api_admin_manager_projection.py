#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Field projection applied to managers in ``ApiAdmin.manager_table_list``.

The hypervisor document carries the node hostname, its ssh user and port
and the viewer proxy hosts. Managers reach the table through the generic
``/admin/items/table/{table}`` endpoint, so the projection has to be
enforced server-side and not by the fields the webapp happens to request.
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

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {"mock_table": mock_table, "ApiAdmin": mod.ApiAdmin}


def test_hypervisors_are_projected_when_no_pluck_is_requested(stub_rdb):
    ApiAdmin = stub_rdb["ApiAdmin"]
    query = stub_rdb["mock_table"].return_value
    query.pluck.return_value.run.return_value = [
        {"id": "hyp-1", "hostname": "hyp-1.local"}
    ]

    result = ApiAdmin.manager_table_list("hypervisors", "cat-1")

    assert query.pluck.call_args.args == (["id", "hostname"],)
    assert result == [{"id": "hyp-1", "hostname": "hyp-1.local"}]


def test_hypervisors_pluck_is_narrowed_to_the_visible_fields(stub_rdb):
    ApiAdmin = stub_rdb["ApiAdmin"]
    query = stub_rdb["mock_table"].return_value
    query.pluck.return_value.run.return_value = [{"id": "hyp-1"}]

    ApiAdmin.manager_table_list(
        "hypervisors", "cat-1", pluck=["id", "user", "port", "status"]
    )

    assert query.pluck.call_args.args == (["id"],)


def test_hypervisors_are_not_merged_with_admin_only_counters(stub_rdb):
    ApiAdmin = stub_rdb["ApiAdmin"]
    query = stub_rdb["mock_table"].return_value
    query.pluck.return_value.run.return_value = []

    ApiAdmin.manager_table_list("hypervisors", "cat-1")

    query.merge.assert_not_called()
