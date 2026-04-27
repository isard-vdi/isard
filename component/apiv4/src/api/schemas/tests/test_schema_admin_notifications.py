# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_notifications.py``.

Covers template CRUD requests/responses, notification CRUD,
notification-data containers, and the AdminUserDisplaysResponse.
"""

import pytest
from api.schemas.admin_notifications import (
    AdminUserDisplaysResponse,
    NotificationActionsResponse,
    NotificationCreateRequest,
    NotificationDataListResponse,
    NotificationDeleteRequest,
    NotificationDetailResponse,
    NotificationGroupedDataResponse,
    NotificationListResponse,
    NotificationResponse,
    NotificationStatusesResponse,
    NotificationUpdateRequest,
    TemplateCreateRequest,
    TemplateListResponse,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    TemplateResponse,
    TemplateUpdateRequest,
)
from pydantic import ValidationError

# ══════════════════════════════════════════════════════════════════════════
#  Template requests/responses
# ══════════════════════════════════════════════════════════════════════════


class TestTemplateCreateRequest:
    _required = {
        "language": "en",
        "title": "Welcome",
        "body": "<p>hi</p>",
        "footer": "",
    }

    def test_accepts_required(self):
        t = TemplateCreateRequest(**self._required)
        assert t.language == "en"
        # Optional fields default to None.
        assert t.name is None
        assert t.kind is None

    @pytest.mark.parametrize("missing", ["language", "title", "body", "footer"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            TemplateCreateRequest(**payload)

    def test_empty_footer_is_valid(self):
        """footer is required (Field) but empty string passes; pin so a
        future min-length=1 doesn't sneak in."""
        t = TemplateCreateRequest(**{**self._required, "footer": ""})
        assert t.footer == ""


class TestTemplateUpdateRequest:
    """Same shape as Create except `kind` is dropped — note this gap
    so a future schema sync doesn't silently re-add it."""

    _required = {
        "language": "en",
        "title": "Updated",
        "body": "<p>x</p>",
        "footer": "",
    }

    def test_accepts_required(self):
        t = TemplateUpdateRequest(**self._required)
        assert t.title == "Updated"

    def test_no_kind_field(self):
        """If `kind` is sent, it's silently dropped (default extra=ignore).
        The Create schema accepts it; Update does NOT. Pin the asymmetry."""
        t = TemplateUpdateRequest(**self._required, kind="custom")
        dump = t.model_dump()
        assert "kind" not in dump


class TestTemplatePreviewRequest:
    def test_event_required(self):
        t = TemplatePreviewRequest(event="shutdown")
        assert t.event == "shutdown"
        assert t.user_id is None
        # data defaults to {} not None — pin the empty-dict default.
        assert t.data == {}

    def test_missing_event_rejected(self):
        with pytest.raises(ValidationError):
            TemplatePreviewRequest()

    def test_data_default_is_empty_dict(self):
        """Default {} vs None matters: the route forwards data verbatim to
        the service. None would crash a `data.get(...)` call."""
        t = TemplatePreviewRequest(event="x")
        # Each instance must get its own dict — Pydantic v2 handles this
        # correctly (no mutable-default trap), pin it.
        t.data["mut"] = "test"
        t2 = TemplatePreviewRequest(event="y")
        assert "mut" not in t2.data


class TestTemplateResponse:
    def test_all_fields_optional(self):
        """Every field on TemplateResponse is Optional. Pin so a route
        that returns a sparsely-populated row doesn't 500."""
        t = TemplateResponse()
        assert t.id is None

    def test_accepts_full(self):
        t = TemplateResponse(
            id="t-1",
            name="Welcome",
            description="x",
            kind="custom",
            default="en",
            lang={"en": {"title": "Hi"}},
            system={"flag": True},
        )
        assert t.lang["en"]["title"] == "Hi"


class TestTemplateListResponse:
    def test_templates_required(self):
        with pytest.raises(ValidationError):
            TemplateListResponse()

    def test_accepts_empty_list(self):
        t = TemplateListResponse(templates=[])
        assert t.templates == []

    def test_accepts_arbitrary_dicts(self):
        """templates: List[Dict[str, Any]] — pin so a typed sub-model
        change is noticed."""
        t = TemplateListResponse(templates=[{"id": "t-1"}, {"any": "shape"}])
        assert len(t.templates) == 2


class TestTemplatePreviewResponse:
    def test_all_fields_optional(self):
        t = TemplatePreviewResponse()
        assert t.title is None
        assert t.channels is None

    def test_accepts_channels_list(self):
        t = TemplatePreviewResponse(
            title="Rendered", body="<p>x</p>", footer="", channels=["email", "modal"]
        )
        assert t.channels == ["email", "modal"]


# ══════════════════════════════════════════════════════════════════════════
#  Notification requests/responses
# ══════════════════════════════════════════════════════════════════════════


class TestNotificationCreateRequest:
    """Every field optional — pin so the create endpoint's tolerant
    contract doesn't accidentally become strict."""

    def test_accepts_empty(self):
        n = NotificationCreateRequest()
        assert n.name is None
        assert n.enabled is None

    def test_allowed_default_factory(self):
        """`allowed: Allowed = Field(default_factory=Allowed)` — pin that
        each instance gets its own Allowed object (not a shared singleton).
        Without default_factory, mutating one instance's `allowed.roles`
        would bleed into the next."""
        a = NotificationCreateRequest()
        b = NotificationCreateRequest()
        assert a.allowed is not b.allowed

    def test_accepts_full(self):
        n = NotificationCreateRequest(
            name="myn",
            description="x",
            trigger="login",
            display=["modal"],
            template_id="t-1",
            action_id="a-1",
            item_type="users",
            order=1,
            enabled=True,
            force_accept=False,
            ignore_after="2026-12-31",
            keep_time=86400,
        )
        assert n.trigger == "login"
        assert n.display == ["modal"]


class TestNotificationUpdateRequest:
    """Same shape, all Optional. `allowed` here is Optional[Allowed] —
    None means "don't touch" (vs Create's default factory)."""

    def test_allowed_optional_default_none(self):
        n = NotificationUpdateRequest()
        assert n.allowed is None

    def test_accepts_partial(self):
        n = NotificationUpdateRequest(name="renamed")
        assert n.name == "renamed"


class TestNotificationDeleteRequest:
    def test_default_delete_logs_true(self):
        """Pin the default — the route relies on it for the "no body"
        case."""
        n = NotificationDeleteRequest()
        assert n.delete_logs is True

    def test_accepts_explicit_false(self):
        n = NotificationDeleteRequest(delete_logs=False)
        assert n.delete_logs is False


class TestNotificationResponse:
    def test_id_optional(self):
        # The create route returns just {"id": "..."}, but id is declared
        # Optional. Pin so a future change that makes it required is
        # noticed.
        assert NotificationResponse().id is None
        assert NotificationResponse(id="n-1").id == "n-1"


class TestNotificationDetailResponse:
    def test_root_model_passthrough(self):
        """RootModel[Dict[str, Any]] — the response IS the dict. Pin so
        a future move to a typed body is noticed (and the route's mock
        DB rows update accordingly)."""
        row = {"id": "n-1", "name": "x", "ignore_after": None}
        n = NotificationDetailResponse(row)
        assert n.model_dump(mode="json") == row


class TestNotificationListResponse:
    def test_notifications_required(self):
        with pytest.raises(ValidationError):
            NotificationListResponse()

    def test_accepts_empty(self):
        assert NotificationListResponse(notifications=[]).notifications == []


class TestNotificationActionsResponse:
    def test_actions_required(self):
        with pytest.raises(ValidationError):
            NotificationActionsResponse()

    def test_accepts_arbitrary_dicts(self):
        r = NotificationActionsResponse(actions=[{"id": "a1", "label": "ack"}])
        assert r.actions[0]["id"] == "a1"


# ══════════════════════════════════════════════════════════════════════════
#  Notification-data responses
# ══════════════════════════════════════════════════════════════════════════


class TestNotificationDataListResponse:
    def test_data_required(self):
        with pytest.raises(ValidationError):
            NotificationDataListResponse()

    def test_round_trip(self):
        r = NotificationDataListResponse(data=[{"id": "nd-1"}])
        assert NotificationDataListResponse(**r.model_dump()) == r


class TestNotificationStatusesResponse:
    def test_statuses_required(self):
        with pytest.raises(ValidationError):
            NotificationStatusesResponse()

    def test_string_list(self):
        r = NotificationStatusesResponse(statuses=["pending", "ack"])
        assert r.statuses == ["pending", "ack"]


class TestNotificationGroupedDataResponse:
    def test_data_required(self):
        with pytest.raises(ValidationError):
            NotificationGroupedDataResponse()


class TestAdminUserDisplaysResponse:
    def test_displays_required(self):
        with pytest.raises(ValidationError):
            AdminUserDisplaysResponse()

    def test_string_list(self):
        r = AdminUserDisplaysResponse(displays=["modal", "banner"])
        assert r.displays == ["modal", "banner"]
