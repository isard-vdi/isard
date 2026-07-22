"""Unit tests for gpu_probe — the read-only GPU probe leaf shared by gpu_apply
and gpu_discovery.

Run locally:
    cd docker/hypervisor/src/lib && python -m pytest gpu_probe_test.py -v

These pin the leaf's own surface (the readers' empty-result guards and the
dependency-injected _live_mdev_suffix); current_profile_from_state is also
exercised through gpu_apply's re-export in gpu_apply_test.py.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import gpu_probe as gp  # noqa: E402


@pytest.mark.parametrize(
    "driver,mig,live,expected",
    [
        ("vfio-pci", "[N/A]", None, "passthrough"),
        ("nvidia", "Disabled", "4Q", "4Q"),
        ("nvidia", "Enabled", None, gp.MIG_CURRENT),
        ("nvidia", "Disabled", None, None),
        (None, None, None, None),
    ],
)
def test_current_profile_from_state(driver, mig, live, expected):
    assert gp.current_profile_from_state(driver, mig, live) == expected


def test_out_guards_empty_result():
    assert gp._out([]) == ""
    assert gp._out(None) == ""
    assert gp._out([{"err": "e"}]) == ""
    assert gp._out([{"out": "x\n"}]) == "x\n"


def test_readers_tolerate_empty_run():
    empty = lambda cmds, timeout=0: []  # noqa: E731
    assert gp._read_driver("0000:c5:00.0", empty) is None
    assert gp._read_mig_mode("0000:c5:00.0", empty) is None
    assert gp._enumerate_vf_sub_paths("0000:c5:00.0", empty) == []


def test_read_driver_basenames_the_symlink():
    run = lambda cmds, timeout=0: [
        {"out": "../../../bus/pci/drivers/vfio-pci\n"}
    ]  # noqa: E731
    assert gp._read_driver("0000:c5:00.0", run) == "vfio-pci"


def test_live_mdev_suffix_injects_profile_source():
    # The profile lister is injected, so the leaf never imports a discovery
    # reader. A live mdev path resolves to its profile suffix via profiles_for.
    run = lambda cmds, timeout=0: [  # noqa: E731
        {
            "out": "/sys/bus/pci/devices/0000:c5:00.1/mdev_supported_types/nvidia-558/devices/uuid\n"
        }
    ]
    profiles_for = lambda bdf: [
        {"name": "A40-4Q", "type_id": "nvidia-558"}
    ]  # noqa: E731
    assert gp._live_mdev_suffix("0000:c5:00.0", run, profiles_for) == "4Q"


def test_live_mdev_suffix_none_when_no_live_mdev():
    run = lambda cmds, timeout=0: [{"out": ""}]  # noqa: E731
    assert gp._live_mdev_suffix("0000:c5:00.0", run, lambda b: []) is None


def test_enumerate_vf_sub_paths_builds_sysfs_paths():
    run = lambda cmds, timeout=0: [
        {"out": "0000:c5:00.1\n0000:c5:00.2\n"}
    ]  # noqa: E731
    assert gp._enumerate_vf_sub_paths("0000:c5:00.0", run) == [
        "/sys/bus/pci/devices/0000:c5:00.1",
        "/sys/bus/pci/devices/0000:c5:00.2",
    ]


# --------------------------------------------------------------------------- #
# vgpu_framework — per-card runtime detection of the vGPU sysfs framework.
# --------------------------------------------------------------------------- #
def test_vgpu_framework_vfio_when_creatable_types_present():
    # A VF exposing nvidia/creatable_vgpu_types => the kernel >=6.8 vendor VFIO
    # variant framework (Ubuntu 24.04+). The probe greps for that file.
    run = lambda cmds, timeout=0: [  # noqa: E731
        {"out": "/sys/bus/pci/devices/0000:c5:00.4/nvidia/creatable_vgpu_types\n"}
    ]
    assert gp.vgpu_framework("0000:c5:00.0", run) == "vfio_variant"


def test_vgpu_framework_legacy_when_no_creatable_types():
    # 22.04/5.15: no creatable_vgpu_types anywhere -> legacy mdev framework.
    run = lambda cmds, timeout=0: [{"out": ""}]  # noqa: E731
    assert gp.vgpu_framework("0000:c5:00.0", run) == "legacy_mdev"


def test_vgpu_framework_legacy_tolerates_empty_run():
    empty = lambda cmds, timeout=0: []  # noqa: E731
    assert gp.vgpu_framework("0000:c5:00.0", empty) == "legacy_mdev"


def test_vgpu_framework_force_override(monkeypatch):
    # The kill-switch forces a framework regardless of host state (debugging /
    # mixed-fleet escape hatch).
    run_vfio = lambda cmds, timeout=0: [  # noqa: E731
        {"out": "/sys/bus/pci/devices/0000:c5:00.4/nvidia/creatable_vgpu_types\n"}
    ]
    monkeypatch.setenv("ISARD_VGPU_FORCE_FRAMEWORK", "legacy_mdev")
    assert gp.vgpu_framework("0000:c5:00.0", run_vfio) == "legacy_mdev"
    monkeypatch.setenv("ISARD_VGPU_FORCE_FRAMEWORK", "vfio_variant")
    assert (
        gp.vgpu_framework("0000:c5:00.0", lambda cmds, timeout=0: [{"out": ""}])
        == "vfio_variant"
    )


def test_vgpu_framework_force_override_ignores_garbage(monkeypatch):
    # A bogus override value must NOT be trusted; fall back to live detection.
    monkeypatch.setenv("ISARD_VGPU_FORCE_FRAMEWORK", "nonsense")
    run = lambda cmds, timeout=0: [{"out": ""}]  # noqa: E731
    assert gp.vgpu_framework("0000:c5:00.0", run) == "legacy_mdev"
