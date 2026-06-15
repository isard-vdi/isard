"""Read-only GPU probe primitives — the dependency-free leaf shared by
``gpu_apply`` (profile *apply*) and ``gpu_discovery`` (profile *discovery*).

These functions ONLY read host state: read-only ``nvidia-smi`` queries and sysfs
symlink/attribute reads. NOTHING here mutates the host — no ``sriov_numvfs``
writes, no mdev create/remove, no ``nvidia-smi -r`` / ``--gpu-reset``, no driver
bind/unbind. The mutating sequences stay in ``gpu_apply`` (apply) and
``gpu_discovery`` (``_reset_sysfs_mdevs`` / ``_cycle_sriov_vfs``).

Extracting these here breaks the historical ``gpu_apply`` <-> ``gpu_discovery``
import cycle: both modules now import THIS leaf one-directionally (and
``gpu_apply`` still imports the two pure-read discovery helpers
``_get_vgpu_profiles`` / ``_vfio_group_in_use`` at module level, which is acyclic
now that ``gpu_discovery`` no longer imports ``gpu_apply``).

Loads under both the container layout (``/src/isardvdi_common/lib``) and the tests'
``sys.path.insert(0, dirname)`` bootstrap: imported by bare name from the same
lib directory, and loads the shared ``gpu_pool_policy`` via the same
``__file__``-relative fallback ``gpu_apply`` uses.
"""

import os
import subprocess
from importlib.machinery import SourceFileLoader


def _load_shared(name):
    """Load a shared leaf (``gpu_cmds`` / ``gpu_pool_policy``).
    ``/src/isardvdi_common/lib`` in the container (the hypervisor image
    ships the isardvdi_common package there); the repo path in a dev/test
    checkout."""
    candidates = [
        os.path.join("/src/isardvdi_common/lib", name + ".py"),
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "..",
            "..",
            "component",
            "_common",
            "src",
            "isardvdi_common",
            "lib",
            name + ".py",
        ),
    ]
    for path in candidates:
        if os.path.exists(path):
            return SourceFileLoader(name, path).load_module()
    raise ImportError(f"shared module {name} not found in {candidates}")


canonical_suffix = _load_shared("gpu_pool_policy").canonical_suffix

# Sentinel for "card is physically in MIG mode but the live GPU-instance profile
# isn't determined here" -- enough to route the MIG teardown at apply time.
MIG_CURRENT = "__mig__"


# --------------------------------------------------------------------------- #
# Local executor — mirrors the engine's execute_commands result shape.
# --------------------------------------------------------------------------- #
def run_local(cmds, timeout=120):
    """Run shell command strings locally; return ``[{"out","err"}]`` (one per
    command), the same shape the engine code expects from execute_commands."""
    results = []
    for cmd in cmds:
        try:
            p = subprocess.run(
                ["/bin/sh", "-c", cmd],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            results.append({"out": p.stdout, "err": p.stderr})
        except subprocess.TimeoutExpired:
            results.append({"out": "", "err": f"timeout: {cmd}"})
        except OSError as e:
            results.append({"out": "", "err": str(e)})
    return results


def _out(res):
    """First command's stdout string from a ``run()`` result, ``""`` when the
    result is empty. Guards every reader against a ``run()`` that returns fewer
    entries than commands issued (an empty list would otherwise IndexError on
    ``res[0]`` and abort the whole apply)."""
    return (res[0].get("out") if res else "") or ""


# --------------------------------------------------------------------------- #
# Pure helper (unit-tested; no host access).
# --------------------------------------------------------------------------- #
def current_profile_from_state(driver, mig_mode, live_mdev_suffix):
    """Resolve a card's CURRENT applied profile suffix from observed state.

    driver           : basename of realpath(/sys/.../driver) -- "vfio-pci",
                       "nvidia", or None.
    mig_mode         : nvidia-smi mig.mode.current -- "Enabled"/"Disabled"/
                       "[N/A]"/None.
    live_mdev_suffix : profile suffix of a live mdev under this card, or None.

    Returns the suffix ("passthrough" / "4Q" / a MIG suffix), the ``MIG_CURRENT``
    marker when the card is in MIG mode but no specific instance is readable, or
    None when the card is nvidia-bound and uncarved (treat as "no profile" ->
    any non-None target differs -> apply)."""
    if driver == "vfio-pci":
        return "passthrough"
    if live_mdev_suffix:
        return live_mdev_suffix
    if (
        driver == "nvidia"
        and isinstance(mig_mode, str)
        and "enabled" in mig_mode.lower()
    ):
        # In MIG mode but the live GPU-instance profile isn't read here; the
        # marker is enough to route the teardown (old_is_mig) at apply time.
        return MIG_CURRENT
    return None


# --------------------------------------------------------------------------- #
# Host-touching READ-ONLY helpers (validated on a GPU host).
# --------------------------------------------------------------------------- #
def _read_driver(pci_bdf, run):
    res = run([f"readlink /sys/bus/pci/devices/{pci_bdf}/driver"], timeout=10)
    out = _out(res).strip()
    return os.path.basename(out) if out else None


def _read_mig_mode(pci_bdf, run):
    res = run(
        [f"nvidia-smi -i {pci_bdf} --query-gpu=mig.mode.current --format=csv,noheader"],
        timeout=30,
    )
    return _out(res).strip() or None


def _live_mdev_suffix(pci_bdf, run, profiles_for):
    """Suffix of a profile that currently has a live mdev created on the card,
    or None. Used to detect the current vGPU/MIG carve.

    ``profiles_for(bdf) -> list[{name,type_id,...}]`` is injected so this leaf
    never imports the discovery profile reader (which stays in gpu_discovery):
    gpu_apply passes its own ``_live_profiles``; gpu_discovery passes its own
    ``_get_vgpu_profiles``."""
    res = run(
        [
            f"ls -d /sys/bus/pci/devices/{pci_bdf}/mdev_supported_types/*/devices/* "
            f"/sys/bus/pci/devices/{pci_bdf}/virtfn*/mdev_supported_types/*/devices/* "
            f"2>/dev/null | head -1"
        ],
        timeout=10,
    )
    path = _out(res).strip()
    if not path:
        return None
    # .../mdev_supported_types/<type_id>/devices/<uuid>
    try:
        type_id = path.split("/mdev_supported_types/")[1].split("/")[0]
    except IndexError:
        return None
    for prof in profiles_for(pci_bdf) or []:
        if prof.get("type_id") == type_id and "-" in (prof.get("name") or ""):
            return canonical_suffix(prof["name"].split("-", 1)[1])
    return None


def _enumerate_vf_sub_paths(pci_bdf, run):
    """Live SR-IOV VF sysfs paths under a PF, via its virtfn* symlinks, in the
    canonical /sys/bus/pci/devices/<vf-bdf> form discovery uses. Used after a
    MIG->vGPU teardown re-enables SR-IOV: the original discovery, taken while
    the card was in MIG mode, saw no VFs (sub_paths None), but the carve must
    target the freshly re-created VFs."""
    res = run(
        [
            # `[ -e "$v" ] || continue` guards the no-VF case: without nullglob
            # the unexpanded glob would loop once on the literal "virtfn*" and
            # yield a bogus path. So a card whose SR-IOV did not come back
            # returns [] and the caller falls back / errors cleanly.
            f"for v in /sys/bus/pci/devices/{pci_bdf}/virtfn*; do "
            f'[ -e "$v" ] || continue; basename "$(readlink -f "$v")"; '
            f"done 2>/dev/null"
        ],
        timeout=15,
    )
    out = _out(res).strip()
    return [
        f"/sys/bus/pci/devices/{b.strip()}"
        for b in out.splitlines()
        if b.strip() and "*" not in b
    ]
