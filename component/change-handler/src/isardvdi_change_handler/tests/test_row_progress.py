# SPDX-License-Identifier: AGPL-3.0-or-later

"""Persisting the row progress a storage worker could not write itself."""

import json
from types import SimpleNamespace

import pytest
from isardvdi_change_handler.task_results import row_progress
from isardvdi_change_handler.task_results.row_progress import (
    ROW_PROGRESS_META_KEY,
    handle_row_progress,
)


class _Row:
    def __init__(self, _id, status="Downloading", kind="desktop"):
        self.id = _id
        self.status = status
        self.progress = None
        self.user = "u1"
        self.category = "c1"
        self.kind = kind


class _Manager:
    """Records what would have reached the SocketIO rooms."""

    def __init__(self):
        self.emitted = []

    async def emit(self, event, payload, namespace=None, room=None):
        self.emitted.append((event, json.loads(payload), namespace, room))


@pytest.fixture
def manager():
    return _Manager()


async def _apply(final=False, manager=None):
    return await handle_row_progress(manager or _Manager(), "t1", final)


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
        # ``move`` is NOT here: it stores nothing even on its final tick, which
        # test_a_move_stores_nothing_even_on_its_final_tick asserts.
    ],
)
@pytest.mark.asyncio
async def test_the_final_flush_reaches_the_row(wire, name, kwargs, item_class):
    """The closing tick is the authoritative record of the transfer and is
    persisted; it rides on the ``result`` entry, hence ``final=True``."""
    payload = {"received_percent": 100, "total_percent": 100}
    row = wire(name, kwargs, {ROW_PROGRESS_META_KEY: payload}, item_class, _Row("m1"))

    assert await _apply(final=True) is True
    assert row.progress == payload


@pytest.mark.parametrize(
    "name, kwargs, item_class",
    [
        ("download_url", {"media_id": "m1"}, "media"),
        ("download_url_for_domain", {"domain_id": "m1"}, "domain"),
        ("move", {"progress_domain_id": "m1"}, "domain"),
    ],
)
@pytest.mark.asyncio
async def test_an_intermediate_tick_never_reaches_the_row(
    wire, name, kwargs, item_class
):
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

    assert await _apply() is False
    assert row.progress is None


@pytest.mark.asyncio
async def test_the_stated_size_reaches_the_row(wire):
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

    assert await _apply(final=True) is True
    assert row.progress["total_bytes"] == 3490290


@pytest.mark.asyncio
async def test_a_worker_that_still_writes_its_own_row_is_a_no_op(wire):
    """No metadata means an old worker: it wrote the row itself."""
    row = wire("download_url", {"media_id": "m1"}, {}, "media", _Row("m1"))

    assert await _apply() is False
    assert row.progress is None


@pytest.mark.asyncio
async def test_the_first_progress_moves_a_starting_row_to_downloading(wire):
    row = wire(
        "download_url",
        {"media_id": "m1"},
        {ROW_PROGRESS_META_KEY: {"received_percent": 1}},
        "media",
        _Row("m1", status="DownloadStarting"),
    )

    assert await _apply() is True
    assert row.status == "Downloading"


@pytest.mark.parametrize("status", ["DownloadAborting", "DownloadFailed", "Deleting"])
@pytest.mark.asyncio
async def test_a_row_on_its_way_out_keeps_its_status(wire, status):
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

    assert await _apply(final=True) is True
    assert row.status == status


@pytest.mark.parametrize("status", ["DownloadAborting", "DownloadFailed", "Deleting"])
@pytest.mark.asyncio
async def test_an_intermediate_tick_does_not_touch_a_row_on_its_way_out(wire, status):
    row = wire(
        "download_url",
        {"media_id": "m1"},
        {ROW_PROGRESS_META_KEY: {"received_percent": 50}},
        "media",
        _Row("m1", status=status),
    )

    assert await _apply() is False
    assert row.status == status
    assert row.progress is None


@pytest.mark.asyncio
async def test_a_deleted_row_is_not_recreated(wire, monkeypatch):
    wire(
        "download_url",
        {"media_id": "m1"},
        {ROW_PROGRESS_META_KEY: {"received_percent": 50}},
        "media",
        _Row("m1"),
    )
    monkeypatch.setitem(row_progress._ITEM_CLASS_MAP, "media", _Model({}))

    assert await _apply() is False


@pytest.mark.asyncio
async def test_a_task_that_owns_no_row_is_ignored(monkeypatch):
    monkeypatch.setattr(
        row_progress,
        "Task",
        lambda _id: _task("convert", {}, {ROW_PROGRESS_META_KEY: {"x": 1}}),
    )

    assert await _apply() is False


@pytest.mark.asyncio
async def test_an_unloadable_task_does_not_raise(monkeypatch):
    def _boom(_id):
        raise RuntimeError("no redis")

    monkeypatch.setattr(row_progress, "Task", _boom)

    assert await _apply() is False


@pytest.mark.asyncio
async def test_a_move_stores_nothing_even_on_its_final_tick(wire):
    """``move``'s payload is only ``{total_percent, received_percent}``, so a
    final write would leave every template row carrying a permanent
    ``{100, 100}`` that nothing reads: every consumer of template progress is
    guarded on ``status == CreatingTemplate``, which is false by then."""
    row = wire(
        "move",
        {"progress_domain_id": "m1"},
        {ROW_PROGRESS_META_KEY: {"total_percent": 100, "received_percent": 100}},
        "domain",
        _Row("m1", status="CreatingTemplate"),
    )

    assert await _apply(final=True) is False
    assert row.progress is None


@pytest.mark.asyncio
async def test_a_download_still_stores_its_final_tick(wire):
    """The counterpart: the key this whole path exists for still lands."""
    row = wire(
        "download_url",
        {"media_id": "m1"},
        {ROW_PROGRESS_META_KEY: {"total_bytes": 123, "total": "123"}},
        "media",
        _Row("m1"),
    )

    assert await _apply(final=True) is True
    assert row.progress["total_bytes"] == 123


@pytest.mark.asyncio
async def test_a_media_tick_reaches_the_owner_and_the_category(wire, manager):
    """The row never carries the intermediate percentage, so no changefeed
    announces it: the emit is the only thing that moves the bar."""
    payload = {"received_percent": 42, "total_percent": 42, "total": "1G"}
    wire(
        "download_url",
        {"media_id": "m1"},
        {ROW_PROGRESS_META_KEY: payload},
        "media",
        _Row("m1"),
    )

    await _apply(manager=manager)

    assert manager.emitted == [
        ("media_progress", {"id": "m1", "progress": payload}, "/userspace", "u1"),
        (
            "media_progress",
            {"id": "m1", "progress": payload},
            "/administrators",
            "admins",
        ),
        ("media_progress", {"id": "m1", "progress": payload}, "/administrators", "c1"),
    ]


@pytest.mark.asyncio
async def test_a_desktop_tick_carries_the_shape_the_card_reads(wire, manager):
    """The card reads the parsed keys; the admin table reads the raw ones."""
    wire(
        "download_url_for_domain",
        {"domain_id": "d1"},
        {
            ROW_PROGRESS_META_KEY: {
                "received_percent": 42,
                "speed_download_average": "10M",
                "time_left": "0:00:10",
                "total": "1G",
            }
        },
        "domain",
        _Row("d1"),
    )

    await _apply(manager=manager)

    raw = {
        "received_percent": 42,
        "speed_download_average": "10M",
        "time_left": "0:00:10",
        "total": "1G",
    }
    assert manager.emitted == [
        (
            "desktop_progress",
            {
                "id": "d1",
                "progress": {
                    "percentage": 42,
                    "throughput_average": "10M",
                    "time_left": "0:00:10",
                    "size": "1G",
                },
            },
            "/userspace",
            "u1",
        ),
        # The admin tables render the row shape, not the card one.
        (
            "desktop_data_progress",
            {"id": "d1", "progress": raw},
            "/administrators",
            "admins",
        ),
        (
            "desktop_data_progress",
            {"id": "d1", "progress": raw},
            "/administrators",
            "c1",
        ),
    ]


@pytest.mark.asyncio
async def test_a_template_tick_carries_the_raw_counters(wire, manager):
    """A template list reads ``total_percent`` off the row shape."""
    payload = {"total_percent": 30, "received_percent": 30}
    wire(
        "move",
        {"progress_domain_id": "t1"},
        {ROW_PROGRESS_META_KEY: payload},
        "domain",
        _Row("t1", status="CreatingTemplate", kind="template"),
    )

    await _apply(manager=manager)

    assert manager.emitted == [
        ("template_progress", {"id": "t1", "progress": payload}, "/userspace", "u1")
    ]


@pytest.mark.asyncio
async def test_a_failing_emit_does_not_break_the_tick(wire, monkeypatch):
    class _Boom:
        async def emit(self, *args, **kwargs):
            raise RuntimeError("no socketio")

    row = wire(
        "download_url",
        {"media_id": "m1"},
        {ROW_PROGRESS_META_KEY: {"received_percent": 1}},
        "media",
        _Row("m1", status="DownloadStarting"),
    )

    assert await _apply(manager=_Boom()) is True
    assert row.status == "Downloading"
