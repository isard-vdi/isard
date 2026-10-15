"""Rows libvirt does not back are settled by the broom, from fresh listings only."""

import logging
from concurrent.futures import Future
from time import time
from unittest.mock import MagicMock, patch

import libvirt
import pytest

import engine.controllers.broom as mod
from engine.services.lib import domain_guard


class _Recorder:
    def __init__(self):
        self.writes = []

    def update_domain_status(self, status, domain_id, **kwargs):
        self.writes.append((domain_id, status, kwargs))

    def update_domain_hyp_started(
        self, domain_id, hyp_id, detail=None, status=None, **kw
    ):
        self.writes.append((domain_id, status or "hyp_started", {"hyp": hyp_id}))

    def statuses_of(self, domain_id):
        return [status for did, status, _ in self.writes if did == domain_id]


def _row(domain_id, status, hyp_started=False):
    return {
        "id": domain_id,
        "status": status,
        "hyp_started": hyp_started,
        "accessed": int(time()),
    }


def _verdict(*running, paused=None):
    states = {d: {"status": "Started", "detail": ""} for d in running}
    states.update(paused or {})
    return {"active_domains": {}, "states": states}


def _passes(
    n, transitional=(), unknown=(), verdicts=None, online=("hyp-1", "hyp-2"), held=()
):
    recorder = _Recorder()
    manager = MagicMock()
    manager.check_actions_domains_enabled.return_value = True
    broom = mod.ThreadBroom(name="broom-test", polling_interval=0, manager=manager)
    for domain_id in held:
        domain_guard.hold(domain_id, "hyp-1", "createXML")
    done = {"n": 0}

    def _count(_data):
        done["n"] += 1
        if done["n"] >= n:
            broom.stop = True

    with patch.object(
        mod, "get_domains_with_transitional_status", return_value=list(transitional)
    ), patch.object(
        mod, "get_domains_with_status_in_list", return_value=list(unknown)
    ), patch.object(
        mod, "get_hyp_hostnames_online", return_value={h: h for h in online}
    ), patch.object(
        broom, "_check_hypervisors_concurrent", return_value=verdicts or {}
    ), patch.object(
        broom, "_assess_storage", return_value={}
    ), patch.object(
        mod, "update_domain_status", recorder.update_domain_status
    ), patch.object(
        mod, "update_domain_hyp_started", recorder.update_domain_hyp_started
    ), patch.object(
        mod, "update_vgpu_info_if_stopped", MagicMock()
    ), patch.object(
        mod, "format_broom_data", _count
    ):
        broom.polling()
    broom.stop_thread()
    return recorder


BOTH = {"hyp-1": _verdict(), "hyp-2": _verdict()}


class TestUnknownIsSettled:
    @pytest.mark.parametrize("hyp_started", [False, "hyp-1"])
    def test_unknown_absent_from_every_hypervisor_is_stopped(self, hyp_started):
        wrote = _passes(2, unknown=[_row("d-1", "Unknown", hyp_started)], verdicts=BOTH)

        assert wrote.statuses_of("d-1") == ["Stopped"]
        assert wrote.writes[0][2]["expected_status"] == "Unknown"

    def test_one_pass_is_not_enough(self):
        wrote = _passes(1, unknown=[_row("d-1", "Unknown")], verdicts=BOTH)

        assert wrote.writes == []

    def test_nothing_is_settled_while_a_hypervisor_has_no_verdict(self):
        wrote = _passes(
            4, unknown=[_row("d-1", "Unknown")], verdicts={"hyp-1": _verdict()}
        )

        assert wrote.writes == []

    def test_unknown_still_running_somewhere_is_not_stopped(self):
        wrote = _passes(
            3,
            unknown=[_row("d-1", "Unknown")],
            verdicts={"hyp-1": _verdict(), "hyp-2": _verdict("d-1")},
        )

        assert "Stopped" not in wrote.statuses_of("d-1")

    def test_unknown_on_a_hypervisor_that_is_not_online_is_left_alone(self):
        wrote = _passes(4, unknown=[_row("d-1", "Unknown", "hyp-off")], verdicts=BOTH)

        assert wrote.writes == []


class TestStartedAbsentFromLibvirt:
    def test_started_absent_from_every_hypervisor_is_stopped(self):
        wrote = _passes(
            2, transitional=[_row("d-1", "Started", "hyp-1")], verdicts=BOTH
        )

        assert wrote.statuses_of("d-1") == ["Stopped"]
        assert wrote.writes[0][2]["expected_status"] == "Started"

    def test_started_that_runs_is_not_rewritten(self):
        wrote = _passes(
            3,
            transitional=[_row("d-1", "Started", "hyp-1")],
            verdicts={"hyp-1": _verdict("d-1"), "hyp-2": _verdict()},
        )

        assert wrote.writes == []

    def test_a_held_domain_is_left_to_the_worker_reconciling_it(self, monkeypatch):
        monkeypatch.setattr(domain_guard, "_mirror", lambda *a: None)
        try:
            wrote = _passes(
                3,
                transitional=[_row("d-1", "Started", "hyp-1")],
                verdicts=BOTH,
                held=["d-1"],
            )
        finally:
            domain_guard._held.clear()

        assert wrote.writes == []


class TestOneWarningPerHypervisorWithoutVerdict:
    def test_a_hypervisor_without_verdict_is_reported_once_with_its_count(self, caplog):
        rows = [_row(f"d-{i}", "Started", "hyp-2") for i in range(25)]
        broom_log = logging.getLogger("broom-test-capture")
        with patch.object(mod.logs, "broom", broom_log), caplog.at_level(
            logging.DEBUG, logger="broom-test-capture"
        ):
            _passes(1, transitional=rows, verdicts={"hyp-1": _verdict()})

        mentioning = [r for r in caplog.records if "hyp-2" in r.getMessage()]
        assert len(mentioning) == 1
        assert mentioning[0].levelno == logging.WARNING
        assert "25 domains" in mentioning[0].getMessage()
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def _connection(listing=None, error=None):
    connection = MagicMock()
    connection.connected = True
    if error is not None:
        connection.list_domain_states.side_effect = error
    else:
        connection.list_domain_states.return_value = listing or {}
    connection.get_domains.return_value = listing or {}
    connection.get_storage_used.return_value = {}
    return connection


def _check(connection, db_status="Stopped"):
    with patch.object(
        mod, "get_hyp_hostname_from_id", return_value=("h", 22, "u", False, None)
    ), patch.object(mod, "hyp", return_value=connection), patch.object(
        mod, "get_domain_status", return_value=db_status
    ), patch.object(
        mod, "update_domain_hyp_started", MagicMock()
    ) as started, patch.object(
        mod, "update_table_dict", MagicMock()
    ):
        return mod._check_single_hypervisor("hyp-1", 0, set()), started


class TestTheListingIsAVerdictOnlyWhenLibvirtAnswered:
    def test_a_listing_libvirt_could_not_answer_is_no_verdict(self):
        result, _ = _check(_connection(error=libvirt.libvirtError("listing failed")))

        assert result["success"] is False

    def test_a_listing_libvirt_answered_is_kept_whole(self):
        result, _ = _check(
            _connection({"d-1": {"status": "Started", "detail": ""}}), "Started"
        )

        assert result["success"] is True
        assert result["states"] == {"d-1": {"status": "Started", "detail": ""}}

    def test_a_held_domain_is_not_adopted(self, monkeypatch):
        monkeypatch.setattr(domain_guard, "_mirror", lambda *a: None)
        domain_guard.hold("d-1", "hyp-1", "createXML")
        try:
            _, started = _check(
                _connection({"d-1": {"status": "Started", "detail": ""}}), "Failed"
            )
        finally:
            domain_guard._held.clear()

        started.assert_not_called()


class TestIdlePausedAtStart:
    def test_a_due_domain_is_destroyed_once_off_the_pass(self, monkeypatch):
        broom = mod.ThreadBroom(name="b", polling_interval=0, manager=MagicMock())
        broom._idle_paused.after_s = 0
        submitted = []
        monkeypatch.setattr(
            broom._executor,
            "submit",
            lambda fn, *args: submitted.append((fn, args)) or Future(),
        )
        monkeypatch.setattr(mod, "get_domain_status", lambda d: "Paused")
        verdicts = {
            "hyp-1": _verdict(
                paused={"d-1": {"status": "Paused", "detail": "", "vcpu_time": 0.2}}
            )
        }

        broom._reap_idle_paused(verdicts, now=1000)
        broom._reap_idle_paused(verdicts, now=1001)
        broom.stop_thread()

        assert submitted == [
            (mod._destroy_idle_paused, ("hyp-1", "d-1", "Paused", 0.2))
        ]

    def _destroy(self, monkeypatch, state, cpu_ns):
        recorder = _Recorder()
        dom = MagicMock()
        dom.state.return_value = [state, 1]
        dom.vcpus.return_value = ([(0, 1, cpu_ns, 0)], [])
        connection = MagicMock()
        connection.connected = True
        connection.conn.lookupByName.return_value = dom
        monkeypatch.setattr(mod, "hyp", MagicMock(return_value=connection))
        monkeypatch.setattr(
            mod, "get_hyp_hostname_from_id", lambda h: ("h", 22, "u", False, None)
        )
        monkeypatch.setattr(mod, "update_domain_status", recorder.update_domain_status)
        monkeypatch.setattr(mod, "update_vgpu_info_if_stopped", MagicMock())
        done = mod._destroy_idle_paused("hyp-1", "d-1", "Paused", 0.2)
        return done, dom, recorder

    def test_it_is_destroyed_and_stopped_from_the_status_it_was_seen_in(
        self, monkeypatch
    ):
        done, dom, wrote = self._destroy(
            monkeypatch, libvirt.VIR_DOMAIN_PAUSED, 200_000_000
        )

        assert done is True
        dom.destroy.assert_called_once()
        assert wrote.statuses_of("d-1") == ["Stopped"]
        assert wrote.writes[0][2]["expected_status"] == "Paused"

    @pytest.mark.parametrize(
        "state,cpu_ns",
        [(libvirt.VIR_DOMAIN_RUNNING, 200_000_000), (libvirt.VIR_DOMAIN_PAUSED, 5e9)],
    )
    def test_one_that_resumed_or_ran_meanwhile_is_kept(
        self, monkeypatch, state, cpu_ns
    ):
        done, dom, wrote = self._destroy(monkeypatch, state, cpu_ns)

        assert done is False
        dom.destroy.assert_not_called()
        assert wrote.writes == []
