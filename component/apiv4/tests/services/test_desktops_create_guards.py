# SPDX-License-Identifier: AGPL-3.0-or-later

"""Precondition / authorization guards on the desktop-create services.

These are the who-can-do-what and is-this-valid gates on
``DesktopService.create_from_media`` and
``create_nonpersistent_desktop``. Each is pinned to BOTH its HTTP status and
its ``description_code`` — telling a 403 (not allowed) from a 404 (missing)
from a 400 (bad input) is exactly what these tests exist to fix.

The service functions run unmocked; only their collaborators (the Rethink
model existence checks, template allowlist, virt-install lookup, quota
helpers) are patched, so the allow/deny decision is the real code.
"""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from api.services.desktops import DesktopService
from api.services.error import Error

PAYLOAD = {
    "user_id": "u1",
    "category_id": "default",
    "group_id": "default-default",
    "role_id": "user",
}
MOD = "api.services.desktops."


def _media_data(**over):
    d = dict(
        media_id="m1",
        os_template="w10",
        name="d1",
        kind="iso",
        hardware=None,
        guest_properties=SimpleNamespace(
            viewers=SimpleNamespace(
                browser_rdp=True,
                browser_vnc=None,
                file_rdpgw=None,
                file_rdpvpn=None,
                file_spice=None,
            )
        ),
    )
    d.update(over)
    return SimpleNamespace(**d)


@pytest.fixture
def media_env():
    """Patch create_from_media collaborators to a happy path; tests break one.

    ``RethinkUser`` / ``RethinkMedia`` are patched as whole classes (the
    media-not-downloaded path instantiates them), so their ``.exists`` is
    controlled via the class mock rather than a separate patch.
    """
    with ExitStack() as es:
        from api.services.desktops import MediaStatusEnum

        user_cls = es.enter_context(patch(MOD + "RethinkUser"))
        user_cls.exists.return_value = True
        media_cls = es.enter_context(patch(MOD + "RethinkMedia"))
        media_cls.exists.return_value = True
        media_cls.return_value.status = MediaStatusEnum.downloaded.value
        virt = es.enter_context(
            patch(
                MOD + "XmlSectionsProcessed.get_virt_install",
                return_value={"id": "w10"},
            )
        )
        es.enter_context(patch(MOD + "Quotas.desktop_create", return_value=None))
        es.enter_context(
            patch(MOD + "Helpers.check_user_duplicated_domain_name", return_value=None)
        )
        yield {"user_cls": user_cls, "media_cls": media_cls, "virt": virt}


class TestCreateFromMediaGuards:
    def test_unknown_user_404(self, media_env):
        media_env["user_cls"].exists.return_value = False
        with pytest.raises(Error) as exc:
            DesktopService.create_from_media("ghost", _media_data())
        assert exc.value.status_code == 404
        assert exc.value.error["description_code"] == "not_found"

    def test_unknown_media_404(self, media_env):
        media_env["media_cls"].exists.return_value = False
        with pytest.raises(Error) as exc:
            DesktopService.create_from_media("u1", _media_data())
        assert exc.value.status_code == 404
        assert exc.value.error["description_code"] == "not_found"

    def test_unknown_os_template_400(self, media_env):
        media_env["virt"].return_value = None
        with pytest.raises(Error) as exc:
            DesktopService.create_from_media("u1", _media_data())
        assert exc.value.status_code == 400
        assert exc.value.error["description_code"] == "os_template_not_found"

    def test_no_viewer_selected_400(self, media_env):
        with pytest.raises(Error) as exc:
            DesktopService.create_from_media("u1", _media_data(guest_properties=None))
        assert exc.value.status_code == 400
        assert exc.value.error["description_code"] == "one_viewer_minimum"

    def test_media_not_downloaded_400(self, media_env):
        media_env["media_cls"].return_value.status = "DownloadStarting"
        with pytest.raises(Error) as exc:
            DesktopService.create_from_media("u1", _media_data())
        assert exc.value.status_code == 400
        assert exc.value.error["description_code"] == "media_not_downloaded"


class TestCreateNonpersistentGuards:
    def test_unknown_user_404(self):
        with patch(MOD + "RethinkUser.exists", return_value=False):
            with pytest.raises(Error) as exc:
                DesktopService.create_nonpersistent_desktop(PAYLOAD, "t1")
        assert exc.value.status_code == 404
        assert exc.value.error["description_code"] == "not_found"

    def test_template_not_allowed_403(self):
        with ExitStack() as es:
            es.enter_context(patch(MOD + "RethinkUser.exists", return_value=True))
            es.enter_context(patch(MOD + "Quotas.volatile_create", return_value=None))
            es.enter_context(patch(MOD + "Quotas.desktop_start", return_value=None))
            es.enter_context(
                patch(MOD + "CommonTemplates.get_template", return_value={"id": "t1"})
            )
            es.enter_context(patch(MOD + "Alloweds.is_allowed", return_value=False))
            with pytest.raises(Error) as exc:
                DesktopService.create_nonpersistent_desktop(PAYLOAD, "t1")
        assert exc.value.status_code == 403
        assert exc.value.error["description_code"] == "template_not_allowed"
