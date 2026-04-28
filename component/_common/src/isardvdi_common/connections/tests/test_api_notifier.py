# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ``isardvdi_common.connections.api_notifier.notify_backup_failure``.

The function emails active admins when a backup record finishes with
``CRITICAL`` or ``ERROR`` status. Best-effort by design: every failure
inside it (no admins, generated client raises, DB unreachable) must be
swallowed so the backup insert that triggered it still completes.
"""

import contextlib
import sys
import types
from unittest.mock import MagicMock

import pytest

# ══════════════════════════════════════════════════════════════════════════
#  Module-import fixture
# ══════════════════════════════════════════════════════════════════════════
#
#  ``api_notifier`` does its imports of ``isardvdi_notifier_client`` and the
#  ``rethinkdb`` driver lazily inside ``notify_backup_failure`` so services
#  that ship the common package but never call the notifier don't pay the
#  import cost. We mirror that lazy boundary in the tests by stubbing the
#  modules in ``sys.modules`` *before* the function looks them up.


@pytest.fixture
def stub_notifier_client(monkeypatch):
    """Inject fake ``isardvdi_notifier_client`` modules so the lazy
    imports inside ``notify_backup_failure`` succeed without the real
    package installed in the test env.

    Returns the ``post_notifier_mail.sync_detailed`` MagicMock so each
    test can assert how it was called.
    """
    api_mail_mod = types.ModuleType("isardvdi_notifier_client.api.mail")
    api_mail_mod.post_notifier_mail = types.SimpleNamespace(
        sync_detailed=MagicMock(return_value=MagicMock(parsed=None))
    )
    api_mod = types.ModuleType("isardvdi_notifier_client.api")
    models_mod = types.ModuleType("isardvdi_notifier_client.models")
    models_mod.NotifyMailRequest = lambda **kw: kw
    root_mod = types.ModuleType("isardvdi_notifier_client")
    auth_mod = types.ModuleType("isardvdi_notifier_client_auth")
    auth_mod.build_client = MagicMock(return_value=contextlib.nullcontext(MagicMock()))
    auth_mod.raise_for_status = MagicMock(return_value=None)
    monkeypatch.setitem(sys.modules, "isardvdi_notifier_client", root_mod)
    monkeypatch.setitem(sys.modules, "isardvdi_notifier_client.api", api_mod)
    monkeypatch.setitem(sys.modules, "isardvdi_notifier_client.api.mail", api_mail_mod)
    monkeypatch.setitem(sys.modules, "isardvdi_notifier_client.models", models_mod)
    monkeypatch.setitem(sys.modules, "isardvdi_notifier_client_auth", auth_mod)
    return api_mail_mod.post_notifier_mail.sync_detailed, auth_mod


@pytest.fixture
def stub_rdb(monkeypatch):
    """Provide an ``RethinkSharedConnection._rdb_context`` no-op and a
    rigged ``r.table(...).get_all(...)...run()`` chain returning the
    admin list under test.

    Returns a setter the test calls with the desired admin list.
    """
    from isardvdi_common.connections.rethink_connection_factory import (
        RethinkSharedConnection,
    )

    monkeypatch.setattr(
        RethinkSharedConnection,
        "_rdb_context",
        contextlib.nullcontext,
    )
    monkeypatch.setattr(
        RethinkSharedConnection,
        "_rdb_connection",
        MagicMock(),
    )

    state = {"admins": [], "raise": None}

    def fake_table(_name):
        chain = MagicMock()
        if state["raise"] is not None:
            chain.get_all.return_value.filter.return_value.pluck.return_value.run.side_effect = state[
                "raise"
            ]
        else:
            chain.get_all.return_value.filter.return_value.pluck.return_value.run.return_value = state[
                "admins"
            ]
        return chain

    from rethinkdb import r

    monkeypatch.setattr(r, "table", fake_table)

    def setter(*, admins=(), raises=None):
        state["admins"] = list(admins)
        state["raise"] = raises

    return setter


# ══════════════════════════════════════════════════════════════════════════
#  Tests
# ══════════════════════════════════════════════════════════════════════════


class TestStatusFilter:
    """Only ``CRITICAL`` / ``ERROR`` trigger an email — every other
    status is a no-op including the absence of the field. We pin this
    so a future ``WARNING`` toggle is an explicit decision."""

    def test_skips_when_status_ok(self, stub_notifier_client, stub_rdb):
        sync_detailed, _auth = stub_notifier_client
        from isardvdi_common.connections import api_notifier

        api_notifier.notify_backup_failure({"status": "OK"})
        sync_detailed.assert_not_called()

    def test_skips_when_status_missing(self, stub_notifier_client, stub_rdb):
        sync_detailed, _auth = stub_notifier_client
        from isardvdi_common.connections import api_notifier

        api_notifier.notify_backup_failure({})
        sync_detailed.assert_not_called()

    def test_skips_warning(self, stub_notifier_client, stub_rdb):
        sync_detailed, _auth = stub_notifier_client
        from isardvdi_common.connections import api_notifier

        api_notifier.notify_backup_failure({"status": "WARNING"})
        sync_detailed.assert_not_called()

    @pytest.mark.parametrize("status", ["CRITICAL", "ERROR"])
    def test_triggers_for_failure_states(self, status, stub_notifier_client, stub_rdb):
        sync_detailed, _auth = stub_notifier_client
        stub_rdb(admins=[{"id": "u-admin", "username": "admin", "email": "a@x"}])
        from isardvdi_common.connections import api_notifier

        api_notifier.notify_backup_failure({"status": status, "scope": "full"})
        assert sync_detailed.called


class TestRecipientFanout:
    def test_sends_one_request_per_admin(self, stub_notifier_client, stub_rdb):
        sync_detailed, _auth = stub_notifier_client
        stub_rdb(
            admins=[
                {"id": "u1", "username": "a1", "email": "a1@x"},
                {"id": "u2", "username": "a2", "email": "a2@x"},
                {"id": "u3", "username": "a3", "email": "a3@x"},
            ]
        )
        from isardvdi_common.connections import api_notifier

        api_notifier.notify_backup_failure(
            {"status": "ERROR", "scope": "full", "summary": "boom"}
        )
        assert sync_detailed.call_count == 3
        sent_user_ids = sorted(
            call.kwargs["body"]["user_id"] for call in sync_detailed.call_args_list
        )
        assert sent_user_ids == ["u1", "u2", "u3"]

    def test_subject_includes_status_and_scope(self, stub_notifier_client, stub_rdb):
        sync_detailed, _auth = stub_notifier_client
        stub_rdb(admins=[{"id": "u", "username": "a", "email": "a@x"}])
        from isardvdi_common.connections import api_notifier

        api_notifier.notify_backup_failure({"status": "CRITICAL", "scope": "db"})
        body = sync_detailed.call_args.kwargs["body"]
        assert "CRITICAL" in body["subject"]
        assert "db" in body["subject"]

    def test_body_includes_summary(self, stub_notifier_client, stub_rdb):
        sync_detailed, _auth = stub_notifier_client
        stub_rdb(admins=[{"id": "u", "username": "a", "email": "a@x"}])
        from isardvdi_common.connections import api_notifier

        api_notifier.notify_backup_failure(
            {"status": "ERROR", "scope": "full", "summary": "disk full"}
        )
        body = sync_detailed.call_args.kwargs["body"]
        assert "disk full" in body["text"]

    def test_body_falls_back_when_summary_missing(self, stub_notifier_client, stub_rdb):
        sync_detailed, _auth = stub_notifier_client
        stub_rdb(admins=[{"id": "u", "username": "a", "email": "a@x"}])
        from isardvdi_common.connections import api_notifier

        api_notifier.notify_backup_failure({"status": "ERROR"})
        body = sync_detailed.call_args.kwargs["body"]
        assert "No summary available" in body["text"]


class TestBestEffort:
    """The function must never raise — the caller is the backup
    insert path and we don't want to lose a record because the
    notifier is down."""

    def test_db_query_failure_is_swallowed(self, stub_notifier_client, stub_rdb):
        sync_detailed, _auth = stub_notifier_client
        stub_rdb(raises=RuntimeError("rdb down"))
        from isardvdi_common.connections import api_notifier

        # Must not raise.
        api_notifier.notify_backup_failure({"status": "ERROR"})
        sync_detailed.assert_not_called()

    def test_no_admins_skips_silently(self, stub_notifier_client, stub_rdb):
        sync_detailed, _auth = stub_notifier_client
        stub_rdb(admins=[])
        from isardvdi_common.connections import api_notifier

        api_notifier.notify_backup_failure({"status": "ERROR"})
        sync_detailed.assert_not_called()

    def test_per_admin_send_failure_is_swallowed(self, stub_notifier_client, stub_rdb):
        """A 500 from the notifier on admin #1 must not stop us from
        trying admins #2 and #3 — and must not raise to the caller."""
        sync_detailed, _auth = stub_notifier_client
        sync_detailed.side_effect = [
            RuntimeError("fail"),
            MagicMock(parsed=None),
            MagicMock(parsed=None),
        ]
        stub_rdb(
            admins=[
                {"id": "u1", "username": "a1", "email": "a1@x"},
                {"id": "u2", "username": "a2", "email": "a2@x"},
                {"id": "u3", "username": "a3", "email": "a3@x"},
            ]
        )
        from isardvdi_common.connections import api_notifier

        api_notifier.notify_backup_failure({"status": "ERROR"})
        assert sync_detailed.call_count == 3
