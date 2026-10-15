"""Reconciling a hypervisor's domains on connect has a timeout and retries, and a
listing that never answers stops nothing."""

import logging
from unittest.mock import MagicMock

import libvirt
import pytest

from engine.models import hyp as hyp_mod
from engine.models.hyp import hyp
from engine.services.lib.libvirt_timeout import LibvirtTimeoutError
from engine.services.threads import hyp_worker_thread as mod
from engine.services.threads.hyp_worker_thread import HypWorkerThread


@pytest.fixture(autouse=True)
def _logs(monkeypatch):
    fake_logs = MagicMock()
    fake_logs.main = logging.getLogger(__name__)
    monkeypatch.setattr(hyp_mod, "logs", fake_logs, raising=False)
    monkeypatch.setattr(hyp_mod, "log", logging.getLogger(__name__), raising=False)


@pytest.fixture
def writes(monkeypatch):
    calls = []
    monkeypatch.setattr(
        hyp_mod,
        "update_domain_status",
        lambda status, domain_id, **kw: calls.append((status, domain_id, kw)),
    )
    monkeypatch.setattr(
        hyp_mod,
        "get_domains_started_in_hyp",
        lambda hyp_id: {"d-up": "Unknown", "d-gone": "Unknown"},
    )
    return calls


def _hyp(listing=None, error=None):
    h = hyp.__new__(hyp)
    h.id_hyp_rethink = "hyp-1"
    h.hostname = "hyp-1"
    h.connected = True
    h.conn = MagicMock()
    if error is not None:
        h.conn.listAllDomains.side_effect = error
    else:
        domains = []
        for name, (state, cpu_ns) in (listing or {}).items():
            d = MagicMock()
            d.name.return_value = name
            d.state.return_value = [state, 1]
            d.vcpus.return_value = ([(0, 1, cpu_ns, 0)], [])
            domains.append(d)
        h.conn.listAllDomains.return_value = domains
    return h


class TestTheModel:
    def test_a_listing_that_fails_raises_instead_of_stopping_everything(self, writes):
        h = _hyp(error=libvirt.libvirtError("listing failed"))

        with pytest.raises(libvirt.libvirtError):
            h.update_domain_coherence_in_db()

        assert writes == []

    def test_get_domains_keeps_answering_empty_on_failure(self):
        assert _hyp(error=libvirt.libvirtError("x")).get_domains() == {}

    def test_absent_rows_are_stopped_from_the_status_they_were_read_in(self, writes):
        h = _hyp({"d-up": (libvirt.VIR_DOMAIN_RUNNING, 10**9)})

        h.update_domain_coherence_in_db()

        stopped = [(d, kw["expected_status"]) for s, d, kw in writes if s == "Stopped"]
        assert stopped == [("d-gone", "Unknown")]

    def test_a_paused_domain_carries_its_vcpu_time(self):
        h = _hyp({"d-p": (libvirt.VIR_DOMAIN_PAUSED, 250_000_000)})

        assert h.list_domain_states()["d-p"]["vcpu_time"] == pytest.approx(0.25)


def _worker(answers):
    w = HypWorkerThread.__new__(HypWorkerThread)
    w.hyp_id = "hyp-1"
    w.stop = False
    w.h = MagicMock()
    w.attempts = 0

    def execute(func, **_):
        w.attempts += 1
        answer = answers[min(w.attempts, len(answers)) - 1]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    w._execute_libvirt_with_timeout = execute
    return w


class TestTheWorker:
    @pytest.fixture(autouse=True)
    def no_sleep(self, monkeypatch):
        slept = []
        monkeypatch.setattr(mod.time, "sleep", slept.append)
        return slept

    def test_a_listing_that_times_out_is_retried_and_then_left_to_the_broom(
        self, no_sleep
    ):
        w = _worker([LibvirtTimeoutError("listAllDomains", 30, "hyp-1")])

        assert w._reconcile_domains_on_connect() is False
        assert w.attempts == len(mod.RECONCILE_ON_CONNECT_RETRY_S) + 1
        assert no_sleep == list(mod.RECONCILE_ON_CONNECT_RETRY_S)
        w.h.update_domain_coherence_in_db.assert_not_called()

    def test_a_retry_that_answers_settles_the_rows(self):
        states = {"d-1": {"status": "Started", "detail": ""}}
        w = _worker([LibvirtTimeoutError("listAllDomains", 30, "hyp-1"), states])

        assert w._reconcile_domains_on_connect() is True
        w.h.update_domain_coherence_in_db.assert_called_once_with(states)

    def test_a_reconnect_tries_once(self):
        w = _worker([LibvirtTimeoutError("listAllDomains", 30, "hyp-1")])

        assert w._reconcile_domains_on_connect(retries=()) is False
        assert w.attempts == 1
