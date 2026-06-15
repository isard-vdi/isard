"""Route tests for the GPU planner delegation gate (upstream MR !4546).

The planner routes moved from admin-only to ``manager_router`` +
``can_manage_gpu_plannings``: admins always pass; a manager passes only
when their category's ``manager_permissions.plannings`` is enabled; plain
users are rejected by the router. The per-card category scoping is pinned
separately in the planner twin suite (test_planner_manager_guards.py).
"""

from api.routes.tests.helpers import MockJWT


def _categories(plannings: bool):
    return [
        {
            "id": "cat-1",
            "name": "Cat 1",
            "manager_permissions": {"plannings": plannings},
        }
    ]


def test_admin_lists_all_plans(test_client):
    jwt = MockJWT(role_id="admin")

    response = test_client(
        url="/items/reservables-planner",
        method="GET",
        jwt=jwt,
        db_tables_data={"resource_planner": [], "gpus": []},
    )

    assert response.status_code == 200


def test_manager_with_plannings_permission_passes(test_client):
    jwt = MockJWT(role_id="manager", category_id="cat-1")

    response = test_client(
        url="/items/reservables-planner",
        method="GET",
        jwt=jwt,
        db_tables_data={
            "categories": _categories(True),
            "resource_planner": [],
            "gpus": [],
        },
    )

    assert response.status_code == 200


def test_manager_without_plannings_permission_403(test_client):
    jwt = MockJWT(role_id="manager", category_id="cat-1")

    response = test_client(
        url="/items/reservables-planner",
        method="GET",
        jwt=jwt,
        db_tables_data={
            "categories": _categories(False),
            "resource_planner": [],
            "gpus": [],
        },
    )

    assert response.status_code == 403


def test_user_role_403(test_client):
    jwt = MockJWT(role_id="user")

    response = test_client(
        url="/items/reservables-planner",
        method="GET",
        jwt=jwt,
        db_tables_data={"resource_planner": [], "gpus": []},
    )

    assert response.status_code == 403


def test_manager_sees_only_delegated_cards_in_type_listing(monkeypatch):
    """ReservableService.get_reservable_detail: a manager's card selector only
    lists cards delegated to their category — another category's or global
    (undelegated) hardware is not enumerable. Exercised at the service layer
    with the rdb listing stubbed: the ``list_items`` merge query
    (r.branch/do/concat_map) is beyond rethinkdb_mock's rewriter, so the
    boundary here is the twin's listing, not the HTTP client."""
    from api.services.reservables import ReservableService

    def _card(card_id, name, category=None):
        card = {
            "id": card_id,
            "brand": "NVIDIA",
            "model": "A40",
            "name": name,
            "description": "",
            "physical_device": None,
            "profiles_enabled": [],
            "active_profile": None,
            "changing_to_profile": None,
            "memory": "24 GB",
            "architecture": "x86_64",
        }
        if category:
            card["category"] = category
        return card

    gpus = [
        _card("card-own", "own", "cat-1"),
        _card("card-other", "other", "cat-2"),
        _card("card-global", "global"),
    ]
    monkeypatch.setattr(
        "isardvdi_common.lib.bookings.reservables.Reservables.list_items",
        lambda self, item_type: list(gpus),
    )
    monkeypatch.setattr(
        "api.services.reservables.ReservableService._get_item_plans",
        staticmethod(lambda reservables, reservable_type, item: []),
    )

    items = ReservableService.get_reservable_detail(
        "gpus", payload={"role_id": "manager", "category_id": "cat-1"}
    )
    assert [i["id"] for i in items] == ["card-own"]

    # Admin (or no payload) keeps the full listing.
    items = ReservableService.get_reservable_detail(
        "gpus", payload={"role_id": "admin", "category_id": "x"}
    )
    assert len(items) == 3
