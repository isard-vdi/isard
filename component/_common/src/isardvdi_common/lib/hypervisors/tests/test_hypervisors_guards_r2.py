#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Round-2 guard paths of ``HypervisorsProcessed`` in ``hypervisors.py``:

* ``update_hyper_virt_pools`` -- unknown hyper (``not_found``), a pool not
  available on the hyper (``precondition_required``), and the enable/disable
  writes (idempotent enable does not duplicate).
* ``get_orchestrator_hypervisors`` -- unknown id raises ``not_found``; the
  present-id and list branches fill defaults for missing fields.
* ``update_fingerprint`` -- the ssh-keygen/ssh-keyscan failure guards return
  ``False`` WITHOUT writing the known_hosts file, and the success path appends
  the scanned key and returns ``True``.

Only rethink / socket / subprocess / filesystem are stubbed; decisions are the
code's. Errors are asserted by type + ``error``/``description``.
"""

import builtins
import socket
from unittest.mock import MagicMock, mock_open

import pytest
from isardvdi_common.helpers.error_base import ErrorBase
from rethinkdb.errors import ReqlNonExistenceError


@pytest.fixture
def stub_rdb(monkeypatch):
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
        "mp": monkeypatch,
    }


# --------------------------------------------------------------------------- #
# update_hyper_virt_pools
# --------------------------------------------------------------------------- #
class TestUpdateHyperVirtPools:
    def _hyp(self, stub):
        return stub["router"]("hypervisors").get.return_value.default.return_value

    def test_unknown_hyper_raises_not_found(self, stub_rdb):
        self._hyp(stub_rdb).run.return_value = None
        with pytest.raises(ErrorBase) as exc:
            stub_rdb["Cls"].update_hyper_virt_pools(
                "gone", {"id": "pool-1", "enable_virt_pool": True}
            )
        assert exc.value.error["error"] == "not_found"
        assert exc.value.status_code == 404
        stub_rdb["router"]("hypervisors").get.return_value.update.assert_not_called()

    def test_pool_not_available_raises_precondition(self, stub_rdb):
        self._hyp(stub_rdb).run.return_value = {
            "virt_pools": ["pool-A"],
            "enabled_virt_pools": [],
        }
        with pytest.raises(ErrorBase) as exc:
            stub_rdb["Cls"].update_hyper_virt_pools(
                "h1", {"id": "pool-X", "enable_virt_pool": True}
            )
        assert exc.value.error["error"] == "precondition_required"
        assert exc.value.status_code == 428
        stub_rdb["router"]("hypervisors").get.return_value.update.assert_not_called()

    def test_enable_appends_pool(self, stub_rdb):
        self._hyp(stub_rdb).run.return_value = {
            "virt_pools": ["pool-1"],
            "enabled_virt_pools": [],
        }
        result = stub_rdb["Cls"].update_hyper_virt_pools(
            "h1", {"id": "pool-1", "enable_virt_pool": True}
        )
        assert result is True
        stub_rdb["router"](
            "hypervisors"
        ).get.return_value.update.assert_called_once_with(
            {"enabled_virt_pools": ["pool-1"]}
        )

    def test_enable_is_idempotent(self, stub_rdb):
        self._hyp(stub_rdb).run.return_value = {
            "virt_pools": ["pool-1"],
            "enabled_virt_pools": ["pool-1"],
        }
        stub_rdb["Cls"].update_hyper_virt_pools(
            "h1", {"id": "pool-1", "enable_virt_pool": True}
        )
        # Already enabled -> no duplicate write.
        stub_rdb["router"]("hypervisors").get.return_value.update.assert_not_called()

    def test_disable_removes_pool(self, stub_rdb):
        self._hyp(stub_rdb).run.return_value = {
            "virt_pools": ["pool-1", "pool-2"],
            "enabled_virt_pools": ["pool-1", "pool-2"],
        }
        stub_rdb["Cls"].update_hyper_virt_pools(
            "h1", {"id": "pool-1", "enable_virt_pool": False}
        )
        stub_rdb["router"](
            "hypervisors"
        ).get.return_value.update.assert_called_once_with(
            {"enabled_virt_pools": ["pool-2"]}
        )


# --------------------------------------------------------------------------- #
# get_orchestrator_hypervisors
# --------------------------------------------------------------------------- #
class TestGetOrchestratorHypervisors:
    def _q(self, stub):
        # r.table("hypervisors").get(id).pluck(...).merge(...)
        hyp = stub["router"]("hypervisors")
        return hyp.get.return_value.pluck.return_value.merge.return_value

    def _q_list(self, stub):
        # r.table("hypervisors").pluck(...).merge(...)
        hyp = stub["router"]("hypervisors")
        return hyp.pluck.return_value.merge.return_value

    def test_unknown_id_raises_not_found(self, stub_rdb):
        self._q(stub_rdb).run.side_effect = ReqlNonExistenceError(
            "no such row", None, None
        )
        with pytest.raises(ErrorBase) as exc:
            stub_rdb["Cls"].get_orchestrator_hypervisors("gone")
        assert exc.value.error["error"] == "not_found"
        assert exc.value.status_code == 404

    def test_present_id_fills_defaults(self, stub_rdb):
        self._q(stub_rdb).run.return_value = {"id": "h1", "status": "Online"}
        stub_rdb["mp"].setattr(
            stub_rdb["Cls"], "_get_hypervisors_gpus", classmethod(lambda cls, i, s: {})
        )
        stub_rdb["mp"].setattr(
            stub_rdb["Cls"], "calc_resource_load", classmethod(lambda cls, stats: {})
        )
        out = stub_rdb["Cls"].get_orchestrator_hypervisors("h1")
        # Data present overrides; missing fields fall back to the defaults.
        assert out["id"] == "h1"
        assert out["status"] == "Online"
        assert out["orchestrator_managed"] is False
        assert out["only_forced"] is False

    def test_list_branch_returns_all_with_defaults(self, stub_rdb):
        self._q_list(stub_rdb).run.return_value = [
            {"id": "h1", "status": "Online"},
            {"id": "h2", "status": "Offline"},
        ]
        stub_rdb["mp"].setattr(
            stub_rdb["Cls"], "_get_hypervisors_gpus", classmethod(lambda cls, i, s: {})
        )
        stub_rdb["mp"].setattr(
            stub_rdb["Cls"], "calc_resource_load", classmethod(lambda cls, stats: {})
        )
        out = stub_rdb["Cls"].get_orchestrator_hypervisors()
        assert [h["id"] for h in out] == ["h1", "h2"]
        assert all(h["orchestrator_managed"] is False for h in out)


# --------------------------------------------------------------------------- #
# update_fingerprint -- keygen/keyscan guards + success write
# --------------------------------------------------------------------------- #
class TestUpdateFingerprintKeyscan:
    @pytest.fixture
    def fp(self, monkeypatch):
        from isardvdi_common.lib.hypervisors import hypervisors as mod

        # Pass the SSRF guard with a public address, and resolve gethostbyname.
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *a, **k: [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 0))
            ],
        )
        monkeypatch.setattr(socket, "gethostbyname", lambda h: "8.8.8.8")
        monkeypatch.setattr(mod.os.path, "exists", lambda p: True)
        return mod

    def test_second_keygen_failure_returns_false_without_writing(self, fp, monkeypatch):
        opened = MagicMock(name="open")
        monkeypatch.setattr(builtins, "open", opened)
        # 1st ssh-keygen ok, 2nd ssh-keygen raises -> return False.
        monkeypatch.setattr(
            fp, "check_output", MagicMock(side_effect=["", RuntimeError("keygen2")])
        )
        assert (
            fp.HypervisorsProcessed.update_fingerprint("host.example", "2022") is False
        )
        opened.assert_not_called()

    def test_keyscan_failure_returns_false_without_writing(self, fp, monkeypatch):
        opened = MagicMock(name="open")
        monkeypatch.setattr(builtins, "open", opened)
        # both keygens ok, ssh-keyscan raises -> return False.
        monkeypatch.setattr(
            fp,
            "check_output",
            MagicMock(side_effect=["", "", RuntimeError("keyscan")]),
        )
        assert (
            fp.HypervisorsProcessed.update_fingerprint("host.example", "2022") is False
        )
        opened.assert_not_called()

    def test_success_appends_key_and_returns_true(self, fp, monkeypatch):
        m = mock_open()
        monkeypatch.setattr(builtins, "open", m)
        monkeypatch.setattr(
            fp,
            "check_output",
            MagicMock(side_effect=["", "", "ssh-rsa AAAAKEY host.example"]),
        )
        assert (
            fp.HypervisorsProcessed.update_fingerprint("host.example", "2022") is True
        )
        m.assert_called_once_with("/sshkeys/known_hosts", "a")
        m().write.assert_called_once_with("ssh-rsa AAAAKEY host.example\n")
