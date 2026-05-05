#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin ``Logging.logs_domain_stop_api`` parity with apiv3.

Apiv3 ``main:api/src/api/libv2/api_logging.py:287-339`` accepted
``user_request`` and recorded ``stopping_ip`` /
``stopping_agent_browser`` / ``stopping_agent_platform`` so admins
could trace which session ended which desktop. The apiv4 port at
``component/_common/src/isardvdi_common/helpers/logging.py:306-341``
silently dropped the parameter, so every ``logs_desktops`` row written
after the cutover lost the session-forensics fields.

These tests pin that the parameter is now accepted and that the rdb
update carries the IP / user-agent fields when a request is provided
(and only the apiv3 base set when it is not).
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def logging_module(monkeypatch):
    from isardvdi_common.helpers import logging as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.Logging, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(mod.Logging),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    # Capture the update payload by intercepting ``r.table(...).get(
    # ...).update(...)``. The chain is opaque so we expose the dict
    # passed to ``.update()`` via a captured side-effect.
    captured = {}

    update_mock = MagicMock(name="update")
    update_mock.return_value = MagicMock(
        run=MagicMock(return_value={"replaced": 1}),
    )

    def fake_update(payload, *args, **kwargs):
        captured["payload"] = payload
        captured["durability"] = kwargs.get("durability")
        return update_mock.return_value

    chained = MagicMock(name="get-chain")
    chained.update = fake_update
    table = MagicMock(name="r.table")
    table.return_value.get.return_value = chained
    monkeypatch.setattr(mod.r, "table", table)

    # Stub Caches.get_document so the helper sees a desktop row with a
    # ``start_logs_id``.
    monkeypatch.setattr(
        mod.Caches,
        "get_document",
        classmethod(
            lambda cls, table, key, fields: {
                "start_logs_id": "log-1",
                "tag": None,
                "user": "user-1",
            }
        ),
    )
    # action_owner returns the agent_by string used for ``stopping_by``.
    monkeypatch.setattr(
        mod.Logging,
        "action_owner",
        classmethod(lambda cls, action_user, owner_user: "owner"),
    )

    yield mod, captured


class _StubStarletteRequest:
    """Minimal Starlette-shaped request for ``parse_user_request``."""

    def __init__(self, ip, user_agent):
        self.headers = {
            "x-forwarded-for": ip,
            "user-agent": user_agent,
        }
        self.client = MagicMock(host="127.0.0.1")


class TestLogsDomainStopApiParity:
    def test_no_user_request_writes_null_telemetry(self, logging_module):
        mod, captured = logging_module
        mod.Logging.logs_domain_stop_api("desk-1", action_user="user-1")
        payload = captured["payload"]
        # Base apiv3 fields always present.
        assert "stopping_time" in payload
        assert payload["stopping_by"] == "owner"
        assert payload["stopping_user"] == "user-1"
        # IP / user-agent keys exist (parse_user_request returns a
        # default dict with None values when no request is provided)
        # but they are explicitly nulled — better than the pre-fix path
        # where they were absent entirely.
        assert payload["stopping_ip"] is None
        assert payload["stopping_agent_browser"] is None
        assert payload["stopping_agent_platform"] is None
        assert captured["durability"] == "soft"

    def test_with_user_request_writes_stopping_ip(self, logging_module):
        mod, captured = logging_module
        request = _StubStarletteRequest(ip="203.0.113.7", user_agent="Mozilla/5.0")
        mod.Logging.logs_domain_stop_api(
            "desk-1", action_user="user-1", user_request=request
        )
        payload = captured["payload"]
        # IP should propagate from x-forwarded-for via parse_user_request.
        assert payload["stopping_ip"] == "203.0.113.7"
        # user-agent fields are populated (browser/platform values depend
        # on whether the user-agents library is installed; assert keys
        # are present, not specific values).
        assert "stopping_agent_browser" in payload
        assert "stopping_agent_platform" in payload

    def test_with_user_request_keeps_base_fields(self, logging_module):
        mod, captured = logging_module
        request = _StubStarletteRequest(ip="203.0.113.7", user_agent="Mozilla/5.0")
        mod.Logging.logs_domain_stop_api(
            "desk-1", action_user="user-1", user_request=request
        )
        payload = captured["payload"]
        assert "stopping_time" in payload
        assert payload["stopping_by"] == "owner"
        assert payload["stopping_user"] == "user-1"


class TestDirectviewerEventDedup:
    """Apiv3 ``_directviewer_event_cache`` (``TTLCache(maxsize=1000,
    ttl=60)``) skipped duplicate ``(domain_id, viewer_type, ip)``
    events within a 60s window — the apiv4 port silently dropped it,
    so reconnect storms (mobile network flap, NAT timeout, browser
    visibility toggle) appended hundreds of duplicate rows to the
    ``logs_desktops.events`` array per session.

    Pin: 5 calls with the same key within 60s ⇒ exactly 1 underlying
    ``_logs_domain_event`` invocation."""

    @pytest.mark.asyncio
    async def test_repeated_calls_dedupe_within_60s(self, monkeypatch):
        from isardvdi_common.helpers import logging as mod

        mod._directviewer_event_cache.clear()

        invocations = {"count": 0}

        async def fake_logs_domain_event(
            start_logs_id, event, action_user=None, viewer_type="", user_request=None
        ):
            invocations["count"] += 1

        monkeypatch.setattr(
            mod.Logging,
            "_logs_domain_event",
            classmethod(lambda cls, *a, **kw: fake_logs_domain_event(*a, **kw)),
        )
        monkeypatch.setattr(
            mod.Caches,
            "get_document",
            classmethod(lambda cls, *a, **kw: "log-1"),
        )

        request = _StubStarletteRequest(ip="203.0.113.7", user_agent="Mozilla/5.0")

        for _ in range(5):
            await mod.Logging._logs_domain_event_directviewer(
                "desk-1",
                action_user="user-1",
                viewer_type="spice",
                user_request=request,
            )

        assert invocations["count"] == 1

    @pytest.mark.asyncio
    async def test_different_keys_do_not_dedupe(self, monkeypatch):
        """The cache key is ``(domain_id, viewer_type, ip)``. A
        different ip MUST trigger a fresh underlying call."""
        from isardvdi_common.helpers import logging as mod

        mod._directviewer_event_cache.clear()

        invocations = {"count": 0}

        async def fake_logs_domain_event(*a, **kw):
            invocations["count"] += 1

        monkeypatch.setattr(
            mod.Logging,
            "_logs_domain_event",
            classmethod(lambda cls, *a, **kw: fake_logs_domain_event(*a, **kw)),
        )
        monkeypatch.setattr(
            mod.Caches,
            "get_document",
            classmethod(lambda cls, *a, **kw: "log-1"),
        )

        # Same domain + viewer_type, different IP each time → 3 calls.
        for ip in ("203.0.113.7", "203.0.113.8", "203.0.113.9"):
            await mod.Logging._logs_domain_event_directviewer(
                "desk-1",
                action_user="user-1",
                viewer_type="spice",
                user_request=_StubStarletteRequest(ip=ip, user_agent="Mozilla/5.0"),
            )

        assert invocations["count"] == 3
