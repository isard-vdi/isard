"""Unit tests for the shared GPU shell-command builders.

Run locally:
    cd component/_common && PYTHONPATH=src python -m pytest \
        src/isardvdi_common/lib/tests/test_gpu_cmds.py -v
"""

from isardvdi_common.lib import gpu_cmds

# --- vendor-specific VFIO framework (kernel >=6.8 / Ubuntu 24.04+) ----------
# A vGPU is created/destroyed by writing the numeric type-id (or 0) to the VF's
# nvidia/current_vgpu_type, instead of the legacy
# `echo <uuid> > mdev_supported_types/<id>/create`.


def test_build_vgpu_set_cmd_writes_current_vgpu_type():
    assert (
        gpu_cmds.build_vgpu_set_cmd("0000:c5:00.4", "694")
        == "echo 694 > /sys/bus/pci/devices/0000:c5:00.4/nvidia/current_vgpu_type"
    )


def test_build_vgpu_clear_cmd_writes_zero():
    assert (
        gpu_cmds.build_vgpu_clear_cmd("0000:c5:00.4")
        == "echo 0 > /sys/bus/pci/devices/0000:c5:00.4/nvidia/current_vgpu_type"
    )
