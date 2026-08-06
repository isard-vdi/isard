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


# --- MIG mode toggle: nvidia-smi --gpu-reset must be GATED to kernel < 7 ------
# A secondary-bus GPU reset of an SR-IOV/MIG card WEDGES the host unkillably on
# Ubuntu 26.04 / kernel 7.0 (verified on hardware). The reset is only needed
# to apply a *pending* MIG-mode change on Ampere-era kernels; on Hopper+/Blackwell
# `nvidia-smi -mig 1/0` takes effect live (verified RTX PRO 6000). So every
# --gpu-reset the builders emit must be guarded by a `uname -r ... -lt 7` check.


def _reset_lines(cmds):
    return [c for c in (cmds or []) if "--gpu-reset" in c]


def test_mig_enable_transition_gpu_reset_is_kernel_gated():
    cmds = gpu_cmds.build_mig_transition_cmds(
        "0000:c1:00.0",
        old_is_mig=False,
        new_is_mig=True,
        old_profile="8Q",
        new_profile="1_24Q",
        new_mig_profile_id=47,
        mig_count=4,
    )
    resets = _reset_lines(cmds)
    assert resets, "MIG-enable still applies a pending mode on older kernels"
    for r in resets:
        assert "uname -r" in r and "-lt 7" in r, f"reset not kernel-gated: {r}"


def test_mig_disable_transition_gpu_reset_is_kernel_gated():
    cmds = gpu_cmds.build_mig_transition_cmds(
        "0000:c1:00.0",
        old_is_mig=True,
        new_is_mig=False,
        old_profile="1_24Q",
        new_profile="8Q",
        new_mig_profile_id=47,
    )
    resets = _reset_lines(cmds)
    assert resets
    for r in resets:
        assert "uname -r" in r and "-lt 7" in r, f"reset not kernel-gated: {r}"


def test_mig_vgpu_carve_gpu_reset_is_kernel_gated():
    cmds = gpu_cmds.build_mig_vgpu_carve_cmds("0000:c1:00.0", 47, 4)
    resets = _reset_lines(cmds)
    assert resets
    for r in resets:
        assert "uname -r" in r and "-lt 7" in r, f"reset not kernel-gated: {r}"
