"""Unit tests for gpu_discovery helpers.

Run locally (no CI pytest gate for the hypervisor lib):
    cd docker/hypervisor/src/lib && python -m pytest gpu_discovery_test.py -v

The module is not packaged, so add its own directory to sys.path before
importing (mirrors how the lib is loaded inside the hypervisor container).
"""

import logging
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from gpu_discovery import (
    _aggregate_subdevice_profiles,
    _canon_vgpu_profile_name,
    _check_gpu_tooling,
    _classify_sriov_state,
    _cycle_sriov_vfs,
    _running_qemu_pids,
    _sriov_manage_usable,
    _vf_vgpu_types_settled,
    _vgpu_host_driver_present,
    _wait_sriov_numvfs_zero,
    _wait_vf_driver_bound,
    canonical_gpu_model,
    discover_gpus,
    normalize_gpu_model,
)


@pytest.mark.parametrize(
    "totalvfs, numvfs, has_profiles, vf_driver, expect_note, expect_warning",
    [
        # Not SR-IOV capable at all (e.g. consumer card / pure passthrough
        # board): nothing to say. Clean UI.
        (0, 0, False, "", False, False),
        (0, 0, True, "", False, False),
        # SR-IOV capable, no VFs, no profiles: the correct steady state for
        # a Blackwell DC board serving passthrough/MIG. One neutral note,
        # NO warning -> admin UI stays clean when everything is correct.
        (16, 0, False, "", True, False),
        (32, 0, False, "", True, False),
        # SR-IOV capable WITH vGPU profiles present (normal A40-style vGPU
        # card): not our concern regardless of VF count -> no note/warning.
        (16, 0, True, "", False, False),
        (16, 16, True, "nvidia", False, False),
        (16, 8, True, "vfio-pci", False, False),
        # VFs created but no profiles and VFs not nvidia-bound: genuine
        # IOMMU/driver misconfiguration -> warning, no note.
        (16, 16, False, "vfio-pci", False, True),
        (16, 4, False, "", False, True),
        # VFs created, nvidia-bound, but still no profiles: genuine
        # unexpected state -> warning, no note.
        (16, 16, False, "nvidia", False, True),
    ],
)
def test_classify_sriov_state(
    totalvfs, numvfs, has_profiles, vf_driver, expect_note, expect_warning
):
    notes, warnings = _classify_sriov_state(totalvfs, numvfs, has_profiles, vf_driver)
    assert bool(notes) is expect_note
    assert bool(warnings) is expect_warning
    # A card is never simultaneously "fine (note)" and "broken (warning)".
    assert not (notes and warnings)


def test_note_text_is_reassuring_not_a_fault():
    """The passthrough/MIG steady-state message must read as expected,
    not as a failure (it used to be a 'VF creation failed' warning)."""
    notes, warnings = _classify_sriov_state(24, 0, False, "")
    assert warnings == []
    assert len(notes) == 1
    msg = notes[0]
    assert "expected" in msg
    assert "passthrough/MIG" in msg
    assert "24 VFs supported" in msg
    assert "fail" not in msg.lower()


def test_vf_unbound_warning_names_the_bound_driver():
    notes, warnings = _classify_sriov_state(16, 16, False, "vfio-pci")
    assert notes == []
    assert len(warnings) == 1
    assert "driver=vfio-pci" in warnings[0]
    # The old text falsely told operators to add iommu=pt to the kernel
    # cmdline. Production NVIDIA vGPU hosts work fine with amd_iommu=on
    # only; the real causes of unbound VFs are nvidia-vgpu-mgr not running
    # and udev binding races between sriov-manage -d and -e.
    assert "iommu=pt" not in warnings[0].lower()
    assert "nvidia-vgpu-mgr" in warnings[0]


def test_vf_unbound_warning_handles_unknown_driver():
    notes, warnings = _classify_sriov_state(16, 16, False, "")
    assert notes == []
    assert "driver=none" in warnings[0]
    assert "iommu=pt" not in warnings[0].lower()


@pytest.mark.parametrize(
    "type_ids, settled",
    [
        (["nvidia-711", "nvidia-713"], True),
        (["nvidia-713"], True),
        # generic half-initialized VF names — must NOT be treated as settled
        (["pci-713"], False),
        (["nvidia-711", "pci-713"], False),
        ([], False),  # no profiles at all
    ],
)
def test_vf_vgpu_types_settled(type_ids, settled):
    profiles = [{"name": f"A16-{i}Q", "type_id": t} for i, t in enumerate(type_ids)]
    assert _vf_vgpu_types_settled(profiles) is settled


def test_vfs_nvidia_bound_no_profiles_points_at_host_vgpud():
    """VFs up + nvidia-bound but no vGPU types means the host nvidia-vgpud
    isn't publishing types (e.g. it lost a boot-time race after GPUs were
    added). The warning must name nvidia-vgpud and tell the operator to restart
    it ON THE HOST (the container can't), not just say 'no profiles found'."""
    notes, warnings = _classify_sriov_state(16, 16, False, "nvidia")
    assert notes == []
    assert len(warnings) == 1
    w = warnings[0]
    assert "nvidia-vgpud" in w
    assert "host" in w.lower()
    assert "passthrough" in w.lower()


# normalize_gpu_model output is used verbatim as a URL path segment inside the
# BRAND-MODEL-PROFILE reservable id, so it must be space-, dash- AND slash-free.
# The A16 die's PCI name "GA107GL [A2 / A16]" is the regression that motivated
# slash stripping: a '/' made the reservables enable route 405.
@pytest.mark.parametrize(
    "gpu_name, expected",
    [
        ("NVIDIA A16", "A16"),
        ("NVIDIA RTX A6000", "RTXA6000"),
        ("NVIDIA GA107GL [A2 / A16]", "GA107GL[A2A16]"),
        ("GA107GL[A2/A16]", "GA107GL[A2A16]"),
    ],
)
def test_normalize_gpu_model_name_path_is_clean(gpu_name, expected):
    result = normalize_gpu_model(gpu_name)
    assert result == expected
    assert "/" not in result
    assert "-" not in result
    assert " " not in result


@pytest.mark.parametrize(
    "profile_name, expected",
    [
        ("A16-2Q", "A16"),
        ("A100-1-5C", "A100"),
        ("GA107GL[A2/A16]-2Q", "GA107GL[A2A16]"),
    ],
)
def test_normalize_gpu_model_profile_path_is_clean(profile_name, expected):
    result = normalize_gpu_model("irrelevant", vgpu_profiles=[{"name": profile_name}])
    assert result == expected
    assert "/" not in result


# canonical_gpu_model unifies the model token for physically identical cards by
# anchoring on the PCI device-id (+ subsystem-id where the die-id is shared).
# The live fragmentation it fixes: one 10de:2bb5 card discovered with vGPU
# profiles -> "RTXPro6000BlackwellDC", an identical one discovered via the
# nvidia-smi name -> "RTXPRO6000BlackwellServerEdition", and a third discovered
# after an NVML failure (sysfs + pci.ids fallback) -> the die-label
# "GB202GL[RTXPRO6000BlackwellServerEdition]". All three are the SAME hardware
# and MUST collapse to one token. The alias therefore takes PRECEDENCE over the
# name/profile paths (which themselves diverge) for a mapped device.


@pytest.mark.parametrize(
    "name, profiles",
    [
        # vGPU-profile-name path (profiles enumerated): would give DC anyway.
        (
            "NVIDIA RTX PRO 6000 Blackwell Server Edition",
            [{"name": "RTXPro6000BlackwellDC-4Q"}],
        ),
        # nvidia-smi-name path (no profiles): would otherwise give ServerEdition.
        ("NVIDIA RTX PRO 6000 Blackwell Server Edition", None),
        # NVML-failed / sysfs+pci.ids fallback path: would otherwise give the
        # bracketed die-label.
        ("NVIDIA GB202GL [RTX PRO 6000 Blackwell Server Edition]", None),
    ],
)
def test_canonical_gpu_model_blackwell_all_paths_collapse(name, profiles):
    # 10de:2bb5 is device-only aliased (subsystem irrelevant for this model).
    result = canonical_gpu_model(
        name, vgpu_profiles=profiles, pci_device_id="10de:2bb5"
    )
    assert result == "RTXPro6000BlackwellDC"


@pytest.mark.parametrize(
    "name, profiles",
    [
        ("NVIDIA A16", [{"name": "A16-2Q"}]),
        ("NVIDIA A16", None),
        # The NVML-failed fallback names the GA107 die ambiguously as A2/A16.
        ("NVIDIA GA107GL [A2 / A16]", None),
    ],
)
def test_canonical_gpu_model_a16_all_paths_collapse(name, profiles):
    # 10de:25b6 is the shared A2/A16 die-id, so the alias is subsystem-qualified.
    result = canonical_gpu_model(
        name,
        vgpu_profiles=profiles,
        pci_device_id="10de:25b6",
        pci_subsystem_id="10de:14a9",
    )
    assert result == "A16"


def test_canonical_gpu_model_does_not_conflate_a2_with_a16():
    # Same die-id 25b6 but a DIFFERENT subsystem (a real A2) must NOT be aliased
    # to A16 — it falls through to the unambiguous nvidia-smi name.
    result = canonical_gpu_model(
        "NVIDIA A2",
        vgpu_profiles=None,
        pci_device_id="10de:25b6",
        pci_subsystem_id="10de:157e",
    )
    assert result == "A2"


def test_canonical_gpu_model_unmapped_device_falls_through_to_name():
    # A40 (10de:2235) is clean fleet-wide -> no alias entry -> identity behaviour
    # of normalize_gpu_model (profile path then name path).
    assert canonical_gpu_model("NVIDIA A40", pci_device_id="10de:2235") == "A40"
    assert (
        canonical_gpu_model(
            "irrelevant",
            vgpu_profiles=[{"name": "A40-12Q"}],
            pci_device_id="10de:2235",
        )
        == "A40"
    )


def test_canonical_gpu_model_no_pci_id_matches_normalize():
    # Without any device-id (e.g. older callers), behaviour is exactly
    # normalize_gpu_model.
    for name in ("NVIDIA A16", "NVIDIA GA107GL [A2 / A16]"):
        assert canonical_gpu_model(name) == normalize_gpu_model(name)


def test_canonical_gpu_model_output_is_url_path_safe():
    # Whatever path is taken, the token is a URL path segment in the reservable
    # id, so it must stay dash/slash/space-free.
    for kwargs in (
        {"pci_device_id": "10de:2bb5"},
        {"pci_device_id": "10de:25b6", "pci_subsystem_id": "10de:14a9"},
        {"pci_device_id": "10de:2235"},
        {},
    ):
        result = canonical_gpu_model("NVIDIA GA107GL [A2 / A16]", **kwargs)
        assert "/" not in result
        assert "-" not in result
        assert " " not in result


# _canon_vgpu_profile_name is the single canonicalization point: discovery emits
# names whose derived "NVIDIA-MODEL-PROFILE" id has exactly two dashes, so the
# engine info.types key and the catalog id agree and set_gpu_profile's
# split("-")[-1] resolves the full MIG suffix (the "1-2Q" -> "2Q" regression).
@pytest.mark.parametrize(
    "name, expected",
    [
        # simple time-sliced profiles are already canonical (idempotent)
        ("A40-4Q", "A40-4Q"),
        ("A16-2Q", "A16-2Q"),
        ("RTXPro6000BlackwellDC-passthrough", "RTXPro6000BlackwellDC-passthrough"),
        # MIG-backed dash suffix -> underscore (the bug this fixes)
        ("RTXPro6000BlackwellDC-1-2Q", "RTXPro6000BlackwellDC-1_2Q"),
        ("RTXPro6000BlackwellDC-2-48Q", "RTXPro6000BlackwellDC-2_48Q"),
        ("A100-1-5C", "A100-1_5C"),
        # dashed MODEL is collapsed so the suffix split stays correct
        ("RTX-A6000-1-2Q", "RTXA6000-1_2Q"),
        ("RTX-A6000-4Q", "RTXA6000-4Q"),
        # already-canonical underscore form is left untouched (idempotent)
        ("RTXPro6000BlackwellDC-1_2Q", "RTXPro6000BlackwellDC-1_2Q"),
    ],
)
def test_canon_vgpu_profile_name(name, expected):
    result = _canon_vgpu_profile_name(name)
    assert result == expected
    # the derived BRAND-MODEL-PROFILE id must split into exactly 3 dash tokens
    assert len(f"NVIDIA-{result}".split("-")) == 3
    # and split("-")[-1] must recover the full suffix (what set_gpu_profile does)
    assert f"NVIDIA-{result}".split("-")[-1] == result.split("-", 1)[1]


def test_canon_vgpu_profile_name_is_idempotent():
    once = _canon_vgpu_profile_name("RTXPro6000BlackwellDC-1-2Q")
    assert _canon_vgpu_profile_name(once) == once


# ----- vfio-variant discovery backend (kernel >=6.8 / Ubuntu 24.04+) -------
# NVIDIA dropped legacy mdev there: profiles come from each VF's
# nvidia/creatable_vgpu_types instead of mdev_supported_types/<id>/{name,...}.


@pytest.mark.parametrize(
    "suffix,expected_mb",
    [
        ("2Q", 2048),
        ("16Q", 16384),
        ("1_2Q", 2048),  # MIG-backed: the framebuffer GB is the LAST number
        ("5C", 5120),
        ("passthrough", 0),
        ("", 0),
    ],
)
def test_framebuffer_mb_from_suffix(suffix, expected_mb):
    from gpu_discovery import _framebuffer_mb_from_suffix

    assert _framebuffer_mb_from_suffix(suffix) == expected_mb


def test_parse_creatable_vgpu_types_parses_id_name_lines():
    from gpu_discovery import _parse_creatable_vgpu_types

    text = (
        "ID  : VGPU Name\n"
        "694 : NVIDIA A16-2Q\n"
        "695 : NVIDIA A16-4Q\n"
        "696 : NVIDIA A16-16Q\n"
    )
    out = _parse_creatable_vgpu_types(text)
    assert out == [
        {"name": "A16-2Q", "type_id": "694", "framebuffer_mb": 2048},
        {"name": "A16-4Q", "type_id": "695", "framebuffer_mb": 4096},
        {"name": "A16-16Q", "type_id": "696", "framebuffer_mb": 16384},
    ]


def test_parse_creatable_vgpu_types_filters_non_qc_and_blank():
    from gpu_discovery import _parse_creatable_vgpu_types

    # A/B profiles (apps/VDI Windows) are not the Q/C desktop profiles IsardVDI
    # books; mirror the legacy reader's C/Q filter. Header + junk are dropped.
    text = "700 : NVIDIA A16-1A\n701 : NVIDIA A16-1B\n702 : NVIDIA A16-8Q\n\ngarbage\n"
    out = _parse_creatable_vgpu_types(text)
    assert out == [{"name": "A16-8Q", "type_id": "702", "framebuffer_mb": 8192}]


def test_get_vgpu_profiles_vfio_reads_creatable_types(monkeypatch, tmp_path):
    from gpu_discovery import _get_vgpu_profiles_vfio

    _redirect_sysfs(monkeypatch, tmp_path)
    vf_bdf = "0000:c5:00.4"
    nvidia_dir = tmp_path / vf_bdf / "nvidia"
    nvidia_dir.mkdir(parents=True)
    _write(
        nvidia_dir / "creatable_vgpu_types",
        "694 : NVIDIA A16-2Q\n695 : NVIDIA A16-4Q\n",
    )
    out = _get_vgpu_profiles_vfio(vf_bdf)
    # Same dict shape as the legacy _get_vgpu_profiles, so downstream ingest is
    # unchanged. One vGPU per VF => available_instances == 1 (the aggregator sums
    # these across VFs to get capacity = free-VF count).
    assert out == [
        {
            "name": "A16-2Q",
            "type_id": "694",
            "available_instances": 1,
            "framebuffer_mb": 2048,
            "max_instances": 0,
        },
        {
            "name": "A16-4Q",
            "type_id": "695",
            "available_instances": 1,
            "framebuffer_mb": 4096,
            "max_instances": 0,
        },
    ]


def test_get_vgpu_profiles_vfio_empty_when_no_nvidia_dir(monkeypatch, tmp_path):
    from gpu_discovery import _get_vgpu_profiles_vfio

    _redirect_sysfs(monkeypatch, tmp_path)
    (tmp_path / "0000:c5:00.4").mkdir(parents=True)  # VF exists, no nvidia/ dir
    assert _get_vgpu_profiles_vfio("0000:c5:00.4") == []


# ----- _wait_sriov_numvfs_zero --------------------------------------------


def _write(path, content):
    """Tiny sysfs-style helper: write content (str) to path. Path may be Path or str."""
    with open(str(path), "w") as f:
        f.write(str(content))


def _redirect_sysfs(monkeypatch, tmp_path):
    """Point gpu_discovery's _SYSFS_PCI_BASE at tmp_path. Returns it as str."""
    import gpu_discovery as gd

    monkeypatch.setattr(gd, "_SYSFS_PCI_BASE", str(tmp_path))
    return str(tmp_path)


def test_wait_sriov_numvfs_zero_returns_true_when_already_zero(monkeypatch, tmp_path):
    _redirect_sysfs(monkeypatch, tmp_path)
    pci_id = "0000:99:00.0"
    dev_dir = tmp_path / pci_id
    dev_dir.mkdir(parents=True)
    _write(dev_dir / "sriov_numvfs", "0")
    assert _wait_sriov_numvfs_zero(pci_id, timeout=1) is True


def test_wait_sriov_numvfs_zero_returns_true_when_becomes_zero(monkeypatch, tmp_path):
    _redirect_sysfs(monkeypatch, tmp_path)
    pci_id = "0000:99:00.0"
    dev_dir = tmp_path / pci_id
    dev_dir.mkdir(parents=True)
    _write(dev_dir / "sriov_numvfs", "16")

    def drop_to_zero():
        time.sleep(0.4)
        _write(dev_dir / "sriov_numvfs", "0")

    threading.Thread(target=drop_to_zero, daemon=True).start()
    assert _wait_sriov_numvfs_zero(pci_id, timeout=3) is True


def test_wait_sriov_numvfs_zero_returns_false_on_timeout(monkeypatch, tmp_path):
    _redirect_sysfs(monkeypatch, tmp_path)
    pci_id = "0000:99:00.0"
    dev_dir = tmp_path / pci_id
    dev_dir.mkdir(parents=True)
    _write(dev_dir / "sriov_numvfs", "16")
    assert _wait_sriov_numvfs_zero(pci_id, timeout=1) is False


def test_wait_vf_driver_bound_succeeds_when_already_nvidia(monkeypatch, tmp_path):
    """When virtfn0 -> VF BDF and VF's driver -> nvidia, the helper returns True."""
    _redirect_sysfs(monkeypatch, tmp_path)
    pci_id = "0000:99:00.0"
    vf_bdf = "0000:99:00.4"
    pf_dir = tmp_path / pci_id
    vf_dir = tmp_path / vf_bdf
    pf_dir.mkdir()
    vf_dir.mkdir()
    # virtfn0 -> VF
    (pf_dir / "virtfn0").symlink_to(vf_dir)
    # driver -> nvidia (real subdir, basename matters)
    nvidia_drv_dir = tmp_path / "drivers" / "nvidia"
    nvidia_drv_dir.mkdir(parents=True)
    (vf_dir / "driver").symlink_to(nvidia_drv_dir)
    assert _wait_vf_driver_bound(pci_id, expected="nvidia", timeout=1) is True


def test_wait_vf_driver_bound_returns_false_when_driver_missing(monkeypatch, tmp_path):
    _redirect_sysfs(monkeypatch, tmp_path)
    pci_id = "0000:99:00.0"
    pf_dir = tmp_path / pci_id
    pf_dir.mkdir()
    # No virtfn0 at all → must time out, not crash.
    assert _wait_vf_driver_bound(pci_id, expected="nvidia", timeout=1) is False


# ----- _cycle_sriov_vfs orchestration -------------------------------------


def test_cycle_sriov_vfs_runs_settle_helpers_in_order(monkeypatch, tmp_path):
    """After `-d` we must wait for sriov_numvfs==0; after `-e` we must wait
    for virtfn0 to be nvidia-bound. Both come from real production breakage
    where back-to-back sriov-manage left VFs driver=none."""
    _redirect_sysfs(monkeypatch, tmp_path)
    pci_id = "0000:05:00.0"
    dev_dir = tmp_path / pci_id
    dev_dir.mkdir()
    _write(dev_dir / "sriov_totalvfs", "16")

    import gpu_discovery as gd

    call_log = []

    class _R:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, *a, **kw):
        call_log.append(("run", tuple(cmd)))
        return _R()

    def fake_wait_numvfs_zero(_id, timeout=10):
        call_log.append(("wait_numvfs_zero",))
        return True

    def fake_wait_vf_bound(_id, expected="nvidia", timeout=15):
        call_log.append(("wait_vf_bound",))
        return True

    monkeypatch.setattr(gd, "_sriov_manage_usable", lambda *a, **k: True)
    monkeypatch.setattr(gd.subprocess, "run", fake_run)
    monkeypatch.setattr(gd, "_wait_sriov_numvfs_zero", fake_wait_numvfs_zero)
    monkeypatch.setattr(gd, "_wait_vf_driver_bound", fake_wait_vf_bound)

    ok = _cycle_sriov_vfs(pci_id)

    assert ok is True
    op_order = []
    for c in call_log:
        if c[0] == "run":
            cmd = c[1]
            if cmd[0] == "sriov-manage":
                op_order.append(("sriov-manage", cmd[1]))
            elif cmd[0] == "udevadm":
                op_order.append(("udevadm",))
        else:
            op_order.append((c[0],))
    assert op_order == [
        ("sriov-manage", "-d"),
        ("wait_numvfs_zero",),
        ("sriov-manage", "-e"),
        ("udevadm",),
        ("wait_vf_bound",),
    ]


def test_cycle_sriov_vfs_survives_missing_udevadm(monkeypatch, tmp_path):
    """A missing `udevadm` binary (FileNotFoundError) must NOT abort the cycle
    into the destructive nvidia-smi -r fallback: sriov-manage -d/-e already
    succeeded and the settle is best-effort. Regression — a real GPU host whose
    image lacks udevadm bus-reset-wedged every card on every discovery."""
    _redirect_sysfs(monkeypatch, tmp_path)
    pci_id = "0000:05:00.0"
    dev_dir = tmp_path / pci_id
    dev_dir.mkdir()
    _write(dev_dir / "sriov_totalvfs", "16")

    import gpu_discovery as gd

    class _R:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, *a, **kw):
        if cmd[0] == "udevadm":
            raise FileNotFoundError(2, "No such file or directory", "udevadm")
        return _R()

    monkeypatch.setattr(gd, "_sriov_manage_usable", lambda *a, **k: True)
    monkeypatch.setattr(gd.subprocess, "run", fake_run)
    monkeypatch.setattr(gd, "_wait_sriov_numvfs_zero", lambda *a, **k: True)
    monkeypatch.setattr(gd, "_wait_vf_driver_bound", lambda *a, **k: True)

    assert _cycle_sriov_vfs(pci_id) is True


def test_cycle_sriov_vfs_returns_false_if_vfs_never_bind(monkeypatch, tmp_path):
    _redirect_sysfs(monkeypatch, tmp_path)
    pci_id = "0000:05:00.0"
    dev_dir = tmp_path / pci_id
    dev_dir.mkdir()
    _write(dev_dir / "sriov_totalvfs", "16")

    import gpu_discovery as gd

    class _R:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(gd, "_sriov_manage_usable", lambda *a, **k: True)
    monkeypatch.setattr(gd.subprocess, "run", lambda *a, **kw: _R())
    monkeypatch.setattr(gd, "_wait_sriov_numvfs_zero", lambda *a, **kw: True)
    monkeypatch.setattr(gd, "_wait_vf_driver_bound", lambda *a, **kw: False)

    # When VFs do not bind, return False so caller knows mdev scan would be
    # a wild goose chase. Engine reconcile then treats this as
    # DISCOVERY_INCOMPLETE rather than "GPU has no profiles".
    assert _cycle_sriov_vfs(pci_id) is False


def test_cycle_sriov_vfs_returns_false_when_sriov_manage_unusable(monkeypatch):
    """When sriov-manage is not a usable executable (missing host source /
    empty-dir bind-mount / not +x) the cycle must bail out cleanly with False
    and never exec the tool — avoiding the confusing mid-call EACCES."""
    import gpu_discovery as gd

    monkeypatch.setattr(gd, "_sriov_manage_usable", lambda *a, **k: False)

    def _boom(*a, **kw):
        raise AssertionError("subprocess.run must not be called when unusable")

    monkeypatch.setattr(gd.subprocess, "run", _boom)
    assert _cycle_sriov_vfs("0000:05:00.0") is False


def test_aggregate_skips_sriov_cycle_without_vgpu_host_driver(monkeypatch):
    """A datacenter/CUDA-driver host (no vGPU host driver) exposes
    sriov_totalvfs but cannot bring vGPU VFs up. Discovery must skip the doomed
    VF cycle + nvidia-smi -r bus reset entirely rather than spamming failures."""
    import gpu_discovery as gd

    monkeypatch.setattr(gd, "_get_vgpu_profiles", lambda *a, **k: [])
    monkeypatch.setattr(gd, "_reset_sysfs_mdevs", lambda *a, **k: None)
    monkeypatch.setattr(gd, "_vgpu_host_driver_present", lambda *a, **k: False)
    monkeypatch.setattr(gd, "_running_qemu_pids", lambda: [])
    monkeypatch.setattr(gd, "_enumerate_sriov_vf_paths", lambda *a, **k: [])
    monkeypatch.setattr(gd.os.path, "exists", lambda p: True)  # sriov_totalvfs
    monkeypatch.setattr(gd.os, "listdir", lambda p: [])
    cycle_calls = []
    reset_calls = []
    monkeypatch.setattr(
        gd, "_cycle_sriov_vfs", lambda *a, **k: cycle_calls.append(a) or False
    )
    monkeypatch.setattr(
        gd, "_nvidia_smi_gpu_reset", lambda bdf: reset_calls.append(bdf)
    )

    gd._aggregate_subdevice_profiles("00000000:05:00.0")

    assert cycle_calls == []  # doomed VF cycle skipped
    assert reset_calls == []  # no bus reset


def test_aggregate_vfio_variant_sums_vf_capacity(monkeypatch, tmp_path):
    """On the vendor-specific VFIO framework (24.04+), each VF exposes
    nvidia/creatable_vgpu_types instead of mdev_supported_types. The aggregator
    must fall back to the vfio reader per VF, report framework='vfio_variant',
    and sum the 1-per-VF capacity (2 VFs -> available_instances 2)."""
    import gpu_discovery as gd

    base = _redirect_sysfs(monkeypatch, tmp_path)
    vf_bdfs = ["0000:05:00.4", "0000:05:00.5"]
    for vf in vf_bdfs:
        nvidia_dir = tmp_path / vf / "nvidia"
        nvidia_dir.mkdir(parents=True)
        _write(
            nvidia_dir / "creatable_vgpu_types",
            "694 : NVIDIA A16-2Q\n696 : NVIDIA A16-16Q\n",
        )

    monkeypatch.setattr(gd, "_get_vgpu_profiles", lambda *a, **k: [])  # legacy empty
    monkeypatch.setattr(gd, "_reset_sysfs_mdevs", lambda *a, **k: None)
    monkeypatch.setattr(gd, "_vgpu_host_driver_present", lambda *a, **k: False)
    monkeypatch.setattr(
        gd, "_enumerate_sriov_vf_paths", lambda _p: [f"{base}/{v}" for v in vf_bdfs]
    )

    profiles, sub_paths, _parent, framework = gd._aggregate_subdevice_profiles(
        "00000000:05:00.0"
    )

    assert framework == "vfio_variant"
    by_name = {p["name"]: p for p in profiles}
    assert by_name["A16-2Q"]["available_instances"] == 2  # 1 per VF, summed
    assert by_name["A16-2Q"]["type_id"] == "694"  # numeric id for current_vgpu_type
    assert by_name["A16-16Q"]["framebuffer_mb"] == 16384
    assert sorted(sub_paths) == [f"{base}/{v}" for v in vf_bdfs]


def test_sriov_manage_usable(monkeypatch):
    import gpu_discovery as gd

    # Real executable file -> usable
    monkeypatch.setattr(gd.shutil, "which", lambda n: "/usr/bin/sriov-manage")
    monkeypatch.setattr(gd.os.path, "isfile", lambda p: True)
    monkeypatch.setattr(gd.os, "access", lambda p, m: True)
    assert _sriov_manage_usable() is True

    # which() returns None (not on PATH) -> not usable
    monkeypatch.setattr(gd.shutil, "which", lambda n: None)
    assert _sriov_manage_usable() is False

    # Resolves to an empty-dir bind-mount target (not a file) -> not usable
    monkeypatch.setattr(gd.shutil, "which", lambda n: "/usr/bin/sriov-manage")
    monkeypatch.setattr(gd.os.path, "isfile", lambda p: False)
    assert _sriov_manage_usable() is False


@pytest.mark.parametrize(
    "smi_stdout, expected",
    [
        ("    Host VGPU Mode                    : SR-IOV", True),
        ("    Host VGPU Mode                    : Non SR-IOV", True),
        ("    Host VGPU Mode                    : N/A", False),
        ("    GPU 00000000:05:00.0\n    Product Name : NVIDIA", False),
    ],
)
def test_vgpu_host_driver_present(monkeypatch, smi_stdout, expected):
    import gpu_discovery as gd

    monkeypatch.setattr(gd, "_vgpu_host_driver", None)  # reset per-process cache

    class _R:
        returncode = 0
        stdout = smi_stdout
        stderr = ""

    monkeypatch.setattr(gd.subprocess, "run", lambda *a, **k: _R())
    assert _vgpu_host_driver_present() is expected


# ----- discover_gpus retry + None sentinel --------------------------------


def test_discover_gpus_emits_none_sentinel_after_retry_exhaustion(
    monkeypatch, tmp_path
):
    _redirect_sysfs(monkeypatch, tmp_path)
    pci_id = "0000:05:00.0"
    dev_dir = tmp_path / pci_id
    dev_dir.mkdir()
    _write(dev_dir / "sriov_totalvfs", "16")

    import gpu_discovery as gd

    monkeypatch.setattr(
        gd,
        "_run_nvidia_smi",
        lambda: [
            {
                "name": "NVIDIA A16",
                "memory_total_mb": 15356,
                "pci_bus_id": "00000000:05:00.0",
                "driver_version": "535.183.04",
                "gpu_uuid": "GPU-xxx",
                "mig_mode": "[N/A]",
            }
        ],
    )
    monkeypatch.setattr(
        gd,
        "_aggregate_subdevice_profiles",
        lambda _pci: ([], None, None, "legacy_mdev"),
    )
    monkeypatch.setattr(gd, "_find_audio_companions", lambda _id: [])
    monkeypatch.setattr(gd, "_scan_sysfs_nvidia_gpus", lambda _known: [])

    gpus = discover_gpus()
    assert len(gpus) == 1
    g = gpus[0]
    # The sentinel: None, NOT empty list. Engine must distinguish "discovery
    # failed" from "GPU genuinely has no vGPU profiles" — the latter is a
    # valid state for compute-mode boards.
    assert g["vgpu_profiles"] is None
    assert "DISCOVERY_FAILED_AFTER_RETRIES" in g.get("errors", [])


def test_discover_gpus_emits_empty_list_for_compute_mode_card(monkeypatch, tmp_path):
    """Non-SR-IOV card with no profiles is a legitimate state (Quadro RTX
    compute, T4 in compute mode). vgpu_profiles must be [], NOT None."""
    _redirect_sysfs(monkeypatch, tmp_path)
    import gpu_discovery as gd

    monkeypatch.setattr(
        gd,
        "_run_nvidia_smi",
        lambda: [
            {
                "name": "NVIDIA Quadro RTX 6000",
                "memory_total_mb": 24576,
                "pci_bus_id": "00000000:08:00.0",
                "driver_version": "535.183.04",
                "gpu_uuid": "GPU-yyy",
                "mig_mode": "[N/A]",
            }
        ],
    )
    monkeypatch.setattr(
        gd,
        "_aggregate_subdevice_profiles",
        lambda _pci: ([], None, None, "legacy_mdev"),
    )
    monkeypatch.setattr(gd, "_find_audio_companions", lambda _id: [])
    monkeypatch.setattr(gd, "_scan_sysfs_nvidia_gpus", lambda _known: [])

    # Critical: no sriov_totalvfs file → the retry loop must NOT engage,
    # vgpu_profiles must stay [] (not None).
    gpus = discover_gpus()
    assert len(gpus) == 1
    g = gpus[0]
    assert g["vgpu_profiles"] == []
    assert g["vgpu_profiles"] is not None
    assert "errors" not in g


def test_discover_gpus_recovers_when_retry_finds_profiles(monkeypatch, tmp_path):
    """First _aggregate_subdevice_profiles call returns empty (race with
    nvidia-vgpu-mgr cold start); second returns the real profile list. The
    GPU dict must contain the recovered profiles, no errors."""
    _redirect_sysfs(monkeypatch, tmp_path)
    pci_id = "0000:05:00.0"
    dev_dir = tmp_path / pci_id
    dev_dir.mkdir()
    _write(dev_dir / "sriov_totalvfs", "16")

    import gpu_discovery as gd

    real_profiles = [
        {"name": "A16-2Q", "type_id": "nvidia-712", "available_instances": 16},
        {"name": "A16-4Q", "type_id": "nvidia-713", "available_instances": 16},
    ]
    call_count = {"n": 0}

    def staged_aggregate(_pci):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return ([], None, None, "legacy_mdev")
        return (
            real_profiles,
            [f"{tmp_path}/0000:05:00.4"],
            f"{tmp_path}/0000:05:00.0",
            "legacy_mdev",
        )

    monkeypatch.setattr(
        gd,
        "_run_nvidia_smi",
        lambda: [
            {
                "name": "NVIDIA A16",
                "memory_total_mb": 15356,
                "pci_bus_id": "00000000:05:00.0",
                "driver_version": "535.183.04",
                "gpu_uuid": "GPU-zzz",
                "mig_mode": "[N/A]",
            }
        ],
    )
    monkeypatch.setattr(gd, "_aggregate_subdevice_profiles", staged_aggregate)
    monkeypatch.setattr(gd, "_find_audio_companions", lambda _id: [])
    monkeypatch.setattr(gd, "_scan_sysfs_nvidia_gpus", lambda _known: [])

    gpus = discover_gpus()
    assert len(gpus) == 1
    g = gpus[0]
    assert g["vgpu_profiles"] == real_profiles
    assert "errors" not in g
    # Sanity: aggregate was called once initially + at least once on retry.
    assert call_count["n"] >= 2


# ----- boot observability: tooling check + qemu-aware reset guard ----------


def test_check_gpu_tooling_errors_when_sriov_manage_missing(monkeypatch, caplog):
    """Missing sriov-manage in the container is the silent root cause of the
    bus-reset wedge — it MUST be logged at ERROR, not swallowed at debug."""
    import gpu_discovery as gd

    monkeypatch.setattr(gd, "_tooling_checked", False)
    monkeypatch.setattr(gd.shutil, "which", lambda name: None)
    monkeypatch.setattr(gd.log, "propagate", True)  # let caplog capture it
    with caplog.at_level(logging.ERROR, logger="gpu_discovery"):
        gd._check_gpu_tooling()
    assert any("sriov-manage NOT found" in r.message for r in caplog.records)


def test_check_gpu_tooling_silent_when_tools_present(monkeypatch, caplog):
    import gpu_discovery as gd

    monkeypatch.setattr(gd, "_tooling_checked", False)
    monkeypatch.setattr(gd.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(gd.log, "propagate", True)
    with caplog.at_level(logging.WARNING, logger="gpu_discovery"):
        gd._check_gpu_tooling()
    assert caplog.records == []


def test_running_qemu_pids_detects_only_qemu(monkeypatch, tmp_path):
    import gpu_discovery as gd

    monkeypatch.setattr(gd, "_PROC_BASE", str(tmp_path))
    for pid, comm in (("123", "qemu-system-x86_64\n"), ("999", "bash\n")):
        (tmp_path / pid).mkdir()
        _write(tmp_path / pid / "comm", comm)
    # Non-numeric proc entries (e.g. 'self') must be ignored without error.
    (tmp_path / "self").mkdir()
    assert gd._running_qemu_pids() == [123]


def _stub_aggregate_fallback(monkeypatch, gd, qemu_pids):
    """Drive _aggregate_subdevice_profiles into its SR-IOV reset-fallback
    branch (main profiles empty, has_sriov True, VF cycle fails) and record
    whether the nvidia-smi -r bus reset is issued."""
    monkeypatch.setattr(gd, "_get_vgpu_profiles", lambda *a, **k: [])
    monkeypatch.setattr(gd, "_reset_sysfs_mdevs", lambda *a, **k: None)
    # vGPU host driver present so has_sriov gates True and the fallback runs
    # (the no-driver skip path is covered separately).
    monkeypatch.setattr(gd, "_vgpu_host_driver_present", lambda *a, **k: True)
    monkeypatch.setattr(gd, "_cycle_sriov_vfs", lambda *a, **k: False)
    monkeypatch.setattr(gd, "_running_qemu_pids", lambda: qemu_pids)
    monkeypatch.setattr(gd, "_enumerate_sriov_vf_paths", lambda *a, **k: [])
    monkeypatch.setattr(gd, "_wait_sriov_numvfs", lambda *a, **k: None)
    monkeypatch.setattr(gd, "_ensure_sriov_max_vfs", lambda *a, **k: None)
    monkeypatch.setattr(gd.os.path, "exists", lambda p: True)  # sriov_totalvfs
    monkeypatch.setattr(gd.os, "listdir", lambda p: [])
    calls = []
    monkeypatch.setattr(gd, "_nvidia_smi_gpu_reset", lambda bdf: calls.append(bdf))
    return calls


def test_aggregate_refuses_reset_when_qemu_running(monkeypatch):
    """A bus reset with live VF consumers wedges unkillably — refuse it while
    any qemu guest is alive (never expected on a fresh boot)."""
    import gpu_discovery as gd

    calls = _stub_aggregate_fallback(monkeypatch, gd, qemu_pids=[123])
    gd._aggregate_subdevice_profiles("00000000:05:00.0")
    assert calls == []


def test_aggregate_runs_reset_when_idle(monkeypatch):
    import gpu_discovery as gd

    calls = _stub_aggregate_fallback(monkeypatch, gd, qemu_pids=[])
    gd._aggregate_subdevice_profiles("00000000:05:00.0")
    assert len(calls) == 1


# --- build_card_descriptor (read-only single-card descriptor for runtime apply) ---
def _patch_descriptor_helpers(
    monkeypatch,
    *,
    vfs,
    vgpu_profiles,
    companions,
    mig_mode,
    mig_profiles,
    sriov,
    framework="legacy_mdev",
):
    """Patch build_card_descriptor's read-only helpers + a fake sysfs open, and
    make the DESTRUCTIVE discovery functions explode so any accidental call
    fails the test (build_card_descriptor must never reset mdevs / cycle VFs)."""
    import gpu_discovery as gd

    monkeypatch.setattr(gd, "_normalize_pci_bus_id", lambda b: b)
    monkeypatch.setattr(gd, "_enumerate_sriov_vf_paths", lambda base: list(vfs))
    # Read-only per-card framework probe (legacy_mdev vs vfio_variant).
    monkeypatch.setattr(gd.gpu_probe, "vgpu_framework", lambda b, run: framework)
    monkeypatch.setattr(gd, "_get_vgpu_profiles", lambda b: list(vgpu_profiles))
    monkeypatch.setattr(gd, "_find_audio_companions", lambda b: list(companions))
    monkeypatch.setattr(gd, "_read_mig_mode_current", lambda b: mig_mode)
    monkeypatch.setattr(gd, "_get_mig_profiles", lambda b: list(mig_profiles))

    def _boom(*a, **k):
        raise AssertionError("destructive discovery called in read-only descriptor")

    monkeypatch.setattr(gd, "_aggregate_subdevice_profiles", _boom)
    monkeypatch.setattr(gd, "_reset_sysfs_mdevs", _boom)
    monkeypatch.setattr(gd, "_cycle_sriov_vfs", _boom)

    class _F:
        def __init__(self, val):
            self.val = val

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self.val

    def fake_open(path, *a, **k):
        for key, val in sriov.items():
            if path.endswith(key):
                return _F(str(val))
        raise OSError("no such file")

    monkeypatch.setattr(gd, "open", fake_open, raising=False)
    return gd


def test_build_card_descriptor_vgpu_sriov(monkeypatch):
    gd = _patch_descriptor_helpers(
        monkeypatch,
        vfs=[
            "/sys/bus/pci/devices/0000:c5:00.4",
            "/sys/bus/pci/devices/0000:c5:00.5",
        ],
        vgpu_profiles=[{"name": "A40-4Q", "type_id": "nvidia-558"}],
        companions=["0000:c5:00.1"],
        mig_mode="[N/A]",
        mig_profiles=[],
        sriov={"sriov_totalvfs": 16, "sriov_numvfs": 16},
    )
    d = gd.build_card_descriptor("0000:c5:00.0", mdevs_reset_at="T")
    assert d["pci_bus_id"] == "0000:c5:00.0"
    assert d["path"] == "/sys/bus/pci/devices/0000:c5:00.0"
    assert d["sub_paths"] == [
        "/sys/bus/pci/devices/0000:c5:00.4",
        "/sys/bus/pci/devices/0000:c5:00.5",
    ]
    assert d["sriov_totalvfs"] == 16 and d["sriov_numvfs"] == 16
    assert d["companion_pci_bdfs"] == ["0000:c5:00.1"]
    assert d["mdevs_reset_at"] == "T"
    assert "mig_profiles" not in d  # not a MIG card
    assert d["framework"] == "legacy_mdev"  # 22.04 fleet default


def test_build_card_descriptor_sets_vfio_variant_framework(monkeypatch):
    # On a 24.04+ card the read-only descriptor must carry framework so the
    # runtime recarve over SSH (gpu_apply_cli -> apply_target) dispatches to the
    # vfio current_vgpu_type path, not the legacy mdev create.
    gd = _patch_descriptor_helpers(
        monkeypatch,
        vfs=["/sys/bus/pci/devices/0000:c5:00.4"],
        vgpu_profiles=[],  # PF exposes none; apply_target resolves per-VF
        companions=[],
        mig_mode="[N/A]",
        mig_profiles=[],
        sriov={"sriov_totalvfs": 64, "sriov_numvfs": 64},
        framework="vfio_variant",
    )
    d = gd.build_card_descriptor("0000:c5:00.0")
    assert d["framework"] == "vfio_variant"


def test_build_card_descriptor_passthrough_no_subpaths(monkeypatch):
    # A vfio-bound (passthrough) card has its VFs torn down -> no virtfn links,
    # so sub_paths is absent. apply_target re-enumerates after the rebind.
    gd = _patch_descriptor_helpers(
        monkeypatch,
        vfs=[],
        vgpu_profiles=[],
        companions=[],
        mig_mode="[N/A]",
        mig_profiles=[],
        sriov={"sriov_totalvfs": 16, "sriov_numvfs": 0},
    )
    d = gd.build_card_descriptor("0000:c5:00.0")
    assert "sub_paths" not in d
    assert d["sriov_numvfs"] == 0
    assert "mdevs_reset_at" not in d  # not passed


def test_build_card_descriptor_mig_card_includes_profiles(monkeypatch):
    gd = _patch_descriptor_helpers(
        monkeypatch,
        vfs=[],
        vgpu_profiles=[],
        companions=[],
        mig_mode="Enabled",
        mig_profiles=[{"name": "1g.10gb", "profile_id": 19}],
        sriov={"sriov_totalvfs": 0},
    )
    d = gd.build_card_descriptor("0000:c5:00.0")
    assert d["mig_profiles"] == [{"name": "1g.10gb", "profile_id": 19}]


def test_build_card_descriptor_is_readonly(monkeypatch):
    # The _boom patches fail the test if any destructive discovery runs; just
    # exercising the full happy path proves the descriptor is read-only.
    gd = _patch_descriptor_helpers(
        monkeypatch,
        vfs=["/sys/bus/pci/devices/0000:c5:00.4"],
        vgpu_profiles=[{"name": "A40-4Q", "type_id": "nvidia-558"}],
        companions=["0000:c5:00.1"],
        mig_mode="Disabled",
        mig_profiles=[{"name": "1g.10gb", "profile_id": 19}],
        sriov={"sriov_totalvfs": 16, "sriov_numvfs": 16},
    )
    gd.build_card_descriptor("0000:c5:00.0", mdevs_reset_at="T")


# --- M0: MIG-backed vGPU profile annotation (DC-N-Q <-> +gfx GI) ---
def test_annotate_mig_backed_vgpu_profiles_maps_slice_to_gfx_gi():
    import gpu_discovery as _gd

    vgpu = [
        {
            "name": "RTXPro6000BlackwellDC-24Q",
            "type_id": "nvidia-1534",
            "available_instances": 0,
            "max_instances": 0,
        },
        {
            "name": "RTXPro6000BlackwellDC-1_24Q",
            "type_id": "nvidia-1561",
            "available_instances": 0,
            "max_instances": 0,
        },
        {
            "name": "RTXPro6000BlackwellDC-2_24Q",
            "type_id": "nvidia-1570",
            "available_instances": 0,
            "max_instances": 0,
        },
        {
            "name": "RTXPro6000BlackwellDC-4_24Q",
            "type_id": "nvidia-1576",
            "available_instances": 0,
            "max_instances": 0,
        },
    ]
    mig = [
        {"name": "1g.24gb", "profile_id": 14, "max_instances": 4, "memory_gib": 23.12},
        {
            "name": "1g.24gb+gfx",
            "profile_id": 47,
            "max_instances": 4,
            "memory_gib": 23.12,
        },
        {
            "name": "2g.48gb+gfx",
            "profile_id": 35,
            "max_instances": 2,
            "memory_gib": 46.5,
        },
        {
            "name": "4g.96gb+gfx",
            "profile_id": 32,
            "max_instances": 1,
            "memory_gib": 93.38,
        },
    ]
    _gd._annotate_mig_backed_vgpu_profiles(vgpu, mig)
    by = {p["name"]: p for p in vgpu}
    # Non-MIG full-card profile is left untouched.
    assert "mig" not in by["RTXPro6000BlackwellDC-24Q"]
    # 1-slice -> 1g.24gb+gfx (the +gfx variant, NOT the plain id 14), count 4.
    p1 = by["RTXPro6000BlackwellDC-1_24Q"]
    assert p1["mig"] is True
    assert p1["mig_profile_id"] == 47
    assert p1["mig_count"] == 4
    assert p1["max_instances"] == 4
    # 2-slice and 4-slice map to their +gfx GIs with the right per-card counts.
    assert by["RTXPro6000BlackwellDC-2_24Q"]["mig_profile_id"] == 35
    assert by["RTXPro6000BlackwellDC-2_24Q"]["max_instances"] == 2
    assert by["RTXPro6000BlackwellDC-4_24Q"]["mig_profile_id"] == 32
    assert by["RTXPro6000BlackwellDC-4_24Q"]["max_instances"] == 1


def test_annotate_mig_backed_noop_without_gfx_gi():
    import gpu_discovery as _gd

    # No +gfx GI for the slice count -> profile stays unannotated (non-MIG).
    vgpu = [{"name": "M-1_24Q", "max_instances": 0}]
    _gd._annotate_mig_backed_vgpu_profiles(
        vgpu, [{"name": "1g.24gb", "profile_id": 14, "max_instances": 4}]
    )
    assert "mig" not in vgpu[0]


def test_card_in_use_detects_vf_holder(monkeypatch):
    """_card_in_use must see a consumer on ANY SR-IOV VF, not just the PF
    group (the gap that let a vGPU desktop's card be torn down -> D-state wedge)."""
    import gpu_discovery as gd

    monkeypatch.setattr(gd, "_vfio_group_in_use", lambda p: False)  # PF free
    monkeypatch.setattr(gd.os, "listdir", lambda p: ["virtfn0", "config", "driver"])
    monkeypatch.setattr(
        gd.os.path,
        "realpath",
        lambda p: "/sys/kernel/iommu_groups/42" if p.endswith("iommu_group") else p,
    )
    monkeypatch.setattr(gd, "_vfio_group_held", lambda g: g == "42")  # VF held
    assert gd._card_in_use("/sys/bus/pci/devices/0000:03:00.0") is True


def test_card_in_use_false_when_pf_and_vfs_free(monkeypatch):
    import gpu_discovery as gd

    monkeypatch.setattr(gd, "_vfio_group_in_use", lambda p: False)
    monkeypatch.setattr(gd.os, "listdir", lambda p: ["virtfn0", "config"])
    monkeypatch.setattr(
        gd.os.path,
        "realpath",
        lambda p: "/sys/kernel/iommu_groups/42" if p.endswith("iommu_group") else p,
    )
    monkeypatch.setattr(gd, "_vfio_group_held", lambda g: False)
    assert gd._card_in_use("/sys/bus/pci/devices/0000:03:00.0") is False


def test_card_in_use_true_when_pf_held(monkeypatch):
    import gpu_discovery as gd

    monkeypatch.setattr(gd, "_vfio_group_in_use", lambda p: True)  # PF held
    assert gd._card_in_use("/sys/bus/pci/devices/0000:03:00.0") is True


def test_discover_gpus_skips_cycle_on_vfio_bound_card(monkeypatch, tmp_path):
    """A card already bound to vfio-pci (passthrough) must NOT be SR-IOV-cycled:
    _aggregate_subdevice_profiles (which runs sriov-manage -d) must never be
    called for it. It is reported as passthrough."""
    _redirect_sysfs(monkeypatch, tmp_path)
    import gpu_discovery as gd

    monkeypatch.setattr(
        gd,
        "_run_nvidia_smi",
        lambda: [
            {
                "name": "NVIDIA RTX PRO 6000 Blackwell Server Edition",
                "memory_total_mb": 98304,
                "pci_bus_id": "00000000:63:00.0",
                "driver_version": "580.65.05",
                "gpu_uuid": "GPU-pt",
                "mig_mode": "[N/A]",
            }
        ],
    )
    monkeypatch.setattr(gd, "_read_driver", lambda *a, **k: "vfio-pci")

    def _boom(*a, **k):
        raise AssertionError("SR-IOV cycle ran on a vfio-bound passthrough card")

    monkeypatch.setattr(gd, "_aggregate_subdevice_profiles", _boom)
    monkeypatch.setattr(gd, "_find_audio_companions", lambda _id: [])
    monkeypatch.setattr(gd, "_scan_sysfs_nvidia_gpus", lambda _known: [])

    gpus = discover_gpus()
    assert len(gpus) == 1
    g = gpus[0]
    assert g["vgpu_profiles"] == []
    assert g.get("current_profile") == "passthrough"


def test_discover_gpus_cycles_nvidia_bound_card(monkeypatch, tmp_path):
    """An nvidia-bound card is still enumerated via the SR-IOV cycle."""
    _redirect_sysfs(monkeypatch, tmp_path)
    import gpu_discovery as gd

    monkeypatch.setattr(
        gd,
        "_run_nvidia_smi",
        lambda: [
            {
                "name": "NVIDIA RTX PRO 6000 Blackwell Server Edition",
                "memory_total_mb": 98304,
                "pci_bus_id": "00000000:86:00.0",
                "driver_version": "580.65.05",
                "gpu_uuid": "GPU-vgpu",
                "mig_mode": "[N/A]",
            }
        ],
    )
    monkeypatch.setattr(gd, "_read_driver", lambda *a, **k: "nvidia")
    called = {"n": 0}

    real_profiles = [
        {
            "name": "RTXPro6000BlackwellDC-24Q",
            "type_id": "nvidia-2000",
            "available_instances": 4,
        }
    ]

    def _agg(_pci):
        called["n"] += 1
        return (real_profiles, None, None, "legacy_mdev")

    monkeypatch.setattr(gd, "_aggregate_subdevice_profiles", _agg)
    monkeypatch.setattr(gd, "_find_audio_companions", lambda _id: [])
    monkeypatch.setattr(gd, "_scan_sysfs_nvidia_gpus", lambda _known: [])

    gpus = discover_gpus()
    assert called["n"] == 1
    assert gpus[0]["vgpu_profiles"] == real_profiles
