"""Unit tests for the pure decision/command core of gpu_apply.

Imported directly (path-inserted). gpu_apply loads the shared builders from
/src/isardvdi_common/lib (container) or the repo path (here). The apply
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
        numvfs=0,
        avail=None,
    ):
        self.driver = driver
        self.mig = mig
        self.live = live
        self.busy = busy
        self.profiles = profiles or []
        self.apply_works = apply_works
        self.numvfs = numvfs
        # VF basename -> available_instances string the carve readback should see
        # (default: unset -> "" -> treated as usable, the pre-guard behaviour).
        self.avail = avail or {}
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
        # The warm-repartition detection reads live sriov_numvfs via run(); the
        # carve reads each VF's available_instances before creating its mdev.
        out = []
        for c in cmds:
            if "sriov_numvfs" in c:
                out.append({"out": f"{self.numvfs}\n", "err": ""})
            elif "available_instances" in c:
                val = next((v for vf, v in self.avail.items() if vf in c), "")
                out.append({"out": f"{val}", "err": ""})
            else:
                out.append({"out": "", "err": ""})
        return out


def _patch_host(monkeypatch, host):
    # Stub the post-restart settle waits so the retry/poll path runs instantly.
    monkeypatch.setattr(ga, "_SLEEP", lambda *a, **k: None)
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


def test_deliberate_busy_quiesce_fail_aborts_without_unbind(monkeypatch):
    # THE anti-wedge assertion: a deliberate change on a busy card whose holders
    # cannot be cleared must report teardown_blocked and emit NO unbind /
    # sriov-manage -d / -mig teardown -- unbinding an in-use vfio device wedges
    # the PF in uninterruptible D-state.
    h = _Host(driver="nvidia", live="4Q", busy=True)
    _patch_host(monkeypatch, h)
    monkeypatch.setattr(
        ga, "_quiesce_card", lambda gpu, run: (False, "card 0000:c5:00.0 still held")
    )
    rep = ga.apply_target(
        {"pci_bus_id": "0000:c5:00.0"},
        {"target_profile": "passthrough", "action": "apply"},
        run=h.run,
        deliberate=True,
    )
    assert rep["result"] == "teardown_blocked"
    assert "still held" in rep["error"]
    joined = "\n".join(h.cmds)
    assert "unbind" not in joined
    assert "sriov-manage -d" not in joined
    assert "-mig 0" not in joined


def test_deliberate_busy_quiesce_ok_proceeds(monkeypatch):
    # When the holders ARE cleared, the deliberate change proceeds to apply.
    h = _Host(driver="nvidia", live=None, busy=True)
    _patch_host(monkeypatch, h)
    monkeypatch.setattr(ga, "_quiesce_card", lambda gpu, run: (True, "cleared"))
    gpu = {"pci_bus_id": "0000:c5:00.0", "sriov_totalvfs": 16, "sriov_numvfs": 16}
    rep = ga.apply_target(
        gpu,
        {"target_profile": "passthrough", "action": "apply"},
        run=h.run,
        deliberate=True,
    )
    assert rep["result"] == "applied"
    assert rep["binding"] == "vfio-pci"


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


def test_apply_self_heals_when_driver_settles_after_carve(monkeypatch):
    # Post-restart race: the carve succeeds but the PF driver readback is None
    # right after (the kernel re-attaches nvidia asynchronously after the
    # gpu-reset/SR-IOV cycle). The settle-poll/retry must let it settle and
    # report 'applied' instead of leaving the card uncarved with a phantom pool.
    h = _Host(
        driver="nvidia",
        live=None,
        profiles=[{"name": "A40-4Q", "type_id": "nvidia-558"}],
    )
    h.vf_paths = [f"/sys/bus/pci/devices/0000:c5:00.{i}" for i in range(4, 7)]
    _patch_host(monkeypatch, h)
    # top detection sees nvidia; the first post-apply readback is None, then it
    # settles to nvidia on the next poll.
    seq = iter(["nvidia", None, "nvidia"])
    monkeypatch.setattr(ga, "_read_driver", lambda b, r: next(seq, "nvidia"))
    gpu = {"pci_bus_id": "0000:c5:00.0", "sriov_totalvfs": 16}
    rep = ga.apply_target(gpu, {"target_profile": "4Q", "action": "apply"}, run=h.run)
    assert rep["result"] == "applied", rep
    assert rep["binding"] == "nvidia"


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


def test_apply_vgpu_vfio_variant_writes_current_vgpu_type_per_vf(monkeypatch):
    # Vendor-specific VFIO framework (Ubuntu 24.04+): no mdev create. Each VF's
    # vGPU is created by writing the numeric type-id to current_vgpu_type, and
    # the pool entry is keyed by VF BDF (not a UUID).
    h = _Host(driver="nvidia", live=None)
    _patch_host(monkeypatch, h)
    # vfio profiles carry a NUMERIC type_id (not nvidia-NNN); resolution reads
    # creatable_vgpu_types via _live_profiles_vfio, not the mdev _live_profiles.
    monkeypatch.setattr(
        ga, "_live_profiles_vfio", lambda b: [{"name": "A16-2Q", "type_id": "694"}]
    )
    # Materialisation check must count live vGPUs (current_vgpu_type != 0), not
    # mdevs (there are none on this framework).
    monkeypatch.setattr(
        ga,
        "_live_vgpu_count",
        lambda sub_paths, run: sum(
            1 for c in h.cmds if "current_vgpu_type" in c and "echo 0 " not in c
        ),
    )
    vfs = [f"/sys/bus/pci/devices/0000:c5:00.{i}" for i in range(4, 7)]
    gpu = {
        "pci_bus_id": "0000:c5:00.0",
        "framework": "vfio_variant",
        "sriov_totalvfs": 64,
        "sriov_numvfs": 64,
        "sub_paths": vfs,
    }
    rep = ga.apply_target(gpu, {"target_profile": "2Q", "action": "apply"}, run=h.run)
    assert rep["result"] == "applied"
    # one pool entry per VF, keyed by VF BDF, each tagged vfio_variant
    pool = rep["mdevs"]["2Q"]
    assert set(pool.keys()) == {os.path.basename(v) for v in vfs}
    assert all(e["framework"] == "vfio_variant" for e in pool.values())
    assert all(e["vf_bdf"] == k for k, e in pool.items())
    # carve wrote current_vgpu_type=694 on each VF, NO mdev create
    sets = [c for c in h.cmds if "current_vgpu_type" in c and "echo 694" in c]
    assert len(sets) == 3
    assert not any("/create'" in c for c in h.cmds)
    # RECARVE SAFETY: every VF is cleared to 0 BEFORE any type is set (a VF won't
    # accept a new type while it holds one, and the new profile won't fit until
    # the whole card's framebuffer is freed).
    clears = [c for c in h.cmds if "current_vgpu_type" in c and "echo 0 " in c]
    assert len(clears) == 3  # one per VF
    first_set = next(i for i, c in enumerate(h.cmds) if "echo 694" in c)
    assert all(
        h.cmds.index(c) < first_set for c in clears
    )  # all clears precede the first set


def test_apply_vgpu_vfio_variant_mig_backed_tags_pool_entries(monkeypatch):
    # MIG-backed vGPU on the vendor-specific VFIO framework (parity with 22.04
    # MIG): the framework-agnostic GI carve (enable MIG + sriov-manage -e +
    # -cgi <gfx> -C) runs first, then the per-VF carve writes current_vgpu_type
    # (NOT mdev create) on `mig_count` VFs, and EACH pool entry must carry
    # mig=True + mig_profile_id so bookings/reconcile track it as MIG-backed.
    h = _Host(
        driver="nvidia",
        mig="Disabled",
        live=None,
        profiles=[{"name": "RTXPro6000BlackwellDC-1_24Q", "type_id": "nvidia-1561"}],
    )
    h.vf_paths = [f"/sys/bus/pci/devices/0000:c1:00.{i}" for i in range(2, 8)]  # 6 VFs
    _patch_host(monkeypatch, h)
    # vfio resolution reads creatable_vgpu_types (numeric type-id), not mdev dirs.
    monkeypatch.setattr(
        ga,
        "_live_profiles_vfio",
        lambda b: [{"name": "RTXPro6000BlackwellDC-1_24Q", "type_id": "1561"}],
    )
    monkeypatch.setattr(
        ga,
        "_live_vgpu_count",
        lambda sub_paths, run: sum(
            1 for c in h.cmds if "current_vgpu_type" in c and "echo 0 " not in c
        ),
    )
    gpu = {
        "pci_bus_id": "0000:c1:00.0",
        "framework": "vfio_variant",
        "sriov_totalvfs": 48,
        "vgpu_profiles": [
            {
                "name": "RTXPro6000BlackwellDC-1_24Q",
                "type_id": "nvidia-1561",
                "mig": True,
                "mig_profile_id": 47,
                "mig_count": 4,
            }
        ],
    }
    rep = ga.apply_target(
        gpu, {"target_profile": "1_24Q", "action": "apply"}, run=h.run
    )
    assert rep["result"] == "applied", rep
    pool = rep["mdevs"]["1_24Q"]
    assert len(pool) == 4  # capped at mig_count, not the 6 VFs
    e = next(iter(pool.values()))
    assert e["mig"] is True and e["mig_profile_id"] == 47  # MIG metadata carried
    assert e["framework"] == "vfio_variant" and "vf_bdf" in e  # vfio entry shape
    # GI carve happened (framework-agnostic) and the carve used current_vgpu_type
    assert any("-cgi 47,47,47,47 -C" in c for c in h.cmds)
    assert any("sriov-manage -e" in c for c in h.cmds)
    assert [c for c in h.cmds if "current_vgpu_type" in c and "echo 1561" in c]
    assert not any("/create'" in c for c in h.cmds)  # NOT the legacy mdev create


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
        lambda gpu, target, run=None, deliberate=False: order.append(gpu["pci_bus_id"])
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


def test_apply_mig_vgpu_carves_gfx_gis_and_caps_mdevs_per_count(monkeypatch):
    # A MIG-backed vGPU target (annotated mig_profile_id=47, mig_count=4) must:
    #  - create 4 +gfx GPU-instances with compute instances (-cgi 47,..,47 -C),
    #  - re-enable SR-IOV, and
    #  - carve exactly `mig_count` mdevs (one per GI), capped even when more VFs
    #    exist, each tagged mig=True/mig_profile_id.
    h = _Host(
        driver="nvidia",
        mig="Disabled",
        live=None,
        profiles=[{"name": "RTXPro6000BlackwellDC-1_24Q", "type_id": "nvidia-1561"}],
    )
    h.vf_paths = [f"/sys/bus/pci/devices/0000:05:00.{i}" for i in range(1, 7)]  # 6 VFs
    _patch_host(monkeypatch, h)
    gpu = {
        "pci_bus_id": "0000:05:00.0",
        "sriov_totalvfs": 12,
        "vgpu_profiles": [
            {
                "name": "RTXPro6000BlackwellDC-1_24Q",
                "type_id": "nvidia-1561",
                "mig": True,
                "mig_profile_id": 47,
                "mig_count": 4,
            },
        ],
    }
    rep = ga.apply_target(
        gpu, {"target_profile": "1_24Q", "action": "apply"}, run=h.run
    )
    assert rep["result"] == "applied", rep
    pool = rep["mdevs"]["1_24Q"]
    assert len(pool) == 4  # capped at mig_count, not the 6 VFs
    entry = next(iter(pool.values()))
    assert entry["mig"] is True
    assert entry["mig_profile_id"] == 47
    assert any("-cgi 47,47,47,47 -C" in c for c in h.cmds)
    assert any("-mig 1" in c for c in h.cmds)
    assert any("sriov-manage -e" in c for c in h.cmds)
    # ORDER IS LOAD-BEARING: sriov-manage -e rebinds the PF driver, which wipes
    # any existing GPU-instances. It MUST run BEFORE -cgi or the GIs are
    # destroyed and the VF DC-N-Q mdev type stays at available_instances=0
    # (0 bookable). Validated on Blackwell hardware.
    sriov_e_idx = next(i for i, c in enumerate(h.cmds) if "sriov-manage -e" in c)
    cgi_idx = next(i for i, c in enumerate(h.cmds) if "-cgi 47,47,47,47 -C" in c)
    assert sriov_e_idx < cgi_idx, h.cmds


def test_apply_mig_vgpu_errors_on_short_carve(monkeypatch):
    # If fewer slices carve than mig_count (e.g. a racy SR-IOV re-enable left
    # only some VFs exposing the type), the apply must ERROR -- not publish a
    # partial MIG pool as "applied". Here only 2 VFs are available, mig_count=4.
    h = _Host(
        driver="nvidia",
        mig="Disabled",
        live=None,
        profiles=[{"name": "RTXPro6000BlackwellDC-1_24Q", "type_id": "nvidia-1561"}],
    )
    h.vf_paths = [f"/sys/bus/pci/devices/0000:05:00.{i}" for i in range(1, 3)]  # 2 VFs
    _patch_host(monkeypatch, h)
    gpu = {
        "pci_bus_id": "0000:05:00.0",
        "sriov_totalvfs": 12,
        "vgpu_profiles": [
            {
                "name": "RTXPro6000BlackwellDC-1_24Q",
                "type_id": "nvidia-1561",
                "mig": True,
                "mig_profile_id": 47,
                "mig_count": 4,
            },
        ],
    }
    rep = ga.apply_target(
        gpu, {"target_profile": "1_24Q", "action": "apply"}, run=h.run
    )
    assert rep["result"] == "error", rep
    assert "2/4" in (rep.get("error") or ""), rep


def test_build_mig_transition_cmds_carves_one_gi_per_slice():
    # The engine inline fallback must carve `mig_count` +gfx GPU-instances (one
    # per bookable slice) with -C, matching the CLI carve path -- NOT a single
    # GI + separate -cci, which under-carves a multi-slice MIG-vGPU profile.
    bmt = ga._cmds.build_mig_transition_cmds
    for old_is_mig, old_profile in ((True, "2_24Q"), (False, "4Q")):
        cmds = bmt("0000:05:00.0", old_is_mig, True, old_profile, "1_24Q", 47, 4)
        assert "nvidia-smi mig -i 0000:05:00.0 -cgi 47,47,47,47 -C" in cmds, cmds
        assert not any(c.rstrip().endswith("-cci") for c in cmds), cmds
    # Default count == 1 -> a single GI (a 1-slice profile is unchanged in shape).
    cmds = bmt("0000:05:00.0", True, True, "x", "y", 9)
    assert "nvidia-smi mig -i 0000:05:00.0 -cgi 9 -C" in cmds, cmds
    # The MIG->non-MIG teardown branch carves nothing and is left untouched.
    cmds = bmt("0000:05:00.0", True, False, "1_24Q", "4Q", None, 4)
    assert any("-mig 0" in c for c in cmds)
    assert not any("-cgi" in c for c in cmds), cmds


def test_apply_mig_vgpu_skips_vf_with_zero_available_instances(monkeypatch):
    # A VF whose available_instances reads 0 has no backing GPU-instance, so the
    # carve must skip it (its create would fail) and surface a precise reason.
    # 4 VFs, mig_count=4, but VF .3 reports 0 -> 3 carve -> MIG short-carve error
    # that names available_instances.
    h = _Host(
        driver="nvidia",
        mig="Disabled",
        live=None,
        profiles=[{"name": "RTXPro6000BlackwellDC-1_24Q", "type_id": "nvidia-1561"}],
        avail={
            "0000:05:00.1": 1,
            "0000:05:00.2": 1,
            "0000:05:00.3": 0,  # no backing GPU-instance
            "0000:05:00.4": 1,
        },
    )
    h.vf_paths = [f"/sys/bus/pci/devices/0000:05:00.{i}" for i in range(1, 5)]  # 4 VFs
    _patch_host(monkeypatch, h)
    gpu = {
        "pci_bus_id": "0000:05:00.0",
        "sriov_totalvfs": 12,
        "vgpu_profiles": [
            {
                "name": "RTXPro6000BlackwellDC-1_24Q",
                "type_id": "nvidia-1561",
                "mig": True,
                "mig_profile_id": 47,
                "mig_count": 4,
            },
        ],
    }
    rep = ga.apply_target(
        gpu, {"target_profile": "1_24Q", "action": "apply"}, run=h.run
    )
    assert rep["result"] == "error", rep
    assert "available_instances=0" in (rep.get("error") or ""), rep
    # The zero-available VF is never echoed a create (in any retry attempt).
    assert not any(
        "0000:05:00.3/mdev_supported_types" in c and c.rstrip().endswith("/create'")
        for c in h.cmds
    ), h.cmds


def test_apply_mig_vgpu_warm_repartition_skips_sriov_reset(monkeypatch):
    # Switching a MIG-vGPU profile on an ALREADY-MIG-enabled card with SR-IOV VFs
    # up must re-lay-out the GPU-instances at the GI level ONLY: NO sriov-manage,
    # NO -mig toggle, NO gpu reset (dynamic symmetric repartition; validated on HW).
    h = _Host(
        driver="nvidia",
        mig="Enabled",
        numvfs=12,
        profiles=[{"name": "RTXPro6000BlackwellDC-2_24Q", "type_id": "nvidia-1570"}],
    )
    h.vf_paths = [f"/sys/bus/pci/devices/0000:05:00.{i}" for i in range(1, 7)]
    _patch_host(monkeypatch, h)
    gpu = {
        "pci_bus_id": "0000:05:00.0",
        "sriov_totalvfs": 12,
        "sriov_numvfs": 12,
        "vgpu_profiles": [
            {
                "name": "RTXPro6000BlackwellDC-2_24Q",
                "type_id": "nvidia-1570",
                "mig": True,
                "mig_profile_id": 35,
                "mig_count": 2,
            },
        ],
    }
    rep = ga.apply_target(
        gpu, {"target_profile": "2_24Q", "action": "apply"}, run=h.run
    )
    assert rep["result"] == "applied", rep
    joined = "\n".join(h.cmds)
    assert "sriov-manage" not in joined  # warm: no SR-IOV re-cycle
    assert "-mig 1" not in joined  # no MIG-mode toggle
    assert "--gpu-reset" not in joined  # no GPU reset
    assert any("-cgi 35,35 -C" in c for c in h.cmds)  # GI-level recarve to 2 slices


def test_apply_normalizes_8digit_bdf_for_sysfs(monkeypatch):
    # Discovery emits the nvidia-smi 8-digit BDF (00000000:84:00.0); apply_target
    # must use the 4-digit sysfs form (0000:84:00.0) for _read_driver and the
    # base_path that _card_busy reads -- otherwise the path doesn't exist,
    # _read_driver returns None and _card_busy mis-reads the card as busy, so the
    # whole startup apply is skipped. Regression: every card came back uncarved
    # after a hypervisor restart with `driver=None action=skipped_busy`.
    h = _Host(driver="vfio-pci")  # current resolves to passthrough -> noop
    seen = {}

    def _rec_driver(b, r):
        seen["driver_bdf"] = b
        return h.driver

    def _rec_busy(p):
        seen["busy_path"] = p
        return h.busy

    monkeypatch.setattr(ga, "_SLEEP", lambda *a, **k: None)
    monkeypatch.setattr(ga, "_read_driver", _rec_driver)
    monkeypatch.setattr(ga, "_read_mig_mode", lambda b, r: h.mig)
    monkeypatch.setattr(ga, "_live_mdev_suffix", lambda b, r: h.live)
    monkeypatch.setattr(ga, "_card_busy", _rec_busy)
    monkeypatch.setattr(ga, "_live_profiles", lambda b: h.profiles)
    monkeypatch.setattr(
        ga, "_live_mdev_count", lambda b, r, sub_paths=None: h.mdev_count
    )
    monkeypatch.setattr(ga, "_enumerate_vf_sub_paths", lambda b, r: h.vf_paths)

    rep = ga.apply_target(
        {"pci_bus_id": "00000000:84:00.0"},
        {"target_profile": "passthrough", "action": "apply"},
        run=h.run,
    )
    assert seen["driver_bdf"] == "0000:84:00.0"
    assert seen["busy_path"] == "/sys/bus/pci/devices/0000:84:00.0"
    assert rep["result"] == "noop"  # already at target; not wrongly skipped_busy


# --- _live_mdev_pool (noop/skipped_busy live-pool report) -------------------
def test_live_mdev_pool_enumerates_existing_uuids(monkeypatch):
    monkeypatch.setattr(ga, "_resolve_type_id", lambda b, s, sp=None: "nvidia-1525")

    def run(cmds, timeout=0):
        out = []
        for c in cmds:
            if "0000:d4:00.2" in c:
                out.append({"out": "uuidA\n", "err": ""})
            elif "0000:d4:00.3" in c:
                out.append({"out": "uuidB\n", "err": ""})
            else:
                out.append({"out": "", "err": ""})
        return out

    sub = ["/sys/bus/pci/devices/0000:d4:00.2", "/sys/bus/pci/devices/0000:d4:00.3"]
    pool = ga._live_mdev_pool("0000:d4:00.0", run, "8Q", {"mig_profiles": []}, sub)
    assert set(pool["8Q"]) == {"uuidA", "uuidB"}
    assert pool["8Q"]["uuidA"]["pci_mdev_id"] == "0000:d4:00.2"
    assert pool["8Q"]["uuidA"]["created"] is True
    assert pool["8Q"]["uuidA"]["domain_started"] is False


def test_live_mdev_pool_none_for_passthrough_and_empty(monkeypatch):
    monkeypatch.setattr(ga, "_resolve_type_id", lambda b, s, sp=None: "nvidia-1525")
    run = lambda cmds, timeout=0: [{"out": "", "err": ""} for _ in cmds]
    # passthrough -> pseudo pool (None, keep timestamp-only); empty card -> None
    assert (
        ga._live_mdev_pool(
            "0000:d4:00.0", run, "passthrough", {"mig_profiles": []}, ["/x"]
        )
        is None
    )
    assert (
        ga._live_mdev_pool("0000:d4:00.0", run, "8Q", {"mig_profiles": []}, ["/x"])
        is None
    )


def test_live_mdev_pool_none_on_truncated_batch(monkeypatch):
    # A short result list (fewer entries than bases) would otherwise yield a
    # PARTIAL pool that, r.literal-replaced, drops the running-desktop UUID on
    # the missing base. Must return None so the caller keeps the pool intact.
    monkeypatch.setattr(ga, "_resolve_type_id", lambda b, s, sp=None: "nvidia-1525")
    run = lambda cmds, timeout=0: [{"out": "uuidA\n", "err": ""}]  # 1 result, 2 bases
    sub = ["/sys/bus/pci/devices/0000:d4:00.2", "/sys/bus/pci/devices/0000:d4:00.3"]
    assert (
        ga._live_mdev_pool("0000:d4:00.0", run, "8Q", {"mig_profiles": []}, sub) is None
    )


# --- _running_mdev_uuids (the "actually running" cross-check) ----------------
def test_running_mdev_uuids_extracts_mdev_addresses():
    def run(cmds, timeout=0):
        out = []
        for c in cmds:
            if "list --name --state-running" in c:
                out.append({"out": "desk1\ndesk2\n", "err": ""})
            elif "dumpxml desk1" in c:
                # mdev hostdev address uuid + a domain <uuid> ELEMENT (must be ignored)
                out.append(
                    {
                        "out": "<domain><uuid>dom-elem-uuid</uuid><devices>"
                        "<hostdev mode='subsystem' type='mdev'><source>"
                        "<address uuid='aaa-111'/></source></hostdev></devices></domain>",
                        "err": "",
                    }
                )
            elif "dumpxml desk2" in c:
                out.append(
                    {
                        "out": "<hostdev type='mdev'><source>"
                        "<address uuid='BBB-222'/></source></hostdev>",
                        "err": "",
                    }
                )
            else:
                out.append({"out": "", "err": ""})
        return out

    # mdev address uuids only (lowercased); the domain <uuid> element is ignored
    assert ga._running_mdev_uuids(run) == {"aaa-111", "bbb-222"}


def test_running_mdev_uuids_shell_safe(monkeypatch):
    # A domain name is interpolated into a shell command: it must be shlex-quoted
    # (no injection) and a flag-like leading-dash name must be skipped.
    dumped = []

    def run(cmds, timeout=0):
        out = []
        for c in cmds:
            if "list --name --state-running" in c:
                out.append({"out": "ok_desk\n--evil\nweird name\n", "err": ""})
            else:
                dumped.append(c)
                out.append({"out": "", "err": ""})
        return out

    ga._running_mdev_uuids(run)
    joined = " ".join(dumped)
    assert "dumpxml ok_desk " in joined  # safe name passes through unquoted
    assert "--evil" not in joined  # leading-dash name skipped (flag-smuggle guard)
    assert "'weird name'" in joined  # space-containing name is shlex-quoted


def test_running_mdev_uuids_empty_when_nothing_running():
    # Startup case: the entrypoint already killed leftover qemu -> no running
    # domains -> empty set -> reconcile frees the whole pool (clean slate).
    run = lambda cmds, timeout=0: [{"out": "", "err": ""} for _ in cmds]
    assert ga._running_mdev_uuids(run) == set()
