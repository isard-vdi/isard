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
import urllib.request

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


def _aggregate_subdevice_profiles(pci_bus_id):
    """For cards like A40 that expose multiple sub-devices, aggregate profiles.

    Some NVIDIA cards (e.g., A40) don't expose mdev_supported_types on the main
    PCI device but on sub-devices (e.g., 0000:41:00.4, 0000:41:00.5, etc.).

    This function checks both the main device and sub-devices, returning
    aggregated profiles with summed available_instances.

    Args:
        pci_bus_id: PCI bus ID from nvidia-smi

    Returns:
        tuple: (profiles_list, sub_paths_set or None, path_parent or None)
    """
    sysfs_pci_id = _normalize_pci_bus_id(pci_bus_id).lower()
    main_path = f"/sys/bus/pci/devices/{sysfs_pci_id}"

    # First try main device
    main_profiles = _get_vgpu_profiles(pci_bus_id)
    if main_profiles:
        return main_profiles, None, None

    # Check sub-devices (e.g., 0000:41:00.4 for main device 0000:41:00.0)
    base = sysfs_pci_id.rsplit(".", 1)[0]  # e.g., '0000:41:00'
    sub_paths = set()
    profile_map = {}  # name -> profile dict with aggregated available_instances

    try:
        for entry in sorted(os.listdir("/sys/bus/pci/devices/")):
            if entry.startswith(base + ".") and entry != sysfs_pci_id:
                sub_profiles = _get_vgpu_profiles(entry)
                if sub_profiles:
                    sub_path = f"/sys/bus/pci/devices/{entry}"
                    sub_paths.add(sub_path)
                    for p in sub_profiles:
                        if p["name"] in profile_map:
                            profile_map[p["name"]]["available_instances"] += p[
                                "available_instances"
                            ]
                        else:
                            profile_map[p["name"]] = dict(p)
    except OSError:
        pass

    if not profile_map:
        return [], None, None

    profiles = sorted(profile_map.values(), key=lambda p: p["name"])
    path_parent = main_path if os.path.exists(main_path) else None
    return profiles, sub_paths if sub_paths else None, path_parent


def normalize_gpu_model(gpu_name, vgpu_profiles=None):
    """Derive a dash-free canonical model name for a GPU.

    Uses vGPU profile name prefix when available (e.g., "A40" from "A40-4Q"),
    otherwise normalizes the nvidia-smi name by stripping "NVIDIA " prefix
    and removing spaces and dashes to produce a dash-free string.

    The model MUST be dash-free because the system uses
    "BRAND-MODEL-PROFILE" format with dashes as separators.
    """
    if vgpu_profiles:
        return vgpu_profiles[0]["name"].split("-")[0]
    return gpu_name.replace("NVIDIA ", "").replace(" ", "").replace("-", "")


def discover_gpus():
    """Discover NVIDIA GPUs and their vGPU profiles.

    Uses nvidia-smi for GPU hardware info and sysfs for vGPU profiles.

    Returns:
        list of GPU dicts. Empty list if no GPUs or nvidia-smi unavailable.
    """
    raw_gpus = _run_nvidia_smi()

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
        except (OSError, ValueError):
            pass

        if sub_paths is not None:
            gpu_info["sub_paths"] = sorted(sub_paths)
        if path_parent is not None:
            gpu_info["path_parent"] = path_parent

        # Detect misconfiguration: SR-IOV GPUs with VFs but no vGPU profiles
        warnings = []
        totalvfs = gpu_info.get("sriov_totalvfs", 0)
        if totalvfs > 0 and not profiles:
            numvfs_path = f"/sys/bus/pci/devices/{sysfs_pci_id}/sriov_numvfs"
            try:
                with open(numvfs_path) as f:
                    numvfs = int(f.read().strip())
            except (OSError, ValueError):
                numvfs = 0
            if numvfs == 0:
                warnings.append(
                    f"SR-IOV capable ({totalvfs} VFs) but VF creation failed. "
                    f"Only passthrough and MIG modes available."
                )
            else:
                # VFs exist but no profiles — likely IOMMU issue
                first_vf = f"/sys/bus/pci/devices/{sysfs_pci_id}/virtfn0"
                vf_driver = ""
                if os.path.exists(first_vf):
                    vf_bdf = os.path.basename(os.path.realpath(first_vf))
                    drv = f"/sys/bus/pci/devices/{vf_bdf}/driver"
                    if os.path.exists(drv):
                        vf_driver = os.path.basename(os.path.realpath(drv))
                if vf_driver != "nvidia":
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
        if warnings:
            gpu_info["warnings"] = warnings
            for w in warnings:
                print(f"  GPU {sysfs_pci_id}: {w}")

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


def discover_numa_topology():
    """Discover per-NUMA-node CPU list and hugepages from sysfs.

    Reads /sys/devices/system/node/node* to build a map of which CPUs and
    hugepages belong to each NUMA node. The cpulist values are static hardware
    topology; the hugepages counts are a snapshot from discovery time.

    Returns:
        dict: {
            "nodes": {
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
    return {"nodes": nodes}


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
        # Already has mdev types on PF (legacy vGPU, not Blackwell)
        if os.path.isdir(os.path.join(dev_path, "mdev_supported_types")):
            continue

        print(f"Enabling {totalvfs} SR-IOV VFs on {dev}...")
        _enable_sriov_for_gpu(dev, totalvfs)


def _check_iommu_available():
    """Check if IOMMU is active (required for SR-IOV VF nvidia binding)."""
    try:
        groups = os.listdir("/sys/kernel/iommu_groups")
        return len(groups) > 0
    except OSError:
        return False


def _enable_sriov_for_gpu(pci_bdf, totalvfs):
    """Run the pci-pf-stub dance to enable SR-IOV VFs for one GPU."""

    def _run(cmd):
        return subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

    if not _check_iommu_available():
        print(
            f"  WARNING: IOMMU not active — VFs will be created but nvidia "
            f"cannot bind them (vGPU mdev creation will fail). "
            f"Enable IOMMU in BIOS and add iommu=pt to kernel cmdline."
        )

    # Get vendor:device for pci-pf-stub new_id
    r = _run(f"lspci -n -s {pci_bdf}")
    if r.returncode != 0:
        print(f"  FAILED: lspci for {pci_bdf}: {r.stderr.strip()}")
        return
    parts = r.stdout.split()
    vend_dev = parts[2].replace(":", " ") if len(parts) >= 3 else ""
    if not vend_dev:
        print(f"  FAILED: could not parse vendor:device for {pci_bdf}")
        return

    steps = [
        # Ensure pci-pf-stub module is loaded
        ("modprobe pci-pf-stub", False),
        # Get nvidia unbindLock
        (f"echo 1 > /proc/driver/nvidia/gpus/{pci_bdf}/unbindLock", True),
        # Unbind PF from nvidia
        (f"echo {pci_bdf} > /sys/bus/pci/drivers/nvidia/unbind", True),
        # Register device with pci-pf-stub and bind
        (f"echo '{vend_dev}' > /sys/bus/pci/drivers/pci-pf-stub/new_id", True),
        (
            f"[ -e /sys/bus/pci/drivers/pci-pf-stub/{pci_bdf} ] || "
            f"echo {pci_bdf} > /sys/bus/pci/drivers/pci-pf-stub/bind",
            False,
        ),
        ("sleep 0.5", False),
        # Create VFs
        (
            f"echo {totalvfs} > /sys/bus/pci/devices/{pci_bdf}/sriov_numvfs",
            False,
        ),
        # Unbind from pci-pf-stub
        (f"echo {pci_bdf} > /sys/bus/pci/drivers/pci-pf-stub/unbind", True),
        (
            f"echo '{vend_dev}' > /sys/bus/pci/drivers/pci-pf-stub/remove_id",
            True,
        ),
        # Bind all VFs to nvidia driver (enumerate via virtfn symlinks)
        (
            f"for vf in /sys/bus/pci/devices/{pci_bdf}/virtfn*/; do "
            f"vf_bdf=$(basename $(readlink -f $vf)); "
            f"[ -e /sys/bus/pci/devices/$vf_bdf/driver ] && "
            f"echo $vf_bdf > /sys/bus/pci/devices/$vf_bdf/driver/unbind 2>/dev/null || true; "
            f"echo $vf_bdf > /sys/bus/pci/drivers/nvidia/bind 2>/dev/null || true; "
            f"done",
            True,
        ),
        # Rebind PF to nvidia
        (f"echo {pci_bdf} > /sys/bus/pci/drivers/nvidia/bind", True),
        ("nvidia-smi -pm 1 2>/dev/null", True),
    ]

    for cmd, ignore_error in steps:
        r = _run(cmd)
        if r.returncode != 0 and not ignore_error:
            print(f"  FAILED at: {cmd}")
            print(f"  stderr: {r.stderr.strip()}")
            return

    # Verify VFs created
    try:
        with open(f"/sys/bus/pci/devices/{pci_bdf}/sriov_numvfs") as f:
            actual = int(f.read().strip())
        if actual > 0:
            print(f"  Enabled {actual} VFs on {pci_bdf}")
        else:
            print(f"  WARNING: sriov_numvfs still 0 after enablement for {pci_bdf}")
            return
    except (OSError, ValueError) as e:
        print(f"  WARNING: could not verify VFs for {pci_bdf}: {e}")
        return

    # Verify at least one VF bound to nvidia (required for mdev creation)
    first_vf = os.path.join(f"/sys/bus/pci/devices/{pci_bdf}", "virtfn0")
    if os.path.exists(first_vf):
        vf_bdf = os.path.basename(os.path.realpath(first_vf))
        driver_link = f"/sys/bus/pci/devices/{vf_bdf}/driver"
        if os.path.exists(driver_link):
            driver = os.path.basename(os.path.realpath(driver_link))
            if driver != "nvidia":
                print(
                    f"  WARNING: VF {vf_bdf} bound to '{driver}' instead of "
                    f"'nvidia' — mdev creation will fail. "
                    f"Check IOMMU is enabled in BIOS and kernel (iommu=pt)."
                )
        else:
            print(
                f"  WARNING: VF {vf_bdf} has no driver — mdev creation will "
                f"fail. Check IOMMU is enabled in BIOS and kernel (iommu=pt)."
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
