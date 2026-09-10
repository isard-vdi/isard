#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin the request-provenance columns of ``logs_users`` / ``logs_desktops``.

Apiv3 ``main-bkp-22-07-26T00-20:component/_common/src/tokens.py:110-122``
read the client IP and User-Agent off the Flask request and handed them to
``LogsUsers``, which persisted ``request_ip`` /
``request_agent_browser`` / ``request_agent_platform``. The apiv4 port
narrowed ``LogsUsers.__init__`` to ``(payload)`` and dropped the three
columns from ``insert()`` — so the admin *Users log* datatable
(``webapp/static/admin/js/logs_users.js:253``) has shown an empty IP
column for every session since the cutover.

These tests pin: the parser (browser families, non-browser clients,
``user-agents``-absent fallback), the identity extraction from both
request flavours, the columns being written again, and the
``source=`` sentinel for engine-initiated desktop starts.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.logging import Logging


class _StubStarletteRequest:
    def __init__(self, headers=None, client_host="10.0.0.9"):
        self.headers = headers or {}
        self.client = MagicMock(host=client_host)


class _StubFlaskRequest:
    """Flask/Werkzeug shape: headers + ``remote_addr``, no ``client``."""

    def __init__(self, headers=None, remote_addr="10.0.0.9"):
        self.headers = headers or {}
        self.remote_addr = remote_addr


class TestParseUserAgent:
    def test_empty_user_agent_is_all_none(self):
        assert Logging._parse_user_agent("") == {
            "browser": None,
            "platform": None,
            "version": None,
        }
        assert Logging._parse_user_agent(None)["browser"] is None

    @pytest.mark.parametrize(
        "user_agent",
        [
            "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/128.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        ],
    )
    def test_real_browsers_report_browser_platform_and_version(self, user_agent):
        parsed = Logging._parse_user_agent(user_agent)
        assert parsed["browser"]
        assert parsed["platform"]
        assert parsed["version"]

    @pytest.mark.parametrize(
        "user_agent",
        ["isardvdi-cli/1.4.2", "isardvdi-sdk-go/0.1", "isardvdi-guac"],
    )
    def test_unrecognised_clients_fall_back_to_the_raw_token(self, user_agent):
        # The whole point of the fix: these used to land as NULL, so an
        # admin could not tell an API client from a missing row. No parser
        # knows the isardvdi user agents, so the raw token is what surfaces.
        assert Logging._parse_user_agent(user_agent)["browser"] == user_agent

    @pytest.mark.parametrize(
        ("user_agent", "browser"),
        [("curl/8.5.0", "curl"), ("python-requests/2.32.4", "Python Requests")],
    )
    def test_known_non_browser_clients_get_their_family(self, user_agent, browser):
        assert Logging._parse_user_agent(user_agent)["browser"] == browser

    def test_unknown_client_first_token_is_truncated(self):
        parsed = Logging._parse_user_agent("x" * 400)
        assert len(parsed["browser"]) == 100

    def test_falls_back_to_regex_without_user_agents_library(self, monkeypatch):
        # `user-agents` is declared only by apiv4; every other consumer of
        # this helper (engine, webapp, scheduler, notifier) must still get
        # a browser out of a browser UA.
        import builtins

        real_import = builtins.__import__

        def _no_user_agents(name, *args, **kwargs):
            if name == "user_agents":
                raise ImportError("simulated: user-agents not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_user_agents)
        parsed = Logging._parse_user_agent(
            "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/128.0"
        )
        assert parsed == {"browser": "firefox", "platform": "linux", "version": "128.0"}


class TestRequestClientIp:
    def test_starlette_prefers_first_forwarded_hop(self):
        request = _StubStarletteRequest(
            headers={"x-forwarded-for": "203.0.113.7, 172.31.255.1"}
        )
        assert Logging.request_client_ip(request) == "203.0.113.7"

    def test_starlette_falls_back_to_peer_address(self):
        assert Logging.request_client_ip(_StubStarletteRequest()) == "10.0.0.9"

    def test_flask_request_is_supported(self):
        request = _StubFlaskRequest(headers={"X-Forwarded-For": "203.0.113.8"})
        assert Logging.request_client_ip(request) == "203.0.113.8"
        assert Logging.request_client_ip(_StubFlaskRequest()) == "10.0.0.9"

    def test_no_request_is_none(self):
        assert Logging.request_client_ip(None) is None


class TestParseUserRequestSource:
    def test_engine_source_labels_the_row(self):
        # Engine-initiated starts have no HTTP request; without the label
        # the audit row is indistinguishable from a lost one.
        parsed = Logging.parse_user_request(source="isard-engine")
        assert parsed["request_ip"] == "isard-engine"
        assert parsed["request_agent_browser"] is None

    def test_no_request_and_no_source_stays_null(self):
        assert Logging.parse_user_request()["request_ip"] is None

    def test_request_wins_over_source(self):
        request = _StubStarletteRequest(
            headers={"x-forwarded-for": "203.0.113.7", "user-agent": "curl/8.5.0"}
        )
        parsed = Logging.parse_user_request(request, source="isard-engine")
        assert parsed["request_ip"] == "203.0.113.7"
        assert parsed["request_agent_browser"] == "curl"


class TestLogsUsersProvenance:
    @staticmethod
    def _insert_payload(monkeypatch, request_ip, user_agent):
        """Run ``LogsUsers.insert`` with the DB stubbed, return the row."""
        from isardvdi_common.helpers import api_logs_users as mod

        captured = {}

        # ``__init__`` opens a real RethinkDB connection, so build the
        # instance without it and set only what ``insert`` reads.
        instance = object.__new__(mod.LogsUsers)
        agent = Logging._parse_user_agent(user_agent)
        instance.request_ip = request_ip
        instance.request_browser = agent["browser"]
        instance.request_platform = agent["platform"]
        instance.request_version = agent["version"]
        instance.conn = MagicMock(name="conn")
        monkeypatch.setattr(
            mod.LogsUsers,
            "get_user",
            lambda self, user_id: {
                "name": "user",
                "role": "user",
                "category": "cat",
                "category_name": "Cat",
                "group": "grp",
                "group_name": "Grp",
            },
        )

        def _fake_table(name):
            table = MagicMock(name=f"table:{name}")
            if name == "logs_users":
                table.insert = (
                    lambda logs: captured.__setitem__("logs", logs) or MagicMock()
                )
            return table

        monkeypatch.setattr(mod.r, "table", _fake_table)
        instance.insert({"data": {"user_id": "u1"}, "exp": 1})
        return captured["logs"]

    def test_insert_writes_ip_and_agent_columns(self, monkeypatch):
        logs = self._insert_payload(
            monkeypatch,
            "203.0.113.7",
            "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/128.0",
        )
        assert logs["request_ip"] == "203.0.113.7"
        assert logs["request_agent_browser"]
        assert logs["request_agent_platform"]
        assert logs["request_agent_version"]

    def test_insert_writes_nulls_without_a_request(self, monkeypatch):
        logs = self._insert_payload(monkeypatch, None, None)
        assert logs["request_ip"] is None
        assert logs["request_agent_browser"] is None


class TestTokenRequestIdentity:
    def test_identity_from_starlette_request(self):
        from isardvdi_common.helpers.token import Token

        request = _StubStarletteRequest(
            headers={"x-forwarded-for": "203.0.113.7", "user-agent": "curl/8.5.0"}
        )
        assert Token.request_identity(request) == ("203.0.113.7", "curl/8.5.0")

    def test_identity_without_request(self):
        from isardvdi_common.helpers.token import Token

        assert Token.request_identity() == (None, None)

    def test_broken_request_never_raises(self):
        from isardvdi_common.helpers.token import Token

        class _Exploding:
            @property
            def headers(self):
                raise RuntimeError("working outside of request context")

        assert Token.request_identity(_Exploding()) == (None, None)
