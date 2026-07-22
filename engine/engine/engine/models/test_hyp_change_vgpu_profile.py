# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
# License: AGPLv3

"""Pin the lazy-init paths in hyp.change_vgpu_profile.

The original code only seeded ``self.mdevs[pci_id][new_profile]`` for the
``passthrough`` profile. Switching to a MIG (or first-time vGPU) target
returned ``False`` with "mdevs data not found" because ``create_uuids`` only
populates the pool on the fresh-discovery branch and a cached load skips it.
Mirrors origin/main ``3369e30c5``.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from engine.models import hyp as hyp_mod
from engine.models.hyp import hyp


@pytest.fixture(autouse=True)
def _logs(monkeypatch):
    """``engine.services.log`` is stubbed by ``engine/engine/conftest.py``,
    so the module-level ``logs`` symbol pulled in via star-import is missing
    under pytest. Inject a real logger only for the duration of each test so
    the production ``logs.main.info(...)`` / ``logs.main.error(...)`` lines
    exercise without NameError."""
    fake_logs = MagicMock()
    fake_logs.main = logging.getLogger(__name__)
    monkeypatch.setattr(hyp_mod, "logs", fake_logs, raising=False)


def _build_hyp():
    """Construct a hyp instance bypassing the heavy __init__ (libvirt + ssh
    + threads). The test only exercises change_vgpu_profile against the
    populated dicts we set explicitly."""
    h = hyp.__new__(hyp)
    h.mdevs = {}
    h.info_nvidia = {}
    return h


@patch("engine.models.hyp.update_vgpu_uuids")
@patch("engine.models.hyp.update_table_field")
def test_change_vgpu_profile_lazy_seeds_mig_pool(mock_update_field, mock_update_uuids):
    """Switching to a MIG profile that exists in info.types but not yet in
    self.mdevs must lazy-init the pool via create_uuids and persist it."""
    h = _build_hyp()
    pci_id = "0000_3b_00_0"
    gpu_id = "hyp-test-" + pci_id
    h.info_nvidia[pci_id] = {
        "path": "/sys/bus/pci/devices/0000:3b:00.0",
        "sub_paths": False,
        "types": {
            "nvidia-mig-1g": {
                "mig": True,
                "max_instances": 7,
            }
        },
    }
    h.mdevs[pci_id] = {}
    seeded_uuids = {
        "uuid-a": {"type_id": "nvidia-mig-1g", "domain_started": False},
        "uuid-b": {"type_id": "nvidia-mig-1g", "domain_started": False},
    }
    h.create_uuids = MagicMock(return_value={"nvidia-mig-1g": seeded_uuids})

    # The downstream path-dependent flow (libvirt MIG flip, ssh) raises
    # because the hyp instance doesn't have id_hyp_rethink/conn/etc. — we
    # don't care, we only assert the lazy-init pool was persisted before
    # control reached the path-dependent block.
    try:
        h.change_vgpu_profile(gpu_id, "nvidia-mig-1g")
    except Exception:
        pass

    # Pool was seeded from create_uuids' return value.
    assert h.mdevs[pci_id]["nvidia-mig-1g"] == seeded_uuids
    h.create_uuids.assert_called_once()
    seed_arg = h.create_uuids.call_args[0][0]
    assert seed_arg["types"] == {
        "nvidia-mig-1g": h.info_nvidia[pci_id]["types"]["nvidia-mig-1g"]
    }
    # update_vgpu_uuids was invoked to persist the freshly seeded pool.
    mock_update_uuids.assert_called_once_with(gpu_id, h.mdevs[pci_id])


@patch("engine.models.hyp.update_vgpu_uuids")
@patch("engine.models.hyp.update_table_field")
def test_change_vgpu_profile_returns_false_when_profile_not_in_types(
    mock_update_field, mock_update_uuids
):
    """If the requested profile is neither already seeded nor present in
    info.types, change_vgpu_profile must return False (the operator needs
    a rediscovery, not a half-baked pool)."""
    h = _build_hyp()
    pci_id = "0000_3b_00_0"
    gpu_id = "hyp-test-" + pci_id
    h.info_nvidia[pci_id] = {"types": {}}
    h.mdevs[pci_id] = {}
    h.create_uuids = MagicMock()

    result = h.change_vgpu_profile(gpu_id, "nvidia-vgpu-unknown")

    assert result is False
    h.create_uuids.assert_not_called()
    mock_update_uuids.assert_not_called()


@patch("engine.models.hyp.update_vgpu_uuids")
@patch("engine.models.hyp.update_table_field")
def test_change_vgpu_profile_returns_false_when_create_uuids_returns_empty(
    mock_update_field, mock_update_uuids
):
    """create_uuids may legitimately return an empty pool (e.g. when the
    sysfs path is missing). Surface that as False instead of leaving an empty
    pool that downstream code would treat as success."""
    h = _build_hyp()
    pci_id = "0000_3b_00_0"
    gpu_id = "hyp-test-" + pci_id
    h.info_nvidia[pci_id] = {
        "types": {"nvidia-mig-1g": {"mig": True, "max_instances": 7}},
    }
    h.mdevs[pci_id] = {}
    h.create_uuids = MagicMock(return_value={})

    result = h.change_vgpu_profile(gpu_id, "nvidia-mig-1g")

    assert result is False
    mock_update_uuids.assert_not_called()


@patch("engine.models.hyp.update_vgpu_uuids")
@patch("engine.models.hyp.update_table_field")
def test_change_vgpu_profile_defers_mig_backed_qprofile_via_sibling_gi(
    mock_update_field, mock_update_uuids, caplog
):
    """A MIG-backed vGPU profile ("<slices>_<mem>Q", e.g. "1_24Q") is NOT in
    info.types while the card is in vGPU mode — its mdev type only appears once
    MIG is enabled and the GIs exist. The pre-fix code bailed here with
    "profile not in info.types" -> 500 (the routing bug that forced the carve
    down the plain-GI compute path and wedged the host). The fix recognises it
    via the sibling "<slices>g.<mem>gb+gfx" GI (enumerated in every mode) and
    DEFERS the pool seed to the MIG carve instead of returning False. This pins
    that the deferral fires for a real MIG-backed target and is NOT taken for a
    bogus one."""
    h = _build_hyp()
    pci_id = "0000_3b_00_0"
    gpu_id = "hyp-test-" + pci_id
    # vGPU-mode card: the "1_24Q" mdev type is absent, but the sibling GI
    # "1g.24gb+gfx" is enumerated with its durable GPU-instance profile id.
    h.info_nvidia[pci_id] = {
        "path": "/sys/bus/pci/devices/0000:3b:00.0",
        "sub_paths": False,
        "types": {
            "1g.24gb+gfx": {
                "mig": True,
                "mig_profile_id": 47,
                "mig_count": 4,
            }
        },
    }
    h.mdevs[pci_id] = {}
    h.create_uuids = MagicMock()

    # Downstream (MIG carve / ssh) raises because the bare hyp lacks
    # conn/hostname — we only care that the deferral gate let control through
    # rather than returning False at "profile not in info.types".
    with caplog.at_level(logging.INFO):
        try:
            h.change_vgpu_profile(gpu_id, "1_24Q")
        except Exception:
            pass

    msgs = "\n".join(r.getMessage() for r in caplog.records)
    assert "deferring pool seed to the MIG carve" in msgs
    assert "profile not in info.types" not in msgs
    # The sibling lookup must NOT have force-bailed: no early changing_to_profile
    # reset for the "not in info.types" reason before the carve was attempted.
    h.create_uuids.assert_not_called()


@patch("engine.models.hyp.update_vgpu_uuids")
@patch("engine.models.hyp.update_table_field")
def test_change_vgpu_profile_bails_when_qprofile_has_no_sibling_gi(
    mock_update_field, mock_update_uuids, caplog
):
    """The deferral is gated on a real sibling "<slices>g.<mem>gb+gfx" GI being
    present. A "<n>_<m>Q"-shaped string with NO matching GI (card genuinely
    can't back it) must still bail with "profile not in info.types" -> False,
    not silently fall through to a carve that can't work."""
    h = _build_hyp()
    pci_id = "0000_3b_00_0"
    gpu_id = "hyp-test-" + pci_id
    h.info_nvidia[pci_id] = {
        "path": "/sys/bus/pci/devices/0000:3b:00.0",
        "types": {},  # no sibling +gfx GI
    }
    h.mdevs[pci_id] = {}
    h.create_uuids = MagicMock()

    with caplog.at_level(logging.INFO):
        result = h.change_vgpu_profile(gpu_id, "9_99Q")

    assert result is False
    msgs = "\n".join(r.getMessage() for r in caplog.records)
    assert "profile not in info.types" in msgs
    assert "deferring pool seed" not in msgs
    h.create_uuids.assert_not_called()
