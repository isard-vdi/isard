"""Route tests for ``GET /admin/item/domain/{domain_id}/live_xml``.

Port of the live-XML half of upstream MR !4535. The engine HTTP boundary
is mocked (B9: mock at the boundary, not the service layer).
"""

from unittest.mock import patch

from api.routes.tests.helpers import MockJWT


class _Resp:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


def test_live_xml_happy_path(test_client):
    jwt = MockJWT(role_id="admin")

    with patch(
        "isardvdi_common.helpers.engine_api.requests.get",
        return_value=_Resp(200, {"xml": "<domain/>", "hyp": "hyper-1"}),
    ):
        response = test_client(
            url="/admin/item/domain/desktop-1/live_xml",
            method="GET",
            jwt=jwt,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["xml"] == "<domain/>"
    assert data["hyp"] == "hyper-1"


def test_live_xml_not_running_maps_409(test_client):
    jwt = MockJWT(role_id="admin")

    with patch(
        "isardvdi_common.helpers.engine_api.requests.get",
        return_value=_Resp(409),
    ):
        response = test_client(
            url="/admin/item/domain/desktop-1/live_xml",
            method="GET",
            jwt=jwt,
        )

    assert response.status_code == 409


def test_live_xml_not_captured_maps_404(test_client):
    jwt = MockJWT(role_id="admin")

    with patch(
        "isardvdi_common.helpers.engine_api.requests.get",
        return_value=_Resp(404),
    ):
        response = test_client(
            url="/admin/item/domain/desktop-1/live_xml",
            method="GET",
            jwt=jwt,
        )

    assert response.status_code == 404


def test_live_xml_requires_admin(test_client):
    jwt = MockJWT(role_id="user")

    response = test_client(
        url="/admin/item/domain/desktop-1/live_xml",
        method="GET",
        jwt=jwt,
    )

    assert response.status_code == 403
