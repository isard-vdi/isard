# SPDX-License-Identifier: AGPL-3.0-or-later

"""The admin logs tables answer a per-column search instead of a 500."""

from __future__ import annotations

import pytest

from .helpers.client import IsardClient


@pytest.mark.real
@pytest.mark.parametrize("table", ["logs_desktops", "logs_users"])
@pytest.mark.parametrize(
    "columns",
    [
        [{"data": "owner_user_id", "search": {"value": "admin"}}],
        [
            {"data": "owner_user_id", "search": {"value": "admin"}},
            {"data": "owner_category_id", "search": {"value": "default"}},
        ],
    ],
    ids=["one-column", "two-columns"],
)
def test_column_search(admin_client: IsardClient, table: str, columns: list):
    body = admin_client.post(
        f"/api/v4/admin/items/{table}",
        json_body={"draw": 1, "start": 0, "length": 5, "columns": columns},
        expected=(200,),
    )
    assert body["draw"] == 1
    assert body["recordsFiltered"] <= body["recordsTotal"]
    assert isinstance(body["data"], list)
