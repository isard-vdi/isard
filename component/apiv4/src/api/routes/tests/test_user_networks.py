# SPDX-License-Identifier: AGPL-3.0-or-later

from api.routes.tests.helpers import MockJWT


def test_list_user_networks(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.user_networks.UserNetworkService.get_user_networks",
        staticmethod(lambda payload: [{"id": "net-1", "name": "Test Network"}]),
    )
    response = test_client(url="/item/user/networks", jwt=jwt)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == "net-1"


def test_get_user_network(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.user_networks.UserNetworkService.get_user_network",
        staticmethod(
            lambda network_id, payload: {"id": network_id, "name": "Test Network"}
        ),
    )
    response = test_client(url="/item/user/networks/net-1", jwt=jwt)
    assert response.status_code == 200
    assert response.json()["id"] == "net-1"


def test_create_user_network(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.user_networks.UserNetworkService.create_user_network",
        staticmethod(lambda data, payload: {"id": "net-new", "name": "New Network"}),
    )
    response = test_client(
        url="/item/user/networks",
        method="POST",
        body={"name": "New Network"},
        jwt=jwt,
    )
    assert response.status_code == 200
    assert response.json()["id"] == "net-new"


def test_delete_user_network(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.user_networks.UserNetworkService.delete_user_network",
        staticmethod(lambda network_id, payload: None),
    )
    response = test_client(
        url="/item/user/networks/net-1",
        method="DELETE",
        jwt=jwt,
    )
    assert response.status_code == 200


def test_create_user_network_missing_name(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.user_networks.UserNetworkService.create_user_network",
        staticmethod(lambda data, payload: {"id": "net-new", "name": "New Network"}),
    )
    response = test_client(
        url="/item/user/networks",
        method="POST",
        body={},
        jwt=jwt,
    )
    assert response.status_code == 400
    assert "validation_error" in response.text
