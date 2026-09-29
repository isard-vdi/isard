# SPDX-License-Identifier: AGPL-3.0-or-later

"""A failed purge gives back only its own claim: a deleted or restored entry keeps its status."""

from __future__ import annotations

import os
import uuid

import pytest

rethinkdb = pytest.importorskip("rethinkdb")
from rethinkdb import r  # noqa: E402

pytestmark = pytest.mark.real


@pytest.fixture
def conn():
    host = os.environ.get("RETHINKDB_HOST", "isard-db")
    try:
        c = r.connect(
            host=host, port=int(os.environ.get("RETHINKDB_PORT", "28015")), db="isard"
        )
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"RethinkDB not reachable at {host}: {exc}")
    yield c
    c.close()


@pytest.fixture
def entry(conn):
    ids = []

    def make(status):
        rb_id = f"e2e-rb-{uuid.uuid4()}"
        r.table("recycle_bin").insert({"id": rb_id, "status": status}).run(conn)
        ids.append(rb_id)
        return rb_id

    yield make
    r.table("recycle_bin").get_all(*ids).delete().run(conn)


@pytest.mark.parametrize(
    "status, expected",
    [
        ("recycled", "recycled"),
        ("queued", "recycled"),
        ("deleting", "recycled"),
        ("deleted", "deleted"),
        ("restored", "restored"),
    ],
)
def test_a_failed_purge_gives_back_only_its_claim(conn, entry, status, expected):
    from isardvdi_common.helpers.recycle_bin import Helpers, RecycleBinStatusEnum

    rb_id = entry(status)
    Helpers.claim_status(
        rb_id,
        [RecycleBinStatusEnum.queued.value, RecycleBinStatusEnum.deleting.value],
        RecycleBinStatusEnum.recycled.value,
    )

    assert r.table("recycle_bin").get(rb_id)["status"].run(conn) == expected
