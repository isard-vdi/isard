# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/resources.py — remote VPN config/install retrieval and
QoS-disk profile add/update. All endpoints live on admin_router (admin
only); QoS profiles affect every desktop's IO behavior so the gate is
intentionally tight.

Route declaration order matters here too:
    GET /remote_vpn/{vpn_id}/{kind}/{os}    must come before
    GET /remote_vpn/{vpn_id}/{kind}
otherwise the shorter pattern wins and the os param is silently ignored.
TestRemoteVpn pins both shapes.
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  GET /remote_vpn/{vpn_id}/{kind}/{os}
#  GET /remote_vpn/{vpn_id}/{kind}
# ══════════════════════════════════════════════════════════════════════════


class TestRemoteVpn:
    def test_get_with_os(self, monkeypatch, test_client):
        captured = {}

        def fake(vpn_id, kind, os=None):
            captured["vpn_id"] = vpn_id
            captured["kind"] = kind
            captured["os"] = os
            return {"data": "config-bytes"}

        monkeypatch.setattr(
            "api.routes.admin.resources.AdminResourcesService.get_remote_vpn",
            staticmethod(fake),
        )
        response = test_client(
            url="/admin/item/remote_vpn/v-1/install/linux", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert captured == {"vpn_id": "v-1", "kind": "install", "os": "linux"}

    def test_get_without_os(self, monkeypatch, test_client):
        """The two-segment variant calls get_remote_vpn(vpn_id, kind)
        with no os — the service signature defaults os to None.
        """
        captured = {}

        def fake(vpn_id, kind, os=None):
            captured["os"] = os
            return {"data": "config"}

        monkeypatch.setattr(
            "api.routes.admin.resources.AdminResourcesService.get_remote_vpn",
            staticmethod(fake),
        )
        response = test_client(
            url="/admin/item/remote_vpn/v-1/config", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert captured["os"] is None

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.resources.AdminResourcesService.get_remote_vpn",
            staticmethod(lambda *a, **k: {}),
        )
        response = test_client(
            url="/admin/item/remote_vpn/v-1/config", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.resources.AdminResourcesService.get_remote_vpn",
            staticmethod(lambda *a, **k: {}),
        )
        response = test_client(
            url="/admin/item/remote_vpn/v-1/config", jwt=MockJWT(role_id="manager")
        )
        assert response.status_code == 403

    def test_invalid_kind_returns_400(self, monkeypatch, test_client):
        def reject(vpn_id, kind, os=None):
            raise Error("bad_request", f"Unknown kind: {kind}")

        monkeypatch.setattr(
            "api.routes.admin.resources.AdminResourcesService.get_remote_vpn",
            staticmethod(reject),
        )
        response = test_client(
            url="/admin/item/remote_vpn/v-1/no_such_kind",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 400


# ══════════════════════════════════════════════════════════════════════════
#  POST /qos_disk
# ══════════════════════════════════════════════════════════════════════════


class TestQosDiskAdd:
    URL = "/admin/item/qos_disk"

    def _payload(self, **overrides):
        body = {
            "name": "Standard",
            "iotune": {"read_iops_sec": 1000, "write_iops_sec": 500},
        }
        body.update(overrides)
        return body

    def test_admin_adds(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.resources.AdminResourcesService.add_qos_disk",
            staticmethod(lambda data: captured.update(data=data)),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),
        )
        assert response.status_code == 204
        assert captured["data"]["name"] == "Standard"
        # exclude_none drops Optional unset fields
        assert "id" not in captured["data"]
        assert "description" not in captured["data"]

    def test_missing_required_field_rejected(self, test_client):
        """name + iotune are required."""
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"description": "missing name"},
        )
        assert response.status_code in (400, 422)

    def test_duplicate_returns_409(self, monkeypatch, test_client):
        def reject(data):
            raise Error("conflict", "QoS profile name in use")

        monkeypatch.setattr(
            "api.routes.admin.resources.AdminResourcesService.add_qos_disk",
            staticmethod(reject),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),
        )
        assert response.status_code == 409

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.resources.AdminResourcesService.add_qos_disk",
            staticmethod(lambda data: None),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="user"),
            body=self._payload(),
        )
        assert response.status_code == 403

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.resources.AdminResourcesService.add_qos_disk",
            staticmethod(lambda data: None),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="manager"),
            body=self._payload(),
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  PUT /qos_disk
# ══════════════════════════════════════════════════════════════════════════


class TestQosDiskUpdate:
    URL = "/admin/item/qos_disk"

    def test_admin_updates(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.resources.AdminResourcesService.update_qos_disk",
            staticmethod(lambda data: captured.update(data=data)),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={
                "id": "q-1",
                "name": "Updated",
                "iotune": {"read_iops_sec": 2000},
            },
        )
        assert response.status_code == 204
        assert captured["data"]["id"] == "q-1"

    def test_id_required(self, test_client):
        """id is the only field required by QosDiskUpdateRequest beyond name."""
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"name": "Updated"},
        )
        assert response.status_code in (400, 422)

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.resources.AdminResourcesService.update_qos_disk",
            staticmethod(lambda data: None),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="user"),
            body={"id": "q-1", "name": "x"},
        )
        assert response.status_code == 403
