# SPDX-License-Identifier: AGPL-3.0-or-later

"""The classification that decides whether a privileged read is worth asking for.

These pin the two ends that are easy to get wrong and expensive to get wrong:

* a THIN pool must never be reported with the filesystem's free space, because
  that number was optimistic by 5x and 17x on the thin pools this was written
  against;
* a NETWORK pool must report that it cannot be measured rather than producing a
  figure, because no capability granted on this host can reveal a backing store
  that lives on another one -- and a fabricated number is indistinguishable
  from a measured one once both are integers in the same field.

The sysfs fixtures are real directories and real symlinks, tied to the tmp
directory's own device number, so ``device_dir`` resolves through the same code
path it uses in production instead of through a patched ``os.stat``.
"""

import os

import pytest
from isardvdi_common.lib.storage import physical_usage as m


def _device(root, name, uuid=None, size=None, slaves=()):
    """Create one sysfs block-device directory, returning its path."""
    path = os.path.join(root, "devices", "virtual", "block", name)
    os.makedirs(path, exist_ok=True)
    if uuid is not None:
        os.makedirs(os.path.join(path, "dm"), exist_ok=True)
        with open(os.path.join(path, "dm", "name"), "w") as handle:
            handle.write(name + "\n")
        with open(os.path.join(path, "dm", "uuid"), "w") as handle:
            handle.write(uuid + "\n")
    if size is not None:
        with open(os.path.join(path, "size"), "w") as handle:
            handle.write(str(size) + "\n")
    if slaves:
        slavedir = os.path.join(path, "slaves")
        os.makedirs(slavedir, exist_ok=True)
        for slave in slaves:
            link = os.path.join(slavedir, os.path.basename(slave))
            if not os.path.lexists(link):
                os.symlink(slave, link)
    return path


def _publish(root, mount_path, device_path):
    """Point /sys/dev/block/<maj>:<min> of ``mount_path`` at ``device_path``."""
    stat = os.stat(mount_path)
    devnum = f"{os.major(stat.st_dev)}:{os.minor(stat.st_dev)}"
    blockdir = os.path.join(root, "dev", "block")
    os.makedirs(blockdir, exist_ok=True)
    link = os.path.join(blockdir, devnum)
    if not os.path.lexists(link):
        os.symlink(device_path, link)


def _mountinfo(tmp_path, entries):
    """Write a mountinfo file; entries are (mount_point, fstype, source)."""
    path = tmp_path / "mountinfo"
    lines = []
    for index, (mount_point, fstype, source) in enumerate(entries, start=25):
        lines.append(
            f"{index} 1 0:{index} / {mount_point} rw,noatime shared:{index} "
            f"- {fstype} {source} rw"
        )
    path.write_text("\n".join(lines) + "\n")
    return str(path)


@pytest.fixture
def pool(tmp_path):
    """A pool directory plus an empty fake sysfs root."""
    sysfs = tmp_path / "sys"
    sysfs.mkdir()
    mount = tmp_path / "pool"
    mount.mkdir()
    return str(mount), str(sysfs)


# find_mount


def test_nested_mount_resolves_to_the_deepest_one(tmp_path):
    """A pool mounted inside another pool's tree is its OWN filesystem.

    Taking the first or the shortest match would classify every pool by its
    parent, so a thin pool nested under a thick tree would inherit "thick" and
    its free space would be trusted.
    """
    outer = str(tmp_path / "storage_pools")
    inner = outer + "/vdo3"
    mountinfo = _mountinfo(
        tmp_path,
        [(outer, "xfs", "/dev/mapper/thick"), (inner, "xfs", "/dev/mapper/vdo")],
    )

    assert m.find_mount(inner, mountinfo=mountinfo) == (
        inner,
        "xfs",
        "/dev/mapper/vdo",
    )
    assert m.find_mount(outer, mountinfo=mountinfo)[2] == "/dev/mapper/thick"


def test_unmatched_path_reports_nothing_rather_than_guessing(tmp_path):
    mountinfo = _mountinfo(tmp_path, [("/somewhere/else", "xfs", "/dev/sda1")])
    assert m.find_mount("/isard/storage_pools/x", mountinfo=mountinfo) == (
        None,
        None,
        None,
    )


# classify


def test_network_pool_is_unmeasurable_and_elevation_would_not_help(pool, tmp_path):
    mount, sysfs = pool
    mountinfo = _mountinfo(tmp_path, [(mount, "nfs4", "10.0.0.1:/export")])

    result = m.classify(mount, sysfs=sysfs, mountinfo=mountinfo)

    assert result["kind"] == "network"
    assert result["thin"] is False
    assert result["elevation"] == m.ELEVATION_USELESS
    assert result["physical_total_bytes"] is None


def test_thick_local_pool_needs_no_elevation(pool, tmp_path):
    """statvfs already IS the physical figure here, so asking for the ioctl
    would grant device-mapper control over the node in exchange for nothing."""
    mount, sysfs = pool
    device = _device(sysfs, "dm-1", uuid="LVM-plainvolume", size=2048)
    _publish(sysfs, mount, device)
    mountinfo = _mountinfo(tmp_path, [(mount, "xfs", "/dev/mapper/vg-fast")])

    result = m.classify(mount, sysfs=sysfs, mountinfo=mountinfo)

    assert result["kind"] == "local-thick"
    assert result["elevation"] == m.ELEVATION_NOT_NEEDED
    assert result["backend"] is None


def test_thin_pool_is_found_through_a_drbd_stack(pool, tmp_path):
    """The mount's own device is NOT the device-mapper node on a DRBD cluster.

    Stopping at the first device (or assuming it is a dm node) misses the VDO
    entirely and the pool is silently classified as thick -- which is the
    production layout this walk exists for.
    """
    mount, sysfs = pool
    vdata = _device(sysfs, "dm-2", uuid="LVM-abc-vdata", size=36387684352)
    vpool = _device(
        sysfs, "dm-3", uuid="LVM-abc-vpool", size=1073741826048, slaves=[vdata]
    )
    lv = _device(sysfs, "dm-4", uuid="LVM-abc", size=1073741824000, slaves=[vpool])
    drbd = _device(sysfs, "drbd2", size=1073741824000, slaves=[lv])
    _publish(sysfs, mount, drbd)
    mountinfo = _mountinfo(tmp_path, [(mount, "xfs", "/dev/drbd2")])

    result = m.classify(mount, sysfs=sysfs, mountinfo=mountinfo)

    assert result["kind"] == "local-thin"
    assert result["thin"] is True
    assert result["backend"] == "lvm-vdo"
    assert result["vpool"] == "dm-3"
    assert result["elevation"] == m.ELEVATION_REQUIRED
    # Capacity comes from the _vdata device and needs no privilege at all.
    assert result["physical_total_bytes"] == 36387684352 * 512
    assert result["chain"] == ["drbd2", "dm-4", "dm-3", "dm-2"]


def test_lvm_thin_pool_is_thin_even_though_its_fill_is_not_read_here(pool, tmp_path):
    """dm-thin gets the same "do not trust statvfs" verdict as VDO.

    Its fill needs a second privileged call this module does not make, but
    classifying it as thick would be the same silent over-estimate.
    """
    mount, sysfs = pool
    tdata = _device(sysfs, "dm-6", uuid="LVM-xyz-tdata", size=1024)
    tpool = _device(sysfs, "dm-7", uuid="LVM-xyz-tpool", size=8192, slaves=[tdata])
    _publish(sysfs, mount, tpool)
    mountinfo = _mountinfo(tmp_path, [(mount, "ext4", "/dev/mapper/vg-thin")])

    result = m.classify(mount, sysfs=sysfs, mountinfo=mountinfo)

    assert result["kind"] == "local-thin"
    assert result["backend"] == "lvm-thin"
    assert result["elevation"] == m.ELEVATION_REQUIRED


def test_pooled_filesystem_is_unproven_not_assumed_thick(pool, tmp_path):
    """btrfs/zfs free space is misleading in its own way; claiming it is the
    physical truth would launder a guess into a fact."""
    mount, sysfs = pool
    device = _device(sysfs, "dm-9", size=2048)
    _publish(sysfs, mount, device)
    mountinfo = _mountinfo(tmp_path, [(mount, "btrfs", "/dev/mapper/vg-btrfs")])

    result = m.classify(mount, sysfs=sysfs, mountinfo=mountinfo)

    assert result["kind"] == "unknown"
    assert result["elevation"] == m.ELEVATION_USELESS


# vdo_status


class _Completed:
    def __init__(self, stdout, returncode=0):
        self.stdout = stdout
        self.returncode = returncode


def test_vdo_status_parses_a_real_production_line():
    line = (
        "vg_pool-data-vpool: 0 181938423808 vdo /dev/dm-2 normal - "
        "online online 30167254 4548460544\n"
    )
    pools = m.vdo_status(runner=lambda *a, **k: _Completed(line))

    assert pools == {
        "vg_pool-data-vpool": {
            "used_bytes": 30167254 * 4096,
            "total_bytes": 4548460544 * 4096,
        }
    }


def test_vdo_status_is_empty_without_the_ioctl_instead_of_raising():
    """The normal state on every node the operator did not opt in.

    A reporter that raised here would take the whole classification down with
    it, and the consumer would fall back to the filesystem lie having been told
    nothing.
    """

    def refused(*args, **kwargs):
        raise FileNotFoundError("dmsetup")

    assert m.vdo_status(runner=refused) == {}
    assert m.vdo_status(runner=lambda *a, **k: _Completed("", returncode=1)) == {}


# pool_physical_usage


def test_thin_pool_reports_the_backing_store_not_the_filesystem(pool, tmp_path):
    mount, sysfs = pool
    vdata = _device(sysfs, "dm-2", uuid="LVM-abc-vdata", size=36387684352)
    vpool = _device(
        sysfs, "dm-3", uuid="LVM-abc-vpool", size=1073741826048, slaves=[vdata]
    )
    _publish(sysfs, mount, vpool)
    mountinfo = _mountinfo(tmp_path, [(mount, "xfs", "/dev/mapper/vg-vdo")])
    vdo = {"dm-3": {"used_bytes": 123565072384, "total_bytes": 18630494388224}}

    usage = m.pool_physical_usage(mount, sysfs=sysfs, mountinfo=mountinfo, vdo=vdo)

    assert usage["source"] == "dm-status"
    assert usage["physical_total_bytes"] == 18630494388224
    assert usage["physical_used_bytes"] == 123565072384
    assert usage["physical_free_bytes"] == 18630494388224 - 123565072384
    # The filesystem figure stays as a separate field: on this class of pool the
    # two disagree by an order of magnitude.
    assert usage["filesystem_free_bytes"] != usage["physical_free_bytes"]


def test_thin_pool_without_the_ioctl_says_so_instead_of_falling_back(pool, tmp_path):
    mount, sysfs = pool
    vdata = _device(sysfs, "dm-2", uuid="LVM-abc-vdata", size=36387684352)
    vpool = _device(
        sysfs, "dm-3", uuid="LVM-abc-vpool", size=1073741826048, slaves=[vdata]
    )
    _publish(sysfs, mount, vpool)
    mountinfo = _mountinfo(tmp_path, [(mount, "xfs", "/dev/mapper/vg-vdo")])

    usage = m.pool_physical_usage(mount, sysfs=sysfs, mountinfo=mountinfo, vdo={})

    assert usage["thin"] is True
    assert usage["source"] == "sysfs"
    # Capacity is known without privileges; the FILL is what is missing, and it
    # stays None rather than borrowing the filesystem's answer.
    assert usage["physical_total_bytes"] == 36387684352 * 512
    assert usage["physical_used_bytes"] is None
    assert usage["physical_free_bytes"] is None
    assert "STORAGE_POOL_VDO_STATS" in usage["reason"]


def test_thick_pool_physical_equals_filesystem(pool, tmp_path):
    mount, sysfs = pool
    device = _device(sysfs, "dm-1", uuid="LVM-plainvolume", size=2048)
    _publish(sysfs, mount, device)
    mountinfo = _mountinfo(tmp_path, [(mount, "xfs", "/dev/mapper/vg-fast")])

    usage = m.pool_physical_usage(mount, sysfs=sysfs, mountinfo=mountinfo, vdo={})

    assert usage["source"] == "statvfs"
    assert usage["physical_free_bytes"] == usage["filesystem_free_bytes"]
    assert usage["physical_total_bytes"] == usage["filesystem_total_bytes"]


def test_network_pool_publishes_no_physical_figure(pool, tmp_path):
    mount, sysfs = pool
    mountinfo = _mountinfo(tmp_path, [(mount, "nfs4", "10.0.0.1:/export")])

    usage = m.pool_physical_usage(mount, sysfs=sysfs, mountinfo=mountinfo, vdo={})

    assert usage["kind"] == "network"
    assert usage["physical_total_bytes"] is None
    assert usage["physical_used_bytes"] is None
    assert usage["physical_free_bytes"] is None
    assert usage["source"] is None
    # The filesystem's own answer is still recorded -- it is the server's
    # reply, which is useful context, just not a physical measurement.
    assert usage["filesystem_free_bytes"] is not None


# publishing: redis, never a database


class _FakeRedis:
    """Enough of redis for the publish/read round trip, including expiry."""

    def __init__(self):
        self.hashes = {}
        self.ttls = {}
        self.ops = []

    def pipeline(self):
        return self

    def delete(self, key):
        self.ops.append(("delete", key))
        self.hashes.pop(key, None)

    def hset(self, key, mapping=None):
        self.ops.append(("hset", key))
        self.hashes[key] = {k: str(v).encode() for k, v in mapping.items()}

    def expire(self, key, ttl):
        self.ops.append(("expire", key))
        self.ttls[key] = ttl

    def execute(self):
        return None

    def hgetall(self, key):
        return self.hashes.get(key, {})

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)


def test_publish_then_read_returns_usable_numbers():
    conn = _FakeRedis()
    usage = {
        "path": "/isard/storage_pools/vdo3",
        "mount_point": "/isard/storage_pools",
        "kind": "local-thin",
        "thin": True,
        "physical_total_bytes": 18630494388224,
        "physical_free_bytes": 18506929315840,
        "chain": ["dm-3", "dm-2"],
    }

    m.publish_usage(conn, usage, 900)
    back = m.read_usage(conn, "/isard/storage_pools/vdo3")

    # Numbers come back as ints so a caller can do arithmetic without having to
    # re-derive which fields redis handed over as strings.
    assert back["physical_free_bytes"] == 18506929315840
    assert back["thin"] is True
    assert back["kind"] == "local-thin"
    # Diagnostics stay local: the chain is for `--json`, not for every reader.
    assert "chain" not in back


def test_publishing_always_sets_an_expiry():
    """Expiry is the ONLY staleness mechanism. A key written without one would
    keep answering for a node that stopped measuring, which is exactly when the
    pool goes on filling unobserved."""
    conn = _FakeRedis()

    m.publish_usage(conn, {"path": "/isard", "kind": "local-thick"}, 900)

    assert conn.ttls["governor:pool:/isard"] == 900
    # Replaced, not merged: a later report that can no longer measure the fill
    # must not leave the old number behind.
    assert ("delete", "governor:pool:/isard") in conn.ops


def test_reading_an_unpublished_mount_is_none_not_a_guess():
    assert m.read_usage(_FakeRedis(), "/isard/storage_pools/nobody") is None


def test_pools_sharing_one_filesystem_get_their_own_keys():
    """The stock layout puts every pool on one filesystem. Keying by mount
    point would collide them all onto a single key and no reader would find the
    pool it asked about -- which is how this was caught, on a bench where two
    pools were directories on the same ext4."""
    conn = _FakeRedis()
    for name in ("mkorigen", "mkdesti"):
        m.publish_usage(
            conn,
            {
                "path": f"/isard/storage_pools/{name}",
                "mount_point": "/isard/storage_pools",
                "kind": "local-thick",
                "physical_free_bytes": 1,
            },
            900,
        )

    assert m.read_usage(conn, "/isard/storage_pools/mkorigen") is not None
    assert m.read_usage(conn, "/isard/storage_pools/mkdesti") is not None


def test_pool_root_maps_a_disk_path_back_to_its_pool():
    assert m.pool_root("/isard/storage_pools/vdo3/groups/x/y.qcow2") == (
        "/isard/storage_pools/vdo3"
    )
    assert m.pool_root("/isard/groups/x/y.qcow2") == "/isard"
    assert m.pool_root("/isard/storage_pools") == "/isard"


def test_the_default_pool_is_measured_where_its_disks_actually_live(
    tmp_path, monkeypatch
):
    """Inside the storage container the pool root is the image's own directory
    and only the binds under it are filesystems, so measuring the root would
    report the overlay and the default pool would silently never be reported."""
    root = tmp_path / "isard"
    (root / "groups").mkdir(parents=True)
    (root / "storage_pools").mkdir()
    monkeypatch.setattr(m, "DEFAULT_POOL_ROOT", str(root))
    monkeypatch.setattr(m, "POOLS_ROOT", str(root / "storage_pools"))
    mountinfo = _mountinfo(tmp_path, [(str(root / "groups"), "ext4", "/dev/sda2")])
    # The root resolves to nothing; the bind under it does.
    monkeypatch.setattr(
        m, "device_dir", lambda p, sysfs="/sys": None if p == str(root) else "/dev/x"
    )

    assert m.pool_paths(mountinfo=mountinfo) == [str(root / "groups")]


def test_a_bind_mounted_usage_directory_answers_for_its_own_contents():
    """The default pool's directories are independently mountable, and in the
    field they are: templates on one device, groups on another. A lookup that
    only asked the pool root would answer for the wrong filesystem."""
    conn = _FakeRedis()
    m.publish_usage(
        conn, {"path": "/isard", "kind": "local-thick", "physical_free_bytes": 999}, 900
    )
    m.publish_usage(
        conn,
        {
            "path": "/isard/templates",
            "kind": "local-thick",
            "physical_free_bytes": 1,
        },
        900,
    )

    deep = m.read_usage_for_path(conn, "/isard/templates/a/b.qcow2")
    other = m.read_usage_for_path(conn, "/isard/groups/a/b.qcow2")

    assert deep["physical_free_bytes"] == 1
    # Nothing published for groups, so the pool root answers -- and says so.
    assert other["physical_free_bytes"] == 999


def test_a_pool_is_as_full_as_its_fullest_path():
    """Averaging, or trusting the root, would hide the directory that is about
    to start failing writes."""
    roomy = {"path": "/isard/groups", "physical_free_bytes": 100}
    tight = {"path": "/isard/templates", "physical_free_bytes": 3}

    assert m.tightest([roomy, tight]) is tight
    # An unmeasured path must not win by being None.
    assert m.tightest([{"path": "/x", "physical_free_bytes": None}, tight]) is tight


def test_every_mount_under_the_storage_root_is_discovered(tmp_path, monkeypatch):
    """No layout convention is assumed: whatever the kernel says is a mount
    under /isard gets measured, including binds nobody anticipated."""
    mountinfo = _mountinfo(
        tmp_path,
        [
            ("/", "ext4", "/dev/sda1"),
            ("/isard/templates", "xfs", "/dev/drbd1"),
            ("/isard/groups", "xfs", "/dev/drbd2"),
            ("/isard/storage_pools/vdo3", "xfs", "/dev/mapper/vdo"),
            ("/somewhere/else", "xfs", "/dev/sdb1"),
        ],
    )

    points = m.mount_points(mountinfo=mountinfo)

    assert points == [
        "/isard/groups",
        "/isard/storage_pools/vdo3",
        "/isard/templates",
    ]
    assert "/" not in points and "/somewhere/else" not in points


def test_another_nodes_live_measurement_is_not_overwritten(caplog):
    """One key per path, so two nodes with a local filesystem at the same path
    would take turns publishing about different disks. The reader cannot tell,
    and the figure is a free-space floor."""
    conn = _FakeRedis()
    m.publish_usage(
        conn,
        {
            "path": "/isard/groups",
            "kind": "local-thick",
            "node": "nas-a",
            "physical_free_bytes": 10,
        },
        900,
    )
    with caplog.at_level("WARNING"):
        m.publish_usage(
            conn,
            {
                "path": "/isard/groups",
                "kind": "local-thick",
                "node": "nas-b",
                "physical_free_bytes": 999,
            },
            900,
        )

    stored = conn.hgetall(m.pool_status_key("/isard/groups"))
    assert stored["node"] == b"nas-a"
    assert stored["physical_free_bytes"] == b"10"
    assert "nas-a" in caplog.text and "nas-b" in caplog.text


def test_the_same_node_keeps_updating_its_own_measurement():
    """The guard must not freeze the reporter that owns the key."""
    conn = _FakeRedis()
    for free in (10, 20):
        m.publish_usage(
            conn,
            {
                "path": "/isard/groups",
                "kind": "local-thick",
                "node": "nas-a",
                "physical_free_bytes": free,
            },
            900,
        )
    assert (
        conn.hgetall(m.pool_status_key("/isard/groups"))["physical_free_bytes"] == b"20"
    )
