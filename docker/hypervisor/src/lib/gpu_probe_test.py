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
