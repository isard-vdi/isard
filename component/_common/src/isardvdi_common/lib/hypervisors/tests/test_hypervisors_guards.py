#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guard paths of ``HypervisorsProcessed`` in ``hypervisors.py``.

Fixes the guards that reject bad input / bad state on the real functions
(never mocking the function under test; only the rethink layer and
collaborators are stubbed):

* ``update_fingerprint`` -- SSRF guard (loopback / link-local hostnames) and
  DNS-resolution failure both ``raise Error("bad_request")``; a public address
  passes the SSRF guard.
* ``set_hyper_deadrow_time`` -- unknown hypervisor (``not_found``), one not
  managed by the orchestrator (``precondition_required``), and the ``reset``
  branch (clears the dead row / refuses when not in it).
* ``hyper`` -- new registration with a failed ``ssh-keyscan`` / add
  (``not_found``), and the same on re-registration.

Assertions check the ``Error`` type and its ``error``/``description``, and for
the state-changing branches also assert what was NOT written.
"""

import socket
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_base import ErrorBase


@pytest.fixture
def stub_rdb(monkeypatch):
    from unittest.mock import MagicMock

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
    tables = {}

    def router(name):
        return tables.setdefault(name, MagicMock(name=f"table-{name}"))

    monkeypatch.setattr(mod.r, "table", MagicMock(side_effect=router))
    return {
        "mod": mod,
        "Cls": mod.HypervisorsProcessed,
        "router": router,
        "monkeypatch": monkeypatch,
    }


# --------------------------------------------------------------------------- #
# update_fingerprint -- SSRF + DNS guards
# --------------------------------------------------------------------------- #
class TestUpdateFingerprintGuards:
    @pytest.fixture
    def fp(self, monkeypatch):
        from isardvdi_common.lib.hypervisors import hypervisors as mod

        # Past the guard the function touches the filesystem + ssh-keygen; make
        # that deterministic (file present, keygen fails -> returns False) so a
        # relaxed-guard mutation lands on a clean False, not a real fs error.
        monkeypatch.setattr(mod.os.path, "exists", lambda p: True)

        def _boom(*a, **k):
            raise RuntimeError("ssh-keygen unavailable")

        monkeypatch.setattr(mod, "check_output", _boom)
        return mod.HypervisorsProcessed

    def _addr(self, ip):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0))]

    def test_loopback_hostname_rejected(self, fp, monkeypatch):
        monkeypatch.setattr(
            socket, "getaddrinfo", lambda *a, **k: self._addr("127.0.0.1")
        )
        with pytest.raises(ErrorBase) as exc:
            fp.update_fingerprint("evil.local", "2022")
        assert exc.value.error["error"] == "bad_request"
        assert exc.value.status_code == 400
        assert "loopback" in exc.value.error["description"]

    def test_link_local_hostname_rejected(self, fp, monkeypatch):
        monkeypatch.setattr(
            socket, "getaddrinfo", lambda *a, **k: self._addr("169.254.1.1")
        )
        with pytest.raises(ErrorBase) as exc:
            fp.update_fingerprint("meta.local", "2022")
        assert exc.value.error["error"] == "bad_request"
        assert exc.value.status_code == 400

    def test_dns_failure_rejected(self, fp, monkeypatch):
        def _gaierror(*a, **k):
            raise socket.gaierror("name or service not known")

        monkeypatch.setattr(socket, "getaddrinfo", _gaierror)
        with pytest.raises(ErrorBase) as exc:
            fp.update_fingerprint("nonexistent.example", "2022")
        assert exc.value.error["error"] == "bad_request"
        assert "DNS resolution failed" in exc.value.error["description"]

    def test_public_address_passes_ssrf_guard(self, fp, monkeypatch):
        # A routable public IP is accepted by the SSRF guard: the function
        # proceeds and only fails later at the (stubbed) ssh-keygen -> False.
        monkeypatch.setattr(
            socket, "getaddrinfo", lambda *a, **k: self._addr("8.8.8.8")
        )
        assert fp.update_fingerprint("host.example", "2022") is False


# --------------------------------------------------------------------------- #
# set_hyper_deadrow_time -- existence / orchestrator / reset guards
# --------------------------------------------------------------------------- #
class TestSetHyperDeadrowTimeGuards:
    def _hyp_get(self, stub):
        return stub["router"]("hypervisors").get.return_value

    def test_unknown_hypervisor_raises_not_found(self, stub_rdb):
        get = self._hyp_get(stub_rdb)
        get.run.return_value = None
        with pytest.raises(ErrorBase) as exc:
            stub_rdb["Cls"].set_hyper_deadrow_time("gone")
        assert exc.value.error["error"] == "not_found"
        assert exc.value.status_code == 404
        get.update.assert_not_called()

    def test_not_orchestrator_managed_raises_precondition(self, stub_rdb):
        get = self._hyp_get(stub_rdb)
        get.run.return_value = {"id": "h1", "orchestrator_managed": False}
        with pytest.raises(ErrorBase) as exc:
            stub_rdb["Cls"].set_hyper_deadrow_time("h1")
        assert exc.value.error["error"] == "precondition_required"
        assert exc.value.status_code == 428
        # A hypervisor the orchestrator does not manage must be left untouched.
        get.update.assert_not_called()

    def test_reset_clears_dead_row(self, stub_rdb):
        get = self._hyp_get(stub_rdb)
        get.run.return_value = {
            "id": "h1",
            "orchestrator_managed": True,
            "only_forced": True,
            "destroy_time": "2026-08-09T10:00+00:00",
        }
        result = stub_rdb["Cls"].set_hyper_deadrow_time("h1", reset=True)
        assert result is True
        # Exactly the dead-row clear, nothing else.
        get.update.assert_called_once_with({"only_forced": False, "destroy_time": None})

    def test_reset_when_not_in_dead_row_raises_and_writes_nothing(self, stub_rdb):
        get = self._hyp_get(stub_rdb)
        get.run.return_value = {
            "id": "h1",
            "orchestrator_managed": True,
            "only_forced": False,
            "destroy_time": None,
        }
        with pytest.raises(ErrorBase) as exc:
            stub_rdb["Cls"].set_hyper_deadrow_time("h1", reset=True)
        assert exc.value.error["error"] == "precondition_required"
        assert "not in dead row" in exc.value.error["description"]
        get.update.assert_not_called()


# --------------------------------------------------------------------------- #
# hyper -- registration ssh-keyscan / add guards
# --------------------------------------------------------------------------- #
class TestHyperRegistrationGuards:
    @pytest.fixture
    def hyper_stub(self, stub_rdb):
        mod = stub_rdb["mod"]
        # get_hypervisors_certs only matters on the success path; keep it off DB.
        stub_rdb["monkeypatch"].setattr(
            mod.HypervisorsProcessed,
            "get_hypervisors_certs",
            classmethod(lambda cls: []),
        )
        return stub_rdb

    def _set_add_hyper(self, stub, value):
        add = MagicMock(name="add_hyper", return_value=value)
        stub["monkeypatch"].setattr(
            stub["mod"].HypervisorsProcessed,
            "add_hyper",
            classmethod(lambda cls, *a, **k: add(*a, **k)),
        )
        return add

    def test_new_hyper_failed_keyscan_raises(self, hyper_stub):
        get = hyper_stub["router"]("hypervisors").get.return_value
        get.run.return_value = None  # not in DB -> new registration
        add = self._set_add_hyper(hyper_stub, None)  # add_hyper falsy -> ssh-keyscan
        with pytest.raises(ErrorBase) as exc:
            hyper_stub["Cls"].hyper("h1", "host.example")
        assert exc.value.error["error"] == "not_found"
        assert "ssh-keyscan" in exc.value.error["description"]
        add.assert_called_once()
        get.update.assert_not_called()

    def test_new_hyper_insert_failure_raises(self, hyper_stub):
        get = hyper_stub["router"]("hypervisors").get.return_value
        get.run.return_value = None
        # add_hyper returns a result that check() rejects (nothing inserted, an error).
        self._set_add_hyper(
            hyper_stub,
            {"inserted": 0, "unchanged": 0, "errors": 1, "replaced": 0},
        )
        with pytest.raises(ErrorBase) as exc:
            hyper_stub["Cls"].hyper("h1", "host.example")
        assert exc.value.error["error"] == "not_found"
        assert "add hypervisor" in exc.value.error["description"]

    def test_reregistration_failed_keyscan_raises(self, hyper_stub):
        get = hyper_stub["router"]("hypervisors").get.return_value
        # Already in DB and disabled -> no enabled=False write before add_hyper.
        get.run.return_value = {"id": "h1", "enabled": False}
        self._set_add_hyper(hyper_stub, None)
        with pytest.raises(ErrorBase) as exc:
            hyper_stub["Cls"].hyper("h1", "host.example")
        assert exc.value.error["error"] == "not_found"
        assert "ssh-keyscan" in exc.value.error["description"]
        # Disabled re-registration must not write anything to the row here.
        get.update.assert_not_called()
