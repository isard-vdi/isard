"""Smoke tests for the vfio-pci heal path in gpu_discovery.

These tests do not run in CI (the hypervisor image has no test pipeline),
but they exercise the file-system contract for ``_vfio_group_in_use`` and
``_rebind_vfio_to_nvidia_if_idle`` against a tmp_path-built sysfs/proc
shape so an operator can validate the heal logic locally before deploying
to production.

Run inside the hypervisor container::

    docker exec isard-hypervisor sh -c \\
        "cd /opt/isardvdi && python3 -m pytest lib/test_gpu_discovery.py -v"
"""

import os
from unittest.mock import patch

import pytest
from lib import gpu_discovery


def _make_pci_dev(tmp_path, bdf, iommu_group, driver_name):
    """Build a fake /sys/bus/pci/devices/<bdf>/ tree."""
    dev = tmp_path / "sys" / "bus" / "pci" / "devices" / bdf
    dev.mkdir(parents=True)
    (dev / "iommu_group").symlink_to(
        tmp_path / "sys" / "kernel" / "iommu_groups" / str(iommu_group)
    )
    (tmp_path / "sys" / "kernel" / "iommu_groups" / str(iommu_group)).mkdir(
        parents=True
    )
    drivers_dir = tmp_path / "sys" / "bus" / "pci" / "drivers"
    drivers_dir.mkdir(parents=True, exist_ok=True)
    (drivers_dir / driver_name).mkdir(exist_ok=True)
    (dev / "driver").symlink_to(drivers_dir / driver_name)
    return dev


def _make_vfio_dev(tmp_path, group):
    vfio_dir = tmp_path / "dev" / "vfio"
    vfio_dir.mkdir(parents=True, exist_ok=True)
    vfio_path = vfio_dir / str(group)
    vfio_path.write_text("")
    return vfio_path


# ---------------------------------------------------------------------------
# _vfio_group_in_use
# ---------------------------------------------------------------------------


def test_vfio_group_in_use_returns_false_when_no_consumer(tmp_path, monkeypatch):
    dev = _make_pci_dev(tmp_path, "0000:3b:00.0", iommu_group=42, driver_name="nvidia")
    vfio_path = _make_vfio_dev(tmp_path, 42)

    # Empty /proc — no fd points at /dev/vfio/42. Capture the real
    # functions BEFORE monkeypatching: the lambdas must delegate to the
    # originals, not to their own patched selves (recursion).
    proc = tmp_path / "proc"
    proc.mkdir()
    real_exists = os.path.exists
    real_listdir = os.listdir
    monkeypatch.setattr(
        "os.path.exists", lambda p: p == str(vfio_path) or real_exists(p)
    )
    monkeypatch.setattr(
        "os.listdir",
        lambda p: [] if p == "/proc" else real_listdir(p),
    )

    assert gpu_discovery._vfio_group_in_use(str(dev)) is False


def test_vfio_group_in_use_missing_group_node_means_no_consumer(tmp_path):
    """Since the upstream gpu lifecycle port (!4496/!4519) a NONEXISTENT
    ``/dev/vfio/<group>`` node means no consumer is possible -> False
    (a missing node cannot be held by qemu). Read ERRORS on an existing
    node stay conservative -> True (see _vfio_group_held)."""
    bogus = tmp_path / "missing"
    # No such device dir: the group resolves to a name with no
    # /dev/vfio/<group> node -> no consumer possible -> False.
    assert gpu_discovery._vfio_group_in_use(str(bogus)) is False


# ---------------------------------------------------------------------------
# _rebind_vfio_to_nvidia_if_idle
# ---------------------------------------------------------------------------


def test_rebind_returns_true_when_already_nvidia(tmp_path):
    dev = _make_pci_dev(tmp_path, "0000:3b:00.0", iommu_group=42, driver_name="nvidia")
    assert gpu_discovery._rebind_vfio_to_nvidia_if_idle(str(dev)) is True


def test_rebind_skips_when_consumer_holds_iommu_group(tmp_path):
    dev = _make_pci_dev(
        tmp_path, "0000:3b:00.0", iommu_group=42, driver_name="vfio-pci"
    )
    with patch.object(gpu_discovery, "_vfio_group_in_use", return_value=True):
        assert gpu_discovery._rebind_vfio_to_nvidia_if_idle(str(dev)) is False


def test_rebind_skips_when_driver_is_other_than_nvidia_or_vfio(tmp_path):
    dev = _make_pci_dev(
        tmp_path, "0000:3b:00.0", iommu_group=42, driver_name="pci-pf-stub"
    )
    # Conservative: only act on vfio-pci leaks.
    assert gpu_discovery._rebind_vfio_to_nvidia_if_idle(str(dev)) is False
