#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin ``HypervisorsProcessed.hyper`` re-registration ``enabled`` read.

When a hypervisor row already exists (re-registration after a
container restart) the method needs to feed ``enabled`` back into
``add_hyper`` AND emit a ``.update({"enabled": False})`` if it was
previously enabled. The ``enabled`` field can be:

* missing entirely (partial row written by another writer mid-flight,
  or row restored from a dump that predates v189),
* stored as ``None`` from a partial write,
* stored as ``True`` / ``False``.

``dict.get(k, default)`` only defaults on a missing key, NOT on a
stored ``None`` (per the engine-hypervisors skill, gotcha #2). The
defensive read is wrapped in ``bool(...)`` so all four shapes
collapse to a clean True/False.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_hyper(monkeypatch):
    from isardvdi_common.lib.hypervisors import hypervisors as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.HypervisorsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.HypervisorsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)

    # ``add_hyper`` is a sibling classmethod that runs the full insert
    # flow; replacing it with a stub that returns a "no-op replace"
    # result lets us exercise just the ``hyper()`` re-registration
    # branch without dragging the whole pipeline in.
    add_hyper_calls = []

    def _fake_add_hyper(cls, *args, **kwargs):
        add_hyper_calls.append({"args": args, "kwargs": kwargs})
        return {
            "deleted": 0,
            "errors": 0,
            "inserted": 0,
            "replaced": 1,
            "skipped": 0,
            "unchanged": 0,
        }

    monkeypatch.setattr(
        mod.HypervisorsProcessed,
        "add_hyper",
        classmethod(_fake_add_hyper),
    )
    # ``hyper()`` ends with ``data["certs"] = cls.get_hypervisors_certs()``
    # which in turn hits rdb. Stubbed here because this test only
    # cares about the ``enabled`` readback branch upstream.
    monkeypatch.setattr(
        mod.HypervisorsProcessed,
        "get_hypervisors_certs",
        classmethod(lambda cls: {"ca-cert.pem": "stub", "server-cert.pem": "stub"}),
    )
    yield {
        "mock_table": mock_table,
        "Processed": mod.HypervisorsProcessed,
        "add_hyper_calls": add_hyper_calls,
    }


def _row(**overrides) -> dict:
    """Build a minimal existing-hypervisor row. ``overrides`` lets each
    test set ``enabled`` to whatever shape it's pinning."""
    base = {
        "id": "isard-hypervisor",
        "hostname": "isard-hypervisor",
        "port": "2022",
    }
    base.update(overrides)
    return base


class TestReregistrationEnabledReadback:
    """The four shapes of a stored ``enabled`` value all flow into
    ``add_hyper(..., enabled=<bool>, ...)`` and only emit the
    ``update({"enabled": False})`` side-effect when the previous
    value coerced to True."""

    def test_enabled_true_disables_first_then_re_adds(self, stub_hyper):
        stub_hyper["mock_table"].return_value.get.return_value.run.return_value = _row(
            enabled=True
        )
        stub_hyper["Processed"].hyper("isard-hypervisor", "isard-hypervisor")
        # add_hyper saw enabled=True (so the engine restarts in the
        # same enabled state once the disable→re-register dance lands).
        assert stub_hyper["add_hyper_calls"][-1]["kwargs"]["enabled"] is True
        # AND the in-flight disable was issued.
        update_calls = stub_hyper[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list
        assert any(
            call.args and call.args[0] == {"enabled": False} for call in update_calls
        )

    def test_enabled_false_skips_disable_and_re_adds(self, stub_hyper):
        stub_hyper["mock_table"].return_value.get.return_value.run.return_value = _row(
            enabled=False
        )
        stub_hyper["Processed"].hyper("isard-hypervisor", "isard-hypervisor")
        assert stub_hyper["add_hyper_calls"][-1]["kwargs"]["enabled"] is False
        update_calls = stub_hyper[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list
        # No ``{"enabled": False}`` update — would have been a no-op.
        assert not any(
            call.args and call.args[0] == {"enabled": False} for call in update_calls
        )

    def test_enabled_missing_collapses_to_false(self, stub_hyper):
        # Partial row mid-flight or pre-v189 dump — no ``enabled`` key.
        stub_hyper["mock_table"].return_value.get.return_value.run.return_value = _row()
        stub_hyper["Processed"].hyper("isard-hypervisor", "isard-hypervisor")
        assert stub_hyper["add_hyper_calls"][-1]["kwargs"]["enabled"] is False
        update_calls = stub_hyper[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list
        assert not any(
            call.args and call.args[0] == {"enabled": False} for call in update_calls
        )

    def test_enabled_stored_none_collapses_to_false(self, stub_hyper):
        # Gotcha #2: dict.get('enabled', False) returns None (NOT False)
        # when the value is None. ``bool(...)`` is what protects the
        # downstream ``add_hyper(enabled=...)`` call.
        stub_hyper["mock_table"].return_value.get.return_value.run.return_value = _row(
            enabled=None
        )
        stub_hyper["Processed"].hyper("isard-hypervisor", "isard-hypervisor")
        assert stub_hyper["add_hyper_calls"][-1]["kwargs"]["enabled"] is False
        update_calls = stub_hyper[
            "mock_table"
        ].return_value.get.return_value.update.call_args_list
        assert not any(
            call.args and call.args[0] == {"enabled": False} for call in update_calls
        )
