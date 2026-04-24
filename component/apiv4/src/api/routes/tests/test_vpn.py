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
