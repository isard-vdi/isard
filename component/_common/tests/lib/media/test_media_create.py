# SPDX-License-Identifier: AGPL-3.0-or-later

"""``MediaProcessed.create`` builds and inserts the media row, then enqueues the
download. The model layer is stubbed so nothing touches RethinkDB."""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.media import media as mod

PAYLOAD = {
    "user_id": "u1",
    "category_id": "default",
    "group_id": "default-default",
    "provider": "local",
}


def _create(**kw):
    args = {
        "payload": PAYLOAD,
        "name": "my iso",
        "description": "",
        "url": "https://example.com/x.iso",
        "kind": "iso",
        "hypervisors_pools": None,
        "allowed": {
            "roles": False,
            "categories": False,
            "groups": False,
            "users": False,
        },
        "insecure_ssl": True,
    }
    args.update(kw)
    return mod.MediaProcessed.create(**args)


@pytest.fixture
def stubs(monkeypatch):
    user = MagicMock(name="User")
    user.get.return_value = {"uid": "admin", "username": "admin"}
    media = MagicMock(name="Media")
    media.resolve_download_path.return_value = (None, "/isard/media/x.iso")
    helpers = MagicMock(name="Helpers")
    monkeypatch.setattr(mod, "User", user)
    monkeypatch.setattr(mod, "Media", media)
    monkeypatch.setattr(mod, "Helpers", helpers)
    return user, media, helpers


def test_inserts_row_and_enqueues_download(stubs):
    _user, media, helpers = stubs

    media_id = _create()

    helpers.check_duplicate.assert_called_once_with(
        item_table="media", item_name="my iso", user="u1", ignore_deleted=True
    )
    row = media.insert_document.call_args.args[0]
    assert row["id"] == media_id
    assert row["status"] == "DownloadStarting"
    assert row["url-web"] == "https://example.com/x.iso"
    assert row["path"] == "default/default-default/local/admin-admin/my_iso"
    assert row["path_downloaded"] == "/isard/media/x.iso"
    assert row["hypervisors_pools"] == ["default"]
    media.build_from.assert_called_once_with(row)
    media.build_from.return_value.enqueue_download_chain.assert_called_once_with(
        user_id="u1", url="https://example.com/x.iso", insecure_ssl=True
    )


def test_unknown_user_not_found_inserts_nothing(stubs):
    user, media, _helpers = stubs
    user.get.return_value = None

    with pytest.raises(Error) as exc:
        _create()

    assert exc.value.error["error"] == "not_found"
    media.insert_document.assert_not_called()
