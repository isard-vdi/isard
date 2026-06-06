"""Shared builders for the host shell commands that apply a vGPU/MIG/passthrough
profile to one physical GPU.

Pure, dependency-free (stdlib only): every function returns a ``list[str]`` (or a
single ``str``) of shell commands and performs NO execution, NO logging, NO DB or
libvirt access. This is the single source of truth for the fragile sysfs /
nvidia-smi / vfio-pci sequences, consumed by:

  * the engine (``engine.models.hyp``), which feeds them to ``execute_commands``
    over SSH (current behaviour, unchanged), and
  * the hypervisor container, which feeds the SAME strings to a local executor
    (``subprocess``) so the hypervisor can apply profiles itself at registration.

Keeping the strings here means the two paths cannot drift. The command strings
are byte-identical to the engine's previous inline sequences.
"""


def build_mig_transition_cmds(
    pci_bdf,
    old_is_mig,
    new_is_mig,
    old_profile,
    new_profile,
    new_mig_profile_id,
):
    """Commands to transition MIG mode for a card (vGPU/PT<->MIG, MIG<->MIG).

    Returns a ``list[str]``, or ``None`` when neither side is MIG (the caller
    should not have routed here). The caller does the logging and execution.
    """
    cmds = []
    if old_is_mig and new_is_mig:
        # MIG -> MIG: destroy old instances, create new ones
        cmds = [
            f"nvidia-smi mig -i {pci_bdf} -dci 2>/dev/null || true",
            f"nvidia-smi mig -i {pci_bdf} -dgi 2>/dev/null || true",
            f"nvidia-smi mig -i {pci_bdf} -cgi {new_mig_profile_id}",
            f"nvidia-smi mig -i {pci_bdf} -cci",
        ]
    elif not old_is_mig and new_is_mig:
        # vGPU/PT -> MIG: remove mdevs, rebind nvidia if PT, enable MIG
        if old_profile == "passthrough":
            # Rebind to nvidia driver first
            cmds.extend(
                [
                    f"echo {pci_bdf} > /sys/bus/pci/drivers/vfio-pci/unbind 2>/dev/null || true",
                    f"echo > /sys/bus/pci/devices/{pci_bdf}/driver_override",
                    f"echo {pci_bdf} > /sys/bus/pci/drivers_probe 2>/dev/null || true",
                    "sleep 2",
                ]
            )
        elif old_profile:
            # vGPU mode with active SR-IOV VFs: nvidia-smi -mig 1 rejects
            # the PF while any VF is bound, so tear them down first.
            # sriov-manage handles the unbind/sriov_numvfs=0 dance the
            # nvidia driver requires.
            cmds.append(f"sriov-manage -d {pci_bdf} 2>/dev/null || true")
        cmds.extend(
            [
                f"nvidia-smi -i {pci_bdf} -mig 1",
                f"nvidia-smi -i {pci_bdf} --gpu-reset 2>/dev/null || true",
                "sleep 2",
                f"nvidia-smi mig -i {pci_bdf} -cgi {new_mig_profile_id}",
                f"nvidia-smi mig -i {pci_bdf} -cci",
            ]
        )
    elif old_is_mig and not new_is_mig:
        # MIG -> vGPU/PT: destroy instances, disable MIG, reset
        cmds = [
            f"nvidia-smi mig -i {pci_bdf} -dci 2>/dev/null || true",
            f"nvidia-smi mig -i {pci_bdf} -dgi 2>/dev/null || true",
            f"nvidia-smi -i {pci_bdf} -mig 0",
            f"nvidia-smi -i {pci_bdf} --gpu-reset 2>/dev/null || true",
            "sleep 2",
        ]
        if new_profile != "passthrough":
            # Restore SR-IOV VFs for vGPU mode. For passthrough the caller
            # tears VFs down again and rebinds to vfio-pci, so re-enabling
            # here would be wasted work.
            cmds.append(f"sriov-manage -e {pci_bdf} 2>/dev/null || true")
    else:
        return None
    return cmds


def build_vfio_bind_cmds(pci_bdf, sriov_totalvfs, sriov_numvfs):
    """Bind a GPU PF to vfio-pci for whole-GPU passthrough.

    SR-IOV cards with VFs actually created must disable VFs (the pci-pf-stub +
    sriov_numvfs=0 dance) before vfio-pci will accept the PF; non-SR-IOV cards
    are a simple driver swap. Skipped-VF case (sriov_numvfs==0) takes the swap.
    """
    if sriov_totalvfs > 0 and sriov_numvfs > 0:
        sb = pci_bdf.replace("00.0", "")
        return [
            "modprobe vfio-pci",
            "modprobe pci-pf-stub",
            f"echo 1 > /proc/driver/nvidia/gpus/{pci_bdf}/unbindLock 2>/dev/null || true",
            f"echo {pci_bdf} > /sys/bus/pci/drivers/nvidia/unbind 2>/dev/null || true",
            f"for vf in $(lspci -D -s '{sb}' | awk '{{print $1}}'); do "
            f'[ "$vf" = "{pci_bdf}" ] && continue; '
            f"[ -e /sys/bus/pci/devices/$vf/driver ] && "
            f"echo $vf > /sys/bus/pci/devices/$vf/driver/unbind 2>/dev/null || true; "
            f"done",
            f'VEND_DEV=$(lspci -n -s {pci_bdf} | awk \'{{gsub(":", " ", $3); print $3}}\') && '
            f'echo "$VEND_DEV" > /sys/bus/pci/drivers/pci-pf-stub/new_id 2>/dev/null || true && '
            f"[ -e /sys/bus/pci/drivers/pci-pf-stub/{pci_bdf} ] || "
            f"echo {pci_bdf} > /sys/bus/pci/drivers/pci-pf-stub/bind",
            "sleep 0.5",
            f"echo 0 > /sys/bus/pci/devices/{pci_bdf}/sriov_numvfs 2>/dev/null || true",
            f"echo {pci_bdf} > /sys/bus/pci/drivers/pci-pf-stub/unbind 2>/dev/null || true",
            f'VEND_DEV=$(lspci -n -s {pci_bdf} | awk \'{{gsub(":", " ", $3); print $3}}\') && '
            f'echo "$VEND_DEV" > /sys/bus/pci/drivers/pci-pf-stub/remove_id 2>/dev/null || true',
            f"printf 'vfio-pci' > /sys/bus/pci/devices/{pci_bdf}/driver_override",
            f"echo {pci_bdf} > /sys/bus/pci/drivers_probe 2>/dev/null || true",
        ]
    return [
        "modprobe vfio-pci",
        f"echo {pci_bdf} > /sys/bus/pci/drivers/nvidia/unbind 2>/dev/null || true",
        f"echo vfio-pci > /sys/bus/pci/devices/{pci_bdf}/driver_override",
        f"echo {pci_bdf} > /sys/bus/pci/drivers_probe",
    ]


def build_vfio_group_mknod_cmds(pci_bdf):
    """Create /dev/vfio/<group> inside the container (the bind mount may not see
    kernel-created nodes on the host devtmpfs after container start)."""
    return [
        f"IOMMU_GROUP=$(basename $(readlink /sys/bus/pci/devices/{pci_bdf}/iommu_group)) && "
        f"if [ ! -e /dev/vfio/$IOMMU_GROUP ]; then "
        f"DEV=$(cat /sys/class/vfio/$IOMMU_GROUP/dev) && "
        f"MAJOR=${{DEV%%:*}} && MINOR=${{DEV##*:}} && "
        f"mknod /dev/vfio/$IOMMU_GROUP c $MAJOR $MINOR && "
        f"chmod 0666 /dev/vfio/$IOMMU_GROUP; "
        f"fi",
    ]


def build_companion_bind_cmds(cbdf):
    """Bind an HD-audio companion function to vfio-pci alongside its GPU."""
    return [
        f"[ -L /sys/bus/pci/devices/{cbdf}/driver ] && "
        f"echo {cbdf} > /sys/bus/pci/devices/{cbdf}/driver/unbind "
        f"2>/dev/null || true",
        f"echo vfio-pci > /sys/bus/pci/devices/{cbdf}/driver_override",
        f"echo {cbdf} > /sys/bus/pci/drivers_probe 2>/dev/null || true",
    ]


def build_vfio_unbind_cmds(pci_bdf, sriov_totalvfs):
    """Unbind a GPU PF from vfio-pci back to nvidia (reverse of passthrough).

    SR-IOV cards re-enable VFs via the pci-pf-stub dance and rebind nvidia;
    non-SR-IOV cards are a simple driver swap back.
    """
    if sriov_totalvfs > 0:
        sb = pci_bdf.replace("00.0", "")
        return [
            f"IOMMU_GROUP=$(basename $(readlink /sys/bus/pci/devices/{pci_bdf}/iommu_group)) && "
            f"rm -f /dev/vfio/$IOMMU_GROUP",
            f"echo {pci_bdf} > /sys/bus/pci/drivers/vfio-pci/unbind 2>/dev/null || true",
            f"echo > /sys/bus/pci/devices/{pci_bdf}/driver_override",
            f"echo {pci_bdf} > /sys/bus/pci/drivers_probe 2>/dev/null || true",
            "sleep 2",
            f"echo 1 > /proc/driver/nvidia/gpus/{pci_bdf}/unbindLock 2>/dev/null || true",
            f"echo {pci_bdf} > /sys/bus/pci/drivers/nvidia/unbind 2>/dev/null || true",
            f'VEND_DEV=$(lspci -n -s {pci_bdf} | awk \'{{gsub(":", " ", $3); print $3}}\') && '
            f'echo "$VEND_DEV" > /sys/bus/pci/drivers/pci-pf-stub/new_id 2>/dev/null || true && '
            f"[ -e /sys/bus/pci/drivers/pci-pf-stub/{pci_bdf} ] || "
            f"echo {pci_bdf} > /sys/bus/pci/drivers/pci-pf-stub/bind",
            "sleep 0.5",
            f"echo {sriov_totalvfs} > /sys/bus/pci/devices/{pci_bdf}/sriov_numvfs 2>/dev/null || true",
            f"echo {pci_bdf} > /sys/bus/pci/drivers/pci-pf-stub/unbind 2>/dev/null || true",
            f'VEND_DEV=$(lspci -n -s {pci_bdf} | awk \'{{gsub(":", " ", $3); print $3}}\') && '
            f'echo "$VEND_DEV" > /sys/bus/pci/drivers/pci-pf-stub/remove_id 2>/dev/null || true',
            f"for vf in $(lspci -D -s '{sb}' | awk '{{print $1}}'); do "
            f'[ "$vf" = "{pci_bdf}" ] && continue; '
            f"[ -e /sys/bus/pci/devices/$vf/driver ] && "
            f"echo $vf > /sys/bus/pci/devices/$vf/driver/unbind 2>/dev/null || true; "
            f"echo $vf > /sys/bus/pci/drivers/nvidia/bind 2>/dev/null || true; "
            f"done",
            f"echo {pci_bdf} > /sys/bus/pci/drivers/nvidia/bind 2>/dev/null || true",
            "nvidia-smi -pm 1 2>/dev/null || true",
        ]
    return [
        f"IOMMU_GROUP=$(basename $(readlink /sys/bus/pci/devices/{pci_bdf}/iommu_group)) && "
        f"rm -f /dev/vfio/$IOMMU_GROUP",
        f"echo {pci_bdf} > /sys/bus/pci/drivers/vfio-pci/unbind 2>/dev/null || true",
        f"echo > /sys/bus/pci/devices/{pci_bdf}/driver_override",
        f"echo {pci_bdf} > /sys/bus/pci/drivers_probe",
    ]


def build_pf_recover_nvidia_cmds(pci_bdf):
    """Recover a PF that is bound to NO driver -- or to a stray transient like
    pci-pf-stub -- back to nvidia, the base state every apply expects.

    A profile transition interrupted mid-flight (e.g. the hypervisor
    crashed/restarted between the vfio unbind and the nvidia rebind, or a
    half-done SR-IOV dance left pci-pf-stub bound) can leave the PF orphaned.
    nvidia-smi/sysfs then operate on a dead PF and the next apply fails. Clear
    any stale driver_override (a half-done passthrough leaves it 'vfio-pci'),
    drop a leftover pci-pf-stub binding, re-probe, and bind nvidia explicitly.
    Every step is best-effort so this is safe to run from any orphaned state.
    """
    return [
        f"echo {pci_bdf} > /sys/bus/pci/drivers/pci-pf-stub/unbind 2>/dev/null || true",
        f"echo > /sys/bus/pci/devices/{pci_bdf}/driver_override 2>/dev/null || true",
        f"echo {pci_bdf} > /sys/bus/pci/drivers_probe 2>/dev/null || true",
        f"echo {pci_bdf} > /sys/bus/pci/drivers/nvidia/bind 2>/dev/null || true",
        "udevadm settle 2>/dev/null || true",
        "nvidia-smi -pm 1 2>/dev/null || true",
    ]


def build_companion_release_cmds(cbdf):
    """Release an HD-audio companion from vfio-pci so the host driver re-binds."""
    return [
        f"[ -L /sys/bus/pci/devices/{cbdf}/driver ] && "
        f"echo {cbdf} > /sys/bus/pci/devices/{cbdf}/driver/unbind "
        f"2>/dev/null || true",
        f"echo > /sys/bus/pci/devices/{cbdf}/driver_override",
        f"echo {cbdf} > /sys/bus/pci/drivers_probe 2>/dev/null || true",
    ]
