"""Which hugepage sizes the hypervisor says QEMU can back."""

import pytest
from isardvdi_hypervisor import gpu_discovery as mod

PROC = "proc /proc proc rw,nosuid,nodev,noexec,relatime 0 0\n"
MEMINFO_2M = "MemTotal: 65536000 kB\nHugepagesize:       2048 kB\n"
MEMINFO_1G = "MemTotal: 65536000 kB\nHugepagesize:    1048576 kB\n"


def _sizes(tmp_path, mounts, meminfo=MEMINFO_2M):
    (tmp_path / "mounts").write_text(PROC + mounts)
    (tmp_path / "meminfo").write_text(meminfo)
    return mod._hugetlbfs_mount_sizes(
        mounts=str(tmp_path / "mounts"), meminfo=str(tmp_path / "meminfo")
    )


@pytest.mark.parametrize(
    "option, expected",
    [
        ("pagesize=1024M", ["1G"]),
        ("pagesize=1G", ["1G"]),
        ("pagesize=2M", ["2M"]),
        ("pagesize=2048K", ["2M"]),
        ("pagesize=16M", []),
    ],
)
def test_the_mount_pagesize_option_names_the_size(tmp_path, option, expected):
    mounts = f"hugetlbfs /dev/hugepages hugetlbfs rw,relatime,{option} 0 0\n"
    assert _sizes(tmp_path, mounts) == expected


@pytest.mark.parametrize(
    "meminfo, expected", [(MEMINFO_2M, ["2M"]), (MEMINFO_1G, ["1G"])]
)
def test_without_pagesize_the_mount_uses_the_default_size(tmp_path, meminfo, expected):
    mounts = "hugetlbfs /dev/hugepages hugetlbfs rw,relatime 0 0\n"
    assert _sizes(tmp_path, mounts, meminfo) == expected


def test_the_last_mount_on_the_path_is_the_one_in_use(tmp_path):
    mounts = (
        "hugetlbfs /dev/hugepages hugetlbfs rw,relatime,pagesize=2M 0 0\n"
        "hugetlbfs /dev/hugepages hugetlbfs rw,relatime,pagesize=1024M 0 0\n"
    )
    assert _sizes(tmp_path, mounts) == ["1G"]


@pytest.mark.parametrize(
    "mounts",
    [
        "tmpfs /dev/hugepages tmpfs rw 0 0\n",
        "hugetlbfs /mnt/huge hugetlbfs rw,relatime,pagesize=2M 0 0\n",
        "",
    ],
)
def test_no_hugetlbfs_at_the_path_backs_nothing(tmp_path, mounts):
    assert _sizes(tmp_path, mounts) == []


def test_unreadable_mounts_back_nothing(tmp_path):
    assert mod._hugetlbfs_mount_sizes(mounts=str(tmp_path / "absent")) == []


def test_discover_hugepages_reports_the_mount_sizes(monkeypatch):
    monkeypatch.setattr(mod, "_hugetlbfs_mount_sizes", lambda: ["1G"])
    assert mod.discover_hugepages()["mount_sizes"] == ["1G"]
