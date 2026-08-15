# SPDX-License-Identifier: AGPL-3.0-or-later

"""Physical (backing-store) usage of a storage pool.

``statvfs`` reports what the FILESYSTEM thinks it has. On a thin pool that is
the LOGICAL size: measured in the field, 83.09 TiB free with 16.83 TiB really
left, and 457 TiB free with 26.1 TiB left. A guard fed that does not guard.

The point: **deciding whether a privileged read is worth asking for costs no
privilege.** :func:`classify` sorts a mount using only ``/proc/self/mountinfo``
and ``/sys``:

===============  =========================  ==============
kind             is ``statvfs`` the truth?  elevation
===============  =========================  ==============
``local-thick``  yes                        ``not-needed``
``local-thin``   no                         ``required``
``network``      it is the server's         ``useless``
``unknown``      unproven                   ``useless``
===============  =========================  ==============

Only ``local-thin`` needs more, and only for the *fill*: it lives behind the
device-mapper ioctl (``CAP_SYS_ADMIN`` + ``/dev/mapper/control``), granted only
where the operator opted in (``STORAGE_POOL_PHYSICAL_STATS``). Without it
the pool is reported thin with an unknown fill -- honest, unlike a filesystem
figure that is wrong by an order of magnitude. On ``network`` no capability
would help: the backing store is on another host. ``unknown`` covers
btrfs/zfs/FUSE, whose free space misleads in its own way.

The thin *capacity* is free too: the ``_vdata`` device's size. The walk
descends through ``slaves``, so it works through DRBD stacked on LVM-VDO as
well as plain LVM -- the mount's own device is often not the dm node.

LVM thin pools (``-tpool``) are classified thin so their ``statvfs`` is not
trusted, but their fill is not read: its data blocks need the block size from
``dmsetup table``, a second privileged call.
"""

import os
import time
from subprocess import DEVNULL, PIPE, run
from typing import Any, Callable, Dict, List, Optional, Tuple

#: Served by another host: no capability granted here could reveal the backing
#: store.
NETWORK_FILESYSTEMS = frozenset(
    {
        "9p",
        "afs",
        "beegfs",
        "ceph",
        "cifs",
        "fuse.ceph",
        "fuse.cephfs",
        "fuse.glusterfs",
        "fuse.sshfs",
        "glusterfs",
        "lustre",
        "nfs",
        "nfs4",
        "smb3",
        "smbfs",
    }
)

#: Local filesystems whose ``statvfs`` reports the block device's truth.
#: Anything else is ``unknown`` rather than assumed: assuming fails silently.
THICK_FILESYSTEMS = frozenset(
    {"ext2", "ext3", "ext4", "jfs", "reiserfs", "vfat", "xfs"}
)

#: A VDO block is 4 KiB; the status line counts in blocks.
VDO_BLOCK_BYTES = 4096

ELEVATION_NOT_NEEDED = "not-needed"
ELEVATION_REQUIRED = "required"
ELEVATION_USELESS = "useless"


def _read(path: str) -> str:
    """A sysfs attribute, or ``""``.

    Every attribute here is absent in some real layout (a partition has no
    ``dm/``, a leaf disk no ``slaves/``), so missing is an answer, not an error.
    """
    try:
        with open(path) as handle:
            return handle.read().strip()
    except OSError:
        return ""


def device_dir(path: str, sysfs: str = "/sys") -> Optional[str]:
    """Sysfs directory of the block device holding ``path``, or ``None``.

    Via ``/sys/dev/block/<major>:<minor>``, which exists for partitions and dm
    nodes alike unlike ``/sys/block/<name>``; the scan is the fallback.
    """
    try:
        stat = os.stat(path)
    except OSError:
        return None
    devnum = f"{os.major(stat.st_dev)}:{os.minor(stat.st_dev)}"

    link = os.path.join(sysfs, "dev", "block", devnum)
    if os.path.exists(link):
        return os.path.realpath(link)

    block = os.path.join(sysfs, "block")
    try:
        names = os.listdir(block)
    except OSError:
        return None
    for name in names:
        if _read(os.path.join(block, name, "dev")) == devnum:
            return os.path.realpath(os.path.join(block, name))
    return None


def backing_chain(directory: str) -> List[str]:
    """``directory`` and everything below it, depth-first through ``slaves``.

    Deepest last. The visited set guards against an unbounded walk of
    kernel-supplied symlinks hanging the reporter rather than failing it.
    """
    order: List[str] = []
    seen = set()

    def visit(current: str) -> None:
        if current in seen:
            return
        seen.add(current)
        order.append(current)
        slaves = os.path.join(current, "slaves")
        try:
            names = sorted(os.listdir(slaves))
        except OSError:
            return
        for name in names:
            visit(os.path.realpath(os.path.join(slaves, name)))

    visit(directory)
    return order


def find_mount(
    path: str, mountinfo: str = "/proc/self/mountinfo"
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """``(mount_point, fstype, source)`` holding ``path``.

    Longest match wins, so a pool mounted inside another pool's tree resolves
    to its own filesystem instead of inheriting its parent's classification.
    """
    try:
        with open(mountinfo) as handle:
            lines = handle.readlines()
    except OSError:
        return (None, None, None)

    target = os.path.realpath(path)
    best: Tuple[Optional[str], Optional[str], Optional[str]] = (None, None, None)
    best_len = -1
    for line in lines:
        # id parent maj:min root mount_point options... - fstype source super
        head, _, tail = line.partition(" - ")
        head_fields = head.split()
        tail_fields = tail.split()
        if len(head_fields) < 5 or len(tail_fields) < 2:
            continue
        mount_point = head_fields[4].replace("\\040", " ")
        if target != mount_point and not target.startswith(
            mount_point.rstrip("/") + "/"
        ):
            continue
        if len(mount_point) > best_len:
            best_len = len(mount_point)
            best = (mount_point, tail_fields[0], tail_fields[1])
    return best


def classify(
    path: str, sysfs: str = "/sys", mountinfo: str = "/proc/self/mountinfo"
) -> Dict[str, Any]:
    """Sort ``path`` into a backing class. Needs no privileges, on purpose:
    a node must always be able to say WHY it does or does not need the
    device-mapper control node."""
    mount_point, fstype, source = find_mount(path, mountinfo=mountinfo)
    result: Dict[str, Any] = {
        "mount_point": mount_point,
        "fstype": fstype,
        "mount_source": source,
        "kind": "unknown",
        "thin": False,
        "backend": None,
        "vpool": None,
        "physical_total_bytes": None,
        "elevation": ELEVATION_USELESS,
        "chain": [],
    }

    if fstype is None:
        result["reason"] = f"no mount found for {path}"
        return result

    if fstype in NETWORK_FILESYSTEMS or fstype.startswith("fuse."):
        result["kind"] = "network" if fstype in NETWORK_FILESYSTEMS else "unknown"
        result["reason"] = (
            f"{fstype} is served by another host; its backing store is not on "
            "this node and no capability here can reveal it"
        )
        return result

    directory = device_dir(path, sysfs=sysfs)
    if directory is None:
        result["reason"] = f"cannot resolve a block device for {path}"
        return result

    chain = backing_chain(directory)
    result["chain"] = [os.path.basename(entry) for entry in chain]

    vpool = vdata = None
    for entry in chain:
        uuid = _read(os.path.join(entry, "dm", "uuid"))
        if uuid.endswith("-vpool"):
            vpool = entry
            result["backend"] = "lvm-vdo"
        elif uuid.endswith("-tpool"):
            vpool = entry
            result["backend"] = "lvm-thin"
        elif uuid.endswith(("-vdata", "-tdata")):
            vdata = entry

    if vpool is not None:
        result["kind"] = "local-thin"
        result["thin"] = True
        result["vpool"] = _read(os.path.join(vpool, "dm", "name")) or None
        result["elevation"] = ELEVATION_REQUIRED
        if vdata is not None:
            size = _read(os.path.join(vdata, "size"))
            if size.isdigit():
                # sysfs sizes are 512-byte sectors, whatever the device's own
                # block size.
                result["physical_total_bytes"] = int(size) * 512
        result["reason"] = (
            "thin-provisioned: the filesystem reports the LOGICAL size, so its "
            "free space is not the constraint"
        )
        return result

    if fstype in THICK_FILESYSTEMS:
        result["kind"] = "local-thick"
        result["elevation"] = ELEVATION_NOT_NEEDED
        result["reason"] = "block-backed and not thin: statvfs IS the physical figure"
        return result

    result["reason"] = (
        f"{fstype} is local but its free space is not a plain reflection of a "
        "block device (compression, snapshots, pooled profile)"
    )
    return result


def vdo_status(runner: Callable[..., Any] = run) -> Dict[str, Dict[str, int]]:
    """Physical fill per VDO pool, keyed by device-mapper name.

    ``{}`` — never a raise — when the ioctl is unavailable, which is the normal
    state wherever the operator did not opt in: a reporter that died here would
    take the classification with it and leave the consumer on the filesystem
    lie. Status line is
    ``<name>: <start> <len> vdo <backing> <mode> <recovery> <index> <compression> <used> <total>``.
    """
    try:
        completed = runner(
            ["dmsetup", "status", "--target", "vdo"],
            stdout=PIPE,
            stderr=DEVNULL,
            text=True,
            timeout=30,
        )
    except Exception:
        return {}
    if getattr(completed, "returncode", 1) != 0:
        return {}

    pools: Dict[str, Dict[str, int]] = {}
    for line in (completed.stdout or "").splitlines():
        name, separator, rest = line.partition(":")
        if not separator:
            continue
        fields = rest.split()
        if len(fields) < 10 or fields[2] != "vdo":
            continue
        try:
            used, total = int(fields[-2]), int(fields[-1])
        except ValueError:
            continue
        pools[name.strip()] = {
            "used_bytes": used * VDO_BLOCK_BYTES,
            "total_bytes": total * VDO_BLOCK_BYTES,
        }
    return pools


def pool_physical_usage(
    path: str,
    sysfs: str = "/sys",
    mountinfo: str = "/proc/self/mountinfo",
    vdo: Optional[Dict[str, Dict[str, int]]] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """What this node can honestly say about the space behind ``path``.

    Pass ``vdo`` from :func:`vdo_status` when measuring several pools: one
    privileged call already reports every VDO on the node.

    ``physical_*`` stay ``None`` whenever the figure is not KNOWN; they are
    never filled with a filesystem number as an approximation. On the mounts
    where the two differ they differ by an order of magnitude, and no caller
    can tell an estimate from a measurement once both are ints in one field.
    """
    backing = classify(path, sysfs=sysfs, mountinfo=mountinfo)
    usage = dict(backing)
    usage["path"] = path
    usage["measured_at"] = int(now if now is not None else time.time())
    usage["filesystem_total_bytes"] = None
    usage["filesystem_free_bytes"] = None
    usage["physical_used_bytes"] = None
    usage["physical_free_bytes"] = None
    usage["source"] = None

    try:
        stat = os.statvfs(path)
        usage["filesystem_total_bytes"] = stat.f_blocks * stat.f_frsize
        usage["filesystem_free_bytes"] = stat.f_bavail * stat.f_frsize
    except OSError:
        pass

    if backing["kind"] == "local-thick":
        usage["physical_total_bytes"] = usage["filesystem_total_bytes"]
        usage["physical_used_bytes"] = (
            None
            if usage["filesystem_total_bytes"] is None
            else usage["filesystem_total_bytes"] - usage["filesystem_free_bytes"]
        )
        usage["physical_free_bytes"] = usage["filesystem_free_bytes"]
        usage["source"] = "statvfs"
        return usage

    if backing["kind"] != "local-thin":
        return usage

    pools = vdo_status() if vdo is None else vdo
    measured = pools.get(backing["vpool"] or "")
    if not measured:
        usage["source"] = "sysfs"
        usage["reason"] = (
            f"{backing['reason']}; its fill needs the device-mapper ioctl, which "
            "this container does not have -- set STORAGE_POOL_PHYSICAL_STATS "
            "on the node holding the physical mounts"
        )
        return usage

    total = measured["total_bytes"] or usage["physical_total_bytes"]
    usage["physical_total_bytes"] = total
    usage["physical_used_bytes"] = measured["used_bytes"]
    if total is not None:
        usage["physical_free_bytes"] = total - measured["used_bytes"]
    usage["source"] = "dm-status"
    return usage


#: Where the pools live. Deriving a pool's root from a path is a rule, not a
#: lookup, so this node never has to read a database.
POOLS_ROOT = "/isard/storage_pools"
DEFAULT_POOL_ROOT = "/isard"

#: Redis hash a storage node publishes a pool's physical usage into, keyed by POOL
#: DIRECTORY -- by mount point every pool on a node would collide on one key.
POOL_STATUS_PREFIX = "governor:pool"


def pool_root(path: str) -> str:
    """The pool directory ``path`` belongs to.

    ``/isard/storage_pools/<name>/...`` -> that pool; anything else -> the
    default pool at ``/isard``. It matches the ``mountpoint`` a pool carries in
    the database, which is what makes the published key joinable by a reader
    without the node having had to look anything up.
    """
    real = os.path.realpath(path)
    if real.startswith(POOLS_ROOT + "/"):
        leaf = real[len(POOLS_ROOT) + 1 :].split("/")[0]
        if leaf:
            return f"{POOLS_ROOT}/{leaf}"
    return DEFAULT_POOL_ROOT


def mount_points(mountinfo: str = "/proc/self/mountinfo") -> List[str]:
    """Every mount point at or under the storage root, as the kernel has them.

    Discovered, not assumed. Any path under ``/isard`` may be its own mount --
    historically ``templates`` is often bind-mounted onto a different device
    from ``groups`` -- and a fixed list of directory names would miss whatever
    an install did that we did not think of. Reading the mount table finds them
    all and needs no layout convention to hold.
    """
    points = []
    try:
        with open(mountinfo) as handle:
            lines = handle.readlines()
    except OSError:
        return points
    for line in lines:
        head, _, tail = line.partition(" - ")
        fields = head.split()
        if len(fields) < 5:
            continue
        point = fields[4].replace("\\040", " ")
        if point == DEFAULT_POOL_ROOT or point.startswith(DEFAULT_POOL_ROOT + "/"):
            if point not in points:
                points.append(point)
    return sorted(points)


def pool_paths(
    sysfs: str = "/sys", mountinfo: str = "/proc/self/mountinfo"
) -> List[str]:
    """Every path worth measuring on this node, discovered rather than looked up.

    Every real mount under the storage root, plus each pool's own directory so a
    reader holding only a pool's mountpoint has something to ask for. A path
    that resolves to no block device is dropped: inside the storage container
    ``/isard`` is the image's own directory and only the binds under it are
    filesystems, so measuring it would report the overlay.
    """
    candidates = list(mount_points(mountinfo=mountinfo))
    for root in [DEFAULT_POOL_ROOT] + _pool_roots():
        if root not in candidates:
            candidates.append(root)

    paths = []
    for candidate in candidates:
        if (
            os.path.isdir(candidate)
            and device_dir(candidate, sysfs=sysfs)
            and candidate not in paths
        ):
            paths.append(candidate)
    return paths


def _pool_roots() -> List[str]:
    try:
        return [
            os.path.join(POOLS_ROOT, name)
            for name in sorted(os.listdir(POOLS_ROOT))
            if os.path.isdir(os.path.join(POOLS_ROOT, name))
        ]
    except OSError:
        return []


def tightest(measurements: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The measurement a pool should be judged by: its most constrained path.

    A pool spanning several filesystems is as full as its fullest one, and that
    is the figure a capacity warning has to be driven by -- averaging them, or
    picking the root's, would hide the directory that is about to fail writes.
    """
    known = [m for m in measurements if m.get("physical_free_bytes") is not None]
    if not known:
        return measurements[0] if measurements else None
    return min(known, key=lambda m: m["physical_free_bytes"])


#: Fields carried to readers. Scalars only, so the value is a plain redis hash
#: like every other governor key; ``chain`` stays local diagnostics.
PUBLISHED_FIELDS = (
    "kind",
    "thin",
    "backend",
    "vpool",
    "fstype",
    "elevation",
    "physical_total_bytes",
    "physical_used_bytes",
    "physical_free_bytes",
    "filesystem_total_bytes",
    "filesystem_free_bytes",
    "measured_at",
    "source",
    "node",
    "reason",
)


def pool_status_key(mountpoint: str) -> str:
    return f"{POOL_STATUS_PREFIX}:{mountpoint}"


def publish_usage(connection: Any, usage: Dict[str, Any], ttl: int) -> None:
    """Publish one mount's measurement, expiring after ``ttl`` seconds.

    ``ttl`` must exceed the publishing cycle, because expiry is the ONLY
    staleness mechanism: a node that stops measuring lets its key die and the
    reader is left with nothing, which is the correct answer. A figure that
    outlived its reporter would be worse than none -- a pool goes on filling
    precisely while nobody is watching it.
    """
    mapping = {}
    for field in PUBLISHED_FIELDS:
        value = usage.get(field)
        if value is None:
            continue
        mapping[field] = int(value) if isinstance(value, bool) else value
    if not mapping:
        return
    key = pool_status_key(usage["path"])
    pipe = connection.pipeline()
    pipe.delete(key)
    pipe.hset(key, mapping=mapping)
    pipe.expire(key, ttl)
    pipe.execute()


def read_usage(connection: Any, mountpoint: str) -> Optional[Dict[str, Any]]:
    """A published measurement, or ``None`` when nobody is publishing one.

    Numeric fields come back as ints so a caller can do arithmetic without
    re-deriving which of them redis handed over as strings.
    """
    try:
        raw = connection.hgetall(pool_status_key(mountpoint))
    except Exception:
        return None
    if not raw:
        return None
    usage = {}
    for key, value in raw.items():
        key = key.decode() if isinstance(key, bytes) else key
        value = value.decode() if isinstance(value, bytes) else value
        if key.endswith("_bytes") or key == "measured_at":
            try:
                value = int(value)
            except (TypeError, ValueError):
                continue
        elif key == "thin":
            value = value in ("1", 1, "True", "true")
        usage[key] = value
    return usage


def read_usage_for_path(connection: Any, path: str) -> Optional[Dict[str, Any]]:
    """The published measurement that governs ``path``, most specific first.

    A destination directory sits under a usage directory which sits under a
    pool root, and any of those can be its own filesystem. Walking up from the
    path means a bind-mounted usage directory answers for its own contents
    instead of the pool root answering for all of them.
    """
    real = os.path.realpath(path)
    root = pool_root(real)
    candidate = real
    while True:
        usage = read_usage(connection, candidate)
        if usage:
            return usage
        if candidate == root or candidate == "/":
            return None
        parent = os.path.dirname(candidate)
        if parent == candidate:
            return None
        candidate = parent
