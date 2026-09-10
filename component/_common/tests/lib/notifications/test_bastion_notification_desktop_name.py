#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Desktop name in the start-desktop bastion notification.

Regression guard for ``NotificationsCompute.get_bastion_notification``: the
notification data row is created once per user and reused on every later
start, so rendering the body from the stored vars showed the name of the
desktop the user was first notified about, not the one just started.

Pins:
* first notification renders (and stores) the started desktop name,
* a later start renders the new desktop name and re-points the stored row.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.lib.notifications import compute as mod

NOTIFICATION = {"id": "n-1", "ignore_after": None}
PAYLOAD = {"user_id": "u-1"}
TEMPLATE = {
    "default": "en",
    "lang": {
        "en": {"title": "Bastion", "body": "Desktop {desktop_name}", "footer": ""}
    },
}


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setattr(
        mod.Helpers, "can_use_bastion", staticmethod(lambda payload: True)
    )
    monkeypatch.setattr(
        mod.UsersProcessed,
        "get_user_last_started_desktop_log",
        classmethod(
            lambda cls, user_id: {"desktop_id": "d-2", "desktop_name": "Second"}
        ),
    )
    monkeypatch.setattr(
        mod.Targets,
        "get_domain_target",
        classmethod(lambda cls, desktop_id: {"ssh": {"enabled": True}}),
    )
    monkeypatch.setattr(
        mod.NotificationTemplatesProcessed,
        "get_notification_template_by_kind",
        classmethod(lambda cls, kind: TEMPLATE),
    )
    add = MagicMock(name="add_notification_data")
    update = MagicMock(name="update_notification_data")
    monkeypatch.setattr(
        mod.NotificationsDataProcessed, "add_notification_data", staticmethod(add)
    )
    monkeypatch.setattr(
        mod.NotificationsDataProcessed, "update_notification_data", staticmethod(update)
    )
    return {"add": add, "update": update}


def _set_existing(monkeypatch, existing):
    monkeypatch.setattr(
        mod.NotificationsDataProcessed,
        "get_user_notifications_data",
        staticmethod(lambda *args, **kwargs: existing),
    )


def test_first_notification_uses_started_desktop(stub, monkeypatch):
    _set_existing(monkeypatch, [])

    notification = mod.NotificationsCompute.get_bastion_notification(
        PAYLOAD, NOTIFICATION, "en"
    )

    assert notification["body"] == "Desktop Second"
    stored = stub["add"].call_args[0][0]
    assert stored["item_id"] == "d-2"
    assert stored["vars"] == {"desktop_name": "Second"}


def test_later_notification_replaces_previous_desktop_name(stub, monkeypatch):
    _set_existing(
        monkeypatch,
        [{"id": "nd-1", "item_id": "d-1", "vars": {"desktop_name": "First"}}],
    )

    notification = mod.NotificationsCompute.get_bastion_notification(
        PAYLOAD, NOTIFICATION, "en"
    )

    assert notification["body"] == "Desktop Second"
    updated = stub["update"].call_args[0][0]
    assert updated["id"] == "nd-1"
    assert updated["item_id"] == "d-2"
    assert updated["vars"] == {"desktop_name": "Second"}
