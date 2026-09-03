# SPDX-License-Identifier: AGPL-3.0-or-later

"""The destination floor must be held against the PHYSICAL figure on a thin pool.

A thin-provisioned pool reports its LOGICAL size to the filesystem, so a floor
enforced against `statvfs` there lets a copy through that fills the backing
store. These pin the order the guard consults its sources, and -- just as
important -- that it does NOT start refusing work on installs where nobody
publishes the physical figure yet.
"""

from types import SimpleNamespace

import pytest


@pytest.fixture
def guard(monkeypatch):
    import task

    monkeypatch.setattr(task, "os_stat", lambda p: SimpleNamespace(st_size=9 * 1024**3))
    return task


def _published(monkeypatch, guard, usage):
    """What a node holding the mounts has published into redis, if anything."""
    from isardvdi_common.lib.storage import physical_usage

    monkeypatch.setattr(guard, "_redis_connection", lambda: object())
    monkeypatch.setattr(physical_usage, "read_usage_for_path", lambda conn, path: usage)


def _thin(monkeypatch, free):
    from isardvdi_common.lib.storage import physical_usage

    monkeypatch.setattr(
        physical_usage,
        "pool_physical_usage",
        lambda path, **kwargs: {
            "thin": True,
            "physical_free_bytes": free,
            "mount_point": "/isard/pool",
        },
    )


def test_physical_figure_wins_over_a_roomy_filesystem(guard, monkeypatch):
    """The case the guard exists for: statvfs says there is a petabyte, the
    backing store has barely the 9 GiB the copy needs, and the 1 GiB floor must
    still refuse it."""
    _thin(monkeypatch, 9 * 1024**3 + 10)
    monkeypatch.setattr(guard, "_free_space", lambda p: 1024**5)

    with pytest.raises(RuntimeError) as excinfo:
        guard._require_free_space(
            "/isard/pool", "/isard/d.qcow2", 1024**3, "move", "copy"
        )

    assert "physical figure" in str(excinfo.value)


def test_physical_headroom_lets_a_fitting_copy_through(guard, monkeypatch):
    _thin(monkeypatch, 40 * 1024**3)
    monkeypatch.setattr(guard, "_free_space", lambda p: 1024**5)

    guard._require_free_space("/isard/pool", "/isard/d.qcow2", 1024**3, "move", "copy")


def test_a_thick_pool_keeps_using_statvfs(guard, monkeypatch):
    """No behaviour change where the filesystem figure is already the truth."""
    from isardvdi_common.lib.storage import physical_usage

    monkeypatch.setattr(
        physical_usage, "pool_physical_usage", lambda path, **kwargs: {"thin": False}
    )
    monkeypatch.setattr(guard, "_free_space", lambda p: 9 * 1024**3 + 10)

    with pytest.raises(RuntimeError) as excinfo:
        guard._require_free_space(
            "/isard/pool", "/isard/d.qcow2", 1024**3, "move", "copy"
        )

    assert "filesystem-level figure" in str(excinfo.value)


def test_thin_without_a_published_figure_falls_back_and_says_so(
    guard, monkeypatch, caplog
):
    """Refusing every move on a thin pool the day this ships would be a
    regression nobody asked for; going quiet about it would hide that the floor
    is not protecting the pool. It does neither."""
    _thin(monkeypatch, None)
    _published(monkeypatch, guard, None)
    monkeypatch.setattr(guard, "_free_space", lambda p: 1024**5)

    with caplog.at_level("WARNING"):
        guard._require_free_space(
            "/isard/pool", "/isard/d.qcow2", 1024**3, "move", "copy"
        )

    assert "STORAGE_POOL_VDO_STATS" in caplog.text


def test_a_published_figure_is_used_when_this_node_cannot_measure(guard, monkeypatch):
    """The NFS-client case: the worker sees no device under the mount, so the
    only figure it can have is the one the owning node published."""
    _thin(monkeypatch, None)
    _published(monkeypatch, guard, {"physical_free_bytes": 9 * 1024**3 + 10})
    monkeypatch.setattr(guard, "_free_space", lambda p: 1024**5)

    with pytest.raises(RuntimeError) as excinfo:
        guard._require_free_space(
            "/isard/pool", "/isard/d.qcow2", 1024**3, "move", "copy"
        )

    assert "physical figure" in str(excinfo.value)


def test_the_guard_never_reaches_a_database():
    """isard-storage talks to redis only. A future edit that resolved the pool
    through RethinkDB would look harmless and reintroduce a dependency this
    container must not have."""
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "task.py").read_text()
    start = source.index("def _physical_free_space")
    end = source.index("def _require_free_space")
    assert "Processed" not in source[start:end]
    assert "models.storage_pool" not in source[start:end]
