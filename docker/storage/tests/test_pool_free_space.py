# SPDX-License-Identifier: AGPL-3.0-or-later

"""The pool_free_space task reports a pool's free/total for the migration
percentage floor. The migration runner has no pool mounts, so it reads space
through this worker task: physical where known (thin, via the published figure),
else statvfs, and never raising (an unreadable pool answers None and the caller
fails open)."""

from isardvdi_common.lib.storage import physical_usage


def _usage(monkeypatch, usage):
    monkeypatch.setattr(physical_usage, "pool_physical_usage", lambda path, **k: usage)


def test_thick_pool_reports_statvfs_figure(monkeypatch):
    from isardvdi_storage import task

    _usage(
        monkeypatch,
        {
            "thin": False,
            "physical_free_bytes": 44,
            "physical_total_bytes": 100,
            "source": "statvfs",
        },
    )
    out = task.pool_free_space("/isard/pool")
    assert (out["free_bytes"], out["total_bytes"]) == (44, 100)


def test_thin_pool_uses_published_physical_figure(monkeypatch):
    from isardvdi_storage import task

    _usage(
        monkeypatch,
        {"thin": True, "physical_free_bytes": None, "physical_total_bytes": None},
    )
    monkeypatch.setattr(task, "_redis_connection", lambda: object())
    monkeypatch.setattr(
        physical_usage,
        "read_usage_for_path",
        lambda conn, path: {"physical_free_bytes": 20, "physical_total_bytes": 200},
    )
    out = task.pool_free_space("/isard/pool")
    assert (out["free_bytes"], out["total_bytes"]) == (20, 200)


def test_thin_without_a_figure_falls_back_to_statvfs(monkeypatch):
    from isardvdi_storage import task

    _usage(
        monkeypatch,
        {
            "thin": True,
            "physical_free_bytes": None,
            "physical_total_bytes": None,
            "filesystem_free_bytes": 500,
            "filesystem_total_bytes": 1000,
            "source": None,
        },
    )
    monkeypatch.setattr(task, "_redis_connection", lambda: object())
    monkeypatch.setattr(physical_usage, "read_usage_for_path", lambda conn, path: None)
    out = task.pool_free_space("/isard/pool")
    assert (out["free_bytes"], out["total_bytes"]) == (500, 1000)


def test_unreadable_pool_returns_none_and_does_not_raise(monkeypatch):
    from isardvdi_storage import task

    def _boom(path, **k):
        raise OSError("mount gone")

    monkeypatch.setattr(physical_usage, "pool_physical_usage", _boom)
    out = task.pool_free_space("/isard/pool")
    assert out["free_bytes"] is None and out["total_bytes"] is None
