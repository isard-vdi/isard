"""What the broom decides, and for which rows it decides nothing.

The broom is the engine's only periodic reconciler for the running half of the
domain lifecycle, and it had no tests. These pin the decisions it makes on one
pass, because every one of them is a status write nobody else will correct.

Two shapes are covered:

* ``_check_single_hypervisor`` — what happens to a domain libvirt reports that
  the database does not expect there.
* one pass of ``polling`` — the per-status branches, driven with a zero polling
  interval and a ``format_broom_data`` that ends the loop, so exactly one pass
  runs and its writes can be read off.

The database helpers arrive as ``MagicMock`` from ``conftest.py``'s stubbing,
so they are patched per test rather than mocked from scratch.
"""

from time import time
from unittest.mock import MagicMock, patch

import pytest

import engine.controllers.broom as mod


class _Recorder:
    """Collects ``(id, status, kwargs)`` for every status write of a pass."""

    def __init__(self):
        self.writes = []

    def update_domain_status(self, status, domain_id, **kwargs):
        self.writes.append((domain_id, status, kwargs))

    def update_domain_hyp_started(self, domain_id, hyp_id, detail=None, status=None):
        self.writes.append((domain_id, status or "hyp_started", {"hyp": hyp_id}))

    def statuses_of(self, domain_id):
        return [status for did, status, _ in self.writes if did == domain_id]


def _domain(domain_id, status, hyp_started=False, accessed=None):
    return {
        "id": domain_id,
        "status": status,
        "hyp_started": hyp_started,
        "accessed": int(time()) if accessed is None else accessed,
    }


def _one_pass(domains, active_by_hyp=None):
    """Run exactly one iteration of ``polling`` and return what it wrote.

    ``active_by_hyp`` is what the hypervisors report as running, in the shape
    ``_check_hypervisors_concurrent`` returns.
    """
    recorder = _Recorder()
    manager = MagicMock()
    manager.check_actions_domains_enabled.return_value = True
    broom = mod.ThreadBroom(name="broom-test", polling_interval=0, manager=manager)

    def _stop_after_one_pass(_data):
        broom.stop = True

    with patch.object(
        mod, "get_domains_with_transitional_status", return_value=domains
    ), patch.object(
        mod, "get_hyp_hostnames_online", return_value={"hyp-1": "host-1"}
    ), patch.object(
        broom, "_check_hypervisors_concurrent", return_value=(active_by_hyp or {})
    ), patch.object(
        mod, "update_domain_status", recorder.update_domain_status
    ), patch.object(
        mod, "update_domain_hyp_started", recorder.update_domain_hyp_started
    ), patch.object(
        mod, "update_vgpu_info_if_stopped", MagicMock()
    ), patch.object(
        mod, "format_broom_data", _stop_after_one_pass
    ):
        broom.polling()

    broom.stop_thread()
    return recorder


class TestADomainWithNoHypervisor:
    def test_an_unrecognised_transitional_status_becomes_unknown(self):
        wrote = _one_pass([_domain("d-1", "Shutting-down")])

        assert wrote.statuses_of("d-1") == ["Unknown"]

    def test_stopping_is_stopped_instead(self):
        """``Stopping`` skips the ``Unknown`` branch and is settled below it:
        the domain is gone from every hypervisor, so it is stopped."""
        wrote = _one_pass([_domain("d-1", "Stopping")])

        assert wrote.statuses_of("d-1") == ["Stopped"]

    @pytest.mark.parametrize("status", ["Starting", "StartingPaused"])
    def test_a_start_is_left_alone_for_ever(self, status):
        """Pins today's behaviour, which is that nothing converges these.

        A start the engine never saw reach a hypervisor is skipped by the
        ``Unknown`` branch and matched by no branch below it, so the row keeps
        its status until someone restarts the engine.
        """
        wrote = _one_pass([_domain("d-1", status)])

        assert wrote.writes == []


class TestADomainWithAHypervisor:
    def test_shutting_down_gone_from_libvirt_is_stopped(self):
        wrote = _one_pass(
            [_domain("d-1", "Shutting-down", hyp_started="hyp-1")],
            {"hyp-1": {"active_domains": {}}},
        )

        assert wrote.statuses_of("d-1") == ["Stopped"]

    def test_the_shutdown_timeout_is_ninety_seconds(self):
        """Pinned as a value, not read from the module.

        The behaviour test below uses an hour-old row so it stays true for any
        sane timeout; that makes it blind to the constant itself, which this
        covers. A deliberate change fails here and nowhere else.
        """
        assert mod.BROOM_SHUTDOWN_TIMEOUT == 90

    def test_shutting_down_that_outlives_the_timeout_is_pushed_to_stopping(self):
        wrote = _one_pass(
            [
                _domain(
                    "d-1",
                    "Shutting-down",
                    hyp_started="hyp-1",
                    accessed=int(time()) - 3600,
                )
            ],
            {"hyp-1": {"active_domains": {"d-1": {"status": "Started", "detail": ""}}}},
        )

        assert wrote.statuses_of("d-1") == ["Stopping"]

    def test_shutting_down_within_the_timeout_is_left_to_finish(self):
        wrote = _one_pass(
            [_domain("d-1", "Shutting-down", hyp_started="hyp-1")],
            {"hyp-1": {"active_domains": {"d-1": {"status": "Started", "detail": ""}}}},
        )

        assert wrote.writes == []

    def test_a_reset_that_never_finished_fails(self):
        wrote = _one_pass(
            [
                _domain(
                    "d-1", "Resetting", hyp_started="hyp-1", accessed=int(time()) - 300
                )
            ],
            {"hyp-1": {"active_domains": {}}},
        )

        assert wrote.statuses_of("d-1") == ["Failed"]

    def test_a_fresh_reset_is_given_its_minute(self):
        wrote = _one_pass(
            [_domain("d-1", "Resetting", hyp_started="hyp-1")],
            {"hyp-1": {"active_domains": {}}},
        )

        assert wrote.writes == []

    def test_a_started_domain_is_not_rewritten(self):
        wrote = _one_pass(
            [_domain("d-1", "Started", hyp_started="hyp-1")],
            {"hyp-1": {"active_domains": {"d-1": {"status": "Started", "detail": ""}}}},
        )

        assert wrote.writes == []


class TestWhatTheHypervisorReportsThatTheDatabaseDoesNotExpect:
    def _check(self, libvirt_domains, db_status, expected_in_db=()):
        connection = MagicMock()
        connection.connected = True
        connection.get_domains.return_value = libvirt_domains
        connection.get_storage_used.return_value = {}
        with patch.object(
            mod, "get_hyp_hostname_from_id", return_value=("h", 22, "u", False, None)
        ), patch.object(mod, "hyp", return_value=connection), patch.object(
            mod, "get_domain_status", return_value=db_status
        ), patch.object(
            mod, "update_domain_hyp_started", MagicMock()
        ) as started, patch.object(
            mod, "update_table_dict", MagicMock()
        ):
            result = mod._check_single_hypervisor("hyp-1", 0, set(expected_in_db))
        return result, connection, started

    def test_a_domain_the_database_never_heard_of_is_destroyed(self):
        result, connection, _ = self._check(
            {"ghost": {"status": "Started", "detail": ""}}, None
        )

        assert result["domains_destroyed"] == ["ghost"]
        connection.conn.lookupByName.return_value.destroy.assert_called_once()

    def test_a_domain_mid_creation_is_left_running(self):
        """It is running because something is creating it. Destroying it, or
        stamping it ``Started``, would fight the flow that put it there."""
        result, connection, started = self._check(
            {"d-1": {"status": "Started", "detail": ""}}, "CreatingDomain"
        )

        assert result["domains_destroyed"] == []
        started.assert_not_called()
        connection.conn.lookupByName.assert_not_called()

    def test_a_domain_the_database_calls_stopped_is_marked_started(self):
        _, _, started = self._check(
            {"d-1": {"status": "Started", "detail": ""}}, "Stopped"
        )

        assert started.call_args[0][0] == "d-1"
        assert started.call_args[0][3] == "Started"

    def test_a_hypervisor_that_will_not_connect_reports_failure(self):
        connection = MagicMock()
        connection.connected = False
        with patch.object(
            mod, "get_hyp_hostname_from_id", return_value=("h", 22, "u", False, None)
        ), patch.object(mod, "hyp", return_value=connection):
            result = mod._check_single_hypervisor("hyp-1", 0, set())

        assert result["success"] is False
        assert "libvirt connection failed" in result["error"]
