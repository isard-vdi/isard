"""The broom's storage verdicts: every pass, apart from libvirt, with the cause."""

import sys
import threading
from unittest.mock import MagicMock

import pytest

try:
    import engine.models.hyp  # noqa: F401
except Exception:
    sys.modules["engine.models.hyp"] = MagicMock()

from engine.controllers import broom  # noqa: E402

ONLINE = ["hyp-1", "hyp-2", "hyp-3"]


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(broom, "domain_guard", MagicMock())
    monkeypatch.setattr(broom, "get_shared_storage_stall", lambda: None)
    monkeypatch.setattr(broom, "update_hyp_libvirt_warning", MagicMock())
    monkeypatch.setattr(broom, "get_degraded_hyp_ids", lambda: set())
    monkeypatch.setattr(broom, "get_hyps_health", lambda hyp_ids: {})


@pytest.fixture
def db(monkeypatch):
    degraded = MagicMock()
    stored = MagicMock()
    monkeypatch.setattr(broom, "update_hyp_degraded_status", degraded)
    monkeypatch.setattr(broom, "set_shared_storage_stall", stored)
    return degraded, stored


@pytest.fixture
def probes(monkeypatch):
    """hyp_id -> what its probe answers; a threading.Event blocks it."""
    answers = {}
    calls = {}

    def fake_probe(hyp_id):
        calls[hyp_id] = calls.get(hyp_id, 0) + 1
        answer = answers.get(hyp_id, {"hung": [], "error": None})
        if isinstance(answer, threading.Event):
            answer.wait(30)
            return {"hung": [], "error": None}
        return answer

    monkeypatch.setattr(broom, "_probe_storage", fake_probe)
    return answers, calls


@pytest.fixture
def libvirt(monkeypatch):
    """hyp_ids the libvirt check is asked about, and the ones that fail it."""
    checked = []
    failing = set()

    def fake_check(hyp_id, disk_interval, started_ids):
        checked.append(hyp_id)
        return {
            "hyp_id": hyp_id,
            "success": hyp_id not in failing,
            "active_domains": {},
            "domains_destroyed": [],
            "domains_handled": [],
            "error": "libvirt connection failed" if hyp_id in failing else None,
        }

    monkeypatch.setattr(broom, "_check_single_hypervisor", fake_check)
    return checked, failing


@pytest.fixture
def b():
    thread = broom.ThreadBroom("broom-test", 1, MagicMock())
    yield thread
    thread.stop_thread()


def _degraded(degraded):
    return {
        c.args[0]: c.kwargs.get("reason")
        for c in degraded.call_args_list
        if c.kwargs.get("is_degraded") is True
    }


def _recovered(degraded):
    return {
        c.args[0]
        for c in degraded.call_args_list
        if c.kwargs.get("is_degraded") is False
    }


def _pass(b, hyp_ids=ONLINE):
    causes = b._assess_storage(hyp_ids)
    b._check_hypervisors_concurrent(hyp_ids, 2, set(), causes=causes)
    return causes


class TestProbeStorage:
    def test_hung_mounts_are_parsed(self, monkeypatch):
        monkeypatch.setattr(
            broom,
            "get_hyp_hostname_from_id",
            lambda hyp_id: ("host", 2022, "root", False, None),
        )
        remote = MagicMock(return_value={"out": b"/isard/groups\n", "err": b""})
        monkeypatch.setattr(broom, "exec_remote_cmd", remote)

        assert broom._probe_storage("hyp-1") == {
            "hung": ["/isard/groups"],
            "error": None,
        }
        assert remote.call_args.kwargs["timeout"] == broom.PROBE_DEADLINE_S
        assert remote.call_args.args[0] == broom.STORAGE_PROBE_CMD

    def test_an_ssh_failure_is_an_error_not_a_pass(self, monkeypatch):
        monkeypatch.setattr(
            broom,
            "get_hyp_hostname_from_id",
            lambda hyp_id: ("host", 2022, "root", False, None),
        )
        monkeypatch.setattr(
            broom, "exec_remote_cmd", MagicMock(side_effect=TimeoutError("timed out"))
        )

        assert broom._probe_storage("hyp-1") == {"hung": [], "error": "timed out"}


class TestEveryPass:
    def test_detected_in_the_first_pass_and_cleared_in_the_next(
        self, b, db, probes, libvirt
    ):
        degraded, _ = db
        answers, calls = probes
        checked, _ = libvirt
        answers["hyp-1"] = {"hung": ["/isard/groups"], "error": None}

        _pass(b)
        assert _degraded(degraded) == {
            "hyp-1": "storage: not responding: /isard/groups"
        }

        answers["hyp-1"] = {"hung": [], "error": None}
        _pass(b)
        assert _recovered(degraded) == {"hyp-1"}
        # probed on both passes: nothing is cached between them
        assert calls["hyp-1"] == 2

    def test_a_hung_hypervisor_gets_no_libvirt_check(self, b, db, probes, libvirt):
        answers, _ = probes
        checked, _ = libvirt
        answers["hyp-1"] = {"hung": ["/isard/groups"], "error": None}

        _pass(b)

        assert "hyp-1" not in checked
        assert sorted(checked) == ["hyp-2", "hyp-3"]

    def test_the_reason_says_libvirt_when_storage_answers(self, b, db, probes, libvirt):
        degraded, _ = db
        _, failing = libvirt
        failing.add("hyp-2")

        _pass(b)

        assert _degraded(degraded) == {
            "hyp-2": "libvirt: check failed: libvirt connection failed"
        }

    def test_a_new_cause_rewrites_the_reason_once(self, b, db, probes, libvirt):
        degraded, _ = db
        answers, _ = probes
        _, failing = libvirt
        failing.add("hyp-1")
        _pass(b)
        answers["hyp-1"] = {"hung": ["/isard/media"], "error": None}
        _pass(b)
        _pass(b)

        reasons = [
            c.kwargs["reason"]
            for c in degraded.call_args_list
            if c.args[0] == "hyp-1" and c.kwargs.get("is_degraded")
        ]
        assert reasons == [
            "libvirt: check failed: libvirt connection failed",
            "storage: not responding: /isard/media",
        ]

    def test_a_stale_health_report_degrades(self, b, db, probes, libvirt, monkeypatch):
        degraded, _ = db
        monkeypatch.setattr(
            broom, "get_hyps_health", lambda hyp_ids: {"hyp-3": {"received_at": 0}}
        )

        _pass(b)

        assert _degraded(degraded)["hyp-3"].startswith("health: no report for")


class TestOnePollingPass:
    def test_a_hung_hypervisor_is_degraded_without_a_libvirt_check(
        self, db, probes, libvirt, monkeypatch
    ):
        degraded, _ = db
        answers, _ = probes
        checked, _ = libvirt
        answers["hyp-1"] = {"hung": ["/isard/groups"], "error": None}
        monkeypatch.setattr(
            broom, "get_domains_with_transitional_status", lambda **k: []
        )
        monkeypatch.setattr(
            broom, "get_hyp_hostnames_online", lambda: {h: h for h in ONLINE}
        )
        manager = MagicMock()
        manager.check_actions_domains_enabled.return_value = True
        thread = broom.ThreadBroom("broom-test", 0, manager)

        def stop_after_one_pass(_data):
            thread.stop = True

        monkeypatch.setattr(broom, "format_broom_data", stop_after_one_pass)
        try:
            thread.polling()
        finally:
            thread.stop_thread()

        assert sorted(checked) == ["hyp-2", "hyp-3"]
        assert _degraded(degraded) == {
            "hyp-1": "storage: not responding: /isard/groups"
        }


class TestProbeConcurrency:
    def test_a_probe_that_never_answers_does_not_hold_the_pass(
        self, b, db, probes, libvirt, monkeypatch
    ):
        monkeypatch.setattr(broom, "PROBE_DEADLINE_S", 0.2)
        answers, calls = probes
        release = threading.Event()
        answers["hyp-1"] = release
        try:
            results = b._probe_storage_concurrent(ONLINE)
            assert "did not answer" in results["hyp-1"]["error"]
            assert results["hyp-2"] == {"hung": [], "error": None}

            again = b._probe_storage_concurrent(ONLINE)
            assert "has not answered" in again["hyp-1"]["error"]
            assert calls["hyp-1"] == 1
            assert calls["hyp-2"] == 2
        finally:
            release.set()

    def test_probes_run_in_parallel(self, b, db, probes, libvirt, monkeypatch):
        monkeypatch.setattr(broom, "PROBE_DEADLINE_S", 0.5)
        answers, _ = probes
        releases = {h: threading.Event() for h in ONLINE}
        answers.update(releases)
        started = threading.Barrier(len(ONLINE) + 1, timeout=2)

        def fake_probe(hyp_id):
            started.wait()
            return {"hung": [], "error": None}

        monkeypatch.setattr(broom, "_probe_storage", fake_probe)
        worker = threading.Thread(target=b._probe_storage_concurrent, args=(ONLINE,))
        worker.start()
        # every probe is running at the same time, or the barrier breaks
        started.wait()
        worker.join(2)
        assert not worker.is_alive()


class TestSharedStall:
    def test_set_in_the_pass_that_sees_it(self, b, db, probes, libvirt):
        _, stored = db
        answers, _ = probes
        for hyp_id in ("hyp-1", "hyp-2"):
            answers[hyp_id] = {"hung": ["/isard/groups"], "error": None}

        _pass(b)

        state = stored.call_args.args[0]
        assert state["active"] is True
        assert state["hypervisors"] == ["hyp-1", "hyp-2"]
        assert state["mounts"] == ["/isard/groups"]

    def test_one_line_is_logged(self, b, db, probes, libvirt, monkeypatch):
        logs = MagicMock()
        monkeypatch.setattr(broom, "logs", logs)
        answers, _ = probes
        for hyp_id in ("hyp-1", "hyp-2"):
            answers[hyp_id] = {"hung": ["/isard/groups"], "error": None}

        _pass(b)
        _pass(b)

        lines = [
            c.args
            for c in logs.broom.error.call_args_list
            if c.args and c.args[0].startswith("%s state=")
        ]
        assert len(lines) == 1
        assert lines[0][1] == "SHARED_STORAGE_STALL"
        assert lines[0][2] == "set"

    def test_one_hung_hypervisor_is_not_a_stall(self, b, db, probes, libvirt):
        _, stored = db
        answers, _ = probes
        answers["hyp-1"] = {"hung": ["/isard/groups"], "error": None}

        _pass(b)

        stored.assert_not_called()

    def test_cleared_after_two_clean_passes(self, b, db, probes, libvirt):
        _, stored = db
        answers, _ = probes
        for hyp_id in ("hyp-1", "hyp-2"):
            answers[hyp_id] = {"hung": ["/isard/groups"], "error": None}
        _pass(b)
        answers.clear()

        _pass(b)
        assert stored.call_count == 1
        _pass(b)
        assert stored.call_count == 2
        cleared = stored.call_args.args[0]
        assert cleared["active"] is False
        assert "cleared_at" in cleared

    def test_a_condition_from_before_a_restart_is_cleared(
        self, db, probes, libvirt, monkeypatch
    ):
        _, stored = db
        monkeypatch.setattr(
            broom,
            "get_shared_storage_stall",
            lambda: {"active": True, "since": 1.0, "hypervisors": ["hyp-1"]},
        )
        thread = broom.ThreadBroom("broom-test", 1, MagicMock())
        try:
            _pass(thread)
            _pass(thread)
        finally:
            thread.stop_thread()

        assert stored.call_args.args[0]["active"] is False

    def test_the_held_domains_of_a_previous_process_are_forgotten(self, monkeypatch):
        guard = MagicMock()
        monkeypatch.setattr(broom, "domain_guard", guard)
        thread = broom.ThreadBroom("broom-test", 1, MagicMock())
        thread.stop_thread()
        guard.reset.assert_called_once_with()
