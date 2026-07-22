#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin ``HypervisorsProcessed.hyper`` persisting ``nvidia_gpus`` on the row.

Regression test for the GPU-placement outage: registration processed the
discovered ``nvidia_gpus`` (building the gpu catalog) but never stored the
inventory on the hypervisor record, and ``HypervisorModel`` has no
``nvidia_gpus`` field to round-trip it through ``add_hyper``. The engine then
read it empty (``hyp.py`` ``nvidia_gpus = hyper_record.get("nvidia_gpus", [])``)
and fell back to the legacy libvirt scan, which writes raw NVML product names
into ``info.nvidia`` — never matching the normalized catalog model, so the
hypervisor silently dropped out of GPU placement.

Pinned here:

* a truthy ``nvidia_gpus`` argument is written verbatim to the row with a
  direct ``update`` (the model round-trip would drop it),
* no ``nvidia_gpus`` argument → no such write,
* the persist is best-effort: a write failure must not abort registration.
"""

from unittest.mock import MagicMock

import pytest

NVIDIA_GPUS = [
    {
        "pci_id": "0000:21:00.0",
        "device_id": "10de:2bb5",
        "model": "RTXPro6000BlackwellDC",
    }
]


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
    # Existing-hypervisor row so ``hyper()`` takes the re-registration path
    # (no ssh-keyscan / fingerprint round-trip).
    mock_table.return_value.get.return_value.run.return_value = {
        "id": "isard-hypervisor",
        "hostname": "isard-hypervisor",
        "port": "2022",
        "enabled": False,
    }
    monkeypatch.setattr(mod.r, "table", mock_table)

    monkeypatch.setattr(
        mod.HypervisorsProcessed,
        "add_hyper",
        classmethod(
            lambda cls, *a, **k: {
                "deleted": 0,
                "errors": 0,
                "inserted": 0,
                "replaced": 1,
                "skipped": 0,
                "unchanged": 0,
            }
        ),
    )
    # The rest of the ``if nvidia_gpus:`` pipeline (catalog build) is not
    # under test and would otherwise emit its own writes into the shared
    # ``r.table`` mock, polluting the update capture below.
    for sibling in (
        "resolve_gpu_models",
        "ensure_gpu_profiles",
        "ensure_gpu_cards",
        "reconcile_unrealizable_gpu_profiles",
        "compute_gpu_targets",
    ):
        monkeypatch.setattr(
            mod.HypervisorsProcessed,
            sibling,
            classmethod(lambda cls, *a, **k: {}),
        )
    monkeypatch.setattr(
        mod.HypervisorsProcessed,
        "get_hypervisors_certs",
        classmethod(lambda cls: {"ca-cert.pem": "stub", "server-cert.pem": "stub"}),
    )
    yield {"mock_table": mock_table, "Processed": mod.HypervisorsProcessed}


def _nvidia_update_calls(stub):
    update_calls = stub[
        "mock_table"
    ].return_value.get.return_value.update.call_args_list
    return [
        call for call in update_calls if call.args and "nvidia_gpus" in call.args[0]
    ]


class TestNvidiaGpusPersist:
    def test_nvidia_gpus_written_verbatim_to_row(self, stub_hyper):
        result = stub_hyper["Processed"].hyper(
            "isard-hypervisor", "isard-hypervisor", nvidia_gpus=NVIDIA_GPUS
        )
        assert result["status"] is True
        calls = _nvidia_update_calls(stub_hyper)
        assert calls, (
            "hyper() must persist nvidia_gpus on the hypervisors row — "
            "HypervisorModel has no such field, so without this direct "
            "update the engine falls back to the legacy libvirt scan and "
            "the host drops out of GPU placement"
        )
        assert calls[-1].args[0] == {"nvidia_gpus": NVIDIA_GPUS}

    def test_no_nvidia_gpus_no_write(self, stub_hyper):
        result = stub_hyper["Processed"].hyper("isard-hypervisor", "isard-hypervisor")
        assert result["status"] is True
        assert not _nvidia_update_calls(stub_hyper)

    def test_persist_failure_does_not_abort_registration(self, stub_hyper):
        stub_hyper[
            "mock_table"
        ].return_value.get.return_value.update.return_value.run.side_effect = Exception(
            "rethink down mid-write"
        )
        result = stub_hyper["Processed"].hyper(
            "isard-hypervisor", "isard-hypervisor", nvidia_gpus=NVIDIA_GPUS
        )
        # Best-effort: registration must still succeed.
        assert result["status"] is True
