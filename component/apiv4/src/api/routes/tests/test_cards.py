#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from api.routes.tests.helpers import MockJWT

MOCK_STOCK_CARDS = [
    {"id": "stock1", "name": "Ubuntu", "type": "stock"},
    {"id": "stock2", "name": "Fedora", "type": "stock"},
]

MOCK_USER_CARDS = [
    {"id": "user1", "name": "My Desktop", "type": "user"},
]


def test_get_desktop_images(monkeypatch, test_client):
    """GET /images/desktops returns combined stock and user cards."""
    monkeypatch.setattr(
        "api.services.cards.CardService.get_stock_cards",
        lambda: MOCK_STOCK_CARDS,
    )
    monkeypatch.setattr(
        "api.services.cards.CardService.get_user_cards",
        lambda user_id, desktop_id=None: MOCK_USER_CARDS,
    )

    jwt = MockJWT()
    response = test_client(url="/api/v4/images/desktops", jwt=jwt)

    # ``response_model=list[CardResponse]`` (extra="allow") declares
    # ``id``/``url``/``type`` so the wire payload also includes
    # ``url: None`` for stub rows that omitted it. Per-key asserts
    # replace equality with the partial stub.
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 3
    assert {row["id"] for row in data} == {"stock1", "stock2", "user1"}


def test_get_desktop_images_forwards_caller_user_id(monkeypatch, test_client):
    """The user_id passed to get_user_cards comes from the JWT, not the
    request — pin the ownership boundary."""
    captured = {}

    def fake_user_cards(user_id, desktop_id=None):
        captured["user_id"] = user_id
        captured["desktop_id"] = desktop_id
        return MOCK_USER_CARDS

    monkeypatch.setattr(
        "api.services.cards.CardService.get_stock_cards",
        lambda: MOCK_STOCK_CARDS,
    )
    monkeypatch.setattr(
        "api.services.cards.CardService.get_user_cards",
        fake_user_cards,
    )

    jwt = MockJWT(user_id="local-default-user-bob")
    response = test_client(url="/api/v4/images/desktops?desktop_id=desk-1", jwt=jwt)
    assert response.status_code == 200
    assert captured == {"user_id": "local-default-user-bob", "desktop_id": "desk-1"}


def test_get_desktop_images_stock_via_kind_route(monkeypatch, test_client):
    """GET /images/desktops/stock returns stock cards only."""
    monkeypatch.setattr(
        "api.services.cards.CardService.get_stock_cards",
        lambda: MOCK_STOCK_CARDS,
    )

    jwt = MockJWT()
    response = test_client(url="/api/v4/images/desktops/stock", jwt=jwt)

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2
    assert {row["id"] for row in data} == {"stock1", "stock2"}


def test_get_desktop_images_user_kind(monkeypatch, test_client):
    """GET /images/desktops/user returns user cards only and forwards
    the JWT user_id to the service."""
    captured = {}

    def fake_user_cards(user_id, desktop_id=None):
        captured["user_id"] = user_id
        return MOCK_USER_CARDS

    monkeypatch.setattr(
        "api.services.cards.CardService.get_user_cards",
        fake_user_cards,
    )

    jwt = MockJWT(user_id="local-default-user-alice")
    response = test_client(url="/api/v4/images/desktops/user", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert {row["id"] for row in body} == {"user1"}
    assert captured["user_id"] == "local-default-user-alice"


def test_get_desktop_images_invalid_kind_rejected(test_client):
    """The /{kind} route rejects anything other than 'stock' / 'user'.
    The Literal route guard returns 422 (validation error) where the
    previous manual ``if not in (...): raise bad_request`` returned 400.
    """
    jwt = MockJWT()
    response = test_client(url="/api/v4/images/desktops/banana", jwt=jwt)
    assert response.status_code in (400, 422)


def test_get_desktop_images_unauthenticated_rejected(test_client):
    """token_router rejects requests with no JWT."""
    response = test_client(url="/api/v4/images/desktops")
    assert response.status_code in (401, 403, 422)
