#
#   Copyright © 2026 IsardVDI
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

"""The web viewers open on the domain the user is on.

A multitenant install serves several domains, but ``viewer.static`` is always
the default one. The frontends set the viewer cookies on the user's domain, so a
viewer opened on the default one found none and failed to connect.
"""

import pytest
from isardvdi_common.helpers.isard_viewer import IsardViewer
from isardvdi_common.schemas.domains import DesktopStatusEnum


def _domain():
    return {
        "id": "desktop-1",
        "name": "Desktop 1",
        "status": DesktopStatusEnum.started.value,
        "user": "user-1",
        "category": "default",
        "guest_properties": {
            "credentials": {"username": "isard", "password": "pirineus"},
        },
        "viewer": {
            "static": "default.example",
            "proxy_video": "video.example",
            "proxy_hyper_host": "isard-hypervisor",
            "html5_ext_port": "443",
            "base_port": 5900,
            "passwd": "secret-passwd",
            "guest_ip": "10.2.0.5",
        },
    }


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_ISARDVDI_SECRET", "test-secret")
    monkeypatch.delenv("DIRECTVIEWER_MODE", raising=False)


def _viewer(protocol, **kwargs):
    return IsardViewer().viewer_data(
        "desktop-1", protocol=protocol, domain=_domain(), **kwargs
    )


def test_browser_vnc_opens_on_the_request_host():
    viewer = _viewer("browser-vnc", host="tenant.example")

    assert viewer["viewer"] == "https://tenant.example/viewer/noVNC/"
    assert viewer["urlp"].startswith("https://tenant.example/viewer/noVNC/?")


def test_browser_vnc_keeps_connecting_to_the_video_proxy():
    # websockify checks ownership by the Host its websocket was opened on, which
    # must stay the desktop's proxy_video.
    viewer = _viewer("browser-vnc", host="tenant.example")

    assert viewer["values"]["host"] == "video.example"


def test_browser_vnc_without_host_opens_on_the_static_domain():
    viewer = _viewer("browser-vnc")

    assert viewer["viewer"] == "https://default.example/viewer/noVNC/"


def test_browser_rdp_opens_and_tunnels_on_the_request_host():
    viewer = _viewer("browser-rdp", host="tenant.example:8443")

    assert viewer["viewer"] == "https://tenant.example:8443/Rdp"
    assert viewer["values"]["host"] == "tenant.example:8443"


def test_browser_rdp_without_host_uses_the_static_domain():
    viewer = _viewer("browser-rdp")

    assert viewer["viewer"] == "https://default.example/Rdp"
    assert viewer["values"]["host"] == "default.example"
