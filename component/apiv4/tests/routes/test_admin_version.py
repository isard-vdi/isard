#
#   Copyright © 2026 Miriam Melina Gamboa Valdez
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from tests.routes.helpers import MockJWT

URL = "/admin/item/version"


def test_admin_gets_version(monkeypatch, test_client):
    monkeypatch.setattr("api.routes.admin.version.version", "17.0.1 2026-09-30")
    response = test_client(url=URL, jwt=MockJWT(role_id="admin"))
    assert response.status_code == 200
    assert response.json() == {"isardvdi_version": "17.0.1 2026-09-30"}


def test_non_admin_forbidden(test_client):
    for role in ["manager", "advanced", "user"]:
        response = test_client(url=URL, jwt=MockJWT(role_id=role))
        assert response.status_code == 403, role


def test_anonymous_unauthorized(test_client):
    response = test_client(url=URL)
    assert response.status_code == 401
