# SPDX-License-Identifier: AGPL-3.0-or-later

"""Persisting the row progress a storage worker could not write itself."""

from types import SimpleNamespace

import pytest
from isardvdi_change_handler.task_results import row_progress
from isardvdi_change_handler.task_results.row_progress import (
    ROW_PROGRESS_META_KEY,
    apply_row_progress,
)


class _Row:
    def __init__(self, _id, status="Downloading"):
        self.id = _id
        self.status = status
        self.progress = None


class _Model:
    """A model whose rows live in a dict, so writes are observable."""

    def __init__(self, rows):
        self.rows = rows

    def exists(self, item_id):
        return item_id in self.rows

    def __call__(self, item_id):
        return self.rows[item_id]

    def build(self, item_id):
        """One read, None when absent — mirrors ``RethinkBase.build``."""
        return self.rows.get(item_id)


def _task(name, kwargs, meta):
    return SimpleNamespace(task=name, kwargs=kwargs, job=SimpleNamespace(meta=meta))


@pytest.fixture
def wire(monkeypatch):
    """Wire a task and its model, and hand back the row for assertions."""

    def _wire(name, kwargs, meta, item_class, row):
        model = _Model({row.id: row})
        monkeypatch.setattr(row_progress, "Task", lambda _id: _task(name, kwargs, meta))
        monkeypatch.setitem(row_progress._ITEM_CLASS_MAP, item_class, model)
        return row

    return _wire


@pytest.mark.parametrize(
    "name, kwargs, item_class",
    [
        ("download_url", {"media_id": "m1"}, "media"),
        ("download_url_for_domain", {"domain_id": "m1"}, "domain"),
        ("move", {"progress_domain_id": "m1"}, "domain"),
    ],
)
def test_the_final_flush_reaches_the_row(wire, name, kwargs, item_class):
    """The closing tick is the authoritative record of the transfer and is
    persisted; it rides on the ``result`` entry, hence ``final=True``."""
    payload = {"received_percent": 100, "total_percent": 100}
    row = wire(name, kwargs, {ROW_PROGRESS_META_KEY: payload}, item_class, _Row("m1"))

    assert apply_row_progress("t1", final=True) is True
    assert row.progress == payload


@pytest.mark.parametrize(
    "name, kwargs, item_class",
    [
        ("download_url", {"media_id": "m1"}, "media"),
        ("download_url_for_domain", {"domain_id": "m1"}, "domain"),
        ("move", {"progress_domain_id": "m1"}, "domain"),
    ],
)
def test_an_intermediate_tick_never_reaches_the_row(wire, name, kwargs, item_class):
    """The percentage between the ends is a transient the next tick supersedes,
    and it had no durability contract even when it was written — the progress
    consumer ACKs whether the write landed or not. The frontend gets it live
    from the task event, so the row does not carry it and the database does not
    pay a hard write per tick."""
    row = wire(
        name,
        kwargs,
        {ROW_PROGRESS_META_KEY: {"received_percent": 42}},
        item_class,
        _Row("m1", status="Downloading"),
    )

    assert apply_row_progress("t1") is False
    assert row.progress is None


def test_the_stated_size_reaches_the_row(wire):
    """The worker states the exact on-disk byte size in ``total_bytes`` on the
    final tick. It is the figure every media-space reader (quota, usage,
    analytics, cleanup) sums, so it has to land on the row verbatim -- not the
    human-rounded ``total`` string ("3408k") that curl prints and that no reader
    consumes."""
    payload = {
        "received": "3408k",
        "total": "3408k",
        "received_percent": 100,
        "total_percent": 100,
        "total_bytes": 3490290,
    }
    row = wire(
        "download_url",
        {"media_id": "m1"},
        {ROW_PROGRESS_META_KEY: payload},
        "media",
        _Row("m1"),
    )

    assert apply_row_progress("t1", final=True) is True
    assert row.progress["total_bytes"] == 3490290


def test_a_worker_that_still_writes_its_own_row_is_a_no_op(wire):
    """No metadata means an old worker: it wrote the row itself."""
    row = wire("download_url", {"media_id": "m1"}, {}, "media", _Row("m1"))

    assert apply_row_progress("t1") is False
    assert row.progress is None


def test_the_first_progress_moves_a_starting_row_to_downloading(wire):
    row = wire(
        "download_url",
        {"media_id": "m1"},
        {ROW_PROGRESS_META_KEY: {"received_percent": 1}},
        "media",
        _Row("m1", status="DownloadStarting"),
    )

    assert apply_row_progress("t1") is True
    assert row.status == "Downloading"


@pytest.mark.parametrize("status", ["DownloadAborting", "DownloadFailed", "Deleting"])
def test_a_row_on_its_way_out_keeps_its_status(wire, status):
    """A tick already in flight must not resurrect a cancelled download. The
    final flush still records the size it measured — that figure is what the
    space readers sum, and it is true whatever became of the row — but the
    status is not touched."""
    row = wire(
        "download_url",
        {"media_id": "m1"},
        {ROW_PROGRESS_META_KEY: {"received_percent": 100}},
        "media",
        _Row("m1", status=status),
    )

    assert apply_row_progress("t1", final=True) is True
    assert row.status == status


@pytest.mark.parametrize("status", ["DownloadAborting", "DownloadFailed", "Deleting"])
def test_an_intermediate_tick_does_not_touch_a_row_on_its_way_out(wire, status):
    row = wire(
        "download_url",
        {"media_id": "m1"},
        {ROW_PROGRESS_META_KEY: {"received_percent": 50}},
        "media",
        _Row("m1", status=status),
    )

    assert apply_row_progress("t1") is False
    assert row.status == status
    assert row.progress is None


def test_a_deleted_row_is_not_recreated(wire, monkeypatch):
    wire(
        "download_url",
        {"media_id": "m1"},
        {ROW_PROGRESS_META_KEY: {"received_percent": 50}},
        "media",
        _Row("m1"),
    )
    monkeypatch.setitem(row_progress._ITEM_CLASS_MAP, "media", _Model({}))

    assert apply_row_progress("t1") is False


def test_a_task_that_owns_no_row_is_ignored(monkeypatch):
    monkeypatch.setattr(
        row_progress,
        "Task",
        lambda _id: _task("convert", {}, {ROW_PROGRESS_META_KEY: {"x": 1}}),
    )

    assert apply_row_progress("t1") is False


def test_an_unloadable_task_does_not_raise(monkeypatch):
    def _boom(_id):
        raise RuntimeError("no redis")

    monkeypatch.setattr(row_progress, "Task", _boom)

    assert apply_row_progress("t1") is False
