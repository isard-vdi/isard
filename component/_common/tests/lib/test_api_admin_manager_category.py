#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Category ownership check of ``ApiAdmin.manager_table_list`` when a
single item is fetched with a ``pluck``.

The webapp asks for one plucked field (e.g. the favourite hypervisor
modal sends ``{"id": ..., "pluck": "favourite_hyp"}``), so the item
returned by rethinkdb carries no ``category`` and the ownership check
must not read it from the plucked result.
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


def test_plucked_item_of_own_category_is_returned(stub_rdb):
    ApiAdmin = stub_rdb["ApiAdmin"]
    query = stub_rdb["mock_table"].return_value.get.return_value
    query.pluck.return_value.run.return_value = {
        "favourite_hyp": ["hyp-a"],
        "category": "cat-1",
    }

    item = ApiAdmin.manager_table_list(
        "domains", "cat-1", id="desktop-1", pluck="favourite_hyp"
    )

    assert item == {"favourite_hyp": ["hyp-a"]}
    assert "category" in query.pluck.call_args.args


def test_a_requested_category_is_not_stripped(stub_rdb):
    """Only the fields added for the check are removed from the answer."""
    ApiAdmin = stub_rdb["ApiAdmin"]
    query = stub_rdb["mock_table"].return_value.get.return_value
    query.pluck.return_value.run.return_value = {
        "favourite_hyp": ["hyp-a"],
        "category": "cat-1",
    }

    item = ApiAdmin.manager_table_list(
        "domains", "cat-1", id="desktop-1", pluck=["favourite_hyp", "category"]
    )

    assert item == {"favourite_hyp": ["hyp-a"], "category": "cat-1"}


def test_plucked_item_of_another_category_is_forbidden(stub_rdb):
    from isardvdi_common.helpers.error_factory import Error

    ApiAdmin = stub_rdb["ApiAdmin"]
    query = stub_rdb["mock_table"].return_value.get.return_value
    query.pluck.return_value.run.return_value = {
        "favourite_hyp": ["hyp-a"],
        "category": "cat-2",
    }

    with pytest.raises(Error) as exc:
        ApiAdmin.manager_table_list(
            "domains", "cat-1", id="desktop-1", pluck="favourite_hyp"
        )

    assert exc.value.error.get("error") == "forbidden"
