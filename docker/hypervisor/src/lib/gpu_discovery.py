"""GPU discovery using nvidia-smi and sysfs.

Runs inside the isard-hypervisor container. Discovers NVIDIA GPUs and their
vGPU profiles without requiring libvirt or hardcoded PCI ID dictionaries.
"""

import gzip
import json
import logging
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_NVIDIA_VENDOR_ID = "10de"
_PCI_IDS_URL = "https://pci-ids.ucw.cz/v2.2/pci.ids.gz"
_BUNDLED_PCI_IDS = os.path.join(os.path.dirname(__file__), "nvidia_pci_ids.txt")

# Cached pci.ids lookup: device_id (int) -> human name (str).
# Populated once by _get_pci_nvidia_names().
_pci_nvidia_names = None


def _parse_bundled_pci_ids(path):
    """Parse the bundled nvidia_pci_ids.txt file.

    Each line has the format: ``<4-hex-device-id>  <name>``.
    Returns a dict mapping device_id (int) to name (str).
    """
    names = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"^([0-9a-fA-F]{4})\s+(.+)", line)
                if m:
                    names[int(m.group(1), 16)] = m.group(2).strip()
    except OSError:
        pass
    return names


def _fetch_upstream_pci_ids():
    """Download NVIDIA device names from the upstream pci.ids database.

    Returns a dict mapping device_id (int) to name (str), or None on failure.
    """
    try:
        req = urllib.request.Request(
            _PCI_IDS_URL, headers={"User-Agent": "isard-hypervisor"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = gzip.decompress(resp.read()).decode("utf-8", errors="replace")
    except Exception:
        return None

    names = {}
    in_nvidia = False
    for line in raw.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if re.match(r"^[0-9a-fA-F]{4}\s", line):
            in_nvidia = line.lower().startswith(_NVIDIA_VENDOR_ID)
            continue
        if in_nvidia and line.startswith("\t") and not line.startswith("\t\t"):
            m = re.match(r"^\t([0-9a-fA-F]{4})\s+(.+)", line)
            if m:
                names[int(m.group(1), 16)] = m.group(2).strip()
    return names


def _get_pci_nvidia_names():
    """Return NVIDIA PCI device-id to name mapping (cached).

    Loads the bundled nvidia_pci_ids.txt first, then tries to refresh from
    the upstream pci.ids database.  Falls back to bundled data if the
    download fails (e.g. airgapped environments).
    """
    global _pci_nvidia_names
    if _pci_nvidia_names is not None:
        return _pci_nvidia_names

    _pci_nvidia_names = _parse_bundled_pci_ids(_BUNDLED_PCI_IDS)
    bundled_count = len(_pci_nvidia_names)
    log.info("Loaded %d NVIDIA PCI IDs from bundled file", bundled_count)

    upstream = _fetch_upstream_pci_ids()
    if upstream is not None:
        _pci_nvidia_names.update(upstream)
        log.info("Refreshed NVIDIA PCI IDs from upstream (%d entries)", len(upstream))
    else:
        log.warning(
            "Could not fetch upstream pci.ids; using %d bundled entries",
            bundled_count,
        )

    return _pci_nvidia_names


def _lookup_gpu_name(device_id):
    """Look up an NVIDIA GPU name by PCI device ID.

    Tries the online pci.ids database first, returns a fallback string
    if not found.
    """
    names = _get_pci_nvidia_names()
    name = names.get(device_id)
    if name:
        return f"NVIDIA {name}"
    return None


def _run_nvidia_smi():
    """Run nvidia-smi and return parsed GPU info.

    Returns:
        list of dicts with keys: name, memory_total_mb, pci_bus_id,
        driver_version, mig_mode, gpu_uuid.
        Empty list if nvidia-smi is not available or fails.
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,pci.bus_id,driver_version,mig.mode.current,gpu_uuid",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
    except (OSError, subprocess.TimeoutExpired):
        return []

    gpus = []
    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        gpus.append(
            {
                "name": parts[0],
                "memory_total_mb": int(float(parts[1])),
                "pci_bus_id": parts[2],
                "driver_version": parts[3],
                "mig_mode": parts[4],
                "gpu_uuid": parts[5] if len(parts) > 5 else None,
            }
        )
    return gpus


def _normalize_pci_bus_id(pci_bus_id):
    """Normalize PCI bus ID to sysfs format.

    nvidia-smi returns e.g. '00000000:41:00.0'
    sysfs uses e.g. '0000:41:00.0'

    Returns the sysfs-compatible form.
    """
    # Strip leading zeros in domain part: 00000000:41:00.0 -> 0000:41:00.0
    match = re.match(
        r"^[0-9a-fA-F]+:([0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9])$", pci_bus_id
    )
    if match:
        return "0000:" + match.group(1)
    return pci_bus_id


def _parse_description_framebuffer(description):
    """Extract framebuffer size in MB from mdev_supported_types description file.

    The description file typically contains a line like:
        'num_heads=1, frl_config=60, framebuffer=4096M, ...'

    Returns:
        int: framebuffer size in MB, or 0 if not found
    """
    match = re.search(r"framebuffer=(\d+)M", description)
    if match:
        return int(match.group(1))
    return 0


def _parse_description_max_instances(description):
    """Extract max_instance from mdev_supported_types description file.

    The description file typically contains a line like:
        'num_heads=1, frl_config=60, framebuffer=4096M, max_resolution=...., max_instance=12'

    Returns:
        int: max instances, or 0 if not found
    """
    match = re.search(r"max_instance=(\d+)", description)
    if match:
        return int(match.group(1))
    return 0


def _get_vgpu_profiles(pci_bus_id):
    """Read vGPU profiles from sysfs for a given PCI device.

    Args:
        pci_bus_id: PCI bus ID as returned by nvidia-smi (e.g. '00000000:41:00.0')

    Returns:
        list of profile dicts, empty if no vGPU driver or no mdev support
    """
    sysfs_pci_id = _normalize_pci_bus_id(pci_bus_id).lower()
    mdev_path = f"/sys/bus/pci/devices/{sysfs_pci_id}/mdev_supported_types"

    if not os.path.isdir(mdev_path):
        return []

    profiles = []
    try:
        for type_dir in sorted(os.listdir(mdev_path)):
            type_path = os.path.join(mdev_path, type_dir)
            if not os.path.isdir(type_path):
                continue

            name_file = os.path.join(type_path, "name")
            avail_file = os.path.join(type_path, "available_instances")
            desc_file = os.path.join(type_path, "description")

            if not os.path.exists(name_file) or not os.path.exists(avail_file):
                continue

            with open(name_file) as f:
                name = f.read().strip().replace("NVIDIA ", "")

            # Only include Q-series and C-series profiles (vGPU)
            if not name or name[-1] not in ("C", "Q"):
                continue

            with open(avail_file) as f:
                available_instances = int(f.read().strip())

            framebuffer_mb = 0
            max_instances = 0
            if os.path.exists(desc_file):
                with open(desc_file) as f:
                    description = f.read().strip()
                framebuffer_mb = _parse_description_framebuffer(description)
                max_instances = _parse_description_max_instances(description)

            profiles.append(
                {
                    "name": name,
                    "type_id": type_dir,
                    "available_instances": available_instances,
                    "framebuffer_mb": framebuffer_mb,
                    "max_instances": max_instances,
                }
            )
    except OSError:
        return []

    return profiles


def _get_mig_profiles(gpu_index):
    """Query MIG GPU Instance profiles for a given GPU index.

    Runs ``nvidia-smi mig -lgip -i <gpu_index>`` and parses the table output.

    Returns:
        list of dicts with keys: name, profile_id, max_instances, memory_gib.
        Empty list if command fails or no profiles found.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "mig", "-lgip", "-i", str(gpu_index)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return []
    except (OSError, subprocess.TimeoutExpired):
        return []

    profiles = []
    for line in result.stdout.strip().splitlines():
        # nvidia-smi mig -lgip output is pipe-delimited:
        #   |  <GPU>  MIG <name>  <ID>  <free>/<total>  <size>  No  ...  |
        line = line.strip().strip("|").strip()
        m = re.match(r"(\d+)\s+MIG\s+(\S+)\s+(\d+)\s+(\d+)/(\d+)\s+([\d.]+)", line)
        if not m:
            continue
        name = m.group(2)  # e.g. "1g.24gb", "2g.48gb+gfx", "1g.24gb-me"
        if not re.match(r"\d+g\.", name):
            continue
        # Normalize: replace "-" with "_" so profile IDs have exactly 2 dashes
        # when combined as BRAND-MODEL-PROFILE (e.g. "1g.24gb_me")
        name = name.replace("-", "_")
        profile_id = int(m.group(3))
        max_instances = int(m.group(5))
        memory_gib = round(float(m.group(6)), 2)
        profiles.append(
            {
                "name": name,
                "profile_id": profile_id,
                "max_instances": max_instances,
                "memory_gib": memory_gib,
            }
        )
    return profiles


def _scan_sysfs_nvidia_gpus(exclude_pci_ids):
    """Scan sysfs for NVIDIA GPUs not already found by nvidia-smi.

    Looks for PCI devices with vendor 0x10de (NVIDIA), class 0x0300xx (VGA
    display controller), function .0 only.  Skips any PCI IDs listed in
    *exclude_pci_ids*.

    Returns:
        list of GPU dicts (same shape as discover_gpus output items) for GPUs
        found in sysfs but absent from nvidia-smi.
    """
    sysfs_base = "/sys/bus/pci/devices"
    gpus = []
    try:
        entries = sorted(os.listdir(sysfs_base))
    except OSError:
        return gpus

    for entry in entries:
        # Only consider function 0
        if not entry.endswith(".0"):
            continue

        dev_path = os.path.join(sysfs_base, entry)

        # Skip SR-IOV Virtual Functions — they are managed by the PF
        if os.path.islink(os.path.join(dev_path, "physfn")):
            continue

        # Check NVIDIA vendor
        try:
            with open(os.path.join(dev_path, "vendor")) as f:
                vendor = f.read().strip()
        except OSError:
            continue
        if vendor.lower() != "0x10de":
            continue

        # Check VGA display controller class (0x0300xx)
        try:
            with open(os.path.join(dev_path, "class")) as f:
                dev_class = f.read().strip()
        except OSError:
            continue
        if not dev_class.lower().startswith("0x03"):
            continue

        # Normalise to the same format as nvidia-smi / rest of codebase
        pci_id = entry.lower()
        if pci_id in exclude_pci_ids:
            continue

        # Read PCI device ID and look up name from pci.ids
        try:
            with open(os.path.join(dev_path, "device")) as f:
                device_id = int(f.read().strip(), 16)
        except (OSError, ValueError):
            device_id = 0

        name = _lookup_gpu_name(device_id) or f"NVIDIA Unknown GPU ({entry})"
        memory_mb = 0

        gpus.append(
            {
                "name": name,
                "memory_total_mb": memory_mb,
                "pci_bus_id": pci_id,
                "driver_version": "N/A",
                "vgpu_profiles": [],
                "mig_mode": "[N/A]",
                "model": normalize_gpu_model(name),
                "gpu_uuid": None,
            }
        )

    return gpus


def _nvidia_smi_gpu_reset(pci_bus_id):
    """Issue ``nvidia-smi -r -i <BDF>`` on a GPU. Best-effort.

    Clears driver-core state that wiping mdev sysfs entries does not reach
    (stale VF bindings, lingering vgpu-vfio allocations). Requires no
    active consumers on the GPU; caller is expected to wipe live mdevs
    via :func:`_reset_sysfs_mdevs` first. Logs and returns False on any
    failure — a failed driver reset must never abort hypervisor start.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "-r", "-i", pci_bus_id],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("GPU %s: nvidia-smi -r error: %s", pci_bus_id, e)
        return False
    if result.returncode != 0:
        log.warning(
            "GPU %s: nvidia-smi -r rc=%d: %s",
            pci_bus_id,
            result.returncode,
            (result.stderr or result.stdout).strip()[:200],
        )
        return False
    log.info("GPU %s: nvidia-smi -r completed", pci_bus_id)
    return True


def _cycle_sriov_vfs(sysfs_pci_id):
    """Tear down every VF and re-create all of them at ``sriov_totalvfs``.

    Uses NVIDIA's ``sriov-manage`` tool (bind-mounted from the host) which
    handles the pci-pf-stub dance required to destroy and recreate VFs.
    The nvidia driver rejects direct sriov_numvfs writes while the PF is
    nvidia-bound; sriov-manage works around this by temporarily binding
    to pci-pf-stub.
    """
    base = f"/sys/bus/pci/devices/{sysfs_pci_id}"
    try:
        with open(f"{base}/sriov_totalvfs") as f:
            totalvfs = int(f.read().strip())
    except (OSError, ValueError):
        return False
    if totalvfs <= 0:
        return False

    try:
        r = subprocess.run(
            ["sriov-manage", "-d", sysfs_pci_id],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r.returncode != 0:
            log.debug(
                "GPU %s: sriov-manage -d failed: %s",
                sysfs_pci_id,
                (r.stderr or r.stdout).strip()[:200],
            )
            return False
        r = subprocess.run(
            ["sriov-manage", "-e", sysfs_pci_id],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r.returncode != 0:
            log.debug(
                "GPU %s: sriov-manage -e failed: %s",
                sysfs_pci_id,
                (r.stderr or r.stdout).strip()[:200],
            )
            return False
    except (OSError, subprocess.TimeoutExpired) as e:
        log.debug(
            "GPU %s: sriov-manage unavailable (%s); using manual pci-pf-stub fallback",
            sysfs_pci_id,
            e,
        )
        return False

    log.info("GPU %s: cycled SR-IOV VFs via sriov-manage", sysfs_pci_id)
    return True


def _wait_sriov_numvfs(sysfs_pci_id, timeout=10):
    """Poll for ``sriov_numvfs`` to reappear after a GPU driver reset.

    ``nvidia-smi -r`` triggers a PCI bus reset; the nvidia driver re-probes
    asynchronously and ``sriov_numvfs`` only reappears once
    ``pci_enable_sriov()`` is called again.  Without this wait,
    :func:`_ensure_sriov_max_vfs` would silently skip because
    ``sriov_numvfs`` cannot be read.
    """
    path = f"/sys/bus/pci/devices/{sysfs_pci_id}/sriov_numvfs"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(path):
            return True
        time.sleep(0.5)
    log.warning(
        "GPU %s: sriov_numvfs did not reappear within %ds after driver reset",
        sysfs_pci_id,
        timeout,
    )
    return False


def _ensure_sriov_max_vfs(sysfs_pci_id):
    """Ensure SR-IOV exposes all VFs (sriov_numvfs == sriov_totalvfs).

    On vGPU cards like A16/A40, mdev_supported_types only appears on VFs that
    are currently bound. If sriov_numvfs is lower than totalvfs at discovery
    time, sub_paths will be incomplete and the engine caps the mdev pool below
    hardware capacity. Top it up here so discovery sees every VF.
    """
    base = f"/sys/bus/pci/devices/{sysfs_pci_id}"
    try:
        with open(f"{base}/sriov_totalvfs") as f:
            totalvfs = int(f.read().strip())
        with open(f"{base}/sriov_numvfs") as f:
            numvfs = int(f.read().strip())
    except (OSError, ValueError):
        return
    if totalvfs <= 0 or numvfs >= totalvfs:
        return
    try:
        with open(f"{base}/sriov_numvfs", "w") as f:
            f.write(str(totalvfs))
        log.info(
            "GPU %s: raised sriov_numvfs %d -> %d to expose all VFs",
            sysfs_pci_id,
            numvfs,
            totalvfs,
        )
    except OSError as e:
        log.warning(
            "GPU %s: could not raise sriov_numvfs (%d -> %d): %s",
            sysfs_pci_id,
            numvfs,
            totalvfs,
            e,
        )


def _reset_sysfs_mdevs(main_path):
    """Remove every live sysfs mdev currently bound under this GPU's PF.

    Scans both the PF (pre-Ampere cards like T4) and every SR-IOV VF
    (``virtfn*`` symlinks) for mdev devices under
    ``mdev_supported_types/<type>/devices/<uuid>`` and writes ``1`` to the
    corresponding ``/sys/bus/mdev/devices/<uuid>/remove``.

    Why: engine-side reconcile is the single source of truth for which mdev
    UUIDs exist. Pre-existing mdevs from prior container lifetimes or from
    NVIDIA vGPU host driver auto-instantiation collide with reconcile-created
    UUIDs (each VF exposes only one mdev at a time), causing libvirt
    ``createXML`` to hang for 30s when engine writes a new UUID into an
    already-occupied ``/create``. Wiping on startup is the bootstrap contract:
    every hypervisor (re)start comes up with an empty pool.
    """
    scan_roots = [main_path]
    i = 0
    while True:
        link = os.path.join(main_path, f"virtfn{i}")
        if not os.path.islink(link):
            break
        try:
            scan_roots.append(os.path.realpath(link))
        except OSError:
            break
        i += 1

    removed = 0
    refused = 0
    for root in scan_roots:
        mdev_dir = os.path.join(root, "mdev_supported_types")
        if not os.path.isdir(mdev_dir):
            continue
        try:
            types = os.listdir(mdev_dir)
        except OSError:
            continue
        for type_name in types:
            devices_dir = os.path.join(mdev_dir, type_name, "devices")
            if not os.path.isdir(devices_dir):
                continue
            try:
                uuids = os.listdir(devices_dir)
            except OSError:
                continue
            for mdev_uuid in uuids:
                remove_path = f"/sys/bus/mdev/devices/{mdev_uuid}/remove"
                try:
                    with open(remove_path, "w") as f:
                        f.write("1")
                    removed += 1
                except OSError as e:
                    refused += 1
                    log.warning(
                        "GPU %s: could not remove mdev %s on %s: %s "
                        "(VF may be attached to a running domain; "
                        "the domain must be stopped before hypervisor restart)",
                        os.path.basename(main_path),
                        mdev_uuid,
                        os.path.basename(root),
                        e,
                    )
    if removed or refused:
        log.info(
            "GPU %s: mdev reset — removed=%d refused=%d",
            os.path.basename(main_path),
            removed,
            refused,
        )


def reset_all_mdevs():
    """Wipe every sysfs mdev on every nvidia-bound PF.

    Walks ``/sys/bus/pci/devices/*`` for entries whose ``driver`` symlink
    resolves to ``nvidia`` and which expose ``mdev_supported_types`` or
    ``sriov_totalvfs``, then calls the per-GPU :func:`_reset_sysfs_mdevs`
    on each. Intended for the shutdown path so the host leaves no live
    mdevs behind for the next container lifetime.

    Returns the number of PFs scanned. Safe to call even when no qemu
    is running; unsafe while a VF is attached to a domain (kernel will
    refuse /remove, warning is logged per refusal).
    """
    pf_count = 0
    try:
        entries = sorted(os.listdir("/sys/bus/pci/devices/"))
    except OSError:
        return 0
    for bdf in entries:
        dev = f"/sys/bus/pci/devices/{bdf}"
        driver_link = os.path.join(dev, "driver")
        try:
            driver_name = os.path.basename(os.path.realpath(driver_link))
        except OSError:
            continue
        if driver_name != "nvidia":
            continue
        has_mdev = os.path.isdir(os.path.join(dev, "mdev_supported_types"))
        has_sriov = os.path.isfile(os.path.join(dev, "sriov_totalvfs"))
        if not (has_mdev or has_sriov):
            continue
        _reset_sysfs_mdevs(dev)
        pf_count += 1
    return pf_count


def _enumerate_sriov_vf_paths(main_path):
    """Return sorted list of SR-IOV VF sysfs paths for a PF device.

    Uses the canonical ``virtfnN`` symlinks published by the kernel when
    SR-IOV is enabled on the PF. Returns an empty list if the PF has no
    SR-IOV VFs (non-SR-IOV card, or VFs not yet created).
    """
    vf_paths = []
    i = 0
    while True:
        link = os.path.join(main_path, f"virtfn{i}")
        if not os.path.islink(link):
            break
        try:
            vf_bdf = os.path.basename(os.path.realpath(link))
            vf_paths.append(f"/sys/bus/pci/devices/{vf_bdf}")
        except OSError:
            break
        i += 1
    return sorted(vf_paths)


def _aggregate_subdevice_profiles(pci_bus_id):
    """For cards like A40 / Blackwell DC that expose mdev on sub-devices, aggregate.

    Some NVIDIA cards don't expose ``mdev_supported_types`` on the main PCI
    device (PF) but on its SR-IOV VFs or on adjacent sub-functions:

    - **SR-IOV path (A40, L40, L40S, Blackwell DC)**: VFs are linked from the
      PF as ``virtfn0`` .. ``virtfnN-1``. We enumerate via those symlinks so
      VFs landing on function numbers other than 00.X (e.g., 01.X on
      Blackwell with 48 VFs) are not missed.
    - **Legacy sub-function path (older A40 configs without SR-IOV)**: VFs
      share the same bus+slot as the PF (``0000:41:00.4`` alongside
      ``0000:41:00.0``) but are not SR-IOV. We fall back to scanning
      ``<base>.N`` when no virtfn symlinks exist.

    This function checks both and returns aggregated profiles with summed
    ``available_instances``.

    Args:
        pci_bus_id: PCI bus ID from nvidia-smi

    Returns:
        tuple: (profiles_list, sub_paths_list or None, path_parent or None)
    """
    sysfs_pci_id = _normalize_pci_bus_id(pci_bus_id).lower()
    main_path = f"/sys/bus/pci/devices/{sysfs_pci_id}"

    # First try main device (pre-Ampere cards like T4)
    main_profiles = _get_vgpu_profiles(pci_bus_id)
    if main_profiles:
        # Clear any pre-existing mdevs on the PF so engine-side reconcile
        # rebuilds the pool from an empty slate.
        _reset_sysfs_mdevs(main_path)
        return main_profiles, None, None

    # SR-IOV reset (Ampere/Ada/Blackwell vGPU cards):
    # 1. wipe live mdevs so VFs have no active consumers,
    # 2. cycle VFs (write 0 → totalvfs to sriov_numvfs) — destroys and
    #    recreates every VF, clearing all mdev/vgpu-vfio state.
    # nvidia-smi -r is reserved for the fallback path: it bus-resets the
    # GPU which causes sriov_numvfs to vanish until the driver re-probes,
    # so calling it before the VF cycle would cause ENOENT.
    _reset_sysfs_mdevs(main_path)
    has_sriov = os.path.exists(f"{main_path}/sriov_totalvfs")
    if has_sriov and not _cycle_sriov_vfs(sysfs_pci_id):
        # VF cycle failed on an SR-IOV card (EBUSY from stuck mdevs, etc.).
        # nvidia-smi -r bus-resets the GPU to unstick the driver, then
        # wait for sriov_numvfs to reappear before topping up VFs.
        _nvidia_smi_gpu_reset(pci_bus_id)
        _wait_sriov_numvfs(sysfs_pci_id)
        _ensure_sriov_max_vfs(sysfs_pci_id)

    # Safety net: after the cycle fresh VFs have no mdevs, so this is a
    # no-op on the happy path. Still needed on the fallback branch where
    # VFs retained their previous bindings.
    _reset_sysfs_mdevs(main_path)

    # Prefer SR-IOV enumeration via virtfn* symlinks (authoritative for
    # Ampere/Ada/Blackwell). Falls through to legacy sub-function scan only
    # when no virtfn symlinks are present.
    candidate_paths = _enumerate_sriov_vf_paths(main_path)
    if not candidate_paths:
        # Legacy: scan sub-functions with the same bus:device prefix
        base = sysfs_pci_id.rsplit(".", 1)[0]  # e.g., '0000:41:00'
        try:
            for entry in sorted(os.listdir("/sys/bus/pci/devices/")):
                if entry.startswith(base + ".") and entry != sysfs_pci_id:
                    candidate_paths.append(f"/sys/bus/pci/devices/{entry}")
        except OSError:
            pass

    sub_paths = set()
    profile_map = {}  # name -> profile dict with aggregated available_instances
    for sub_path in candidate_paths:
        entry = os.path.basename(sub_path)
        sub_profiles = _get_vgpu_profiles(entry)
        if not sub_profiles:
            continue
        sub_paths.add(sub_path)
        for p in sub_profiles:
            if p["name"] in profile_map:
                profile_map[p["name"]]["available_instances"] += p[
                    "available_instances"
                ]
            else:
                profile_map[p["name"]] = dict(p)

    if not profile_map:
        return [], None, None

    profiles = sorted(profile_map.values(), key=lambda p: p["name"])
    path_parent = main_path if os.path.exists(main_path) else None
    return profiles, sub_paths if sub_paths else None, path_parent


def normalize_gpu_model(gpu_name, vgpu_profiles=None):
    """Derive a dash- and slash-free canonical model name for a GPU.

    Uses vGPU profile name prefix when available (e.g., "A40" from "A40-4Q"),
    otherwise normalizes the nvidia-smi name by stripping "NVIDIA " prefix
    and removing spaces, dashes and slashes to produce a clean string.

    The model MUST be dash-free because the system uses
    "BRAND-MODEL-PROFILE" format with dashes as separators. It MUST also be
    slash-free because that id is used verbatim as a URL path segment
    (e.g. /api/v3/admin/reservables/enable/gpus/<card>/<id>): a '/' in the
    model -- as in the A16 die name "GA107GL [A2 / A16]" -- would inject an
    extra path segment and make the route unmatchable (HTTP 405).
    """
    if vgpu_profiles:
        # Extract model from vGPU profile name by removing the profile suffix.
        # Profile suffix patterns:
        #   - Simple: "-4Q", "-12A", "-96Q" (digits + letter)
        #   - With slot: "-1-3Q", "-2-12Q", "-4-48Q" (slot-digits + letter)
        # The model is everything before the suffix.
        profile_name = vgpu_profiles[0]["name"]
        match = re.match(r"^(.+?)(-\d+-\d+[ABCQ]|-\d+[ABCQ])$", profile_name)
        if match:
            model_part = match.group(1)
        else:
            # Fallback: use rsplit for simple cases
            model_part = profile_name.rsplit("-", 1)[0]
        # Strip vendor prefix and remove spaces/dashes/slashes so the two code
        # paths (profile-derived and nvidia-smi-name-derived) produce the same
        # model.
        result = (
            model_part.replace("NVIDIA ", "")
            .replace("GRID ", "")
            .replace(" ", "")
            .replace("-", "")
            .replace("/", "")
        )
        return result
    result = (
        gpu_name.replace("NVIDIA ", "")
        .replace(" ", "")
        .replace("-", "")
        .replace("/", "")
    )
    return result


def _classify_sriov_state(totalvfs, numvfs, has_profiles, vf_driver):
    """Classify a GPU's SR-IOV state into informational notes vs warnings.

    Pure decision logic split out of :func:`discover_gpus` so it can be
    unit-tested without sysfs. Inputs are already-resolved primitives:

    - ``totalvfs``     -- ``sriov_totalvfs`` (capability; 0 = not SR-IOV).
    - ``numvfs``       -- ``sriov_numvfs`` (VFs created right now).
    - ``has_profiles`` -- truthy if vGPU mdev profiles exist on the PF.
    - ``vf_driver``    -- driver bound to ``virtfn0`` ("" if none); only
                          consulted when VFs exist but no profiles.

    Returns ``(notes, warnings)``: ``notes`` are non-fault states rendered
    neutrally; ``warnings`` are genuine misconfigurations rendered as the
    orange fault icon. A correctly configured passthrough/MIG card (no VFs
    and no profiles) yields a single note and *no* warning, so the admin
    UI stays clean when everything is correct.
    """
    notes = []
    warnings = []
    if totalvfs > 0 and not has_profiles:
        if numvfs == 0:
            notes.append(
                f"SR-IOV not in use ({totalvfs} VFs supported, none "
                f"created); serving passthrough/MIG. This is expected "
                f"unless a time-sliced vGPU (Q) profile is required."
            )
        elif vf_driver != "nvidia":
            warnings.append(
                f"SR-IOV VFs created ({numvfs}) but nvidia driver "
                f"cannot bind VFs (driver={vf_driver or 'none'}). "
                f"vGPU requires IOMMU enabled in BIOS and kernel "
                f"(iommu=pt). Only passthrough and MIG modes available."
            )
        else:
            warnings.append(
                f"SR-IOV VFs active ({numvfs}) and nvidia-bound but "
                f"no vGPU profiles found on VFs."
            )
    return notes, warnings


def discover_gpus():
    """Discover NVIDIA GPUs and their vGPU profiles.

    Uses nvidia-smi for GPU hardware info and sysfs for vGPU profiles.

    Returns:
        list of GPU dicts. Empty list if no GPUs or nvidia-smi unavailable.
    """
    raw_gpus = _run_nvidia_smi()

    # Single timestamp for this discovery run. Stamped on every GPU so engine
    # reconcile can tell "this hypervisor came up fresh and wiped its mdevs at
    # T", triggering an authoritative rebuild of vgpus.mdevs and stopping any
    # domains still holding now-removed UUIDs.
    mdevs_reset_at = datetime.now(timezone.utc).isoformat()
    # SR-IOV cards get a full driver+VF reset inside
    # _aggregate_subdevice_profiles before enumeration. Stamp the same run
    # timestamp so admins / scripts can confirm the reset fired.
    gpu_reset_at = mdevs_reset_at

    gpus = []
    for gpu_index, gpu in enumerate(raw_gpus):
        profiles, sub_paths, path_parent = _aggregate_subdevice_profiles(
            gpu["pci_bus_id"]
        )

        mig_mode = gpu.get("mig_mode", "[N/A]")

        gpu_info = {
            "name": gpu["name"],
            "memory_total_mb": gpu["memory_total_mb"],
            "pci_bus_id": gpu["pci_bus_id"],
            "driver_version": gpu["driver_version"],
            "vgpu_profiles": profiles,
            "mig_mode": mig_mode,
            "model": normalize_gpu_model(gpu["name"], profiles),
            "gpu_uuid": gpu.get("gpu_uuid"),
            "mdevs_reset_at": mdevs_reset_at,
            "gpu_reset_at": gpu_reset_at,
        }

        if mig_mode != "[N/A]":
            mig_profiles = _get_mig_profiles(gpu_index)
            if mig_profiles:
                gpu_info["mig_profiles"] = mig_profiles

        # Check for SR-IOV capability (vGPU cards like A40, Blackwell)
        sysfs_pci_id = _normalize_pci_bus_id(gpu["pci_bus_id"]).lower()
        sriov_path = f"/sys/bus/pci/devices/{sysfs_pci_id}/sriov_totalvfs"
        try:
            with open(sriov_path) as f:
                totalvfs = int(f.read().strip())
            if totalvfs > 0:
                gpu_info["sriov_totalvfs"] = totalvfs
                # Current VF count, recorded for *every* SR-IOV-capable
                # card (not only profile-less ones): the engine gates the
                # passthrough VF-teardown dance on VFs actually existing,
                # so an A40 that *does* have VFs must still report its
                # real count or the teardown would be wrongly skipped.
                numvfs_path = f"/sys/bus/pci/devices/{sysfs_pci_id}/sriov_numvfs"
                try:
                    with open(numvfs_path) as nf:
                        gpu_info["sriov_numvfs"] = int(nf.read().strip())
                except (OSError, ValueError):
                    gpu_info["sriov_numvfs"] = 0
        except (OSError, ValueError):
            pass

        if sub_paths is not None:
            gpu_info["sub_paths"] = sorted(sub_paths)
        if path_parent is not None:
            gpu_info["path_parent"] = path_parent

        # Classify SR-IOV state. `notes` are non-fault informational items
        # (rendered neutrally, not the orange fault icon); `warnings` are
        # genuine misconfigurations. Pure decision in _classify_sriov_state;
        # only the VF-driver sysfs walk (needed when VFs exist but no
        # profiles) is resolved here.
        totalvfs = gpu_info.get("sriov_totalvfs", 0)
        numvfs = gpu_info.get("sriov_numvfs", 0)
        vf_driver = ""
        if totalvfs > 0 and not profiles and numvfs > 0:
            first_vf = f"/sys/bus/pci/devices/{sysfs_pci_id}/virtfn0"
            if os.path.exists(first_vf):
                vf_bdf = os.path.basename(os.path.realpath(first_vf))
                drv = f"/sys/bus/pci/devices/{vf_bdf}/driver"
                if os.path.exists(drv):
                    vf_driver = os.path.basename(os.path.realpath(drv))
        notes, warnings = _classify_sriov_state(
            totalvfs, numvfs, bool(profiles), vf_driver
        )
        if warnings:
            gpu_info["warnings"] = warnings
            for w in warnings:
                print(f"  GPU {sysfs_pci_id}: {w}")
        if notes:
            gpu_info["notes"] = notes
            for n in notes:
                print(f"  GPU {sysfs_pci_id} [info]: {n}")

        gpus.append(gpu_info)

    # Detect NVIDIA GPUs not bound to the nvidia driver (invisible to
    # nvidia-smi).  These are passthrough-only since we cannot query vGPU
    # profiles without the driver.
    known_pci_ids = {_normalize_pci_bus_id(g["pci_bus_id"]).lower() for g in raw_gpus}
    gpus.extend(_scan_sysfs_nvidia_gpus(known_pci_ids))

    return gpus


def _read_sysfs_attr(dev_path, attr, strip_prefix="0x"):
    """Read a sysfs attribute file, stripping optional prefix."""
    try:
        with open(os.path.join(dev_path, attr)) as f:
            val = f.read().strip()
        if strip_prefix and val.lower().startswith(strip_prefix):
            val = val[len(strip_prefix) :]
        return val.lower()
    except OSError:
        return None


def discover_pci_devices(gpu_list=None):
    """Scan sysfs for all PCI devices and build a hardware inventory map.

    Returns a dict keyed by normalized PCI address (e.g., "0000:41:00.0")
    with device attributes. Only includes primary function (.0) devices and
    skips PCI bridges/host controllers (class 06xxxx).

    If *gpu_list* is provided (output of discover_gpus()), NVIDIA GPU entries
    are enriched with gpu_uuid from the GPU discovery data.
    """
    sysfs_base = "/sys/bus/pci/devices"
    devices = {}

    try:
        entries = sorted(os.listdir(sysfs_base))
    except OSError:
        return devices

    # Build gpu_uuid lookup from gpu_list: normalized_pci_id -> gpu_uuid
    gpu_uuids = {}
    if gpu_list:
        for gpu in gpu_list:
            norm = _normalize_pci_bus_id(gpu["pci_bus_id"]).lower()
            if gpu.get("gpu_uuid"):
                gpu_uuids[norm] = gpu["gpu_uuid"]

    for entry in entries:
        # Only primary function devices
        if not entry.endswith(".0"):
            continue

        dev_path = os.path.join(sysfs_base, entry)
        pci_addr = entry.lower()

        vendor = _read_sysfs_attr(dev_path, "vendor")
        device_id = _read_sysfs_attr(dev_path, "device")
        class_code = _read_sysfs_attr(dev_path, "class")

        if not vendor or not class_code:
            continue

        # Skip PCI bridges and host controllers (class 06xxxx)
        if class_code.startswith("06"):
            continue

        # Skip SR-IOV Virtual Functions — they belong to their PF
        if os.path.islink(os.path.join(dev_path, "physfn")):
            continue

        info = {
            "vendor": vendor,
            "device_id": device_id,
            "class_code": class_code,
        }

        subsys_vendor = _read_sysfs_attr(dev_path, "subsystem_vendor")
        subsys_device = _read_sysfs_attr(dev_path, "subsystem_device")
        if subsys_vendor:
            info["subsystem_vendor"] = subsys_vendor
        if subsys_device:
            info["subsystem_device"] = subsys_device

        # Driver currently bound
        driver_link = os.path.join(dev_path, "driver")
        if os.path.islink(driver_link):
            info["driver"] = os.path.basename(os.readlink(driver_link))
        else:
            info["driver"] = None

        # IOMMU group
        iommu_link = os.path.join(dev_path, "iommu_group")
        if os.path.islink(iommu_link):
            info["iommu_group"] = os.path.basename(os.readlink(iommu_link))

        # NUMA node
        numa = _read_sysfs_attr(dev_path, "numa_node", strip_prefix="")
        if numa is not None:
            try:
                info["numa_node"] = int(numa)
            except ValueError:
                pass

        # Attach gpu_uuid for NVIDIA GPUs
        if vendor == "10de" and pci_addr in gpu_uuids:
            info["gpu_uuid"] = gpu_uuids[pci_addr]

        devices[pci_addr] = info

    return devices


def discover_hugepages():
    """Detect hugepage availability from /sys/kernel/mm/hugepages/.

    Reads the kernel's hugepage configuration (total and free counts per size)
    and checks whether hugetlbfs is mounted at /dev/hugepages (required for
    QEMU inside a container to use hugepages).

    Returns:
        dict with keys:
            "1G":  {"total": int, "free": int}
            "2M":  {"total": int, "free": int}
            "mounted": bool  (True if /dev/hugepages is a mount point)
    """
    # Map sysfs directory suffixes to human-readable size labels
    _SIZE_MAP = {
        1048576: "1G",  # hugepages-1048576kB = 1G pages
        2048: "2M",  # hugepages-2048kB = 2M pages
    }

    result = {"1G": {"total": 0, "free": 0}, "2M": {"total": 0, "free": 0}}

    hugepages_dir = "/sys/kernel/mm/hugepages"
    try:
        entries = os.listdir(hugepages_dir)
    except OSError:
        entries = []

    for entry in entries:
        # entry format: "hugepages-1048576kB" or "hugepages-2048kB"
        match = re.match(r"hugepages-(\d+)kB", entry)
        if not match:
            continue

        size_kb = int(match.group(1))
        label = _SIZE_MAP.get(size_kb)
        if not label:
            continue

        path = os.path.join(hugepages_dir, entry)
        total = 0
        free = 0
        try:
            with open(os.path.join(path, "nr_hugepages")) as f:
                total = int(f.read().strip())
        except (OSError, ValueError):
            pass
        try:
            with open(os.path.join(path, "free_hugepages")) as f:
                free = int(f.read().strip())
        except (OSError, ValueError):
            pass

        result[label] = {"total": total, "free": free}

    # Check if hugetlbfs is mounted (QEMU needs this inside the container)
    result["mounted"] = os.path.ismount("/dev/hugepages")

    return result


def _expand_cpulist(cpulist):
    """Expand a "0-3,8,10-11" string into a sorted set of ints."""
    result = set()
    if not cpulist:
        return result
    for part in cpulist.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            try:
                result.update(range(int(lo), int(hi) + 1))
            except ValueError:
                continue
        else:
            try:
                result.add(int(part))
            except ValueError:
                continue
    return result


def _get_libvirt_capabilities_xml():
    """Return libvirt host capabilities XML, or None if libvirt is unavailable.

    Prefers the Python binding (faster, no subprocess). Falls back to `virsh
    capabilities` — the hypervisor container ships `virsh` but not the Python
    `libvirt` module.
    """
    try:
        import libvirt  # noqa: PLC0415

        conn = libvirt.open("qemu:///system")
        try:
            return conn.getCapabilities()
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["virsh", "capabilities"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout
    except Exception as e:
        log.warning("NUMA: virsh capabilities failed: %s", e)
        return None


def _probe_libvirt_numa_cells():
    """Parse <cells> from libvirt host capabilities.

    Returns:
        list of {"id": int, "memory_kb": int, "cpus": set(int)} or None if
        libvirt capabilities are unreachable.
    """
    xml = _get_libvirt_capabilities_xml()
    if not xml:
        return None

    # Stdlib xml.etree — the hypervisor image does not ship lxml.
    import xml.etree.ElementTree as ET

    root = ET.fromstring(xml)
    cells = []
    for cell in root.findall("./host/topology/cells/cell"):
        try:
            cell_id = int(cell.get("id"))
        except (TypeError, ValueError):
            continue
        mem_elem = cell.find("memory")
        memory_kb = int(mem_elem.text) if mem_elem is not None and mem_elem.text else 0
        cpus = set()
        for cpu in cell.findall("./cpus/cpu"):
            try:
                cpus.add(int(cpu.get("id")))
            except (TypeError, ValueError):
                continue
        cells.append({"id": cell_id, "memory_kb": memory_kb, "cpus": cpus})
    return cells


def _validate_libvirt_numa(sysfs_nodes, libvirt_cells):
    """Compare libvirt's NUMA view against sysfs.

    Returns (ok: bool, reason: str). The reason is a short machine-readable
    token, useful in logs and DB queries.
    """
    if not libvirt_cells:
        return False, "libvirt_empty_cells"
    if len(libvirt_cells) != len(sysfs_nodes):
        return False, "cell_count_mismatch"

    ids = [c["id"] for c in libvirt_cells]
    if len(set(ids)) != len(ids):
        return False, "duplicate_cell_ids"

    sysfs_ids = {int(n) for n in sysfs_nodes.keys()}
    if set(ids) != sysfs_ids:
        return False, "cell_id_mismatch"

    # Each cell's cpu set must match the corresponding sysfs cpulist.
    for cell in libvirt_cells:
        sys_cpulist = sysfs_nodes.get(str(cell["id"]), {}).get("cpulist", "")
        sys_cpus = _expand_cpulist(sys_cpulist)
        if cell["cpus"] != sys_cpus:
            return False, "cpu_mismatch"

    # Per-cell memory must look per-node, not a flat "every cell owns all RAM"
    # (a libvirt-in-container bug we've seen on some hosts).
    mems = [c["memory_kb"] for c in libvirt_cells]
    if len(mems) >= 2 and len(set(mems)) == 1:
        return False, "flat_cell_memory"

    return True, "ok"


def discover_numa_topology(probe_libvirt=False):
    """Discover per-NUMA-node CPU list and hugepages from sysfs.

    Reads /sys/devices/system/node/node* to build a map of which CPUs and
    hugepages belong to each NUMA node. The cpulist values are static hardware
    topology; the hugepages counts are a snapshot from discovery time.

    When `probe_libvirt=True` (call post-libvirt-start) the sysfs view is
    cross-checked against libvirt's own host capabilities (<cells>). Only when
    both views agree does the result advertise `libvirt_numa_ok: True` — the
    engine gates NUMA pinning on that flag, because libvirt will reject any
    <numatune> block referencing a cell it doesn't believe in.

    Returns:
        dict: {
            "libvirt_numa_ok": bool,
            "reason": str,       # "ok" | "libvirt_unreachable" | "cpu_mismatch" | ...
            "nodes": {           # always populated from sysfs, for diagnostics
                "0": {
                    "cpulist": "0-15,32-47",
                    "hugepages": {"1G": {"total": 168, "free": 105}, "2M": {...}}
                },
                "1": {...}
            }
        }
        Returns empty dict if /sys/devices/system/node is not available.
    """
    _SIZE_MAP = {
        1048576: "1G",
        2048: "2M",
    }

    node_dir = "/sys/devices/system/node"
    try:
        entries = sorted(d for d in os.listdir(node_dir) if re.match(r"node\d+$", d))
    except OSError:
        return {}

    nodes = {}
    for entry in entries:
        node_id = entry.replace("node", "")
        node_path = os.path.join(node_dir, entry)

        # Read CPU list for this NUMA node
        cpulist = ""
        try:
            with open(os.path.join(node_path, "cpulist")) as f:
                cpulist = f.read().strip()
        except (OSError, ValueError):
            pass

        # Read per-size hugepages for this NUMA node
        hugepages = {"1G": {"total": 0, "free": 0}, "2M": {"total": 0, "free": 0}}
        for size_kb, label in _SIZE_MAP.items():
            hp_dir = os.path.join(node_path, "hugepages", f"hugepages-{size_kb}kB")
            try:
                with open(os.path.join(hp_dir, "nr_hugepages")) as f:
                    hugepages[label]["total"] = int(f.read().strip())
            except (OSError, ValueError):
                pass
            try:
                with open(os.path.join(hp_dir, "free_hugepages")) as f:
                    hugepages[label]["free"] = int(f.read().strip())
            except (OSError, ValueError):
                pass

        nodes[node_id] = {"cpulist": cpulist, "hugepages": hugepages}

    if not nodes:
        return {}

    # Cross-check with libvirt if a connection was provided. Single-cell hosts
    # don't need NUMA pinning at all, so treat them as "ok" regardless.
    if len(nodes) < 2:
        return {"libvirt_numa_ok": True, "reason": "single_cell", "nodes": nodes}

    if not probe_libvirt:
        return {
            "libvirt_numa_ok": False,
            "reason": "libvirt_unreachable",
            "nodes": nodes,
        }

    try:
        libvirt_cells = _probe_libvirt_numa_cells()
    except Exception as e:
        log.warning("NUMA: libvirt capabilities probe failed: %s", e)
        return {
            "libvirt_numa_ok": False,
            "reason": "libvirt_probe_error",
            "nodes": nodes,
        }
    if libvirt_cells is None:
        return {
            "libvirt_numa_ok": False,
            "reason": "libvirt_unreachable",
            "nodes": nodes,
        }

    ok, reason = _validate_libvirt_numa(nodes, libvirt_cells)
    if not ok:
        log.warning(
            "NUMA: libvirt view inconsistent with sysfs (%s). "
            "sysfs_nodes=%s libvirt_cells=%s",
            reason,
            {k: v.get("cpulist") for k, v in nodes.items()},
            [
                {"id": c["id"], "memory_kb": c["memory_kb"], "n_cpus": len(c["cpus"])}
                for c in libvirt_cells
            ],
        )
    return {"libvirt_numa_ok": ok, "reason": reason, "nodes": nodes}


def _vfio_group_in_use(dev_path):
    """True if any process holds /dev/vfio/<group> for this PCI device.

    Walks /proc/*/fd to detect open handles. Conservative — on read errors,
    returns True so we never rebind a device a live qemu is using.
    """
    iommu_link = os.path.join(dev_path, "iommu_group")
    try:
        group = os.path.basename(os.path.realpath(iommu_link))
    except OSError:
        return True
    vfio_dev = f"/dev/vfio/{group}"
    if not os.path.exists(vfio_dev):
        return False
    try:
        target = os.path.realpath(vfio_dev)
    except OSError:
        return True
    try:
        pids = os.listdir("/proc")
    except OSError:
        return True
    for pid in pids:
        if not pid.isdigit():
            continue
        fd_dir = f"/proc/{pid}/fd"
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue
        for fd in fds:
            try:
                if os.path.realpath(os.path.join(fd_dir, fd)) == target:
                    return True
            except OSError:
                pass
    return False


def _rebind_vfio_to_nvidia_if_idle(dev_path):
    """If a GPU PF is leaked on vfio-pci with no live consumer, rebind to nvidia.

    Libvirt's `<hostdev managed="yes">` attaches vfio-pci on domain start and
    detaches on stop. If a domain start fails before qemu spawns (e.g. invalid
    XML), or the host is killed mid-flight, the vfio-pci binding can leak —
    the PF stays bound to vfio-pci with `driver_override=vfio-pci`,
    `sriov_numvfs=0`, and no `mdev_supported_types/`. NVIDIA's `sriov-manage`
    then silently fails because its unbind/rebind dance assumes the source
    driver is `nvidia`.

    Returns True if the device ends bound to nvidia (or was already), False if
    rebind was unsafe (live VFIO consumer) or failed.
    """
    bdf = os.path.basename(dev_path.rstrip("/"))
    driver_link = os.path.join(dev_path, "driver")
    try:
        cur_driver = (
            os.path.basename(os.path.realpath(driver_link))
            if os.path.islink(driver_link)
            else None
        )
    except OSError:
        cur_driver = None
    if cur_driver == "nvidia":
        return True
    if cur_driver != "vfio-pci":
        return False

    if _vfio_group_in_use(dev_path):
        log.info(
            "GPU %s: bound to vfio-pci with live VFIO consumer; not rebinding",
            bdf,
        )
        return False

    log.warning(
        "GPU %s: bound to vfio-pci with no live consumer; rebinding to nvidia",
        bdf,
    )
    try:
        with open(os.path.join(dev_path, "driver_override"), "w") as f:
            f.write("\n")
        with open("/sys/bus/pci/drivers/vfio-pci/unbind", "w") as f:
            f.write(bdf)
        with open("/sys/bus/pci/drivers/nvidia/bind", "w") as f:
            f.write(bdf)
    except OSError as e:
        log.warning("GPU %s: rebind to nvidia failed: %s", bdf, e)
        return False

    try:
        new_driver = os.path.basename(os.path.realpath(driver_link))
    except OSError:
        new_driver = None
    if new_driver != "nvidia":
        log.warning(
            "GPU %s: post-rebind driver is %r (expected 'nvidia')",
            bdf,
            new_driver,
        )
        return False
    log.info("GPU %s: rebound to nvidia", bdf)
    return True


def ensure_sriov_vfs():
    """Enable SR-IOV virtual functions on GPUs that need them for vGPU.

    Blackwell and newer NVIDIA GPUs expose vGPU mdev types on SR-IOV VFs,
    not on the physical function (PF).  Without VFs, discover_gpus() finds
    no vGPU profiles and falls back to MIG.

    For each NVIDIA GPU with sriov_totalvfs > 0 and sriov_numvfs == 0 and
    no mdev_supported_types on the PF, this enables VFs using the same
    pci-pf-stub dance that NVIDIA's sriov-manage -e performs:

        unbind nvidia → bind pci-pf-stub → write sriov_numvfs → unbind
        pci-pf-stub → rebind nvidia

    GPUs leaked on vfio-pci (e.g. after a failed managed-mode passthrough
    start) are rebound to nvidia first when no live VFIO consumer holds the
    IOMMU group, so the same flow can run.

    Must be called before discover_gpus().
    """
    pci_dir = "/sys/bus/pci/devices"
    try:
        entries = os.listdir(pci_dir)
    except OSError:
        return

    for dev in sorted(entries):
        dev_path = os.path.join(pci_dir, dev)
        # Only PFs (function 0)
        if not dev.endswith(".0"):
            continue
        # Only NVIDIA
        try:
            with open(os.path.join(dev_path, "vendor")) as f:
                if f.read().strip() != "0x10de":
                    continue
        except OSError:
            continue
        # Must support SR-IOV with multiple VFs (single VF is not vGPU)
        try:
            with open(os.path.join(dev_path, "sriov_totalvfs")) as f:
                totalvfs = int(f.read().strip())
            if totalvfs <= 1:
                continue
        except (OSError, ValueError):
            continue
        # Already has VFs enabled
        try:
            with open(os.path.join(dev_path, "sriov_numvfs")) as f:
                if int(f.read().strip()) > 0:
                    continue
        except (OSError, ValueError):
            continue
        # Heal a leaked vfio-pci binding before sriov-manage would silently
        # fail on it. If unsafe (live consumer) or failed, skip this device.
        if not _rebind_vfio_to_nvidia_if_idle(dev_path):
            driver_link = os.path.join(dev_path, "driver")
            try:
                cur = os.path.basename(os.path.realpath(driver_link))
            except OSError:
                cur = None
            if cur != "nvidia":
                continue
        # Already has mdev types on PF (legacy vGPU, not Blackwell)
        if os.path.isdir(os.path.join(dev_path, "mdev_supported_types")):
            continue

        log.info("Enabling SR-IOV VFs on %s (totalvfs=%d)", dev, totalvfs)
        _enable_sriov_for_gpu(dev)


def _enable_sriov_for_gpu(pci_bdf):
    """Enable SR-IOV VFs using NVIDIA's sriov-manage tool."""
    try:
        r = subprocess.run(
            ["sriov-manage", "-e", pci_bdf],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r.returncode != 0:
            log.debug(
                "GPU %s: sriov-manage -e unavailable (%s); manual "
                "pci-pf-stub path handles VF enablement",
                pci_bdf,
                (r.stderr or r.stdout).strip()[:200],
            )
            return
    except (OSError, subprocess.TimeoutExpired) as e:
        log.debug(
            "GPU %s: sriov-manage unavailable (%s); manual pci-pf-stub "
            "path handles VF enablement",
            pci_bdf,
            e,
        )
        return

    # Verify VFs created. sriov-manage exits 0 even when the underlying
    # numvfs write is rejected (e.g. PF still bound to vfio-pci, IOMMU
    # disabled), so the post-check is the real gate.
    driver_link = f"/sys/bus/pci/devices/{pci_bdf}/driver"
    try:
        bound = os.path.basename(os.path.realpath(driver_link))
    except OSError:
        bound = None
    try:
        with open(f"/sys/bus/pci/devices/{pci_bdf}/sriov_numvfs") as f:
            actual = int(f.read().strip())
        if actual > 0:
            log.info("GPU %s: enabled %d VFs", pci_bdf, actual)
        else:
            log.error(
                "GPU %s: sriov_numvfs still 0 after sriov-manage -e (PF "
                "driver=%s); VF discovery will not find vGPU profiles",
                pci_bdf,
                bound,
            )
            return
    except (OSError, ValueError) as e:
        log.error("GPU %s: could not verify VFs: %s", pci_bdf, e)
        return

    # Verify at least one VF bound to nvidia (required for mdev creation)
    first_vf = os.path.join(f"/sys/bus/pci/devices/{pci_bdf}", "virtfn0")
    if os.path.exists(first_vf):
        vf_bdf = os.path.basename(os.path.realpath(first_vf))
        driver_link = f"/sys/bus/pci/devices/{vf_bdf}/driver"
        if os.path.exists(driver_link):
            driver = os.path.basename(os.path.realpath(driver_link))
            if driver != "nvidia":
                log.warning(
                    "VF %s bound to %r instead of 'nvidia' — mdev creation "
                    "will fail. Check IOMMU is enabled in BIOS and kernel "
                    "(iommu=pt).",
                    vf_bdf,
                    driver,
                )
        else:
            log.warning(
                "VF %s has no driver — mdev creation will fail. Check IOMMU "
                "is enabled in BIOS and kernel (iommu=pt).",
                vf_bdf,
            )


if __name__ == "__main__":
    gpus = discover_gpus()
    if gpus:
        print(json.dumps(gpus, indent=2))
    else:
        print("No NVIDIA GPUs found")

    pci = discover_pci_devices(gpus)
    print(json.dumps(pci, indent=2))

    hp = discover_hugepages()
    print(json.dumps(hp, indent=2))
