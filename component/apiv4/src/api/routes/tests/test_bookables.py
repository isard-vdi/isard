# SPDX-License-Identifier: AGPL-3.0-or-later

"""Route tests for the dedicated Bookables endpoint (#1650 / MR !4599).

``GET /items/bookables/{reservable_type}`` lists bookable reservables, each
enriched with the distinct categories of the GPU cards backing it. It replaces
the generic ``admin/items/table/reservables_vgpus`` feed so the response carries
the computed ``categories`` natively; the response model keeps only the declared
bookable fields.
"""

from unittest.mock import patch

from api.routes.tests.helpers import MockJWT

_BOOKABLES = [
    {
        "id": "NVIDIA-X-passthrough",
        "name": "GPU X",
        "description": "",
        "profile": "passthrough",
        "total_units": 1,
        "categories": ["Cat One"],
        # a stray field the response model must drop
        "item_id": "should-not-leak",
    },
    {
        "id": "NVIDIA-X-8Q",
        "name": "GPU X 8Q",
        "total_units": 2,
        "categories": [],
    },
]


def test_list_bookables_returns_enriched_categories(test_client):
    with patch(
        "isardvdi_common.lib.bookings.reservables.ResourceItemsGpus.list_bookables",
        return_value=_BOOKABLES,
    ):
        response = test_client(
            url="/items/bookables/gpus", method="GET", jwt=MockJWT(role_id="admin")
        )

    assert response.status_code == 200
    items = {it["id"]: it for it in response.json()}
    assert items["NVIDIA-X-passthrough"]["categories"] == ["Cat One"]
    assert items["NVIDIA-X-8Q"]["categories"] == []
    # response model whitelists fields: the stray key must not leak
    assert "item_id" not in items["NVIDIA-X-passthrough"]


def test_list_bookables_unknown_type_404(test_client):
    response = test_client(
        url="/items/bookables/not_a_type", method="GET", jwt=MockJWT(role_id="admin")
    )
    assert response.status_code == 404
