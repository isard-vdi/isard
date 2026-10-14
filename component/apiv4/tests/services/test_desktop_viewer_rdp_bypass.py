# SPDX-License-Identifier: AGPL-3.0-or-later
"""Who may open an RDP viewer before it is verified is decided from the token's role, per desktop category."""


import pytest
from api.services import desktops as mod
from api.services.desktops import DesktopService


@pytest.fixture
def viewer(monkeypatch):
    calls = []
    mod._GET_DESKTOP_VIEWER_CACHE.clear()
    monkeypatch.setattr(
        mod,
        "RethinkDomain",
        type(
            "D",
            (),
            {
                "exists": staticmethod(lambda _id: True),
                "__init__": lambda self, _id: setattr(self, "category", "cat-a"),
            },
        ),
    )

    def desktop_viewer(desktop_id, **kwargs):
        calls.append(kwargs)
        return {"kind": "file"}

    monkeypatch.setattr(
        mod.DesktopDirectViewer, "desktop_viewer", staticmethod(desktop_viewer)
    )

    def get(viewer_type, role_id, category_id):
        DesktopService.get_desktop_viewer(
            user_id="u-" + role_id + category_id,
            desktop_id="d1",
            viewer_type=viewer_type,
            host="h",
            is_admin=role_id == "admin",
            role_id=role_id,
            category_id=category_id,
        )
        return calls[-1]["rdp_bypass"]

    return get


@pytest.mark.parametrize(
    "role_id,category_id,allowed",
    [
        ("user", "cat-a", False),
        ("advanced", "cat-a", False),
        ("manager", "cat-b", False),
        ("manager", "cat-a", True),
        ("admin", "cat-b", True),
    ],
)
def test_only_an_admin_or_the_desktops_manager_may_force_rdp(
    viewer, role_id, category_id, allowed
):
    assert viewer("browser-rdp", role_id, category_id) is allowed


def test_non_rdp_viewers_never_carry_a_bypass(viewer):
    assert viewer("browser-vnc", "admin", "cat-a") is False
