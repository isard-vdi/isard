# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/notifications.py``."""

import pytest
from api.schemas.notifications import (
    NotificationFlatItem,
    NotificationItem,
    NotificationResponse,
    NotificationsUserDisplaysTriggerResponse,
    NotificationsUserTriggerDisplayFlatResponse,
    NotificationsUserTriggerDisplayResponse,
    NotificationTemplate,
    NotificationUserData,
    StatusBarNotificationResponse,
)
from pydantic import ValidationError


class TestNotificationResponse:
    """Empty-body sentinel response — pin so a future field addition
    is intentional and updates the route mock data."""

    def test_accepts_empty(self):
        r = NotificationResponse()
        assert r.model_dump() == {}


class TestStatusBarNotificationResponse:
    def test_all_optional(self):
        r = StatusBarNotificationResponse()
        assert r.text is None
        assert r.level is None
        assert r.migration_config is None

    def test_full(self):
        r = StatusBarNotificationResponse(
            text="Migration in progress",
            level="warning",
            migration_config={"target": "v4"},
        )
        assert r.level == "warning"


class TestNotificationItem:
    def test_id_required(self):
        with pytest.raises(ValidationError):
            NotificationItem()

    def test_minimal(self):
        n = NotificationItem(id="n-1")
        assert n.id == "n-1"
        assert n.vars is None


class TestNotificationTemplate:
    @pytest.mark.parametrize("missing", ["body", "footer", "title"])
    def test_all_required(self, missing):
        payload = {"body": "b", "footer": "f", "title": "t"}
        del payload[missing]
        with pytest.raises(ValidationError):
            NotificationTemplate(**payload)


class TestNotificationUserData:
    _required = {
        "display": ["modal"],
        "action_id": "a-1",
        "template_id": "t-1",
        "force_accept": False,
        "notifications": [],
    }

    def test_accepts_required(self):
        n = NotificationUserData(**self._required)
        assert n.display == ["modal"]

    @pytest.mark.parametrize(
        "missing",
        ["display", "action_id", "template_id", "force_accept", "notifications"],
    )
    def test_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            NotificationUserData(**payload)

    def test_template_optional(self):
        n = NotificationUserData(**self._required)
        assert n.template is None


class TestNotificationsUserTriggerDisplayResponse:
    def test_default_empty_dict(self):
        """notifications defaults to {} — pin the empty-state."""
        r = NotificationsUserTriggerDisplayResponse()
        assert r.notifications == {}


class TestNotificationFlatItem:
    def test_id_required(self):
        with pytest.raises(ValidationError):
            NotificationFlatItem()

    def test_defaults(self):
        n = NotificationFlatItem(id="n-1")
        assert n.title == ""
        assert n.body == ""
        assert n.footer is None
        assert n.force_accept is False


class TestNotificationsUserTriggerDisplayFlatResponse:
    def test_default_empty_list(self):
        r = NotificationsUserTriggerDisplayFlatResponse()
        assert r.notifications == []


class TestNotificationsUserDisplaysTriggerResponse:
    def test_default_empty_list(self):
        r = NotificationsUserDisplaysTriggerResponse()
        assert r.displays == []
