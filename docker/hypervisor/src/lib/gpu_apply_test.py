"""Unit tests for the pure decision/command core of gpu_apply.

Imported directly (path-inserted). gpu_apply loads the shared builders from
/src/_common (container) or the repo's component/_common/src (here). The apply
orchestration is driven through a STATEFUL host fake whose run() applies the
driver/mdev side effects the real sysfs writes would, so the post-apply readback
gate, VF-carving and post-prep type resolution are genuinely exercised (the old
fakes masked those by returning fixed/unreachable states).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import gpu_apply as ga  # noqa: E402


# --- current_profile_from_state --------------------------------------------
@pytest.mark.parametrize(
    "driver,mig,live,expected",
    [
        ("vfio-pci", "[N/A]", None, "passthrough"),
        ("nvidia", "Disabled", "4Q", "4Q"),
        ("nvidia", "Enabled", "1g.10gb", "1g.10gb"),
        ("nvidia", "Enabled", None, ga.MIG_CURRENT),  # MIG mode, uncarved
        ("nvidia", "Disabled", None, None),  # nvidia-bound, uncarved
        (None, None, None, None),
    ],
)
def test_current_profile_from_state(driver, mig, live, expected):
    assert ga.current_profile_from_state(driver, mig, live) == expected


# --- decide_apply_action ----------------------------------------------------
def test_decide_noop_when_equal():
    assert ga.decide_apply_action("4Q", "4Q", busy=False) == "noop"


def test_decide_passthrough_default_when_target_none():
    assert ga.decide_apply_action("passthrough", None, busy=False) == "noop"
    assert ga.decide_apply_action("4Q", None, busy=False) == "apply"


def test_decide_skipped_busy_takes_precedence_over_apply():
    assert ga.decide_apply_action("4Q", "passthrough", busy=True) == "skipped_busy"


def test_decide_apply_when_differs_and_idle():
    assert ga.decide_apply_action(None, "4Q", busy=False) == "apply"


# --- small pure builders ----------------------------------------------------
def test_build_mdev_create_cmd():
    cmd = ga.build_mdev_create_cmd(
        "/sys/bus/pci/devices/0000:c5:00.4", "nvidia-713", "u-1"
    )
    assert cmd == (
        "echo u-1 > '/sys/bus/pci/devices/0000:c5:00.4/mdev_supported_types/nvidia-713/create'"
    )


def test_new_mdev_pool_entry_schema():
    uid, entry = ga.new_mdev_pool_entry("0000:c5:00.4", "nvidia-713")
    assert isinstance(uid, str) and len(uid) == 36
    assert entry == {
        "pci_mdev_id": "0000:c5:00.4",
        "type_id": "nvidia-713",
        "created": True,
        "domain_started": False,
        "domain_reserved": False,
    }
    _, mig_entry = ga.new_mdev_pool_entry(
        "0000:c5:00.4", "nvidia-19", mig=True, mig_profile_id=19
    )
    assert mig_entry["mig"] is True and mig_entry["mig_profile_id"] == 19


def test_target_suffix_and_is_actionable():
    assert ga.target_suffix(None) == "passthrough"
    assert ga.target_suffix({"target_profile": "1-2Q"}) == "1_2Q"  # canonicalized
    assert ga.is_actionable(None) is True
    assert ga.is_actionable({"action": "apply"}) is True
    assert ga.is_actionable({"action": "seed_and_apply"}) is True
    assert ga.is_actionable({"action": "keep_current"}) is True
    assert ga.is_actionable({"action": "skip_fault"}) is False
    assert ga.is_actionable({"action": "skip_retry"}) is False


# --- robustness guards (R1) -------------------------------------------------
def test_out_helper_guards_empty_result():
    assert ga._out([]) == ""
    assert ga._out(None) == ""
    assert ga._out([{"err": "e"}]) == ""  # missing "out" key
    assert ga._out([{"out": "x\n"}]) == "x\n"


def test_readers_tolerate_empty_run():
    # A run() that returns fewer entries than commands (or none) must not
    # IndexError on res[0] -- the readers degrade to None/[]/0.
    empty = lambda cmds, timeout=0: []  # noqa: E731
    assert ga._read_driver("0000:c5:00.0", empty) is None
    assert ga._read_mig_mode("0000:c5:00.0", empty) is None
    assert ga._enumerate_vf_sub_paths("0000:c5:00.0", empty) == []
    assert ga._live_mdev_count("0000:c5:00.0", empty) == 0


def test_apply_errors_on_carve_result_count_mismatch(monkeypatch):
    # A run() that returns fewer results than carve commands must ERROR the card
    # (not silently zip-truncate and under-record the mdev pool).
    h = _Host(driver="nvidia", profiles=[{"name": "A40-4Q", "type_id": "nvidia-558"}])
    _patch_host(monkeypatch, h)
    real_run = h.run

    def short_run(cmds, timeout=120):
        res = real_run(cmds, timeout=timeout)
        if any(c.rstrip().endswith("/create'") for c in cmds):
            return res[:-1]  # drop one result -> length mismatch
        return res

    gpu = {
        "pci_bus_id": "0000:c5:00.0",
        "sub_paths": ["/sys/bus/pci/devices/0000:c5:00.1"],
        "sriov_totalvfs": 1,
    }
    rep = ga.apply_target(
        gpu, {"target_profile": "4Q", "action": "apply"}, run=short_run
    )
    assert rep["result"] == "error"
    assert "count" in rep["error"]


def test_apply_recovers_orphaned_pf_before_applying(monkeypatch):
    # A PF bound to NO driver (orphaned by a transition interrupted mid-flight,
    # e.g. a restart/crash between the vfio unbind and the nvidia rebind) must be
    # recovered to nvidia BEFORE the apply proceeds -- not operated on as a dead
    # PF (which fails). The card starts orphaned (driver=None); the apply must
    # rebind it and then carve the requested vGPU profile.
    h = _Host(
        driver=None,
        mig="Disabled",
        profiles=[{"name": "A40-4Q", "type_id": "nvidia-558"}],
    )
    h.vf_paths = ["/sys/bus/pci/devices/0000:c5:00.1"]
    _patch_host(monkeypatch, h)
    gpu = {
        "pci_bus_id": "0000:c5:00.0",
        "sub_paths": ["/sys/bus/pci/devices/0000:c5:00.1"],
        "sriov_totalvfs": 1,
    }
    rep = ga.apply_target(gpu, {"target_profile": "4Q", "action": "apply"}, run=h.run)
    assert any("drivers/nvidia/bind" in c for c in h.cmds)  # recovery ran
    assert h.driver == "nvidia"  # no longer orphaned
    assert rep["result"] == "applied", rep


# --- apply_target orchestration (stateful host fake) ------------------------
class _Host:
    """Simulates a card's observable state across an apply. run() applies the
    driver/mdev side effects the real sysfs writes would, so the readback gate
    and post-prep resolution are exercised for real. apply_works=False simulates
    a silently-failed sysfs sequence (the critical-gate case)."""

    def __init__(
        self,
        driver,
        mig="Disabled",
        live=None,
        busy=False,
        profiles=None,
        apply_works=True,
    ):
        self.driver = driver
        self.mig = mig
        self.live = live
        self.busy = busy
        self.profiles = profiles or []
        self.apply_works = apply_works
        self.mdev_count = 0
        self.cmds = []
        # VF paths a MIG->vGPU teardown re-creates (sriov-manage -e); the carve
        # re-enumerates them since MIG-mode discovery reported none.
        self.vf_paths = []

    def run(self, cmds, timeout=120):
        self.cmds.extend(cmds)
        if self.apply_works:
            for c in cmds:
                if "driver_override" in c and "vfio-pci" in c:
                    self.driver = "vfio-pci"
                elif "drivers/nvidia/bind" in c:
                    self.driver = "nvidia"
                if c.rstrip().endswith("/create'"):
                    self.mdev_count += 1
                if "-mig 1" in c:
                    self.mig = "Enabled"
                elif "-mig 0" in c:
                    self.mig = "Disabled"
        return [{"out": "", "err": ""} for _ in cmds]


def _patch_host(monkeypatch, host):
    monkeypatch.setattr(ga, "_read_driver", lambda b, r: host.driver)
    monkeypatch.setattr(ga, "_read_mig_mode", lambda b, r: host.mig)
    monkeypatch.setattr(ga, "_live_mdev_suffix", lambda b, r: host.live)
    monkeypatch.setattr(ga, "_card_busy", lambda p: host.busy)
    # mdev types are only visible while nvidia-bound AND on the VFs, mirroring
    # real SR-IOV / datacenter cards: a resolve attempted while still vfio-bound
    # sees nothing, and the PF (bdf ending ".0") exposes no mdev types -- only
    # the VFs do. So a MIG->vGPU carve must re-enumerate the VFs, not probe the PF.
    monkeypatch.setattr(
        ga,
        "_live_profiles",
        lambda b: (
            [] if (host.driver == "vfio-pci" or b.endswith(".0")) else host.profiles
        ),
    )
    monkeypatch.setattr(
        ga, "_live_mdev_count", lambda b, r, sub_paths=None: host.mdev_count
    )
    monkeypatch.setattr(ga, "_enumerate_vf_sub_paths", lambda b, r: host.vf_paths)


def test_apply_noop_when_already_target(monkeypatch):
    h = _Host(driver="vfio-pci")
    _patch_host(monkeypatch, h)
    rep = ga.apply_target(
        {"pci_bus_id": "0000:c5:00.0"},
        {"target_profile": "passthrough", "action": "apply"},
        run=h.run,
    )
    assert rep["result"] == "noop"
    assert h.cmds == []  # no host mutation on a no-op


def test_apply_noop_and_busy_carry_mdevs_reset_at(monkeypatch):
    # noop / skipped_busy must carry mdevs_reset_at so the API re-pins
    # mdevs_last_synced_at -> the engine confirms instead of running the
    # authoritative rebuild that would stop a still-alive desktop.
    h = _Host(driver="vfio-pci")
    _patch_host(monkeypatch, h)
    gpu = {"pci_bus_id": "0000:c5:00.0", "mdevs_reset_at": "2026-06-05T00:00:00"}
    noop = ga.apply_target(
        gpu, {"target_profile": "passthrough", "action": "apply"}, run=h.run
    )
    assert noop["result"] == "noop"
    assert noop["mdevs_reset_at"] == "2026-06-05T00:00:00"

    hb = _Host(driver="nvidia", live="4Q", busy=True)
    hb_gpu = {"pci_bus_id": "0000:c5:00.0", "mdevs_reset_at": "2026-06-05T00:00:00"}
    _patch_host(monkeypatch, hb)
    busy = ga.apply_target(
        hb_gpu, {"target_profile": "passthrough", "action": "apply"}, run=hb.run
    )
    assert busy["result"] == "skipped_busy"
    assert busy["mdevs_reset_at"] == "2026-06-05T00:00:00"


def test_apply_skipped_when_busy(monkeypatch):
    h = _Host(driver="nvidia", live="4Q", busy=True)
    _patch_host(monkeypatch, h)
    rep = ga.apply_target(
        {"pci_bus_id": "0000:c5:00.0"},
        {"target_profile": "passthrough", "action": "apply"},
        run=h.run,
    )
    assert rep["result"] == "skipped_busy"
    assert h.cmds == []


def test_apply_advisory_skip(monkeypatch):
    h = _Host(driver="nvidia", live="4Q")
    _patch_host(monkeypatch, h)
    rep = ga.apply_target(
        {"pci_bus_id": "0000:c5:00.0"},
        {"target_profile": "8Q", "action": "skip_fault"},
        run=h.run,
    )
    assert rep["result"] == "skipped_advisory"
    assert h.cmds == []


def test_apply_passthrough_succeeds_and_gates_on_driver(monkeypatch):
    h = _Host(driver="nvidia", live=None)
    _patch_host(monkeypatch, h)
    gpu = {"pci_bus_id": "0000:c5:00.0", "sriov_totalvfs": 16, "sriov_numvfs": 16}
    rep = ga.apply_target(
        gpu, {"target_profile": "passthrough", "action": "apply"}, run=h.run
    )
    assert rep["result"] == "applied"
    assert rep["binding"] == "vfio-pci"
    assert "mknod /dev/vfio/$IOMMU_GROUP" in "\n".join(h.cmds)
    # Reports ONE bookable passthrough pool entry (not an empty pool): the
    # engine's no-fight confirm path needs a created==True slot or the card is
    # unbookable. type_id is the "passthrough" sentinel (never echoed to sysfs).
    pool = rep["mdevs"]["passthrough"]
    assert len(pool) == 1
    (entry,) = pool.values()
    assert entry["type_id"] == "passthrough"
    assert entry["created"] is True
    assert entry["pci_mdev_id"] == "0000:c5:00.0"


def test_apply_passthrough_to_vgpu_reenumerates_vfs_when_subpaths_empty(monkeypatch):
    # Runtime case (engine-invoked CLI): the descriptor is built read-only while
    # the card is still vfio-bound, so its VFs are torn down and sub_paths is
    # empty. The vGPU prep's unbind re-enables the VFs; the carve must
    # RE-ENUMERATE them (not fall back to the empty PF and hard-error).
    h = _Host(
        driver="vfio-pci",
        live=None,
        profiles=[{"name": "A40-4Q", "type_id": "nvidia-558"}],
    )
    h.vf_paths = [f"/sys/bus/pci/devices/0000:c5:00.{i}" for i in range(4, 7)]  # 3 VFs
    _patch_host(monkeypatch, h)
    gpu = {"pci_bus_id": "0000:c5:00.0", "sriov_totalvfs": 16}  # NO sub_paths
    rep = ga.apply_target(gpu, {"target_profile": "4Q", "action": "apply"}, run=h.run)
    assert rep["result"] == "applied"
    assert rep["binding"] == "nvidia"
    assert len(rep["mdevs"]["4Q"]) == 3  # one mdev per RE-ENUMERATED VF


def test_apply_passthrough_reports_error_when_bind_silently_fails(monkeypatch):
    # CRITICAL gate: sysfs sequence "ran" but driver never became vfio-pci.
    h = _Host(driver="nvidia", live=None, apply_works=False)
    _patch_host(monkeypatch, h)
    gpu = {"pci_bus_id": "0000:c5:00.0", "sriov_totalvfs": 16, "sriov_numvfs": 16}
    rep = ga.apply_target(
        gpu, {"target_profile": "passthrough", "action": "apply"}, run=h.run
    )
    assert rep["result"] == "error"  # NOT 'applied' -> ingest won't persist a lie
    assert "driver" in rep["error"]


def test_apply_vgpu_sriov_carves_one_mdev_per_vf(monkeypatch):
    # SR-IOV: PF exposes no mdev types; types live on the VFs (sub_paths).
    h = _Host(
        driver="nvidia",
        live=None,
        profiles=[{"name": "A40-4Q", "type_id": "nvidia-558"}],
    )
    _patch_host(monkeypatch, h)
    vfs = [f"/sys/bus/pci/devices/0000:c5:00.{i}" for i in range(4, 8)]
    gpu = {
        "pci_bus_id": "0000:c5:00.0",  # PF
        "sriov_totalvfs": 16,
        "sriov_numvfs": 16,
        "sub_paths": vfs,
    }
    rep = ga.apply_target(gpu, {"target_profile": "4Q", "action": "apply"}, run=h.run)
    assert rep["result"] == "applied"
    assert len(rep["mdevs"]["4Q"]) == 4  # one per VF
    assert {e["pci_mdev_id"] for e in rep["mdevs"]["4Q"].values()} == {
        os.path.basename(v) for v in vfs
    }
    creates = [c for c in h.cmds if "/create'" in c]
    assert len(creates) == 4
    assert all(any(vf in c for vf in vfs) for c in creates)  # created on the VFs


def test_apply_vgpu_from_passthrough_resolves_after_rebind(monkeypatch):
    # While vfio-bound, _live_profiles returns [] (mirrors hardware). The fix
    # runs the unbind FIRST, then resolves -> must succeed, proving resolution
    # happens post-rebind (the pre-fix bug would error 'not exposed').
    h = _Host(
        driver="vfio-pci",
        live=None,
        profiles=[{"name": "A40-4Q", "type_id": "nvidia-558"}],
    )
    _patch_host(monkeypatch, h)
    vfs = [f"/sys/bus/pci/devices/0000:c5:00.{i}" for i in range(4, 6)]
    gpu = {"pci_bus_id": "0000:c5:00.0", "sriov_totalvfs": 16, "sub_paths": vfs}
    rep = ga.apply_target(gpu, {"target_profile": "4Q", "action": "apply"}, run=h.run)
    assert rep["result"] == "applied"
    assert rep["binding"] == "nvidia"
    # unbind ran before the first create
    joined = h.cmds
    first_create = next(i for i, c in enumerate(joined) if "/create'" in c)
    assert any(
        "drivers/nvidia/bind" in c for c in joined[:first_create]
    )  # rebound before carving


def test_apply_vgpu_reports_error_when_carve_does_not_materialise(monkeypatch):
    # Driver ok (nvidia) but no live mdev appeared -> must be 'error', not applied.
    h = _Host(
        driver="nvidia",
        live=None,
        profiles=[{"name": "A40-4Q", "type_id": "nvidia-558"}],
        apply_works=False,  # creates don't increment mdev_count
    )
    _patch_host(monkeypatch, h)
    gpu = {
        "pci_bus_id": "0000:c5:00.0",
        "sub_paths": ["/sys/bus/pci/devices/0000:c5:00.4"],
    }
    rep = ga.apply_target(gpu, {"target_profile": "4Q", "action": "apply"}, run=h.run)
    assert rep["result"] == "error"
    assert "materialise" in rep["error"]


def test_apply_mig_current_card_to_passthrough_emits_mig_teardown(monkeypatch):
    # Card physically in MIG mode (mig=Enabled, uncarved) -> target passthrough
    # must route through the MIG teardown (-mig 0) before the vfio bind.
    h = _Host(driver="nvidia", mig="Enabled", live=None)
    _patch_host(monkeypatch, h)
    gpu = {
        "pci_bus_id": "0000:c5:00.0",
        "sriov_totalvfs": 0,
        "mig_profiles": [{"name": "1g.10gb", "profile_id": 19}],
    }
    rep = ga.apply_target(
        gpu, {"target_profile": "passthrough", "action": "apply"}, run=h.run
    )
    joined = "\n".join(h.cmds)
    assert "-mig 0" in joined  # MIG teardown emitted (old_is_mig honored)
    assert "--gpu-reset" in joined
    # The teardown is only the prep: apply must FALL THROUGH to the vfio bind and
    # actually land on passthrough, not stop after disabling MIG.
    assert rep["result"] == "applied"
    assert rep["binding"] == "vfio-pci"


def test_apply_mig_current_card_to_vgpu_completes_carve(monkeypatch):
    # MIG-mode card -> vGPU target. A MIG-mode card has NO live SR-IOV VFs at
    # discovery (sub_paths omitted); the teardown's sriov-manage -e re-creates
    # them, so the carve must RE-ENUMERATE the now-live VFs and carve on them
    # (datacenter MIG cards expose mdev types on the VFs, not the PF). The
    # early-return bug stopped after teardown (0 mdevs); the stale-sub_paths bug
    # carved on a None PF and hard-errored.
    h = _Host(
        driver="nvidia",
        mig="Enabled",
        live=None,
        profiles=[{"name": "A40-4Q", "type_id": "nvidia-558"}],
    )
    # VFs become visible only after the teardown re-enables SR-IOV.
    h.vf_paths = [f"/sys/bus/pci/devices/0000:c5:00.{i}" for i in range(4, 6)]
    _patch_host(monkeypatch, h)
    gpu = {
        "pci_bus_id": "0000:c5:00.0",
        "sriov_totalvfs": 16,
        # NO sub_paths: MIG-mode discovery does not surface VFs.
        "mig_profiles": [{"name": "1g.10gb", "profile_id": 19}],
    }
    rep = ga.apply_target(gpu, {"target_profile": "4Q", "action": "apply"}, run=h.run)
    joined = "\n".join(h.cmds)
    assert "-mig 0" in joined  # MIG torn down first
    assert rep["result"] == "applied"
    assert len(rep["mdevs"]["4Q"]) == 2  # one mdev per RE-ENUMERATED VF
    assert {e["pci_mdev_id"] for e in rep["mdevs"]["4Q"].values()} == {
        "0000:c5:00.4",
        "0000:c5:00.5",
    }


def test_apply_to_mig_succeeds_when_mode_enables(monkeypatch):
    # Plain nvidia card -> MIG target: -mig 1 takes (mig=Enabled) -> applied.
    h = _Host(driver="nvidia", mig="Disabled", live=None)
    _patch_host(monkeypatch, h)
    gpu = {
        "pci_bus_id": "0000:c5:00.0",
        "sriov_totalvfs": 0,
        "mig_profiles": [{"name": "1g.10gb", "profile_id": 19}],
    }
    rep = ga.apply_target(
        gpu, {"target_profile": "1g.10gb", "action": "apply"}, run=h.run
    )
    assert rep["result"] == "applied"
    assert "1g.10gb" in rep["mdevs"]


def test_apply_mig_target_errors_when_mig_enable_silently_fails(monkeypatch):
    # -mig 1 does not take (mig stays Disabled). The driver readback is a
    # tautology for MIG (card stays nvidia), so only the mig.mode gate catches
    # this -> must report 'error', never a silent 'applied'.
    h = _Host(driver="nvidia", mig="Disabled", live=None, apply_works=False)
    _patch_host(monkeypatch, h)
    gpu = {
        "pci_bus_id": "0000:c5:00.0",
        "sriov_totalvfs": 0,
        "mig_profiles": [{"name": "1g.10gb", "profile_id": 19}],
    }
    rep = ga.apply_target(
        gpu, {"target_profile": "1g.10gb", "action": "apply"}, run=h.run
    )
    assert rep["result"] == "error"
    assert "did not take" in rep["error"]


def test_apply_mig_carve_entry_has_mig_metadata(monkeypatch):
    # The injected mig_profiles (the gpu_apply_cli seed for a MIG-disabled card)
    # drive the carve; the pool entry must carry mig=True + mig_profile_id so the
    # engine ingest persists a correct MIG pool.
    h = _Host(driver="nvidia", mig="Disabled", live=None)
    _patch_host(monkeypatch, h)
    gpu = {
        "pci_bus_id": "0000:c5:00.0",
        "sriov_totalvfs": 0,
        "mig_profiles": [{"name": "1g.10gb", "profile_id": 19}],
    }
    rep = ga.apply_target(
        gpu, {"target_profile": "1g.10gb", "action": "apply"}, run=h.run
    )
    assert rep["result"] == "applied"
    entry = next(iter(rep["mdevs"]["1g.10gb"].values()))
    assert entry["mig"] is True
    assert entry["mig_profile_id"] == 19


def test_apply_targets_orders_non_mig_before_mig(monkeypatch):
    order = []
    monkeypatch.setattr(
        ga,
        "apply_target",
        lambda gpu, target, run=None: order.append(gpu["pci_bus_id"])
        or {"result": "applied"},
    )
    gpus = [
        {  # MIG target listed FIRST in the input...
            "pci_bus_id": "0000:c5:00.0",
            "vgpu_profiles": [],
            "mig_profiles": [{"name": "1g.10gb", "profile_id": 19}],
        },
        {"pci_bus_id": "0000:06:00.0", "vgpu_profiles": [{"name": "A16-4Q"}]},
    ]
    targets = {
        "0000:c5:00.0": {"target_profile": "1g.10gb", "action": "apply"},
        "0000:06:00.0": {"target_profile": "4Q", "action": "apply"},
    }
    ga.apply_targets(gpus, targets)
    # ...but the non-MIG card is applied first (MIG --gpu-reset comes last).
    assert order == ["0000:06:00.0", "0000:c5:00.0"]
