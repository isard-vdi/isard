# SPDX-License-Identifier: AGPL-3.0-or-later

from api.routes.tests.helpers import MockJWT


def test_register_vpn_connection(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.admin_vpn.AdminVpnService.active_client",
        staticmethod(lambda kind, client_ip, remote_ip, remote_port, connected: True),
    )
    response = test_client(
        url="/admin/vpn_connection/users/10.0.0.1",
        method="POST",
        body={"remote_ip": "192.168.1.1", "remote_port": 1194},
        jwt=jwt,
    )
    assert response.status_code == 200


def test_disconnect_vpn_client(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.admin_vpn.AdminVpnService.active_client",
        staticmethod(lambda *args, **kwargs: True),
    )
    response = test_client(
        url="/admin/vpn_connection/users/10.0.0.1",
        method="DELETE",
        jwt=jwt,
    )
    assert response.status_code == 200


def test_reset_vpn_connections(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.admin_vpn.AdminVpnService.reset_connection_status",
        staticmethod(lambda kind: True),
    )
    monkeypatch.setattr(
        "api.services.admin_vpn.AdminVpnService.active_client",
        staticmethod(lambda *args, **kwargs: True),
    )
    response = test_client(
        url="/admin/vpn_connection/all",
        method="DELETE",
        jwt=jwt,
    )
    assert response.status_code == 200


def test_vpn_roam_connection(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.admin_vpn.AdminVpnService.active_client",
        staticmethod(lambda kind, client_ip, remote_ip, remote_port, connected: True),
    )
    response = test_client(
        url="/admin/vpn_connection/users/10.0.0.1",
        method="PUT",
        body={"remote_ip": "192.168.1.1", "remote_port": 1194},
        jwt=jwt,
    )
    assert response.status_code == 200


# ─── DELETE /admin/vpn_connections (Category A5) ─────────────────────────


def test_admin_vpn_connections_disconnect_happy_path(monkeypatch, client):
    """Typed body ``AdminVpnConnectionsDisconnectRequest``. The service
    now receives the validated ``List[VpnDisconnectListItem]`` Pydantic
    models directly (no dict coercion at the route boundary)."""
    jwt = MockJWT()
    captured = {}

    def fake_reset(peers):
        captured["peers"] = peers
        return True

    monkeypatch.setattr(
        "api.services.admin_vpn.AdminVpnService.reset_connections_list_status",
        staticmethod(fake_reset),
    )

    response = client.request(
        "DELETE",
        "/api/v4/admin/vpn_connections",
        headers=jwt.header,
        json=[
            {"kind": "users", "client_ip": "10.0.0.1"},
            {"kind": "hypers", "client_ip": "10.0.0.2"},
        ],
    )

    assert response.status_code == 200
    # Per-field assertions (not exact dict comparison) so adding a new
    # optional field to ``VpnDisconnectListItem`` does not require
    # updating this test in lockstep. Use ``_rejects_bad_item`` and
    # ``_rejects_unknown_field``-style tests to lock the contract.
    peers = captured["peers"]
    assert len(peers) == 2
    assert peers[0].kind == "users"
    assert peers[0].client_ip == "10.0.0.1"
    assert peers[1].kind == "hypers"
    assert peers[1].client_ip == "10.0.0.2"


def test_admin_vpn_connections_disconnect_empty_list(monkeypatch, client):
    """Pins empty-list semantics: an empty body is valid and the
    service receives an empty peers list (no-op). Regression guard so
    a future ``min_items=1`` or similar tightening requires an explicit
    contract update."""
    jwt = MockJWT()
    captured = {}

    def fake_reset(peers):
        captured["peers"] = peers
        return True

    monkeypatch.setattr(
        "api.services.admin_vpn.AdminVpnService.reset_connections_list_status",
        staticmethod(fake_reset),
    )

    response = client.request(
        "DELETE",
        "/api/v4/admin/vpn_connections",
        headers=jwt.header,
        json=[],
    )

    assert response.status_code == 200
    assert captured["peers"] == []


def test_admin_vpn_connections_disconnect_rejects_bad_item(monkeypatch, client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.admin_vpn.AdminVpnService.reset_connections_list_status",
        staticmethod(lambda data: True),
    )

    response = client.request(
        "DELETE",
        "/api/v4/admin/vpn_connections",
        headers=jwt.header,
        json=[{"kind": "users"}],  # missing client_ip
    )

    # apiv4 installs a RequestValidationError handler that reshapes
    # FastAPI's default 422 into the legacy 400 envelope.
    assert response.status_code == 400
