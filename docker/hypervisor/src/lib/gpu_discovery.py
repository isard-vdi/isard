"""GPU discovery using nvidia-smi and sysfs.

Runs inside the isard-hypervisor container. Discovers NVIDIA GPUs and their
vGPU profiles without requiring libvirt or hardcoded PCI ID dictionaries.
"""

import json
import os
import re
import subprocess


def _run_nvidia_smi():
    """Run nvidia-smi and return parsed GPU info.

    Returns:
        list of dicts with keys: name, memory_total_mb, pci_bus_id, driver_version, mig_mode
        Empty list if nvidia-smi is not available or fails.
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,pci.bus_id,driver_version,mig.mode.current",
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
        if len(parts) != 5:
            continue
        gpus.append(
            {
                "name": parts[0],
                "memory_total_mb": int(float(parts[1])),
                "pci_bus_id": parts[2],
                "driver_version": parts[3],
                "mig_mode": parts[4],
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
        line = line.strip()
        if not line.startswith("|"):
            continue
        # Split table columns: | GPU  MIG_name  ID  Instances  Memory | ...
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 5:
            continue
        # Skip header rows
        try:
            profile_id = int(cols[2])
        except (ValueError, IndexError):
            continue
        name = cols[1]  # e.g. "1g.24gb", "2g.48gb+gfx", "1g.24gb-me"
        if not name or not re.match(r"\d+g\.", name):
            continue
        # Instances field like "4/4" or "7" — parse free/total or just total
        instances_str = cols[3]
        parts = instances_str.split("/")
        try:
            max_instances = int(parts[-1])
        except ValueError:
            max_instances = 0
        # Memory field like "23.62 GiB" or "23616 MiB"
        mem_str = cols[4]
        mem_match = re.search(r"([\d.]+)\s*(GiB|MiB|GB|MB)", mem_str)
        if mem_match:
            mem_val = float(mem_match.group(1))
            if mem_match.group(2) in ("MiB", "MB"):
                mem_val /= 1024.0
            memory_gib = round(mem_val, 2)
        else:
            memory_gib = 0.0
        profiles.append(
            {
                "name": name,
                "profile_id": profile_id,
                "max_instances": max_instances,
                "memory_gib": memory_gib,
            }
        )
    return profiles


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


def discover_gpus():
    """Discover NVIDIA GPUs and their vGPU profiles.

    Uses nvidia-smi for GPU hardware info and sysfs for vGPU profiles.

    Returns:
        list of GPU dicts. Empty list if no GPUs or nvidia-smi unavailable.
    """
    raw_gpus = _run_nvidia_smi()
    if not raw_gpus:
        return []

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
        }

        if mig_mode != "[N/A]":
            mig_profiles = _get_mig_profiles(gpu_index)
            if mig_profiles:
                gpu_info["mig_profiles"] = mig_profiles

        # Check for SR-IOV capability (vGPU cards like A40)
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

        gpus.append(gpu_info)

    return gpus


if __name__ == "__main__":
    gpus = discover_gpus()
    if gpus:
        print(json.dumps(gpus, indent=2))
    else:
        print("No NVIDIA GPUs found")
